<div align="center">

# AimiliVPN

**A VPNGate node manager and HTTP / HTTPS / SOCKS5 proxy gateway for Linux VPS hosts**

[![Release](https://img.shields.io/github/v/release/askfname/aimili-vpngate?style=flat-square&label=stable&color=16a34a)](https://github.com/askfname/aimili-vpngate/releases/latest)
[![License](https://img.shields.io/badge/License-GPL--3.0-334155?style=flat-square)](../LICENSE)

[简体中文](../README.md) · **English** · [日本語](README.ja.md) · [한국어](README.ko.md)

[Quick install](#quick-install) · [Installation](#installation) · [Connection](#connection) · [Legal notice](#legal)

</div>

AimiliVPN uses Python's standard library to manage VPNGate nodes. It provides node discovery and testing, connection switching, a Web dashboard, and HTTP, HTTPS website proxying, and SOCKS5 access on one local port.

| Item | Default or supported range |
| --- | --- |
| Web dashboard | TCP `8787`, a private path, username, and password |
| Local proxy | `127.0.0.1:7928`, HTTP, HTTPS `CONNECT`, and SOCKS5 |
| OpenCode checks | Filter nodes by country + IP type, then test public free models through each node's exit IP |
| Source deployment | x64, x86, ARM64, and ARM32 Linux |
| Update channel | GitHub `main` stable branch / latest stable Release |

> [!IMPORTANT]
> **Network availability:** Some regions, data centers, and network providers may restrict DNS, VPNGate APIs, GitHub mirrors, or VPN protocols. Mirrors and local snapshots improve node-list availability but cannot guarantee a successful connection on every host. Confirm that local law and your VPS provider permit VPN/TUN before deployment.

<a id="quick-install"></a>
## Quick Install

Run as `root` on a supported Linux VPS:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

The installer prints the complete Web URL, private path, username, and password. Run `ml` to open the management menu.

For unattended installation, explicitly skip the first-run prompts and generate the Web path and credentials automatically:

```bash
AIMILIVPN_NONINTERACTIVE=1 bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

> [!TIP]
> Enable TUN/TAP in the VPS control panel and verify that `/dev/net/tun` exists. The Web dashboard uses TCP `8787` by default; restrict firewall access to your own IP whenever possible.

<a id="installation"></a>
## Installation

### Requirements

- Ubuntu, Debian, Alpine, CentOS, RHEL, Rocky Linux, AlmaLinux, Fedora, Oracle Linux, or Amazon Linux.
- `root`, OpenVPN, iptables, policy routing, and TUN/TAP.
- Windows and macOS can be proxy clients, but cannot run the full gateway.

### Source installer

```bash
bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

The installer deploys to `/opt/aimilivpn` and registers a system service.

```bash
ml                 # Open the management menu
ml status          # Show status, Web URL, and username
ml logs            # Follow logs
ml restart         # Restart the service
ml password        # Reset Web credentials
ml update          # Update from the stable main branch
ml uninstall       # Uninstall
```

To inspect the installer first:

```bash
git clone --branch main --single-branch https://github.com/askfname/aimili-vpngate.git
cd aimili-vpngate
sudo bash install.sh
```

Universal Linux source archives and SHA-256 checksums are available from [GitHub Releases](https://github.com/askfname/aimili-vpngate/releases/latest). Version changes are documented in the Release Notes.

<a id="connection"></a>
## Connection and Use

### 1. Sign in to the Web dashboard

For a source installation, open the URL printed by the installer:

```text
http://VPS_IP:8787/private_path/
```

Run `ml status` to recover the URL, or `ml password` to reset credentials.

### 2. Fetch and connect to a node

1. Sign in and wait for the first node list, or select **Update nodes**.
2. Filter by country and use **Test** to measure reachability and latency from the VPS.
3. Select **Switch** on the target node. A failed target precheck should leave the current usable connection in place when possible.
4. Choose Smart Auto, Fixed Country, or Fixed IP routing.
5. Confirm the VPN state and outbound IP in the status area.

### 3. Use the proxy on the VPS

HTTP, HTTPS website proxying, and SOCKS5 share `127.0.0.1:7928`. HTTPS sites use the HTTP proxy's `CONNECT` method, so the proxy URL remains `http://127.0.0.1:7928`.

```bash
# HTTP / HTTPS
curl -x http://127.0.0.1:7928 https://api.ipify.org

# SOCKS5 with remote DNS resolution
curl --proxy socks5h://127.0.0.1:7928 https://api.ipify.org
```

<details>
<summary><strong>Shell environment variables and Python example</strong></summary>

```bash
export http_proxy="http://127.0.0.1:7928"
export https_proxy="http://127.0.0.1:7928"
curl https://api.ipify.org
```

```python
import requests

proxies = {
  "http": "http://127.0.0.1:7928",
  "https": "http://127.0.0.1:7928",
}

response = requests.get("https://api.ipify.org", proxies=proxies, timeout=20)
print(response.text)
```

</details>

### 4. Check OpenCode nodes

**Check OpenCode** in the Web toolbar opens temporary test tunnels concurrently for all nodes matching the current **country + IP type** filters, then requests OpenCode public free models through each node's exit IP. The check uses only country and IP type filters, ignoring availability and favorites, so it covers every node in the selected scope.

- **Available:** The node exit returns a non-empty model response; OpenCode's free quota can be used.
- **Quota exhausted:** The response indicates a quota limit, such as `402`, `429`, or Free usage limit.
- **Unavailable:** Tunnel setup, TLS/connection, or authentication fails, or the response is empty.
- **Not checked:** No check has been run yet.
- Stop the check at any time. Results and progress update live, and **Show available only** filters successful nodes.
- Checks temporarily use multiple `tun` interfaces and policy routes. Node switching and manual tests are disabled while a check runs; wait for it to finish or stop it first.

> The check requires Linux TUN/TAP, OpenVPN, `iproute2`, `root`/`NET_ADMIN` privileges, and the **Bun runtime**; Windows/macOS clients cannot run it. The installer installs Bun automatically. Set `OPENCODE_BUN_PATH` to select a `bun` executable. Public-channel quotas are based on node exit IP and do not imply long-term stability of third-party nodes.

<details>
<summary><strong>OpenCode check environment variables</strong></summary>

| Variable | Default | Description |
| --- | --- | --- |
| `OPENCODE_API_BASE` | `https://opencode.ai/inference/v1` | Public API root (model list) |
| `OPENCODE_API_URL` | `https://opencode.ai/inference/openai/v1/chat/completions` | Completion endpoint used for checks |
| `OPENCODE_MODELS_URL` | `${OPENCODE_API_BASE}/models` | Free-model list endpoint |
| `OPENCODE_API_KEY` | `public` | Bearer value for the public channel |
| `OPENCODE_MODEL` | Empty (automatically selects a free model) | Check model; takes precedence over the page dropdown |
| `OPENCODE_FALLBACK_MODEL` | `beam-free` | Fallback if the model list is unavailable |
| `OPENCODE_CHECK_WORKERS` | `10` | Concurrent test tunnels, range 1–24 |
| `OPENCODE_CHECK_TIMEOUT_SECONDS` | `20` | Per-node API request timeout |
| `OPENCODE_OPENVPN_TIMEOUT_SECONDS` | `12` | Per-node tunnel setup timeout |
| `OPENCODE_CHECK_NODE_LIMIT` | `2000` | Maximum nodes per check |
| `OPENCODE_BUN_PATH` | Empty (auto-detect PATH and common install locations) | Path to the Bun executable |
| `OPENCODE_EXTRA_HEADERS` | Empty | Extra request headers as a JSON object string (model list only) |

Restart the service or container for environment variable changes to take effect.

</details>

### 5. Connect from another computer

The proxy listens on the VPS loopback address by default. Use an SSH tunnel instead of exposing it publicly:

```bash
ssh -N \
  -L 8787:127.0.0.1:8787 \
  -L 7928:127.0.0.1:7928 \
  root@VPS_IP
```

After the tunnel is established:

- Web: `http://127.0.0.1:8787/private_path/`
- HTTP / HTTPS proxy: `127.0.0.1:7928`
- SOCKS5 proxy: `127.0.0.1:7928`; enable remote DNS or `socks5h` when available

> [!WARNING]
> Port `7928` has no public-facing user authentication by default. Never expose it directly without a firewall, source-IP restriction, or another reliable access-control layer.

<a id="legal"></a>
## Scope of Use and Legal Notice

> [!CAUTION]
> By downloading, deploying, or using this project, you are responsible for confirming compliance with the laws of your location, the laws where the VPS is hosted, provider terms, and applicable VPNGate rules. This section defines project boundaries, is not legal advice, and cannot guarantee exemption from any liability imposed by law.

1. **Permitted purpose:** Use only for lawful network research, education, development testing, privacy protection, and authorized access. Do not use it to evade lawfully imposed controls, gain unauthorized access, attack or scan systems, send spam, commit fraud, infringe rights, or conduct any unlawful activity.
2. **Network and regional restrictions:** Some regions and data centers may restrict VPNGate, GitHub mirrors, or remote VPN nodes. The project does not guarantee continuous availability in any region or on any host. Use it only where local law and provider terms permit.
3. **Third-party nodes:** VPNGate nodes are operated by third-party volunteers. This project does not own, control, or audit them and cannot guarantee availability, speed, security, privacy practices, or logging behavior. Do not send passwords, financial information, trade secrets, or other sensitive data through untrusted nodes.
4. **User responsibility:** The user is responsible for node selection, traffic, deployment location, exposed ports, and account security, and bears legal responsibility for unlawful use, misconfiguration, third-party nodes, outages, data leaks, or account abuse.
5. **No warranty:** The software is provided “as is.” To the maximum extent permitted by applicable law, maintainers disclaim warranties of availability, merchantability, fitness for a particular purpose, and indirect damages. Liability that cannot lawfully be excluded remains unaffected.
6. **Stop if uncertain:** If you cannot confirm that local law and provider policy permit this use, do not deploy or use the software and consult a qualified lawyer in the relevant jurisdiction.

<div align="center">

[Stable Release](https://github.com/askfname/aimili-vpngate/releases/latest) · [Issues](https://github.com/askfname/aimili-vpngate/issues) · [GPL-3.0 License](../LICENSE)

</div>
