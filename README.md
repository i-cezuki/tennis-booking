# tennis-booking

目黒区施設予約システムの「駒場体育館 > 駒場庭球場」を5分おきに巡回し、
土日・直近2週間の枠に新しい空き（キャンセル等）が出たらDiscordに通知します。

## 仕組み

- `src/main.py` が Playwright でログイン不要の空き状況ページを巡回し、
  `state.json`（前回の空き状況）と比較して新規に空いた枠だけをDiscordに通知します。
- GitHub Actions (`.github/workflows/watch.yml`) が5分間隔でこれを実行します。
- v1では自動予約は行いません。ログイン情報は使用していません。

詳細設計: `docs/superpowers/specs/2026-08-16-meguro-tennis-watcher-design.md`

## セットアップ

1. Discordでこの通知を受け取りたいチャンネルのWebhook URLを作成する
   （チャンネル設定 → 連携サービス → Webhook）。
2. このリポジトリの Settings → Secrets and variables → Actions で
   `DISCORD_WEBHOOK_URL` という名前のシークレットに上記URLを登録する。
3. Actions タブから `Watch Komaba tennis court availability` を手動実行し、
   成功することを確認する。以降は5分おきに自動実行される。

## ローカル開発

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m pytest -v
```
