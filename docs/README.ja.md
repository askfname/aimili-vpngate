<div align="center">

# AimiliVPN

**Linux VPS 向け VPNGate ノード管理・HTTP / HTTPS / SOCKS5 プロキシゲートウェイ**

[![Release](https://img.shields.io/github/v/release/askfname/aimili-vpngate?style=flat-square&label=stable&color=16a34a)](https://github.com/askfname/aimili-vpngate/releases/latest)
[![License](https://img.shields.io/badge/License-GPL--3.0-334155?style=flat-square)](../LICENSE)

[简体中文](../README.md) · [English](README.en.md) · **日本語** · [한국어](README.ko.md)

[クイックインストール](#quick-install) · [インストール](#installation) · [接続方法](#connection) · [法的通知](#legal)

</div>

このプロジェクトがお役に立ちましたら、以下のリンクからご支援いただけると幸いです。皆さまのご支援が継続的なメンテナンスの励みになります。

<p align="center">
  <a href="https://ko-fi.com/playlaboratory"><img src="https://img.shields.io/badge/Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Ko-fi で支援する"></a>
  <a href="https://afdian.com/a/playlab"><img src="https://img.shields.io/badge/Afdian-946CE6?style=for-the-badge&logo=afdian&logoColor=white" alt="愛発電で支援する"></a>
</p>

AimiliVPN は Python 標準ライブラリで VPNGate ノードを管理し、ノード取得・テスト、接続切り替え、Web 管理画面、HTTP / HTTPS サイト用プロキシと SOCKS5 を提供します。

| 項目 | デフォルトまたは対応範囲 |
| --- | --- |
| Web 管理画面 | TCP `8787`、専用パス、ユーザー名、パスワード |
| ローカルプロキシ | `127.0.0.1:7928`、HTTP、HTTPS `CONNECT`、SOCKS5 |
| OpenCode 検査 | 国 + IP 種別でノードを絞り込み、各ノードの出口から公開無料モデルを検査 |
| ソース版 | x64、x86、ARM64、ARM32 Linux |

> [!IMPORTANT]
> **ネットワーク可用性：** 地域、データセンター、ネットワーク事業者によっては、DNS、VPNGate API、GitHub ミラー、VPN プロトコルが制限される場合があります。ミラーとローカルスナップショットはノード一覧の可用性を高めますが、すべての環境で接続を保証するものではありません。展開前に、現地法と VPS 事業者が VPN/TUN を許可していることを確認してください。

<a id="quick-install"></a>
## クイックインストール

対応する Linux VPS で `root` として実行します。

```bash
bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

完了後、Web 管理画面の URL、専用パス、ユーザー名、パスワードが表示されます。`ml` で管理メニューを開けます。

無人インストールでは、初回の質問を明示的にスキップし、Web パスと認証情報を自動生成します。

```bash
AIMILIVPN_NONINTERACTIVE=1 bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

> [!TIP]
> VPS の管理画面で TUN/TAP を有効にし、`/dev/net/tun` が存在することを確認してください。Web のデフォルトポートは TCP `8787` です。可能な限り自分の IP だけを許可してください。

<a id="installation"></a>
## インストール

### 動作要件

- Ubuntu、Debian、Alpine、CentOS、RHEL、Rocky Linux、AlmaLinux、Fedora、Oracle Linux、Amazon Linux。
- `root`、OpenVPN、iptables、ポリシールーティング、TUN/TAP。
- Windows と macOS はプロキシクライアントとして利用できますが、ゲートウェイ本体は実行できません。

### ソースインストーラー

```bash
bash <(curl -Ls https://raw.githubusercontent.com/askfname/aimili-vpngate/main/install.sh)
```

`/opt/aimilivpn` に配置し、システムサービスを登録します。

```bash
ml                 # 管理メニュー
ml status          # 状態、Web URL、ユーザー名
ml logs            # ログ
ml restart         # 再起動
ml password        # Web 認証情報を再設定
ml update          # main 安定版から更新
ml uninstall       # アンインストール
```

事前にスクリプトを確認する場合：

```bash
git clone --branch main --single-branch https://github.com/askfname/aimili-vpngate.git
cd aimili-vpngate
sudo bash install.sh
```

Linux 共通ソースアーカイブと SHA-256 は [GitHub Releases](https://github.com/askfname/aimili-vpngate/releases/latest) から取得できます。変更内容は Release Notes に掲載されます。

<a id="connection"></a>
## 接続と利用方法

### 1. Web 管理画面へログイン

ソース版では、インストーラーが表示した URL を開きます。

```text
http://VPS_IP:8787/private_path/
```

URL は `ml status`、認証情報の再設定は `ml password` を使用します。

### 2. ノードを取得して接続

1. ログイン後、最初の一覧を待つか「ノード更新」を実行します。
2. 国で絞り込み、「テスト」で VPS からの到達性と遅延を確認します。
3. 対象ノードの「切り替え」を選択します。事前確認に失敗した場合、可能な限り現在の接続を維持します。
4. スマート自動、国固定、IP 固定からルーティングモードを選びます。
5. 接続状態と出口 IP を確認します。

### 3. VPS 上でプロキシを使用

HTTP、HTTPS サイト用プロキシ、SOCKS5 は `127.0.0.1:7928` を共有します。

```bash
# HTTP / HTTPS
curl -x http://127.0.0.1:7928 https://api.ipify.org

# SOCKS5、DNS もプロキシ経由
curl --proxy socks5h://127.0.0.1:7928 https://api.ipify.org
```

<details>
<summary><strong>Shell 環境変数と Python の例</strong></summary>

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

### 4. OpenCode ノードを検査

Web ツールバーの「OpenCode 検査」は、現在のフィルター結果に含まれるすべてのノードに一時テストトンネルを並行して作成し、各ノードの出口から OpenCode の公開無料モデルへリクエストします。

- **利用可能：** ノード出口から空でないモデル応答が返り、OpenCode の無料枠を利用できます。
- **枠を使い切り：** `402`、`429`、Free usage limit などの利用制限が返されました。
- **利用不可：** トンネル確立、TLS/接続、認証に失敗したか、応答が空です。
- **未検査：** まだ検査を実行していません。
- 検査はいつでも停止できます。結果と進捗はリアルタイムで更新され、「利用可能のみ表示」で成功ノードを絞り込めます。
- 実行中は複数の `tun` インターフェースとポリシールートを一時使用します。検査の終了または停止まで、ノード切り替えと手動テストは無効になります。

> Linux TUN/TAP、OpenVPN、`iproute2`、`root`/`NET_ADMIN` 権限、および **Bun ランタイム**が必要です。Windows/macOS クライアントでは実行できません。インストールスクリプトが Bun を自動でインストールします。別の実行ファイルを指定する場合は `OPENCODE_BUN_PATH` を設定してください。公開チャンネルの利用枠はノード出口 IP ごとに計算され、第三者ノードの長期的な安定性を保証するものではありません。

<details>
<summary><strong>OpenCode 検査の環境変数</strong></summary>

| 変数 | デフォルト | 説明 |
| --- | --- | --- |
| `OPENCODE_API_BASE` | `https://opencode.ai/inference/v1` | 公開 API ルート（モデル一覧） |
| `OPENCODE_API_URL` | `https://opencode.ai/inference/openai/v1/chat/completions` | 検査に使用する補完エンドポイント |
| `OPENCODE_MODELS_URL` | `${OPENCODE_API_BASE}/models` | 無料モデル一覧エンドポイント |
| `OPENCODE_API_KEY` | `public` | 公開チャンネルの Bearer 値 |
| `OPENCODE_MODEL` | 空（無料モデルを自動選択） | 検査モデル。画面の選択より優先 |
| `OPENCODE_FALLBACK_MODEL` | `beam-free` | モデル一覧を取得できない場合の代替モデル |
| `OPENCODE_CHECK_WORKERS` | `10` | 同時テストトンネル数、範囲 1–24 |
| `OPENCODE_CHECK_TIMEOUT_SECONDS` | `20` | ノードごとの API リクエストタイムアウト |
| `OPENCODE_OPENVPN_TIMEOUT_SECONDS` | `12` | ノードごとのトンネル確立タイムアウト |
| `OPENCODE_CHECK_NODE_LIMIT` | `2000` | 1 回の検査で処理するノード上限 |
| `OPENCODE_BUN_PATH` | 空（PATH と一般的なインストール先を自動検出） | Bun 実行ファイルのパス |
| `OPENCODE_EXTRA_HEADERS` | 空 | 追加ヘッダー（モデル一覧にのみ適用する JSON オブジェクト文字列） |

環境変数の変更を反映するには、サービスまたはコンテナを再起動してください。

</details>

### 5. 別の端末から接続

プロキシを公開せず、SSH トンネルを利用してください。

```bash
ssh -N \
  -L 8787:127.0.0.1:8787 \
  -L 7928:127.0.0.1:7928 \
  root@VPS_IP
```

- Web：`http://127.0.0.1:8787/private_path/`
- HTTP / HTTPS：`127.0.0.1:7928`
- SOCKS5：`127.0.0.1:7928`。可能な場合はリモート DNS または `socks5h` を使用

> [!WARNING]
> `7928` には、デフォルトで公開用のユーザー認証がありません。ファイアウォール、接続元 IP 制限などの確実なアクセス制御なしで公開しないでください。

<a id="legal"></a>
## 利用範囲と法的通知

> [!CAUTION]
> 本プロジェクトをダウンロード、展開、使用する前に、利用地と VPS 所在地の法律、事業者の規約、VPNGate の規則への適合を利用者自身で確認してください。本節は利用範囲を示すもので、法律上の助言ではなく、法的責任の免除を保証するものではありません。

1. **許可される用途：** 合法なネットワーク研究、教育、開発テスト、プライバシー保護、許可されたアクセスに限ります。法的な規制の回避、不正アクセス、攻撃、スキャン、スパム、詐欺、権利侵害、その他の違法行為に使用してはいけません。
2. **ネットワークと地域の制限：** 地域やデータセンターによっては VPNGate、GitHub ミラー、VPN ノードが制限される場合があります。本プロジェクトは、いかなる地域・環境でも継続的な可用性を保証しません。現地法と事業者規約が許可する場合に限り使用してください。
3. **第三者ノード：** VPNGate ノードは第三者のボランティアが運営しています。本プロジェクトはノードを所有・管理・監査せず、可用性、速度、安全性、プライバシー方針、ログ動作を保証しません。機密情報を信頼できないノードで送信しないでください。
4. **利用者の責任：** ノード選択、通信内容、設置場所、公開ポート、アカウント管理は利用者の責任です。違法利用、設定不備、第三者ノード、停止、情報漏えい、不正利用に伴う責任は利用者が負います。
5. **無保証：** 本ソフトウェアは「現状有姿」で提供されます。適用法で認められる最大限の範囲で、保守者は可用性、商品性、特定目的適合性、間接損害を保証しません。法律上排除できない責任には影響しません。
6. **不明な場合：** 現地法や事業者規約で許可されているか確認できない場合は使用を中止し、該当法域の有資格法律専門家に相談してください。

<div align="center">

[Stable Release](https://github.com/askfname/aimili-vpngate/releases/latest) · [Issues](https://github.com/askfname/aimili-vpngate/issues) · [GPL-3.0 License](../LICENSE)

</div>
