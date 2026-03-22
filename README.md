# 無在庫転売管理ツール

Amazon × メルカリの価格差アービトラージを支援するツールです。

## 機能

| フェーズ | 機能 | 説明 |
|---------|------|------|
| 1 | 価格差リサーチ | Amazonとメルカリの価格差を自動比較し、利益商品を抽出 |
| 2 | 在庫監視＆通知 | Amazon在庫を5分間隔で監視し、在庫切れ時にDiscord/LINE通知 |
| 3 | メルカリ自動停止 | 在庫切れ商品のメルカリ出品を自動で公開停止 |

## セットアップ

```bash
# 1. 仮想環境の作成
python3 -m venv .venv
source .venv/bin/activate

# 2. 依存パッケージのインストール
pip install -r dropshipping/requirements.txt

# 3. Playwrightブラウザのインストール
playwright install chromium

# 4. 環境変数の設定
cp dropshipping/.env.example .env
# .env を編集して各種APIキー・認証情報を設定
```

## 使い方

### フェーズ1: 価格差リサーチ

```bash
# Amazon URLリストでリサーチ
python -m dropshipping research --urls "https://www.amazon.co.jp/dp/XXXXXXXXXX,https://www.amazon.co.jp/dp/YYYYYYYYYY"

# キーワード検索でリサーチ
python -m dropshipping research --keyword "ワイヤレスイヤホン"

# オプション: 送料・最低利益を指定
python -m dropshipping research --keyword "充電器" --shipping 500 --min-profit 5000
```

### フェーズ2: 在庫監視

```bash
# 単発チェック
python -m dropshipping monitor

# 継続監視（5分間隔）
python -m dropshipping monitor --loop

# 間隔を変更（秒指定）
python -m dropshipping monitor --loop --interval 600
```

### フェーズ3: メルカリ公開停止

```bash
python -m dropshipping pause
```

### データベース操作

```bash
# 全商品一覧
python -m dropshipping list

# 利益商品のみ
python -m dropshipping list --profitable

# ステータス変更（例: 商品ID 1を「出品中」に）
python -m dropshipping set-status 1 listed
```

## ステータス一覧

| ステータス | 説明 |
|-----------|------|
| `researched` | リサーチ済み（初期状態） |
| `listed` | メルカリに出品中 |
| `out_of_stock` | Amazon在庫切れ（要対応） |
| `paused` | メルカリ出品停止済み |
| `sold` | 販売完了 |
| `archived` | アーカイブ |

## 運用フロー

1. `research` で利益商品を発見 → DBに自動保存
2. 手動でメルカリに出品 → `set-status <id> listed` でステータス変更
3. `monitor --loop` で在庫監視を常時実行
4. 在庫切れ時 → Discord/LINEに通知 → ステータスが `out_of_stock` に自動更新
5. `pause` で在庫切れ商品のメルカリ出品を自動停止

## 注意事項

- スクレイピングは対象サイトに負荷をかけないよう適切な待機時間を設定しています
- メルカリの利用規約を確認の上、自己責任でご利用ください
- 二段階認証対応：メルカリログイン時に認証コード入力を待機します
