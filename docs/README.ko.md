<div align="center">

# AimiliVPN

**Linux VPS용 VPNGate 노드 관리 및 HTTP / HTTPS / SOCKS5 프록시 게이트웨이**

[![Release](https://img.shields.io/github/v/release/askfname/aimili-vpngate?style=flat-square&label=stable&color=16a34a)](https://github.com/askfname/aimili-vpngate/releases/latest)
[![License](https://img.shields.io/badge/License-GPL--3.0-334155?style=flat-square)](../LICENSE)

[简体中文](../README.md) · [English](README.en.md) · [日本語](README.ja.md) · **한국어**

[빠른 설치](#quick-install) · [설치](#installation) · [연결](#connection) · [법적 고지](#legal)

</div>

AimiliVPN은 Python 표준 라이브러리로 VPNGate 노드를 관리하며 노드 검색과 테스트, 연결 전환, Web 관리 화면, HTTP / HTTPS 웹사이트 프록시 및 SOCKS5 접속을 제공합니다.

| 항목 | 기본값 또는 지원 범위 |
| --- | --- |
| Web 관리 화면 | TCP `8787`, 전용 경로, 사용자 이름, 비밀번호 |
| 로컬 프록시 | `127.0.0.1:7928`, HTTP, HTTPS `CONNECT`, SOCKS5 |
| OpenCode 검사 | 국가 + IP 유형으로 노드를 필터링하고 각 노드 출구 IP로 공개 무료 모델 검사 |
| 소스 배포 | x64, x86, ARM64, ARM32 Linux |

> [!IMPORTANT]
> **네트워크 가용성:** 일부 지역, 데이터 센터 및 네트워크 제공업체는 DNS, VPNGate API, GitHub 미러 또는 VPN 프로토콜을 제한할 수 있습니다. 미러와 로컬 스냅샷은 노드 목록 가용성을 높이지만 모든 환경의 연결 성공을 보장하지 않습니다. 배포 전에 현지 법률과 VPS 제공업체가 VPN/TUN을 허용하는지 확인하십시오.

<a id="quick-install"></a>
## 빠른 설치

지원되는 Linux VPS에서 `root`로 실행합니다.

```bash
bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

설치 후 Web 관리 화면의 전체 URL, 전용 경로, 사용자 이름과 비밀번호가 표시됩니다. `ml` 명령으로 관리 메뉴를 열 수 있습니다.

무인 설치 시 첫 실행 질문을 명시적으로 건너뛰고 Web 경로와 로그인 정보를 자동 생성합니다.

```bash
AIMILIVPN_NONINTERACTIVE=1 bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

> [!TIP]
> VPS 제어판에서 TUN/TAP을 활성화하고 `/dev/net/tun`이 존재하는지 확인하십시오. Web 기본 포트는 TCP `8787`이며 가능하면 자신의 IP만 허용하십시오.

<a id="installation"></a>
## 설치

### 요구 사항

- Ubuntu, Debian, Alpine, CentOS, RHEL, Rocky Linux, AlmaLinux, Fedora, Oracle Linux 또는 Amazon Linux.
- `root`, OpenVPN, iptables, 정책 라우팅 및 TUN/TAP.
- Windows와 macOS는 프록시 클라이언트로 사용할 수 있지만 전체 게이트웨이를 실행할 수 없습니다.

### 소스 설치 프로그램

```bash
bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

`/opt/aimilivpn`에 배포하고 시스템 서비스를 등록합니다.

```bash
ml                 # 관리 메뉴
ml status          # 상태, Web URL, 사용자 이름
ml logs            # 로그 보기
ml restart         # 서비스 재시작
ml password        # Web 인증 정보 재설정
ml update          # main 안정 브랜치에서 업데이트
ml uninstall       # 제거
```

먼저 설치 프로그램을 검토하려면:

```bash
git clone --branch main --single-branch https://github.com/askfname/aimili-vpngate.git
cd aimili-vpngate
sudo bash install.sh
```

공통 Linux 소스 아카이브와 SHA-256 체크섬은 [GitHub Releases](https://github.com/askfname/aimili-vpngate/releases/latest)에서 받을 수 있습니다. 변경 사항은 Release Notes에 기록됩니다.

<a id="connection"></a>
## 연결 및 사용

### 1. Web 관리 화면 로그인

소스 설치에서는 설치 프로그램이 출력한 URL을 엽니다.

```text
http://VPS_IP:8787/private_path/
```

URL은 `ml status`, 인증 정보 재설정은 `ml password`를 사용합니다.

### 2. 노드 가져오기 및 연결

1. 로그인 후 첫 노드 목록을 기다리거나 “노드 업데이트”를 실행합니다.
2. 국가별로 필터링하고 “테스트”로 VPS에서의 연결 가능 여부와 지연 시간을 확인합니다.
3. 대상 노드의 “전환”을 선택합니다. 사전 확인에 실패하면 가능한 경우 현재 연결을 유지합니다.
4. 스마트 자동, 국가 고정 또는 IP 고정 라우팅을 선택합니다.
5. 상태 영역에서 VPN 연결과 출구 IP를 확인합니다.

### 3. VPS에서 프록시 사용

HTTP, HTTPS 웹사이트 프록시와 SOCKS5는 `127.0.0.1:7928`을 공유합니다.

```bash
# HTTP / HTTPS
curl -x http://127.0.0.1:7928 https://api.ipify.org

# SOCKS5 및 원격 DNS
curl --proxy socks5h://127.0.0.1:7928 https://api.ipify.org
```

<details>
<summary><strong>Shell 환경 변수 및 Python 예시</strong></summary>

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

### 4. OpenCode 노드 검사

Web 도구 모음의 “OpenCode 검사”는 현재 “국가 + IP 유형” 필터 결과에 포함된 모든 노드에 임시 테스트 터널을 동시에 만들고 각 노드 출구 IP를 통해 OpenCode 공개 무료 모델을 요청합니다. 검사는 국가와 IP 유형 필터만 적용하며 가용 상태와 즐겨찾기 필터는 무시해 선택 범위의 모든 노드를 검사합니다.

- **사용 가능:** 노드 출구에서 비어 있지 않은 모델 응답을 받아 OpenCode 무료 할당량을 사용할 수 있습니다.
- **할당량 소진:** `402`, `429` 또는 Free usage limit 등의 할당량 제한 응답입니다.
- **사용 불가:** 터널 생성, TLS/연결 또는 인증에 실패했거나 응답이 비어 있습니다.
- **검사 안 함:** 아직 검사를 실행하지 않았습니다.
- 검사는 언제든 중지할 수 있습니다. 결과와 진행률은 실시간으로 업데이트되며 “사용 가능한 항목만 보기”로 성공한 노드를 필터링할 수 있습니다.
- 검사 중 여러 `tun` 인터페이스와 정책 경로를 임시 사용합니다. 검사가 끝나거나 중지될 때까지 노드 전환과 수동 테스트가 비활성화됩니다.

> Linux TUN/TAP, OpenVPN, `iproute2`, `root`/`NET_ADMIN` 권한 및 **Bun 런타임**이 필요합니다. Windows/macOS 클라이언트에서는 실행할 수 없습니다. 설치 스크립트가 Bun을 자동 설치하며, `OPENCODE_BUN_PATH`로 `bun` 실행 파일을 지정할 수 있습니다. 공개 채널 할당량은 노드 출구 IP를 기준으로 하며 제3자 노드의 장기적인 안정성을 보장하지 않습니다.

<details>
<summary><strong>OpenCode 검사 환경 변수</strong></summary>

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `OPENCODE_API_BASE` | `https://opencode.ai/inference/v1` | 공개 API 루트(모델 목록) |
| `OPENCODE_API_URL` | `https://opencode.ai/inference/openai/v1/chat/completions` | 검사에 사용하는 완료 요청 엔드포인트 |
| `OPENCODE_MODELS_URL` | `${OPENCODE_API_BASE}/models` | 무료 모델 목록 엔드포인트 |
| `OPENCODE_API_KEY` | `public` | 공개 채널 Bearer 값 |
| `OPENCODE_MODEL` | 비어 있음(무료 모델 자동 선택) | 검사 모델 지정(페이지 드롭다운보다 우선) |
| `OPENCODE_FALLBACK_MODEL` | `beam-free` | 모델 목록을 사용할 수 없을 때 대체 모델 |
| `OPENCODE_CHECK_WORKERS` | `10` | 동시 테스트 터널 수, 범위 1–24 |
| `OPENCODE_CHECK_TIMEOUT_SECONDS` | `20` | 노드별 API 요청 시간 제한 |
| `OPENCODE_OPENVPN_TIMEOUT_SECONDS` | `12` | 노드별 터널 생성 시간 제한 |
| `OPENCODE_CHECK_NODE_LIMIT` | `2000` | 한 번의 검사에서 처리할 최대 노드 수 |
| `OPENCODE_BUN_PATH` | 비어 있음(PATH 및 일반적인 설치 경로 자동 탐색) | Bun 실행 파일 경로 |
| `OPENCODE_EXTRA_HEADERS` | 비어 있음 | 추가 요청 헤더(JSON 객체 문자열, 모델 목록에만 적용) |

환경 변수 변경을 적용하려면 서비스 또는 컨테이너를 재시작하십시오.

</details>

### 5. 다른 컴퓨터에서 연결

프록시를 공개하지 말고 SSH 터널을 사용하십시오.

```bash
ssh -N \
  -L 8787:127.0.0.1:8787 \
  -L 7928:127.0.0.1:7928 \
  root@VPS_IP
```

- Web: `http://127.0.0.1:8787/private_path/`
- HTTP / HTTPS: `127.0.0.1:7928`
- SOCKS5: `127.0.0.1:7928`, 가능하면 원격 DNS 또는 `socks5h` 사용

> [!WARNING]
> `7928`은 기본적으로 공개 사용자 인증을 제공하지 않습니다. 방화벽, 접속 원본 IP 제한 또는 기타 신뢰할 수 있는 접근 제어 없이 공개하지 마십시오.

<a id="legal"></a>
## 사용 범위 및 법적 고지

> [!CAUTION]
> 이 프로젝트를 다운로드, 배포 또는 사용하기 전에 사용 지역과 VPS 소재지의 법률, 제공업체 약관 및 VPNGate 규칙을 준수하는지 직접 확인해야 합니다. 이 내용은 프로젝트의 사용 범위를 설명할 뿐 법률 자문이 아니며 법적 책임의 면제를 보장하지 않습니다.

1. **허용 목적:** 합법적인 네트워크 연구, 교육, 개발 테스트, 개인정보 보호 및 승인된 접속에만 사용하십시오. 법에 따라 시행되는 통제 회피, 무단 접속, 공격, 스캔, 스팸, 사기, 권리 침해 또는 기타 불법 활동에 사용해서는 안 됩니다.
2. **네트워크 및 지역 제한:** 일부 지역과 데이터 센터는 VPNGate, GitHub 미러 또는 원격 VPN 노드를 제한할 수 있습니다. 이 프로젝트는 어떤 지역이나 호스트에서도 지속적인 가용성을 보장하지 않습니다. 현지 법률과 제공업체 약관이 허용하는 환경에서만 사용하십시오.
3. **제3자 노드:** VPNGate 노드는 제3자 자원봉사자가 운영합니다. 이 프로젝트는 해당 노드를 소유, 통제 또는 감사하지 않으며 가용성, 속도, 보안, 개인정보 처리 또는 로그 기록을 보장하지 않습니다. 신뢰할 수 없는 노드로 민감한 정보를 전송하지 마십시오.
4. **사용자 책임:** 노드 선택, 트래픽, 배포 위치, 공개 포트 및 계정 보안은 사용자의 책임입니다. 불법 사용, 잘못된 설정, 제3자 노드, 서비스 중단, 데이터 유출 또는 계정 남용에 대한 법적 책임은 사용자에게 있습니다.
5. **무보증:** 소프트웨어는 “있는 그대로” 제공됩니다. 적용 법률이 허용하는 최대 범위에서 유지관리자는 가용성, 상품성, 특정 목적 적합성 또는 간접 손해를 보증하지 않습니다. 법적으로 제외할 수 없는 책임에는 영향을 주지 않습니다.
6. **불확실한 경우 중단:** 현지 법률이나 제공업체 정책이 이를 허용하는지 확인할 수 없다면 배포 및 사용을 중단하고 해당 관할권의 자격 있는 법률 전문가와 상담하십시오.

<div align="center">

[Stable Release](https://github.com/askfname/aimili-vpngate/releases/latest) · [Issues](https://github.com/askfname/aimili-vpngate/issues) · [GPL-3.0 License](../LICENSE)

</div>
