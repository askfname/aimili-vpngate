<div align="center">

# AimiliVPN

**面向 Linux VPS 的 VPNGate 节点管理与 HTTP / HTTPS / SOCKS5 代理网关**

[![正式版本](https://img.shields.io/github/v/release/askfname/aimili-vpngate?style=flat-square&label=正式版&color=16a34a)](https://github.com/askfname/aimili-vpngate/releases/latest)
[![License](https://img.shields.io/badge/License-GPL--3.0-334155?style=flat-square)](LICENSE)

**简体中文** · [English](docs/README.en.md) · [日本語](docs/README.ja.md) · [한국어](docs/README.ko.md)

[快速安装](#quick-install) · [完整安装](#installation) · [连接使用](#connection) · [法律声明](#legal)

</div>

如果你觉得这个项目对你有帮助，欢迎点击下方的链接支持我们，你的支持是我们持续维护的动力。

<p align="center">
  <a href="https://ko-fi.com/playlaboratory"><img src="https://img.shields.io/badge/Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="在 Ko-fi 上支持我们"></a>
  <a href="https://afdian.com/a/playlab"><img src="https://img.shields.io/badge/Afdian-946CE6?style=for-the-badge&logo=afdian&logoColor=white" alt="在爱发电上支持我们"></a>
</p>

AimiliVPN 使用 Python 标准库管理 VPNGate 节点，提供节点获取与检测、连接切换、Web 管理后台，以及共用一个端口的 HTTP、HTTPS 网站代理和 SOCKS5 代理服务。

| 项目 | 默认值或支持范围 |
| --- | --- |
| Web 管理后台 | TCP `8787` + 独立安全路径 + 账号密码 |
| 本机代理 | `127.0.0.1:7928`，支持 HTTP、HTTPS `CONNECT` 和 SOCKS5 |
| OpenCode 检测 | 按国家 + IP 类型筛选节点，多线程按节点出口检测公开免费模型 |
| 源码部署 | x64、x86、ARM64、ARM32 Linux |
| 更新通道 | GitHub `main` 正式分支 / 最新正式 Release |

> [!IMPORTANT]
> **网络可用性提示：** 不同地区、数据中心和网络服务商可能限制 DNS、VPNGate API、GitHub 镜像或 VPN 协议。镜像与本地缓存只能提高节点列表的可用性，不能保证所有机型都能建立连接。部署前请确认所在地法律和 VPS 服务商条款允许使用 VPN/TUN。

<a id="quick-install"></a>
## 快速安装

使用 `root` 用户在受支持的 Linux VPS 上执行：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

安装完成后，终端会显示 Web 后台完整地址、随机安全路径、登录账号和密码。输入 `ml` 可打开管理菜单。

无人值守安装可显式跳过首次参数询问，并自动生成安全路径和登录凭据：

```bash
AIMILIVPN_NONINTERACTIVE=1 bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

> [!TIP]
> 安装前请在 VPS 控制面板启用 TUN/TAP，并确认 `/dev/net/tun` 存在。Web 默认使用 TCP `8787`，安全组建议只允许自己的 IP 访问。

<a id="installation"></a>
## 完整安装

### 运行条件

- 操作系统：Ubuntu、Debian、Alpine、CentOS、RHEL、Rocky Linux、AlmaLinux、Fedora、Oracle Linux 或 Amazon Linux。
- 权限与组件：`root`、OpenVPN、iptables、策略路由和 TUN/TAP。
- Windows 与 macOS 可作为代理客户端，但不能直接运行完整网关。

### 一键源码安装

```bash
bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

安装器会部署到 `/opt/aimilivpn` 并注册系统服务。常用命令：

```bash
ml                 # 打开管理菜单
ml status          # 查看状态、Web 地址和账号
ml logs            # 查看实时日志
ml restart         # 重启服务
ml password        # 重设 Web 账号密码
ml update          # 从 main 正式分支更新
ml uninstall       # 卸载
```

需要先审查脚本时：

```bash
git clone --branch main --single-branch https://github.com/askfname/aimili-vpngate.git
cd aimili-vpngate
sudo bash install.sh
```

通用 Linux 源码包与 SHA-256 校验文件可在 [GitHub Releases](https://github.com/askfname/aimili-vpngate/releases/latest) 下载，版本变更记录也统一放在 Release Notes 中。

<a id="connection"></a>
## 连接与使用

### 1. 登录 Web 后台

源码安装完成后，使用终端输出的地址访问：

```text
http://VPS_IP:8787/随机安全路径/
```

忘记地址时执行 `ml status`；需要重设账号密码时执行 `ml password`。

### 2. 获取并连接节点

1. 登录后台，等待首次节点加载完成，或点击“更新节点”。
2. 按国家筛选节点，并使用“测试”检查本机实测延迟与可用性。
3. 点击目标节点的“切换”；目标预检失败时，程序会尽量保留当前可用连接。
4. 根据需要选择智能自动、固定国家或固定 IP 模式。
5. 在状态区域确认 VPN 已连接，并核对当前出口 IP。

### 3. 在 VPS 本机使用代理

HTTP、HTTPS 网站代理和 SOCKS5 共用 `127.0.0.1:7928`。HTTPS 网站通过 HTTP 代理的 `CONNECT` 方法访问，代理地址仍填写 `http://127.0.0.1:7928`。

```bash
# HTTP / HTTPS
curl -x http://127.0.0.1:7928 https://api.ipify.org

# SOCKS5，并通过代理解析域名
curl --proxy socks5h://127.0.0.1:7928 https://api.ipify.org
```

<details>
<summary><strong>查看 Shell 环境变量与 Python 示例</strong></summary>

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

### 4. 一键检测 OpenCode 节点

Web 工具栏的“检测 OpenCode”会对当前筛选结果中的全部节点并发建立临时测试隧道，并通过各节点出口请求 OpenCode 公开免费模型。

- **可用**：节点出口成功返回非空模型回复，可直接使用 OpenCode 免费额度。
- **额度用尽**：返回 `402`、`429` 或 Free usage limit 等额度限制。
- **不可用**：建隧失败、TLS/连接失败、鉴权失败或响应为空。
- **未检测**：尚未运行检测。
- 检测可随时停止；结果列与进度面板实时更新，“只看可用”可快速筛出成功节点。
- 检测会临时占用多个 `tun` 接口和策略路由，期间节点切换与手动测试暂时禁用，请等待检测结束或先停止检测。

> 检测依赖 Linux TUN/TAP、OpenVPN、`iproute2` 以及 `root`/`NET_ADMIN` 权限，并需要 **Bun 运行时**；Windows/macOS 客户端无法执行。安装脚本会自动安装 Bun，也可用 `OPENCODE_BUN_PATH` 指定 `bun` 可执行文件。公开通道额度按节点出口 IP 计算，不代表第三方节点本身长期稳定。

<details>
<summary><strong>OpenCode 检测环境变量</strong></summary>

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPENCODE_API_BASE` | `https://opencode.ai/inference/v1` | 公开 API 根地址（模型列表） |
| `OPENCODE_API_URL` | `https://opencode.ai/inference/openai/v1/chat/completions` | 检测用补全接口 |
| `OPENCODE_MODELS_URL` | `${OPENCODE_API_BASE}/models` | 免费模型列表接口 |
| `OPENCODE_API_KEY` | `public` | 公开通道 Bearer 值 |
| `OPENCODE_MODEL` | 空（自动选择免费模型） | 指定检测模型（优先于页面下拉选择） |
| `OPENCODE_FALLBACK_MODEL` | `beam-free` | 模型列表不可用时的备用模型 |
| `OPENCODE_CHECK_WORKERS` | `10` | 并发测试隧道数，范围 1–24 |
| `OPENCODE_CHECK_TIMEOUT_SECONDS` | `20` | 单节点 API 请求超时 |
| `OPENCODE_OPENVPN_TIMEOUT_SECONDS` | `12` | 单节点建隧超时 |
| `OPENCODE_CHECK_NODE_LIMIT` | `2000` | 单次检测节点上限 |
| `OPENCODE_BUN_PATH` | 空（自动探测 PATH 与常见安装路径） | Bun 可执行文件路径 |
| `OPENCODE_EXTRA_HEADERS` | 空 | 额外请求头，JSON 对象字符串（仅作用于模型列表） |

修改环境变量后重启服务或容器生效。

</details>

### 5. 从电脑或其他设备连接

代理默认只监听 VPS 回环地址。推荐使用 SSH 隧道，不要直接暴露代理端口：

```bash
ssh -N \
  -L 8787:127.0.0.1:8787 \
  -L 7928:127.0.0.1:7928 \
  root@VPS_IP
```

隧道建立后：

- Web：`http://127.0.0.1:8787/随机安全路径/`
- HTTP / HTTPS 代理：`127.0.0.1:7928`
- SOCKS5 代理：`127.0.0.1:7928`，支持时选择远程 DNS 或 `socks5h`

> [!WARNING]
> `7928` 默认没有面向公网的用户认证。请勿在没有防火墙、来源 IP 限制或其他可靠访问控制的情况下将其直接开放到公网。

<a id="legal"></a>
## 使用范围与法律声明

> [!CAUTION]
> 下载、部署或使用本项目即表示您应自行确认用途符合所在地法律、VPS 所在地法律、网络服务商条款及 VPNGate 的相关规则。以下内容是项目使用边界，不构成法律意见，也不能保证免除任何个人或组织依法应承担的责任。

1. **限定用途**：本项目仅用于合法的网络研究、教育、开发测试、隐私保护和经授权的网络访问，不得用于绕过依法实施的监管措施、未授权访问、攻击、扫描、垃圾信息、欺诈、侵权或其他违法活动。
2. **网络与地区限制**：不同地区和数据中心可能限制 VPNGate、GitHub 镜像或远端 VPN 节点。本项目不承诺任何地区或机型始终可用；仅应在当地法律和服务商条款允许的环境中合理使用。
3. **第三方节点**：VPNGate 节点由第三方志愿者运营，本项目不拥有、不控制也不审核这些节点，无法保证其稳定性、速度、安全性、隐私政策或日志行为。请勿通过不可信节点传输账号密码、金融信息、商业机密等敏感数据。
4. **用户责任**：节点选择、流量内容、部署位置、端口开放和账号安全均由使用者负责。因违法使用、配置不当、第三方节点、服务中断、数据泄露或账号滥用产生的后果，由使用者依法承担。
5. **无保证提供**：软件按“现状”提供，在适用法律允许的最大范围内，维护者不对可用性、适销性、特定用途适用性或间接损失作出保证。无法依法排除的责任不受本声明影响。
6. **不确定时停止使用**：如无法确认当地法律或服务商是否允许，请停止部署和使用，并咨询当地有执业资格的法律专业人士。

<div align="center">

[正式版本](https://github.com/askfname/aimili-vpngate/releases/latest) · [问题反馈](https://github.com/askfname/aimili-vpngate/issues) · [GPL-3.0 License](LICENSE)

</div>
