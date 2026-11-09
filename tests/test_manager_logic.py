from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import proxy_server
import snapshot_utils

_import_data_dir = tempfile.TemporaryDirectory()
_original_data_dir = os.environ.get("VPNGATE_DATA_DIR")
os.environ["VPNGATE_DATA_DIR"] = _import_data_dir.name
try:
    import vpngate_manager as manager
finally:
    if _original_data_dir is None:
        os.environ.pop("VPNGATE_DATA_DIR", None)
    else:
        os.environ["VPNGATE_DATA_DIR"] = _original_data_dir


class FakeProcess:
    def __init__(self) -> None:
        self.running = True
        self.terminated = False

    def poll(self):
        return None if self.running else 0

    def terminate(self) -> None:
        self.terminated = True
        self.running = False

    def wait(self, timeout=None):
        self.running = False
        return 0

    def kill(self) -> None:
        self.running = False


def valid_snapshot_rows(rows: list[tuple[str, str, str]]) -> str:
    csv_rows = [
        "#HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,NumVpnSessions,OpenVPN_ConfigData_Base64"
    ]
    for index, (ip, country_long, country_short) in enumerate(rows):
        config_text = (
            "client\n"
            "dev tun\n"
            "proto udp\n"
            f"remote {ip} 1194 udp\n"
            "resolv-retry infinite\n"
            "nobind\n"
            "<ca>\nCA\n</ca>\n"
            "<cert>\nCERT\n</cert>\n"
            "<key>\nKEY\n</key>\n"
        )
        config = base64.b64encode(config_text.encode("utf-8")).decode("ascii")
        csv_rows.append(
            f"vpn{index}.example,{ip},100,20,1000,{country_long},{country_short},1,{config}"
        )
    return "\n".join(csv_rows) + "\n"


def valid_snapshot(ip: str = "198.51.100.10") -> str:
    return valid_snapshot_rows([(ip, "Japan", "JP")])


class FakeSocket:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent = b""
        self.address = None
        self.options = []
        self.closed = False

    def setsockopt(self, level, option, value) -> None:
        self.options.append((level, option, value))

    def settimeout(self, timeout) -> None:
        pass

    def connect(self, address) -> None:
        self.address = address

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, size: int) -> bytes:
        if not self.response:
            return b""
        chunk, self.response = self.response[:size], self.response[size:]
        return chunk

    def close(self) -> None:
        self.closed = True


class FakeProbeProcess:
    """模拟 Bun 探针子进程：控制输出、第几次 wait 后结束与 kill 标记。"""

    def __init__(self, output: str, finish_after: int | None = 0) -> None:
        self.output = output
        self.finish_after = finish_after
        self.wait_calls = 0
        self.finished = False
        self.killed = False
        self.cmdline: list[str] = []

    def poll(self):
        return 0 if (self.finished or self.killed) else None

    def terminate(self):
        self.killed = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.killed or (self.finish_after is not None and self.wait_calls > self.finish_after):
            self.finished = True
            return 0
        raise subprocess.TimeoutExpired(self.cmdline or ["bun"], timeout)

    def communicate(self, timeout=5):
        self.finished = True
        return self.output, ""


class ManagerLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.path_patches = [
            mock.patch.object(manager, "DATA_DIR", root),
            mock.patch.object(manager, "CONFIG_DIR", root / "configs"),
            mock.patch.object(manager, "NODES_FILE", root / "nodes.json"),
            mock.patch.object(manager, "STATE_FILE", root / "state.json"),
            mock.patch.object(manager, "AUTH_FILE", root / "auth.txt"),
            mock.patch.object(manager, "BLACKLIST_FILE", root / "blacklist.json"),
            mock.patch.object(manager, "API_CACHE_FILE", root / "api_snapshot.csv"),
            mock.patch.object(manager, "API_CACHE_META_FILE", root / "api_snapshot.meta.json"),
            mock.patch.object(manager, "BUNDLED_SNAPSHOT_FILE", root / "bundled_snapshot.csv"),
            mock.patch.object(manager.vpn_utils, "DATA_DIR", root),
            mock.patch.object(manager.vpn_utils, "IP_CACHE_FILE", root / "ip_cache.json"),
        ]
        for patcher in self.path_patches:
            patcher.start()
        manager.ensure_dirs()
        manager.active_openvpn_process = None
        manager.pending_openvpn_process = None
        manager.active_openvpn_node_id = ""
        manager.active_connection_cancel_event = None
        manager.is_connecting = False
        manager.consecutive_proxy_failures = 0
        manager.last_proxy_failure_node_id = ""
        manager.background_refill_thread = None
        manager.background_refill_cancel_event.clear()
        manager.active_sessions.clear()
        manager.clear_login_rate_limits()
        manager._last_auth_signature = ""
        manager.opencode_check_thread = None
        manager.opencode_check_cancel_event.clear()
        if manager.opencode_check_lock.locked():
            manager.opencode_check_lock.release()
        manager.update_opencode_check_stats(
            running=False,
            total=0,
            done=0,
            available=0,
            limited=0,
            failed=0,
            model="",
            message="",
            started_at=0.0,
            finished_at=0.0,
            cancelled=False,
        )

    def tearDown(self) -> None:
        if manager.connection_attempt_lock.locked():
            manager.connection_attempt_lock.release()
        manager.background_refill_cancel_event.set()
        manager.background_refill_thread = None
        for patcher in reversed(self.path_patches):
            patcher.stop()
        self.temp_dir.cleanup()

    def write_nodes(self, count: int) -> list[dict]:
        nodes = []
        for index in range(count):
            node_id = f"node-{index}"
            nodes.append(
                {
                    "id": node_id,
                    "ip": f"192.0.2.{index + 1}",
                    "remote_host": f"192.0.2.{index + 1}",
                    "remote_port": 1194,
                    "ping": index + 1,
                    "score": 1000 - index,
                    "config_text": "client\nremote 192.0.2.1 1194 udp\n",
                    "config_file": str(manager.CONFIG_DIR / f"{node_id}.ovpn"),
                    "probe_status": "not_checked",
                    "probed_at": 0,
                    "active": False,
                }
            )
        manager.write_json(manager.NODES_FILE, nodes)
        return nodes

    def test_node_probe_stops_after_target_batch(self) -> None:
        nodes = self.write_nodes(12)
        calls = []

        def fake_openvpn(config_file, **kwargs):
            calls.append(config_file)
            return True, "ready", None

        with (
            mock.patch.object(manager.vpn_utils, "ping_latency_ms", return_value=10),
            mock.patch.object(manager.vpn_utils, "enrich_ip_info"),
            mock.patch.object(manager, "run_openvpn_until_ready", side_effect=fake_openvpn),
            mock.patch.object(manager, "NODE_PROBE_WORKERS", 5),
        ):
            results = manager.test_multiple_nodes(
                [node["id"] for node in nodes],
                target_available=3,
            )

        self.assertEqual(5, len(calls))
        self.assertEqual(5, len(results))
        stored = manager.read_nodes()
        self.assertEqual(5, sum(node.get("probe_status") == "available" for node in stored))
        self.assertEqual(7, sum(node.get("probe_status") == "not_checked" for node in stored))

    def test_ip_classification_separates_proxy_use_from_network_type(self) -> None:
        residential, residential_reason = manager.vpn_utils.classify_ip_type(
            {
                "isp": "Sony Network Communications Inc.",
                "org": "Sony Network Communications Inc.",
                "proxy": True,
                "hosting": False,
                "mobile": False,
            }
        )
        softether, softether_reason = manager.vpn_utils.classify_ip_type(
            {
                "isp": "SoftEther",
                "org": "SoftEther Corporation",
                "proxy": True,
                "hosting": False,
                "mobile": False,
            }
        )
        hosting, hosting_reason = manager.vpn_utils.classify_ip_type(
            {"proxy": True, "hosting": True, "mobile": False}
        )
        mobile, mobile_reason = manager.vpn_utils.classify_ip_type(
            {"proxy": False, "hosting": False, "mobile": True}
        )
        unknown, unknown_reason = manager.vpn_utils.classify_ip_type(
            {"proxy": True, "hosting": False, "mobile": False}
        )

        self.assertEqual(("residential", "consumer_or_unclassified_network"), (residential, residential_reason))
        self.assertEqual(("hosting", "proxy_provider_datacenter"), (softether, softether_reason))
        self.assertEqual(("hosting", "hosting_flag"), (hosting, hosting_reason))
        self.assertEqual(("mobile", "mobile_flag"), (mobile, mobile_reason))
        self.assertEqual(("unknown", "missing_provider_data"), (unknown, unknown_reason))
        self.assertEqual("low", manager.vpn_utils.classification_confidence(unknown_reason))

    def test_ip_enrichment_reclassifies_legacy_cache_and_keeps_proxy_quality(self) -> None:
        ip = "118.240.250.95"
        manager.vpn_utils.IP_CACHE_FILE.write_text(
            json.dumps(
                {
                    ip: {
                        "ip_type": "hosting",
                        "quality": "proxy",
                        "cached_at": 9999999999,
                        "classification_version": 1,
                    }
                }
            ),
            encoding="utf-8",
        )
        api_result = [
            {
                "status": "success",
                "query": ip,
                "country": "Japan",
                "regionName": "Tokyo",
                "city": "Tokyo",
                "isp": "Sony Network Communications Inc.",
                "org": "Sony Network Communications Inc.",
                "as": "AS2527 Sony Network Communications Inc.",
                "asname": "Sony Network Communications Inc.",
                "proxy": True,
                "hosting": False,
                "mobile": False,
            }
        ]
        response = mock.MagicMock()
        response.read.return_value = json.dumps(api_result).encode("utf-8")
        response.__enter__.return_value = response
        node = {"id": "sony", "ip": ip}

        with mock.patch.object(manager.vpn_utils.urllib.request, "urlopen", return_value=response) as urlopen_mock:
            manager.vpn_utils.enrich_ip_info([node])

        self.assertEqual("residential", node["ip_type"])
        self.assertEqual("proxy", node["quality"])
        self.assertTrue(node["is_proxy"])
        self.assertFalse(node["is_hosting"])
        urlopen_mock.assert_called_once()
        cache = json.loads(manager.vpn_utils.IP_CACHE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(manager.vpn_utils.IP_CLASSIFICATION_VERSION, cache[ip]["classification_version"])

    def test_ambiguous_datacenter_uses_secondary_source_and_geo_country(self) -> None:
        ip = "219.100.37.98"
        primary_payload = [{
            "status": "success",
            "query": ip,
            "country": "Japan",
            "countryCode": "JP",
            "regionName": "Tokyo",
            "city": "Chiyoda",
            "isp": "SoftEther",
            "org": "SoftEther Corporation",
            "as": "AS36599 SoftEther",
            "asname": "SOFTETHER",
            "proxy": True,
            "hosting": False,
            "mobile": False,
        }]
        primary = mock.MagicMock()
        primary.read.return_value = json.dumps(primary_payload).encode("utf-8")
        primary.__enter__.return_value = primary
        secondary = mock.MagicMock()
        secondary.read.return_value = json.dumps({"is_datacenter": True, "is_vpn": True}).encode("utf-8")
        secondary.__enter__.return_value = secondary
        node = {"id": "softether", "ip": ip}

        with mock.patch.object(
            manager.vpn_utils.urllib.request,
            "urlopen",
            side_effect=[primary, secondary],
        ):
            manager.vpn_utils.enrich_ip_info([node])

        self.assertEqual("hosting", node["ip_type"])
        self.assertEqual("high", node["ip_type_confidence"])
        self.assertEqual("datacenter", node["quality"])
        self.assertTrue(node["is_hosting"])
        self.assertEqual(["ip-api.com", "ipapi.is"], node["ip_type_sources"])
        self.assertEqual("JP", node["geo_country_short"])

    def test_unverified_datacenter_conflict_becomes_unknown(self) -> None:
        ip = "203.0.113.10"
        primary_payload = [{
            "status": "success",
            "query": ip,
            "country": "Japan",
            "countryCode": "JP",
            "regionName": "Tokyo",
            "city": "Tokyo",
            "isp": "Example VPS",
            "org": "Example VPS Hosting",
            "as": "AS64500 Example",
            "asname": "EXAMPLE",
            "proxy": True,
            "hosting": False,
            "mobile": False,
        }]
        primary = mock.MagicMock()
        primary.read.return_value = json.dumps(primary_payload).encode("utf-8")
        primary.__enter__.return_value = primary
        node = {"id": "ambiguous", "ip": ip}

        with mock.patch.object(
            manager.vpn_utils.urllib.request,
            "urlopen",
            side_effect=[primary, TimeoutError("secondary unavailable")],
        ):
            manager.vpn_utils.enrich_ip_info([node])

        self.assertEqual("unknown", node["ip_type"])
        self.assertEqual("low", node["ip_type_confidence"])
        strict = manager.apply_routing_filters([node], {"routing_mode": "auto", "routing_ip_type": "residential"})
        self.assertEqual([], strict)

    def test_missing_provider_data_uses_secondary_source_or_stays_unknown(self) -> None:
        ip = "203.0.113.11"
        primary_payload = [{
            "status": "success",
            "query": ip,
            "country": "Japan",
            "countryCode": "JP",
            "regionName": "Tokyo",
            "city": "Tokyo",
            "isp": "",
            "org": "",
            "as": "",
            "asname": "",
            "proxy": True,
            "hosting": False,
            "mobile": False,
        }]
        primary = mock.MagicMock()
        primary.read.return_value = json.dumps(primary_payload).encode("utf-8")
        primary.__enter__.return_value = primary
        node = {"id": "missing-provider", "ip": ip}

        with mock.patch.object(
            manager.vpn_utils.urllib.request,
            "urlopen",
            side_effect=[primary, TimeoutError("secondary unavailable")],
        ):
            manager.vpn_utils.enrich_ip_info([node])

        self.assertEqual("unknown", node["ip_type"])
        self.assertEqual("provider_data_unverified", node["ip_type_reason"])
        self.assertEqual("low", node["ip_type_confidence"])
        strict = manager.apply_routing_filters(
            [node],
            {"routing_mode": "auto", "routing_ip_type": "residential"},
        )
        self.assertEqual([], strict)

    def test_strict_residential_filter_requires_medium_or_high_confidence(self) -> None:
        nodes = [
            {"id": "low", "ip_type": "residential", "ip_type_confidence": "low"},
            {"id": "medium", "ip_type": "residential", "ip_type_confidence": "medium"},
            {"id": "mobile", "ip_type": "mobile", "ip_type_confidence": "high"},
            {"id": "hosting", "ip_type": "hosting", "ip_type_confidence": "high"},
        ]

        strict = manager.apply_routing_filters(
            nodes,
            {"routing_mode": "auto", "routing_ip_type": "residential"},
        )

        self.assertEqual(["medium", "mobile"], [node["id"] for node in strict])

    def test_background_ip_enrichment_merges_metadata_without_replacing_status(self) -> None:
        nodes = self.write_nodes(2)
        nodes[0]["probe_status"] = "available"
        manager.write_json(manager.NODES_FILE, nodes)

        def fake_enrich(items):
            for item in items:
                item["ip_type"] = "residential"
                item["quality"] = "proxy"
                item["owner"] = "Consumer ISP"
                item["is_proxy"] = True

        with mock.patch.object(manager.vpn_utils, "enrich_ip_info", side_effect=fake_enrich):
            changed = manager.enrich_stored_nodes()

        stored = manager.read_nodes()
        self.assertGreater(changed, 0)
        self.assertEqual("available", next(node for node in stored if node["id"] == "node-0")["probe_status"])
        self.assertTrue(all(node["ip_type"] == "residential" for node in stored))

    def test_source_deadline_still_tries_official_http(self) -> None:
        csv_text = valid_snapshot()

        def fake_fetch(url, verify_ssl=True, deadline_seconds=None):
            if url == manager.API_HTTPS_URL:
                raise manager.SourceDeadlineExceeded("slow official source")
            if url == manager.API_HTTP_URL:
                return csv_text
            raise AssertionError(f"unexpected source: {url}")

        with (
            mock.patch.object(manager, "fetch_api_text_with_deadline", side_effect=fake_fetch) as fetch_mock,
            mock.patch.object(manager, "load_blacklist", return_value={}),
            mock.patch.object(manager, "log_to_json"),
        ):
            nodes = manager.fetch_candidates()

        self.assertEqual(1, len(nodes))
        self.assertEqual(
            [manager.API_HTTPS_URL, manager.API_HTTP_URL],
            [call.args[0] for call in fetch_mock.call_args_list],
        )

    def test_probe_failure_preserves_existing_ip_metadata(self) -> None:
        nodes = self.write_nodes(1)
        nodes[0].update(
            {
                "owner": "Existing ISP",
                "location": "日本 东京",
                "ip_type": "residential",
                "ip_type_confidence": "medium",
            }
        )
        manager.write_json(manager.NODES_FILE, nodes)

        with (
            mock.patch.object(manager.vpn_utils, "ping_latency_ms", return_value=0),
            mock.patch.object(manager, "run_openvpn_until_ready", return_value=(False, "offline", None)),
        ):
            manager.test_multiple_nodes([nodes[0]["id"]])

        stored = manager.read_nodes()[0]
        self.assertEqual("unavailable", stored["probe_status"])
        self.assertEqual("Existing ISP", stored["owner"])
        self.assertEqual("日本 东京", stored["location"])
        self.assertEqual("residential", stored["ip_type"])
        self.assertEqual("medium", stored["ip_type_confidence"])

    def test_country_matching_accepts_iso_and_legacy_name(self) -> None:
        node = {"country": "日本", "country_short": "JP"}
        self.assertTrue(manager.country_matches(node["country"], "JP", node["country_short"]))
        self.assertTrue(manager.country_matches(node["country"], "日本", node["country_short"]))
        self.assertFalse(manager.country_matches(node["country"], "KR", node["country_short"]))
        self.assertEqual("JP", manager.normalize_routing_country("日本", [node]))

    def test_web_and_proxy_ports_must_be_distinct(self) -> None:
        self.assertTrue(manager.ports_conflict(8787, "8787"))
        self.assertFalse(manager.ports_conflict(8787, 7928))

    def test_ui_connection_requires_tunnel_and_proxy_readiness(self) -> None:
        manager.active_openvpn_node_id = "node-1"
        manager.active_openvpn_process = FakeProcess()
        base_state = {"is_connecting": False, "tunnel_ready": True, "proxy_ready": False, "proxy_ok": False}
        self.assertFalse(manager.connection_ready_for_ui(base_state))
        ready_state = {**base_state, "proxy_ready": True, "proxy_ok": True}
        self.assertTrue(manager.connection_ready_for_ui(ready_state))

    def test_manual_disconnect_state_clears_all_readiness_flags(self) -> None:
        nodes = self.write_nodes(1)
        nodes[0]["active"] = True
        manager.write_json(manager.NODES_FILE, nodes)
        manager.set_state(
            is_connecting=True,
            tunnel_ready=True,
            proxy_ready=True,
            proxy_ok=True,
            proxy_ip="198.51.100.20",
        )

        with mock.patch.object(manager, "stop_active_openvpn") as stop_mock:
            manager.clear_active_connection_state("手动断开连接")

        stop_mock.assert_called_once_with()
        state = manager.get_state()
        self.assertFalse(state["is_connecting"])
        self.assertFalse(state["tunnel_ready"])
        self.assertFalse(state["proxy_ready"])
        self.assertFalse(state["proxy_ok"])
        self.assertEqual("-", state["proxy_ip"])
        self.assertFalse(any(node.get("active") for node in manager.read_nodes()))

    def test_ui_auth_json_is_written_private(self) -> None:
        auth_file = manager.DATA_DIR / "ui_auth.json"
        manager.write_json(auth_file, {"username": "test", "password": "secret"})
        if os.name != "nt":
            self.assertEqual(0o600, stat.S_IMODE(auth_file.stat().st_mode))

    def test_source_deadline_limits_total_fetch_time(self) -> None:
        def slow_fetch(url, verify_ssl=True):
            threading.Event().wait(0.1)
            return valid_snapshot()

        with mock.patch.object(manager, "fetch_api_text", side_effect=slow_fetch):
            started = manager.time.monotonic()
            with self.assertRaises(manager.SourceDeadlineExceeded):
                manager.fetch_api_text_with_deadline(
                    manager.API_HTTPS_URL,
                    deadline_seconds=0.01,
                )

        self.assertLess(manager.time.monotonic() - started, 0.08)

    def test_node_probe_stops_after_systemic_openvpn_failure(self) -> None:
        nodes = self.write_nodes(12)

        with (
            mock.patch.object(manager.vpn_utils, "ping_latency_ms", return_value=10),
            mock.patch.object(
                manager,
                "run_openvpn_until_ready",
                return_value=(False, "[ERR_OVPN_TUN_NOT_AVAILABLE] missing TUN", None),
            ) as openvpn_mock,
            mock.patch.object(manager, "NODE_PROBE_WORKERS", 5),
            mock.patch.object(manager, "log_to_json"),
        ):
            results = manager.test_multiple_nodes(
                [node["id"] for node in nodes],
                target_available=3,
            )

        self.assertEqual(5, openvpn_mock.call_count)
        self.assertEqual(5, len(results))
        stored = manager.read_nodes()
        self.assertEqual(5, sum(node.get("probe_status") == "unavailable" for node in stored))
        self.assertEqual(7, sum(node.get("probe_status") == "not_checked" for node in stored))

    def test_maintenance_does_not_start_second_batch_after_systemic_failure(self) -> None:
        candidates = self.write_nodes(12)

        with (
            mock.patch.object(manager, "fetch_candidates", return_value=candidates),
            mock.patch.object(manager.vpn_utils, "ping_latency_ms", return_value=10),
            mock.patch.object(
                manager,
                "run_openvpn_until_ready",
                return_value=(False, "[ERR_OVPN_CMD_NOT_FOUND] openvpn missing", None),
            ) as openvpn_mock,
            mock.patch.object(manager, "NODE_PROBE_WORKERS", 5),
            mock.patch.object(manager, "log_to_json"),
        ):
            result = manager.maintain_valid_nodes()

        self.assertEqual(5, openvpn_mock.call_count)
        self.assertIn("Tested 5", result)

    def test_cancel_pending_connection_stops_handshake_process(self) -> None:
        process = FakeProcess()
        event = threading.Event()
        manager.pending_openvpn_process = process
        manager.active_connection_cancel_event = event
        manager.is_connecting = True
        previous_epoch = manager.connection_epoch

        manager.cancel_pending_connection_attempt()

        self.assertTrue(event.is_set())
        self.assertTrue(process.terminated)
        self.assertIsNone(manager.pending_openvpn_process)
        self.assertFalse(manager.is_connecting)
        self.assertEqual(previous_epoch + 1, manager.connection_epoch)

    def test_proxy_failures_reset_when_node_changes(self) -> None:
        self.assertEqual(1, manager.record_proxy_failure("node-a"))
        self.assertEqual(2, manager.record_proxy_failure("node-a"))
        self.assertEqual(1, manager.record_proxy_failure("node-b"))
        manager.reset_proxy_failure_counter("node-b")
        self.assertEqual(1, manager.record_proxy_failure("node-b"))

    def test_failed_switch_preflight_keeps_current_connection(self) -> None:
        nodes = self.write_nodes(2)
        nodes[0]["active"] = True
        manager.write_json(manager.NODES_FILE, nodes)
        current_process = FakeProcess()
        manager.active_openvpn_process = current_process
        manager.active_openvpn_node_id = nodes[0]["id"]

        with (
            mock.patch.object(
                manager,
                "run_openvpn_until_ready",
                return_value=(False, "preflight failed", None),
            ),
            mock.patch.object(manager, "log_to_json"),
        ):
            with self.assertRaisesRegex(RuntimeError, "已保留当前连接"):
                manager.connect_node(nodes[1]["id"])

        self.assertIs(manager.active_openvpn_process, current_process)
        self.assertEqual(nodes[0]["id"], manager.active_openvpn_node_id)
        self.assertTrue(current_process.running)
        stored = {node["id"]: node for node in manager.read_nodes()}
        self.assertEqual("unavailable", stored[nodes[1]["id"]]["probe_status"])

    def test_proxy_failure_does_not_report_connection_success(self) -> None:
        nodes = self.write_nodes(1)
        process = FakeProcess()

        with (
            mock.patch.object(
                manager,
                "run_openvpn_until_ready",
                return_value=(True, "ready", process),
            ),
            mock.patch.object(manager, "setup_policy_routing", return_value=False),
            mock.patch.object(manager, "cleanup_policy_routing"),
            mock.patch.object(manager.vpn_utils, "ping_latency_ms", return_value=10),
            mock.patch.object(manager, "check_proxy_health", return_value={"ok": False, "error": "no route"}),
            mock.patch.object(manager, "log_to_json"),
        ):
            with self.assertRaisesRegex(RuntimeError, "代理出口不可用"):
                manager.connect_node(nodes[0]["id"])

        self.assertFalse(process.running)
        self.assertIsNone(manager.active_openvpn_process)
        self.assertEqual("", manager.active_openvpn_node_id)
        stored = manager.read_nodes()
        self.assertEqual("unavailable", stored[0]["probe_status"])

    def test_manual_failure_recovery_prefers_previous_node(self) -> None:
        with (
            mock.patch.object(manager, "active_openvpn_running", return_value=False),
            mock.patch.object(manager, "connect_node", return_value="connected") as connect_mock,
            mock.patch.object(manager, "log_to_json"),
            mock.patch.object(manager, "auto_switch_node") as auto_switch_mock,
        ):
            manager.recover_after_manual_connect_failure("old-node")

        connect_mock.assert_called_once_with("old-node")
        auto_switch_mock.assert_not_called()

    def test_auto_switch_exhaustion_schedules_background_refill(self) -> None:
        with (
            mock.patch.object(manager, "schedule_background_refill", return_value=True) as schedule_mock,
            mock.patch.object(manager, "log_to_json") as log_mock,
        ):
            manager.auto_switch_node(attempt=3)

        schedule_mock.assert_called_once_with()
        log_mock.assert_called_once_with("INFO", "Main", "连续自动切换失败，已启动唯一后台节点补齐任务")

    def test_physical_interface_detection_is_cached(self) -> None:
        original_cache = manager.vpn_utils.physical_interface_cache
        manager.vpn_utils.physical_interface_cache = (None, 0.0)
        try:
            with mock.patch.object(
                manager.vpn_utils,
                "_detect_physical_interface",
                return_value="eth0",
            ) as detect_mock:
                self.assertEqual("eth0", manager.vpn_utils.get_physical_interface())
                self.assertEqual("eth0", manager.vpn_utils.get_physical_interface())
            detect_mock.assert_called_once_with()
        finally:
            manager.vpn_utils.physical_interface_cache = original_cache

    def test_forced_refresh_keeps_healthy_active_connection(self) -> None:
        process = FakeProcess()
        manager.active_openvpn_process = process
        manager.active_openvpn_node_id = "active-node"

        with (
            mock.patch.object(manager, "fetch_candidates", return_value=[]),
            mock.patch.object(manager, "stop_active_openvpn") as stop_mock,
            mock.patch.object(manager, "log_to_json"),
        ):
            result = manager.maintain_valid_nodes(force=True)

        self.assertEqual("没有拉取到新节点", result)
        self.assertTrue(process.running)
        stop_mock.assert_not_called()

    def test_fetch_timeout_skips_insecure_https_retry(self) -> None:
        csv_text = valid_snapshot()

        def fake_fetch(url, verify_ssl):
            if url.startswith("https://"):
                raise TimeoutError("timed out")
            return csv_text

        with (
            mock.patch.object(manager, "fetch_api_text", side_effect=fake_fetch) as fetch_mock,
            mock.patch.object(manager, "load_blacklist", return_value={}),
            mock.patch.object(manager, "set_state"),
            mock.patch.object(manager, "log_to_json"),
        ):
            nodes = manager.fetch_candidates()

        self.assertEqual(1, len(nodes))
        self.assertEqual(
            [mock.call(manager.API_HTTPS_URL, True), mock.call(manager.API_HTTP_URL, True)],
            fetch_mock.call_args_list,
        )

    def test_discovery_countries_are_normalized_and_persisted(self) -> None:
        countries = manager.persist_discovery_countries(["jp", "US", "JP", "bad", ""])

        self.assertEqual(["JP", "US"], countries)
        self.assertEqual(["JP", "US"], manager.load_ui_config()["discovery_countries"])
        self.assertEqual(["JP", "US"], manager.get_state()["discovery_countries"])

    def test_fetch_filters_country_after_source_is_accepted(self) -> None:
        csv_text = valid_snapshot_rows(
            [
                ("198.51.100.60", "Japan", "JP"),
                ("198.51.100.61", "United States", "US"),
            ]
        )
        manager.persist_discovery_countries(["JP"])

        with (
            mock.patch.object(manager, "fetch_api_text", return_value=csv_text) as fetch_mock,
            mock.patch.object(manager, "load_blacklist", return_value={}),
            mock.patch.object(manager, "log_to_json"),
        ):
            nodes = manager.fetch_candidates()

        self.assertEqual(["JP"], [node["country_short"] for node in nodes])
        fetch_mock.assert_called_once_with(manager.API_HTTPS_URL, True)
        self.assertEqual(csv_text, manager.API_CACHE_FILE.read_text(encoding="utf-8"))
        self.assertIn("成功获取 2 个", manager.get_state()["last_fetch_message"])
        self.assertIn("保留 1 个", manager.get_state()["last_fetch_message"])

    def test_empty_country_result_does_not_fall_through_to_next_source(self) -> None:
        csv_text = valid_snapshot_rows(
            [
                ("198.51.100.70", "Japan", "JP"),
                ("198.51.100.71", "United States", "US"),
            ]
        )
        manager.persist_discovery_countries(["DE"])

        with (
            mock.patch.object(manager, "fetch_api_text", return_value=csv_text) as fetch_mock,
            mock.patch.object(manager, "load_blacklist", return_value={}),
            mock.patch.object(manager, "log_to_json"),
        ):
            nodes = manager.fetch_candidates()

        self.assertEqual([], nodes)
        fetch_mock.assert_called_once_with(manager.API_HTTPS_URL, True)
        state = manager.get_state()
        self.assertEqual("ok", state["last_fetch_status"])
        self.assertEqual("official_https", state["last_fetch_source"])
        self.assertIn("保留 0 个", state["last_fetch_message"])

    def test_get_available_countries_contains_catalog_and_counts(self) -> None:
        mock_nodes = [
            {"country_short": "JP", "country": "Japan"},
            {"country_short": "JP", "country": "Japan"},
            {"country_short": "US", "country": "United States"},
        ]
        available = manager.get_available_countries(mock_nodes)
        self.assertGreaterEqual(len(available), 58)
        
        counts = {item["code"]: item["count"] for item in available}
        self.assertEqual(2, counts.get("JP"))
        self.assertEqual(1, counts.get("US"))
        self.assertEqual(0, counts.get("KR"))
        self.assertEqual(0, counts.get("DE"))
        
        # 验证有节点的国家排在最前
        self.assertEqual("JP", available[0]["code"])
        self.assertEqual("US", available[1]["code"])

    def test_state_includes_available_countries(self) -> None:
        state = manager.get_state()
        self.assertIn("available_countries", state)
        self.assertIsInstance(state["available_countries"], list)
        self.assertGreaterEqual(len(state["available_countries"]), 58)
        first = state["available_countries"][0]
        self.assertIn("code", first)
        self.assertIn("name", first)
        self.assertIn("count", first)

    def test_normalize_routing_country_fallback_to_catalog(self) -> None:
        self.assertEqual("US", manager.normalize_routing_country("美国", []))
        self.assertEqual("US", manager.normalize_routing_country("United States", []))
        self.assertEqual("DE", manager.normalize_routing_country("德国", []))
        self.assertEqual("DE", manager.normalize_routing_country("Germany", []))
        self.assertEqual("JP", manager.normalize_routing_country("JP", []))

    def test_clear_discovery_countries_clears_state_and_config(self) -> None:
        manager.persist_discovery_countries(["JP", "US"])
        self.assertEqual(["JP", "US"], manager.load_ui_config()["discovery_countries"])
        
        cleared = manager.persist_discovery_countries([])
        self.assertEqual([], cleared)
        self.assertEqual([], manager.load_ui_config()["discovery_countries"])
        self.assertEqual([], manager.get_state()["discovery_countries"])

    def test_opencode_models_preserve_listing_order(self) -> None:
        payload = {
            "data": [
                {"id": "paid-model", "cost": {"text": {"input": {"price": 10}, "output": {"price": 50}}}},
                {"id": "beam-free", "cost": {"text": {"input": {"price": 0}, "output": {"price": 0}}}},
                {"id": "big-pickle", "cost": {"text": {"input": {"price": 0}, "output": {"price": 0}}}},
                {"id": "opaque-free"},
            ]
        }

        models = manager.parse_opencode_models(json.dumps(payload))

        self.assertEqual(["beam-free", "big-pickle", "opaque-free"], models)
        self.assertNotIn("paid-model", models)

    def test_opencode_failure_kind_distinguishes_quota_from_errors(self) -> None:
        self.assertEqual("limited", manager.opencode_failure_kind(429, "too many requests"))
        self.assertEqual("limited", manager.opencode_failure_kind(402, "insufficient funds"))
        # 403 属于形状/权限问题，不再误标为额度用尽
        self.assertEqual("failed", manager.opencode_failure_kind(403, "Free usage limit reached"))
        self.assertEqual("limited", manager.opencode_failure_kind(200, "FreeTierError"))
        self.assertEqual("failed", manager.opencode_failure_kind(401, "Unauthorized"))
        self.assertEqual("failed", manager.opencode_failure_kind(500, "internal error"))

    def test_opencode_probe_output_parsing_and_classification(self) -> None:
        result = manager.opencode_parse_probe_output(
            'PROBE: {"status": 429, "content": "", "message": "Free usage limit reached.", "latency": 55, "retry_after": 47472}'
        )
        self.assertTrue(result.get("structured"))
        self.assertEqual(47472, result.get("retry_after"))
        status, message = manager.opencode_probe_result_status(result)
        self.assertEqual("limited", status)
        self.assertIn("Free usage limit", message)

        available = manager.opencode_probe_result_status(
            {"status": 200, "content": "OK", "message": "", "latency": 88}
        )
        self.assertEqual(("available", "正常回复: OK"), available)

        fallback = manager.opencode_parse_probe_output("bun: 1 | ERROR boom")
        self.assertFalse(fallback.get("structured"))
        self.assertEqual("bun: 1 | ERROR boom", fallback.get("message"))
        self.assertEqual(0, fallback.get("retry_after"))

    def test_next_utc_midnight_aligns_with_day_boundary(self) -> None:
        self.assertEqual(0, manager.next_utc_midnight(86400 * 10) % 86400)
        self.assertEqual(86400 * 11, manager.next_utc_midnight(86400 * 10 + 3600))

    def test_bun_probe_script_matches_client_shape(self) -> None:
        script = manager.BUN_PROBE_SCRIPT
        for marker in (
            "authorization",
            "traceparent",
            "x-opencode-client",
            "x-opencode-project",
            "x-opencode-session-id",
            "x-session-affinity",
            "stream_options",
            'TOOL_PARAMETER = { edit: "path", glob: "pattern", grep: "pattern", read: "path", shell: "command" }',
            "Working directory: ${cwd}",
            "Platform: ${process.platform}",
            # 真实 CLI 始终携带 max_tokens；系统消息为完整指令 + 环境块；
            # 429 的 retry-after 被回传用于展示额度重置时间
            "max_tokens",
            "SYSTEM_PREAMBLE",
            "retry_after",
            "response.headers.get(\"retry-after\")",
        ):
            self.assertIn(marker, script)

    def test_find_bun_executable_prefers_explicit_path(self) -> None:
        # 走真实函数（不 mock），可暴露模块级导入缺失等运行期错误
        real_bun = manager.find_bun_executable()
        self.assertTrue(real_bun == "" or Path(real_bun).is_file())
        fake = str(Path(manager.__file__).with_name("fake_bun_probe.exe"))
        if getattr(manager.os, "name", "") == "nt":
            fake_exe = Path(tempfile.gettempdir()) / "aimili_fake_bun.exe"
            fake_exe.write_bytes(b"")
            try:
                with mock.patch.dict(manager.os.environ, {"OPENCODE_BUN_PATH": str(fake_exe)}):
                    self.assertEqual(str(fake_exe), manager.find_bun_executable())
            finally:
                fake_exe.unlink(missing_ok=True)
        else:
            with mock.patch.dict(manager.os.environ, {"OPENCODE_BUN_PATH": "/nonexistent/bun/path"}):
                self.assertNotEqual("/nonexistent/bun/path", manager.find_bun_executable())

    def test_bun_probe_script_syntax_is_valid(self) -> None:
        if not shutil.which("node"):
            self.skipTest("Node.js is not installed; Bun probe script check skipped")
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", encoding="utf-8", delete=False) as handle:
            handle.write(manager.BUN_PROBE_SCRIPT)
            script_path = Path(handle.name)
        try:
            result = subprocess.run(
                ["node", "--check", str(script_path)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
        finally:
            Path(script_path).unlink(missing_ok=True)

    def test_opencode_probe_requests_via_bun_and_local_proxy(self) -> None:
        output = 'PROBE: {"status": 200, "content": "OK", "message": "", "latency": 123}\n'
        process = FakeProbeProcess(output)
        with self.patched_bun_probe(process) as captured:
            status, message, latency, reset_at = manager.opencode_probe_fetch(
                self.opencode_probe_target(), "beam-free", 0x4F430002, threading.Event()
            )

        self.assertEqual("available", status)
        self.assertIn("OK", message)
        self.assertEqual(123, latency)
        self.assertEqual(0.0, reset_at)
        proxy_cls = captured["proxy_cls"]
        proxy_args = proxy_cls.call_args[0]
        self.assertEqual("opencode.ai", proxy_args[0]["host"])
        self.assertEqual(0x4F430002, proxy_args[1])
        cmdline = captured["cmdline"]
        self.assertEqual("/usr/bin/bun", cmdline[0])
        self.assertEqual("beam-free", cmdline[-1])
        kwargs = captured["kwargs"]
        self.assertEqual("http://127.0.0.1:47521", kwargs["env"]["HTTPS_PROXY"])
        self.assertNotIn("NO_PROXY", kwargs["env"])
        self.assertEqual(str(manager.DATA_DIR), kwargs["cwd"])
        self.assertTrue(captured["proxy"].close.called)

    def test_opencode_probe_reports_timeout_when_bun_hangs(self) -> None:
        process = FakeProbeProcess("", finish_after=None)
        with mock.patch.object(manager, "OPENCODE_CHECK_TIMEOUT_SECONDS", 1):
            with self.patched_bun_probe(process) as captured:
                status, message, _, reset_at = manager.opencode_probe_fetch(
                    self.opencode_probe_target(), "beam-free", 0, threading.Event()
                )

        self.assertEqual("failed", status)
        self.assertIn("超时", message)
        self.assertEqual(0.0, reset_at)
        self.assertTrue(process.killed)

    def test_opencode_probe_honors_cancel_before_start(self) -> None:
        cancel = threading.Event()
        cancel.set()
        process = FakeProbeProcess("", finish_after=None)
        with self.patched_bun_probe(process) as captured:
            status, message, _, _ = manager.opencode_probe_fetch(
                self.opencode_probe_target(), "beam-free", 0, cancel
            )

        self.assertEqual("failed", status)
        self.assertEqual("检测已取消", message)
        self.assertFalse(captured["proxy_cls"].called)
        self.assertFalse(captured["popen"].called)

    def test_opencode_probe_surfaces_proxy_failure(self) -> None:
        process = FakeProbeProcess("bun: 1 | ERROR boom")
        with self.patched_bun_probe(process) as captured:
            status, message, _, _ = manager.opencode_probe_fetch(
                self.opencode_probe_target(), "beam-free", 0, threading.Event()
            )

        self.assertEqual("failed", status)
        self.assertIn("连接 OpenCode API 失败", message)
        self.assertFalse(process.killed)

    def test_opencode_probe_limited_result_carries_reset_time(self) -> None:
        output = (
            'PROBE: {"status": 429, "content": "", '
            '"message": "Free usage limit reached. Free models work in OpenCode", '
            '"latency": 210, "retry_after": 3600}\n'
        )
        process = FakeProbeProcess(output)
        with self.patched_bun_probe(process) as captured:
            status, message, _, reset_at = manager.opencode_probe_fetch(
                self.opencode_probe_target(), "beam-free", 0, threading.Event()
            )

        self.assertEqual("limited", status)
        self.assertGreater(reset_at, time.time())
        self.assertLessEqual(reset_at, time.time() + 3600)
        self.assertIn("UTC 重置", message)

    def opencode_probe_target(self) -> dict:
        return {
            "host": "opencode.ai",
            "port": 443,
            "path": "/inference/openai/v1/chat/completions",
            "ips": ["203.0.113.10"],
            "https": True,
            "host_header": "opencode.ai",
        }

    @contextmanager
    def patched_bun_probe(self, process: FakeProbeProcess):
        """打桩 Bun 探针的外部依赖：bun 路径、本地代理与子进程。"""
        captured: dict = {}

        def fake_popen(cmdline, **kwargs):
            captured["cmdline"] = cmdline
            captured["kwargs"] = kwargs
            process.cmdline = cmdline
            return process

        proxy_stub = mock.Mock()
        proxy_stub.port = 47521
        proxy_stub.last_error = "连接 OpenCode API 失败 (203.0.113.10): connection refused"
        with (
            mock.patch.object(manager, "find_bun_executable", return_value="/usr/bin/bun"),
            mock.patch.object(manager, "OpencodeLocalProxy", return_value=proxy_stub) as proxy_cls,
            mock.patch.object(manager.subprocess, "Popen", side_effect=fake_popen) as popen_mock,
        ):
            captured["proxy_cls"] = proxy_cls
            captured["popen"] = popen_mock
            captured["proxy"] = proxy_stub
            yield captured

    def test_failed_opencode_start_keeps_external_maintenance_lock(self) -> None:
        self.assertTrue(manager.maintenance_lock.acquire(blocking=False))
        try:
            with (
                mock.patch.object(manager, "ensure_opencode_probe_supported"),
                self.assertRaises(RuntimeError),
            ):
                manager.start_opencode_check(["node-0"])
            self.assertTrue(manager.maintenance_lock.locked())
            self.assertFalse(manager.opencode_check_lock.locked())
        finally:
            manager.maintenance_lock.release()

    def test_opencode_results_persist_and_reset_interrupted_checks(self) -> None:
        nodes = self.write_nodes(2)
        for node in nodes:
            node["opencode_status"] = "checking"
        manager.write_json(manager.NODES_FILE, nodes)
        pending = {
            nodes[0]["id"]: {
                "id": nodes[0]["id"],
                "opencode_status": "available",
                "opencode_message": "正常回复: OK",
                "opencode_model": "big-pickle",
                "opencode_latency_ms": 321,
                "opencode_checked_at": 100.0,
            }
        }

        manager.flush_opencode_results(pending, {nodes[1]["id"]})
        stored = {node["id"]: node for node in manager.read_nodes()}
        self.assertEqual("available", stored[nodes[0]["id"]]["opencode_status"])
        self.assertEqual(321, stored[nodes[0]["id"]]["opencode_latency_ms"])
        self.assertEqual("", stored[nodes[1]["id"]]["opencode_status"])
        self.assertEqual("检测已取消", stored[nodes[1]["id"]]["opencode_message"])

        stored[nodes[0]["id"]]["opencode_status"] = "checking"
        manager.write_json(manager.NODES_FILE, list(stored.values()))
        manager.reset_stale_opencode_checks()
        stored = {node["id"]: node for node in manager.read_nodes()}
        self.assertEqual("", stored[nodes[0]["id"]]["opencode_status"])

    def test_opencode_check_skips_limited_nodes_until_reset(self) -> None:
        nodes = self.write_nodes(3)
        # node-0：额度用尽且重置时间在未来 → 跳过重复请求
        nodes[0]["opencode_status"] = "limited"
        nodes[0]["opencode_message"] = "额度用尽（IP 每日额度，16:00 UTC 重置）"
        nodes[0]["opencode_reset_at"] = time.time() + 3600
        # node-1：额度用尽但重置时间已过 → 重新检测
        nodes[1]["opencode_status"] = "limited"
        nodes[1]["opencode_reset_at"] = time.time() - 10
        manager.write_json(manager.NODES_FILE, nodes)

        probed: list[str] = []

        def fake_probe_node(node, target, model, cancel_event):
            probed.append(str(node.get("id")))
            return {
                "id": str(node.get("id")),
                "opencode_status": "available",
                "opencode_message": "正常回复: OK",
                "opencode_model": model,
                "opencode_latency_ms": 100,
                "opencode_checked_at": time.time(),
                "opencode_reset_at": 0.0,
            }

        with (
            mock.patch.object(manager, "ensure_opencode_probe_supported"),
            mock.patch.object(manager, "ensure_opencode_probe_script", return_value=Path("probe.mjs")),
            mock.patch.object(manager, "resolve_opencode_model", return_value="beam-free"),
            mock.patch.object(manager, "resolve_opencode_target", return_value=self.opencode_probe_target()),
            mock.patch.object(manager, "opencode_probe_node", side_effect=fake_probe_node),
        ):
            manager._run_opencode_check([str(node["id"]) for node in nodes])

        self.assertEqual(["node-1", "node-2"], probed)
        stored = {node["id"]: node for node in manager.read_nodes()}
        self.assertEqual("limited", stored["node-0"]["opencode_status"])
        self.assertIn("重置前跳过重复检测", stored["node-0"]["opencode_message"])
        self.assertGreater(float(stored["node-0"]["opencode_reset_at"]), time.time())
        self.assertEqual("available", stored["node-1"]["opencode_status"])
        self.assertEqual("available", stored["node-2"]["opencode_status"])

    def test_opencode_state_is_exposed_and_blocks_switching(self) -> None:
        manager.update_opencode_check_stats(running=True, total=3, done=1, available=1)
        self.assertEqual(3, manager.get_state()["opencode_check"]["total"])

        manager.opencode_check_lock.acquire()
        try:
            with self.assertRaises(RuntimeError):
                manager.begin_connection_attempt()
        finally:
            manager.opencode_check_lock.release()

    def test_web_dashboard_exposes_opencode_check_controls(self) -> None:
        for marker in (
            'id="btn_opencode_check"',
            'id="opencode_panel"',
            'id="opencode_only_available"',
            'id="opencode_progress_bar"',
            'id="opencode_model_select"',
            "function getFilteredNodes",
            "function startOpencodeCheck",
            "function stopOpencodeCheck",
            "./api/opencode_check",
            "./api/opencode_models",
            "ensureOpencodeModelsLoaded",
            "opencodeBadgeHtml(n)",
        ):
            self.assertIn(marker, manager.INDEX_HTML)
        self.assertIn("额度用尽", manager.INDEX_HTML)
        self.assertIn("只看可用", manager.INDEX_HTML)
        # 加载动画统一用 .spin 类锚定字形墨迹中心旋转，避免视觉偏移
        self.assertIn(".spin {\n      animation: spin 1s linear infinite;\n      transform-box: fill-box;\n      transform-origin: center;\n    }", manager.INDEX_HTML)
        self.assertEqual(4, manager.INDEX_HTML.count('class="spin"'))
        # 工具栏按钮加载态与其余加载器使用同一居中的圆环扫弧字形
        self.assertEqual(3, manager.INDEX_HTML.count('stroke="currentColor" stroke-opacity="0.2"'))
        self.assertIn('class="spin" style="width:16px; height:16px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">', manager.INDEX_HTML)

    def test_node_table_contains_latency_country_panel_and_test_action(self) -> None:
        self.assertIn('<th style="width: 125px;">延迟</th>', manager.INDEX_HTML)
        self.assertIn('colspan="8"', manager.INDEX_HTML)
        self.assertIn('class="country-option-input"', manager.INDEX_HTML)
        self.assertIn('${testBtn}', manager.INDEX_HTML)

    def test_web_dashboard_has_browser_freeze_safeguards(self) -> None:
        self.assertNotIn("backdrop-filter", manager.LOGIN_HTML)
        self.assertNotIn("backdrop-filter", manager.INDEX_HTML)
        self.assertNotIn("background-attachment: fixed", manager.INDEX_HTML)
        self.assertIn("@media (prefers-reduced-motion: reduce)", manager.LOGIN_HTML)
        self.assertIn("@media (prefers-reduced-motion: reduce)", manager.INDEX_HTML)
        self.assertIn("const pageSize = 50;", manager.INDEX_HTML)
        self.assertIn('id="pagination_container"', manager.INDEX_HTML)
        self.assertIn('paginationContainer.style.display = totalPages > 1 ? "flex" : "none";', manager.INDEX_HTML)
        self.assertIn("const MAX_RENDERED_LOG_LINES = 300;", manager.INDEX_HTML)
        self.assertIn("nodesRequestPromise", manager.INDEX_HTML)
        self.assertIn("backgroundPollInFlight", manager.INDEX_HTML)
        self.assertIn('let lastNodesSnapshotSignature = "";', manager.INDEX_HTML)
        self.assertIn("if (signature === lastNodesSnapshotSignature) return false;", manager.INDEX_HTML)
        self.assertIn('typeof document.hidden !== "boolean" || !document.hidden', manager.INDEX_HTML)
        self.assertEqual(500, manager.WEB_LOG_MAX_ENTRIES)

    def test_web_dashboard_has_cross_browser_interaction_safeguards(self) -> None:
        self.assertNotIn("fonts.googleapis.com", manager.LOGIN_HTML)
        self.assertNotIn("fonts.googleapis.com", manager.INDEX_HTML)
        self.assertIn('const pwd = document.getElementById("password").value;', manager.LOGIN_HTML)
        self.assertIn('const password = $("cred_password").value;', manager.INDEX_HTML)
        self.assertIn("function fetchWithTimeout", manager.LOGIN_HTML)
        self.assertIn("function fetchWithTimeout", manager.INDEX_HTML)
        self.assertNotIn("await fetch(", manager.INDEX_HTML)
        self.assertIn('role="dialog" aria-modal="true"', manager.INDEX_HTML)
        self.assertIn('aria-label="关闭网页安全设置"', manager.INDEX_HTML)
        self.assertIn('class="option-card active" data-value="auto" aria-pressed="true"', manager.INDEX_HTML)
        self.assertIn('position: static;', manager.INDEX_HTML)
        self.assertIn('-webkit-overflow-scrolling: touch;', manager.INDEX_HTML)
        self.assertIn('formatUrlHost(window.location.hostname)', manager.INDEX_HTML)
        self.assertNotIn('id="status" class="status" style="display: none;"', manager.INDEX_HTML)
        self.assertIn('${esc(localProxy)}', manager.INDEX_HTML)
        self.assertIn('${esc(statusMessage)}', manager.INDEX_HTML)

    def test_dashboard_javascript_is_valid(self) -> None:
        if not shutil.which("node"):
            self.skipTest("Node.js is not installed; JavaScript syntax check skipped")
        scripts = re.findall(r"<script>(.*?)</script>", manager.INDEX_HTML, re.DOTALL)
        self.assertTrue(scripts)
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write("\n".join(scripts))
            script_path = handle.name
        try:
            result = subprocess.run(
                ["node", "--check", script_path],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
        finally:
            Path(script_path).unlink(missing_ok=True)

    def test_random_password_uses_cryptographic_randomness(self) -> None:
        with mock.patch.object(manager.secrets, "choice", side_effect=list("aA0aA0aA0aA0")) as choice:
            password = manager.generate_random_password()

        self.assertEqual("aA0aA0aA0aA0", password)
        self.assertEqual(12, choice.call_count)

    def test_expired_sessions_are_removed(self) -> None:
        manager.active_sessions.update({"expired": 99.0, "active": 101.0})

        removed = manager.purge_expired_sessions(now=100.0)

        self.assertEqual(1, removed)
        self.assertEqual({"active": 101.0}, manager.active_sessions)

    def test_login_rate_limiting_and_lockout(self) -> None:
        client_ip = "192.168.1.100"
        manager.clear_login_rate_limits()

        allowed, _ = manager.check_login_rate_limit(client_ip)
        self.assertTrue(allowed)

        for _ in range(4):
            fails, lockout = manager.record_login_failure(client_ip)
            self.assertEqual(0, lockout)

        allowed, _ = manager.check_login_rate_limit(client_ip)
        self.assertTrue(allowed)

        fails, lockout = manager.record_login_failure(client_ip)
        self.assertEqual(5, fails)
        self.assertEqual(manager.LOGIN_LOCKOUT_SECONDS, lockout)

        allowed, remaining = manager.check_login_rate_limit(client_ip)
        self.assertFalse(allowed)
        self.assertGreater(remaining, 0)

        manager.record_login_success(client_ip)
        allowed, _ = manager.check_login_rate_limit(client_ip)
        self.assertTrue(allowed)

    def test_credential_change_invalidates_active_sessions(self) -> None:
        manager.clear_login_rate_limits()
        manager.active_sessions.clear()
        manager._last_auth_signature = ""

        auth_file = manager.DATA_DIR / "ui_auth.json"
        manager.write_json(auth_file, {"username": "admin", "password": "password123"})

        handler = mock.MagicMock(spec=manager.Handler)
        handler.headers = {"Cookie": "session=valid_token_123"}
        handler.extract_session_token = manager.Handler.extract_session_token.__get__(handler)
        handler.is_authorized = manager.Handler.is_authorized.__get__(handler)

        manager.active_sessions["valid_token_123"] = time.time() + 3600

        self.assertTrue(handler.is_authorized())

        manager.write_json(auth_file, {"username": "admin", "password": "new_password456"})

        self.assertFalse(handler.is_authorized())
        self.assertNotIn("valid_token_123", manager.active_sessions)

    def test_session_cookie_generation_security_flags(self) -> None:
        handler = mock.MagicMock(spec=manager.Handler)
        handler.get_secret_path.return_value = "EJsW2EeBo9lY"

        handler.headers = {}
        handler.is_https = manager.Handler.is_https.__get__(handler)
        handler.build_session_cookie = manager.Handler.build_session_cookie.__get__(handler)
        cookie = handler.build_session_cookie("tok123", 3600)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Path=/;", cookie)
        self.assertNotIn("Secure", cookie)

        handler.headers = {"X-Forwarded-Proto": "https"}
        cookie_secure = handler.build_session_cookie("tok123", 3600)
        self.assertIn("; Secure", cookie_secure)

    def test_session_cookie_compatible_with_reverse_proxy_subpath(self) -> None:
        handler = mock.MagicMock(spec=manager.Handler)
        handler.get_secret_path.return_value = "aimili"
        handler.headers = {"X-Forwarded-Proto": "https"}
        handler.is_https = manager.Handler.is_https.__get__(handler)
        handler.build_session_cookie = manager.Handler.build_session_cookie.__get__(handler)
        
        cookie = handler.build_session_cookie("reverse_proxy_tok", 3600)
        # 验证 Cookie 路径为根路径，确保能够被 /aimili-ui/ 等反代子路径访问匹配
        self.assertIn("Path=/;", cookie)
        self.assertIn("; Secure", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_is_authorized_with_multiple_session_cookies(self) -> None:
        handler = mock.MagicMock(spec=manager.Handler)
        handler.headers = {"Cookie": "session=old_invalid_token; session=valid_session_token_999"}
        handler.extract_session_tokens = manager.Handler.extract_session_tokens.__get__(handler)
        handler.extract_session_token = manager.Handler.extract_session_token.__get__(handler)
        handler.is_authorized = manager.Handler.is_authorized.__get__(handler)
        
        manager.active_sessions.clear()
        manager.active_sessions["valid_session_token_999"] = time.time() + 3600
        
        self.assertTrue(handler.is_authorized())
        self.assertEqual("old_invalid_token", handler.extract_session_token())
        self.assertEqual(["old_invalid_token", "valid_session_token_999"], handler.extract_session_tokens())

    def test_build_clear_cookies_clears_root_and_secret_path(self) -> None:
        handler = mock.MagicMock(spec=manager.Handler)
        handler.get_secret_path.return_value = "aimili"
        handler.headers = {}
        handler.is_https = manager.Handler.is_https.__get__(handler)
        handler.build_clear_cookies = manager.Handler.build_clear_cookies.__get__(handler)
        
        cookies = handler.build_clear_cookies()
        self.assertEqual(2, len(cookies))
        self.assertTrue(any("Path=/;" in c for c in cookies))
        self.assertTrue(any("Path=/aimili/;" in c for c in cookies))

    def test_purge_expired_sessions_caps_maximum_sessions(self) -> None:
        manager.active_sessions.clear()
        now = time.time()
        for i in range(manager.MAX_ACTIVE_SESSIONS + 50):
            manager.active_sessions[f"tok_{i}"] = now + 1000 + i

        manager.purge_expired_sessions(now=now)
        self.assertLessEqual(len(manager.active_sessions), manager.MAX_ACTIVE_SESSIONS)

    def test_api_login_endpoint_behavior(self) -> None:
        import io
        manager.clear_login_rate_limits()
        manager.active_sessions.clear()
        manager._last_auth_signature = ""
        orig_delay = manager.LOGIN_FAIL_PENALTY_DELAY
        manager.LOGIN_FAIL_PENALTY_DELAY = 0.0

        try:
            auth_file = manager.DATA_DIR / "ui_auth.json"
            manager.write_json(auth_file, {"username": "admin", "password": "password123", "secret_path": "test_path"})

            def make_login_request(body_dict, ip="192.168.1.101"):
                body_bytes = json.dumps(body_dict).encode("utf-8")
                handler = mock.MagicMock(spec=manager.Handler)
                handler.path = "/test_path/api/login"
                handler.client_address = (ip, 12345)
                handler.headers = {"Content-Length": str(len(body_bytes))}
                handler.rfile = io.BytesIO(body_bytes)
                handler.wfile = io.BytesIO()
                handler.get_secret_path = manager.Handler.get_secret_path.__get__(handler)
                handler.validate_path = manager.Handler.validate_path.__get__(handler)
                handler.get_client_ip = manager.Handler.get_client_ip.__get__(handler)
                handler.is_https = manager.Handler.is_https.__get__(handler)
                handler.build_session_cookie = manager.Handler.build_session_cookie.__get__(handler)
                handler.read_request_body = manager.Handler.read_request_body.__get__(handler)
                handler.read_json_body = manager.Handler.read_json_body.__get__(handler)
                
                sent_status = []
                sent_headers = {}
                def mock_send_response(code):
                    sent_status.append(code)
                def mock_send_header(k, v):
                    sent_headers[k] = v
                def mock_send_bytes(body, ctype, status=200):
                    sent_status.append(status)
                def mock_send_json(data, status=200):
                    sent_status.append(status)
                    handler.sent_data = data

                handler.send_response = mock_send_response
                handler.send_header = mock_send_header
                handler.end_headers = lambda: None
                handler.send_bytes = mock_send_bytes
                handler.send_json = mock_send_json
                handler.sent_headers = sent_headers
                handler.sent_status = sent_status

                manager.Handler.do_POST(handler)
                return handler

            h_ok = make_login_request({"username": "admin", "password": "password123"})
            self.assertEqual([200], h_ok.sent_status)
            self.assertIn("session=", h_ok.sent_headers.get("Set-Cookie", ""))
            self.assertEqual(1, len(manager.active_sessions))

            h_fail = make_login_request({"username": "admin", "password": "wrongpassword"})
            self.assertEqual([403], h_fail.sent_status)
            self.assertIn("剩余尝试次数", h_fail.sent_data.get("error", ""))

            for _ in range(3):
                make_login_request({"username": "admin", "password": "wrongpassword"})
            h_locked = make_login_request({"username": "admin", "password": "wrongpassword"})
            self.assertEqual([429], h_locked.sent_status)
            self.assertIn("临时锁定", h_locked.sent_data.get("error", ""))

            h_locked2 = make_login_request({"username": "admin", "password": "password123"})
            self.assertEqual([429], h_locked2.sent_status)
        finally:
            manager.LOGIN_FAIL_PENALTY_DELAY = orig_delay

    def test_web_log_reader_only_returns_recent_valid_entries(self) -> None:
        log_file = manager.DATA_DIR / "logs" / "current.json"
        log_file.parent.mkdir(parents=True)
        with log_file.open("w", encoding="utf-8") as f:
            for index in range(520):
                f.write(json.dumps({"index": index}) + "\n")
            f.write("not-json\n")

        entries = manager.read_recent_log_entries(log_file)

        self.assertEqual(500, len(entries))
        self.assertEqual(20, entries[0]["index"])
        self.assertEqual(519, entries[-1]["index"])

    def test_web_update_controls_only_expose_stable_main_channel(self) -> None:
        self.assertEqual("2.2.0", manager.APP_VERSION)
        self.assertEqual("V2.2.0 正式版", manager.APP_VERSION_LABEL)
        self.assertIn("检测更新", manager.INDEX_HTML)
        self.assertIn("/api/check_update", manager.INDEX_HTML)
        self.assertIn("/tree/main", manager.INDEX_HTML)
        self.assertIn("/releases/latest", manager.INDEX_HTML)
        self.assertNotIn("/tree/bate", manager.INDEX_HTML)
        self.assertNotIn(">测试版<", manager.INDEX_HTML)
        self.assertIn('id="deployment_mode_label"', manager.INDEX_HTML)

    def test_installer_updates_only_from_main(self) -> None:
        install_text = (manager.ROOT_DIR / "install.sh").read_text(encoding="utf-8")

        self.assertIn('DEPLOY_BRANCH="main"', install_text)
        self.assertIn('branch = "main"', install_text)
        self.assertNotIn("CURRENT_BRANCH", install_text)
        self.assertNotIn("origin/master", install_text)
        self.assertNotIn("bate", install_text.lower())

    def test_installer_uses_secure_credentials_and_current_version(self) -> None:
        install_text = (manager.ROOT_DIR / "install.sh").read_text(encoding="utf-8")

        self.assertNotIn("random.choices", install_text)
        self.assertIn("secrets.choice", install_text)
        self.assertIn('get_app_version()', install_text)
        self.assertNotIn("管理终端 v2.0", install_text)
        self.assertIn("5-90 秒", install_text)
        self.assertIn('new_pwd = input("请输入新管理密码 (不能为空): ")', install_text)
        self.assertIn('state["active_openvpn_node_id"] = ""', install_text)
        self.assertIn("ip link show dev tun0", install_text)
        self.assertIn("pidof openvpn", install_text)
        self.assertIn('chmod 600 "$AUTH_FILE"', install_text)
        self.assertIn("AIMILIVPN_NONINTERACTIVE", install_text)
        self.assertIn('["ip", "rule", "del", "table", "100"]', install_text)
        self.assertIn('/etc/sysctl.d/99-aimilivpn.conf', install_text)
        self.assertNotIn('http://[::1]:${PROXY_PORT}', install_text)

    def test_openvpn_command_requires_server_certificate_usage(self) -> None:
        with mock.patch.object(manager, "get_openvpn_version", return_value=2.5):
            command = manager.openvpn_command("node.ovpn", route_nopull=True)
        index = command.index("--remote-cert-tls")
        self.assertEqual("server", command[index + 1])

    def test_release_workflow_uses_full_patch_version(self) -> None:
        workflow_text = (manager.ROOT_DIR / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

        self.assertIn("default: v2.2.0", workflow_text)
        self.assertIn("AimiliVPN V$(tr -d '\\r\\n' < VERSION) 正式版", workflow_text)
        self.assertNotIn("cut -d. -f1,2 VERSION", workflow_text)

    def test_latest_release_check_ignores_non_version_name_text(self) -> None:
        release = {
            "tag_name": "v2.3.0",
            "name": "AimiliVPN V2.3 正式版",
            "published_at": "2026-09-01T00:00:00Z",
            "draft": False,
            "prerelease": False,
        }
        with mock.patch.object(manager, "fetch_api_text", return_value=json.dumps(release)) as fetch_mock:
            result = manager.check_latest_release()

        self.assertTrue(result["ok"])
        self.assertTrue(result["update_available"])
        self.assertEqual("2.3.0", result["latest_version"])
        self.assertEqual("v2.3.0", result["latest_tag"])
        self.assertEqual(
            "https://github.com/askfname/aimili-vpngate/releases/tag/v2.3.0",
            result["release_url"],
        )
        fetch_mock.assert_called_once_with(manager.GITHUB_LATEST_RELEASE_API, True)

    def test_latest_release_check_reports_current_formal_version(self) -> None:
        release = {
            "tag_name": "v2.2.0",
            "name": "AimiliVPN V2.2.0 正式版",
            "draft": False,
            "prerelease": False,
        }
        with mock.patch.object(manager, "fetch_api_text", return_value=json.dumps(release)):
            result = manager.check_latest_release()

        self.assertFalse(result["update_available"])
        self.assertEqual("V2.2.0 正式版", result["current_version_label"])

    def test_latest_release_check_reports_source_update_command(self) -> None:
        release = {"tag_name": "v2.2.0", "draft": False, "prerelease": False}
        with (
            mock.patch.object(manager, "fetch_api_text", return_value=json.dumps(release)),
            mock.patch.object(manager, "DEPLOYMENT_MODE", "source"),
            mock.patch.object(manager, "DEPLOYMENT_MODE_LABEL", "Python 源码"),
            mock.patch.object(manager, "UPDATE_COMMAND", "ml update"),
        ):
            result = manager.check_latest_release()

        self.assertEqual("source", result["deployment_mode"])
        self.assertEqual("ml update", result["update_command"])

    def test_latest_release_check_reports_docker_update_command(self) -> None:
        release = {"tag_name": "v2.2.0", "draft": False, "prerelease": False}
        with (
            mock.patch.object(manager, "fetch_api_text", return_value=json.dumps(release)),
            mock.patch.object(manager, "DEPLOYMENT_MODE", "docker"),
            mock.patch.object(manager, "DEPLOYMENT_MODE_LABEL", "Docker 容器"),
            mock.patch.object(
                manager,
                "UPDATE_COMMAND",
                "docker compose pull && docker compose up -d",
            ),
        ):
            result = manager.check_latest_release()

        self.assertEqual("docker", result["deployment_mode"])
        self.assertEqual(
            "docker compose pull && docker compose up -d",
            result["update_command"],
        )

    def test_fetch_uses_github_mirror_after_official_sources(self) -> None:
        csv_text = valid_snapshot()

        def fake_fetch(url, verify_ssl):
            if url == manager.MIRROR_HTTPS_URL:
                return csv_text
            raise TimeoutError("blocked")

        with (
            mock.patch.object(manager, "fetch_api_text", side_effect=fake_fetch) as fetch_mock,
            mock.patch.object(manager, "load_blacklist", return_value={}),
            mock.patch.object(manager, "log_to_json"),
            mock.patch.object(manager, "read_mirror_freshness", return_value=(0.0, "")),
        ):
            nodes = manager.fetch_candidates()

        self.assertEqual(1, len(nodes))
        self.assertEqual(
            [manager.API_HTTPS_URL, manager.API_HTTP_URL, manager.MIRROR_HTTPS_URL],
            [call.args[0] for call in fetch_mock.call_args_list],
        )
        self.assertEqual(csv_text, manager.API_CACHE_FILE.read_text(encoding="utf-8"))
        self.assertEqual("github_pages_https", manager.get_state()["last_fetch_source"])

    def test_http_source_does_not_replace_trusted_cache(self) -> None:
        cached_text = valid_snapshot("198.51.100.20")
        http_text = valid_snapshot("198.51.100.21")
        manager.API_CACHE_FILE.write_text(cached_text, encoding="utf-8")

        def fake_fetch(url, verify_ssl):
            if url == manager.API_HTTP_URL:
                return http_text
            raise TimeoutError("TLS unavailable")

        with (
            mock.patch.object(manager, "fetch_api_text", side_effect=fake_fetch),
            mock.patch.object(manager, "load_blacklist", return_value={}),
            mock.patch.object(manager, "log_to_json"),
        ):
            nodes = manager.fetch_candidates()

        self.assertEqual("198.51.100.21", nodes[0]["ip"])
        self.assertEqual(cached_text, manager.API_CACHE_FILE.read_text(encoding="utf-8"))

    def test_fetch_falls_back_to_local_cache(self) -> None:
        cached_text = valid_snapshot("198.51.100.30")
        manager.API_CACHE_FILE.write_text(cached_text, encoding="utf-8")

        with (
            mock.patch.object(manager, "fetch_api_text", side_effect=TimeoutError("all blocked")),
            mock.patch.object(manager, "load_blacklist", return_value={}),
            mock.patch.object(manager, "log_to_json"),
        ):
            nodes = manager.fetch_candidates()

        self.assertEqual("198.51.100.30", nodes[0]["ip"])
        self.assertEqual("local_cache", manager.get_state()["last_fetch_source"])

    def test_bundled_snapshot_seeds_local_cache(self) -> None:
        bundled_text = valid_snapshot("198.51.100.40")
        manager.BUNDLED_SNAPSHOT_FILE.write_text(bundled_text, encoding="utf-8")

        with (
            mock.patch.object(manager, "fetch_api_text", side_effect=TimeoutError("all blocked")),
            mock.patch.object(manager, "load_blacklist", return_value={}),
            mock.patch.object(manager, "log_to_json"),
        ):
            nodes = manager.fetch_candidates()

        self.assertEqual("198.51.100.40", nodes[0]["ip"])
        self.assertEqual(bundled_text, manager.API_CACHE_FILE.read_text(encoding="utf-8"))
        self.assertEqual("bundled_initial", manager.get_state()["last_fetch_source"])

    def test_snapshot_rejects_executable_openvpn_directive(self) -> None:
        unsafe_config = (
            "client\ndev tun\nproto udp\nremote 198.51.100.50 1194 udp\n"
            "script-security 2\nup /tmp/payload\n"
            "<ca>\nCA\n</ca>\n<cert>\nCERT\n</cert>\n<key>\nKEY\n</key>\n"
        )
        encoded = base64.b64encode(unsafe_config.encode("utf-8")).decode("ascii")
        csv_text = (
            "#HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,NumVpnSessions,OpenVPN_ConfigData_Base64\n"
            f"vpn.example,198.51.100.50,100,20,1000,Japan,JP,1,{encoded}\n"
        )

        with self.assertRaisesRegex(ValueError, "no valid nodes"):
            snapshot_utils.parse_and_validate_snapshot(csv_text)


class ProxyServerConcurrencyTests(unittest.TestCase):
    def test_socks5_rejects_client_without_no_auth_method(self) -> None:
        class Client:
            def __init__(self):
                self.incoming = bytearray(b"\x01\x02")
                self.sent = bytearray()
                self.closed = False

            def recv(self, size):
                chunk = self.incoming[:size]
                del self.incoming[:size]
                return bytes(chunk)

            def sendall(self, data):
                self.sent.extend(data)

            def close(self):
                self.closed = True

        client = Client()
        with mock.patch.object(proxy_server, "proxy_auth_enabled", return_value=False):
            proxy_server.socks5_client(client, b"\x05")

        self.assertEqual(b"\x05\xff", bytes(client.sent))
        self.assertTrue(client.closed)

    def test_each_proxy_worker_keeps_its_accepted_socket(self) -> None:
        class Client:
            def __init__(self, name):
                self.name = name

            def close(self):
                pass

        class FakeServer:
            def __init__(self):
                self.items = [(Client("first"), ("first", 1)), (Client("second"), ("second", 2))]

            def setsockopt(self, *args):
                pass

            def bind(self, *args):
                pass

            def listen(self, *args):
                pass

            def accept(self):
                if self.items:
                    return self.items.pop(0)
                raise KeyboardInterrupt()

        class DeferredThread:
            targets = []

            def __init__(self, target, daemon=True):
                self.target = target
                self.targets.append(target)

            def start(self):
                pass

        seen = []
        semaphore = mock.Mock()
        semaphore.acquire.return_value = True
        with (
            mock.patch.object(proxy_server.socket, "socket", return_value=FakeServer()),
            mock.patch.object(proxy_server.threading, "Thread", DeferredThread),
            mock.patch.object(
                proxy_server,
                "proxy_client",
                side_effect=lambda client, address: seen.append((client.name, address[0])),
            ),
            mock.patch.object(proxy_server, "proxy_connection_sem", semaphore),
        ):
            with self.assertRaises(KeyboardInterrupt):
                proxy_server.start_proxy_server("127.0.0.1", 7928)
            for target in DeferredThread.targets:
                target()

        self.assertEqual([("first", "first"), ("second", "second")], seen)


    def test_set_state_dirty_checking_and_latency_exemption(self) -> None:
        manager.set_state(proxy_ok=True, proxy_ip="1.2.3.4")
        mtime_initial = manager.STATE_FILE.stat().st_mtime

        # Calling set_state with identical values must not rewrite the file
        manager.set_state(proxy_ok=True, proxy_ip="1.2.3.4")
        self.assertEqual(mtime_initial, manager.STATE_FILE.stat().st_mtime)

        # Updating ephemeral active_node_latency must reflect in get_state without waking disk
        manager.set_state(active_node_latency="42 ms")
        self.assertEqual("42 ms", manager.get_state().get("active_node_latency"))
        self.assertEqual(mtime_initial, manager.STATE_FILE.stat().st_mtime)

    def test_read_nodes_in_memory_caching(self) -> None:
        manager.write_json(manager.NODES_FILE, [{"id": "node1", "ip": "1.1.1.1"}])
        first_read = manager.read_nodes()
        self.assertEqual(1, len(first_read))

        # Modifying returned dict must not corrupt in-memory cache
        first_read[0]["ip"] = "modified"
        second_read = manager.read_nodes()
        self.assertEqual("1.1.1.1", second_read[0]["ip"])

    def test_prune_orphaned_configs(self) -> None:
        manager.CONFIG_DIR.mkdir(exist_ok=True, parents=True)
        valid_cfg = manager.CONFIG_DIR / "valid_node.ovpn"
        orphan_cfg = manager.CONFIG_DIR / "orphan_node.ovpn"
        test_tmp = manager.CONFIG_DIR / ".test_temp_123.ovpn"

        valid_cfg.write_text("client\n", encoding="utf-8")
        orphan_cfg.write_text("client\n", encoding="utf-8")
        test_tmp.write_text("client\n", encoding="utf-8")

        manager.write_json(manager.NODES_FILE, [{"id": "valid_node", "ip": "1.1.1.1"}])
        removed = manager.prune_orphaned_configs()

        self.assertTrue(valid_cfg.exists())
        self.assertFalse(orphan_cfg.exists())
        self.assertFalse(test_tmp.exists())
        self.assertEqual(2, removed)

    def test_api_nodes_etag_and_gzip_support(self) -> None:
        manager.write_json(manager.NODES_FILE, [{"id": "test_node", "ip": "2.2.2.2"}])
        current_etag = manager.get_nodes_snapshot_etag()

        handler = manager.Handler.__new__(manager.Handler)
        handler.client_address = ("127.0.0.1", 54321)
        handler.path = "/EJsW2EeBo9lY/api/nodes"
        handler.is_authorized = lambda: True

        sent_status = []
        sent_headers = {}
        sent_bytes_payload = []

        def mock_send_response(code):
            sent_status.append(code)
        def mock_send_header(k, v):
            sent_headers[k] = v
        def mock_send_bytes(body, ctype, status=200, extra_headers=None):
            sent_status.append(status)
            sent_bytes_payload.append(body)

        handler.send_response = mock_send_response
        handler.send_header = mock_send_header
        handler.end_headers = lambda: None
        handler.send_bytes = mock_send_bytes
        handler.wfile = mock.Mock()

        # Conditional request with matching If-None-Match receives 304
        handler.headers = {"If-None-Match": current_etag}
        manager.Handler.do_GET(handler)
        self.assertIn(304, sent_status)

        # Transparent Gzip support check in send_bytes
        sent_status.clear()
        sent_headers.clear()
        large_json = json.dumps({"nodes": [{"id": f"node_{i}", "data": "x" * 100} for i in range(20)]}).encode("utf-8")
        handler.headers = {"Accept-Encoding": "gzip, deflate"}
        handler.wfile = mock.Mock()
        manager.Handler.send_bytes(handler, large_json, "application/json")
        self.assertEqual("gzip", sent_headers.get("Content-Encoding"))
        self.assertEqual(200, sent_status[0])

    def test_save_ip_cache_pruning(self) -> None:
        now = time.time()
        # Entry 1: fresh (2 days old)
        # Entry 2: expired (20 days old)
        cache_data = {
            "1.1.1.1": {"cached_at": now - 2 * 86400, "isp": "Fresh ISP"},
            "2.2.2.2": {"cached_at": now - 20 * 86400, "isp": "Expired ISP"},
        }
        manager.vpn_utils.save_ip_cache(cache_data)
        loaded = manager.vpn_utils.load_ip_cache()
        self.assertIn("1.1.1.1", loaded)
        self.assertNotIn("2.2.2.2", loaded)

if __name__ == "__main__":
    unittest.main()
