# AimiliVPN V2.2.0 正式版

V2.2.0 在 V2.1.5 的基础上新增 OpenCode 公开免费模型可用性一键检测，并对管理后台的检测进度、结果标记和筛选体验进行了完整支持。

## OpenCode 免费模型检测

- Web 工具栏新增“检测 OpenCode”，对当前“国家 + IP 类型”筛选范围内的全部节点并发检测，不受可用状态与收藏过滤影响。
- 每个节点通过独立临时 TUN 接口、`SO_MARK` 和策略路由隔离测试出口，不干扰现有连接与代理服务。
- 通过 OpenCode Zen 公开通道发起最小化流式请求，只有收到非空回复内容才判定为“可用”，避免仅凭 HTTP 200 误判。
- 明确区分“可用”“额度用尽”“不可用”“检测中”和“未检测”；`402`、`429` 及额度限制提示归类为额度用尽。
- 自动读取模型列表并优先选择 `big-pickle` 等免费模型，支持环境变量覆盖 API 地址、密钥、模型、并发数、超时和额外请求头。
- 节点表新增“OpenCode 额度”列，检测面板实时展示进度与可用、额度用尽、不可用统计，支持“只看可用”和随时停止。
- 检测结果持久化保存；检测期间禁止切换节点；服务重启时自动清理中断的检测状态。

## 验证

- 本地 Python 单元测试 62/62 通过。
- Python 源码编译、Dashboard JavaScript 语法、安装脚本语法和发行归档构建检查通过。
- 公开接口在线校验返回 `429 FreeUsageLimitError`，已正确归类为额度用尽；真实节点端到端检测需在 Linux TUN/TAP、OpenVPN、`iproute2` 与 root/NET_ADMIN 环境中执行。

## 平台限制

- OpenCode 检测依赖 Linux TUN/TAP、OpenVPN、`iproute2` 以及 `root`/`NET_ADMIN` 权限，Windows/macOS 客户端无法执行。
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
