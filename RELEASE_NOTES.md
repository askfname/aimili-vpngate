# AimiliVPN V2.2.0 正式版

V2.2.0 在 V2.1.5 的基础上新增 OpenCode 公开免费模型可用性一键检测，并对管理后台的检测进度、结果标记和筛选体验进行了完整支持。

## OpenCode 免费模型检测

- Web 工具栏新增“检测 OpenCode”，检测范围为页面当前筛选实际显示的节点列表（国家、IP 类型、状态“全部/可用/检测中/失效”、“只看可用”、收藏筛选的交集）。
- 每个节点通过独立临时 TUN 接口、`SO_MARK` 和策略路由隔离测试出口，不干扰现有连接与代理服务。
- 请求统一由 Bun 运行时发出并复刻真实 OpenCode 客户端形状（会话 ID、追踪头、环境块与工具集），避免被网关判定为非客户端形状而误报“额度用尽”。
- 通过本地 CONNECT 代理把 Bun 请求注入节点隧道；只有收到非空流式回复内容才判定为“可用”，避免仅凭 HTTP 200 误判。
- 明确区分“可用”“额度用尽”“不可用”“检测中”和“未检测”；`402`、`429` 及额度限制提示归类为额度用尽，`401`/`403` 归类为不可用。
- 页面可下拉选择任意免费模型（自动读取模型列表，默认第一个免费模型），选择持久化保存，支持环境变量覆盖 API 地址、密钥、模型、并发数、超时和 Bun 路径。
- 节点表新增“OpenCode 额度”列，检测面板实时展示进度与可用、额度用尽、不可用统计，支持“只看可用”和随时停止。
- 检测结果持久化保存；检测期间禁止切换节点；服务重启时自动清理中断的检测状态。

## 验证

- 本地 Python 单元测试 66/66 通过。
- Python 源码编译、Dashboard JavaScript 语法、Bun 探针脚本语法、安装脚本语法和发行归档构建检查通过。
- 公开接口在非真实客户端形状下返回 `429 FreeUsageLimitError` 已知晓；Bun 探针复刻真实客户端形状后经节点隧道返回流式内容并正确归类为可用。真实节点端到端检测需在 Linux TUN/TAP、OpenVPN、`iproute2` 与 root/NET_ADMIN 环境中执行。

## 平台限制

- OpenCode 检测依赖 Linux TUN/TAP、OpenVPN、`iproute2` 以及 `root`/`NET_ADMIN` 权限，Windows/macOS 客户端无法执行，且必须安装 Bun 运行时（安装脚本与 Dockerfile 已内置）。
- OpenCode 公开通道额度按节点出口 IP 计算，第三方 VPNGate 节点的长期稳定性不由本项目保证。

## 下载与更新

- GitHub Release：`aimilivpn-v2.2.0-linux-source.tar.gz` 和 `sha256sums.txt`。
- GHCR：`2.2.0`、`2.2`、`latest` 多架构镜像标签。

Python 源码安装更新：

```bash
ml update
```

Docker Compose 更新：

```bash
docker compose pull
docker compose up -d
```
