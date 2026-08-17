# 目黒区施設予約システム 駒場庭球場 空き監視 設計書

- Date: 2026-08-16
- Status: Approved

## 背景・目的

目黒区施設予約システム(https://resv.city.meguro.tokyo.jp/Web/Yoyaku/WgR_ShisetsuKensaku)の
「駒場体育館 > 駒場庭球場」は土日の予約が取りにくく満枠(×)になっていることが多い。
キャンセルによって空きが発生した瞬間を検知し、Discordに通知することで、
手動で巡回しなくても予約のチャンスを逃さないようにする。

v1のスコープは「検知して通知する」までで、自動予約は行わない。

## 対象サイトの構造（2026-08-16 手動確認済み）

サイトはASP.NET WebForms製で、`__doPostBack`によるページ遷移を行う。空き状況の閲覧は
ログイン不要で到達可能。確認したナビゲーションフロー:

1. `https://resv.city.meguro.tokyo.jp/Web/` → トップページ (`WgR_ModeSelect`)
   - 直接 `WgR_ShisetsuKensaku` にURLアクセスすると `InternalError.html` になる
     (セッション/ViewStateが必要なためトップから遷移する必要がある)
2. トップページで「スポーツ施設」ボタンをクリック → 施設検索 (`WgR_ShisetsuKensaku`)
3. 施設一覧テーブルから「駒場体育館」の行をクリックしてチェック → 「次へ進む」
4. 施設別空き状況 (`WgR_ShisetsubetsuAkiJoukyou`)
   - 表示開始日・表示期間（1週間/2週間/1ヶ月）を選んで「表示」
   - 施設ごとに日別の一覧表が出る。「駒場庭球場」の行に日付ごとの記号（○空き/△一部空き/×空きなし/－申込期間外）
   - 対象の日付セルをチェックして「次へ進む」（複数日選択可）
5. 時間帯別空き状況 (`WgR_JikantaibetsuAkiJoukyou`)
   - 選択した日付ごとに表が出る。各表は施設名（駒場庭球場）の下に
     コート（A面/B面/C面/D面兼ゲートボール場）× 時間帯（9:00-11:00, 11:00-13:00, 13:00-15:00,
     15:00-17:00, 17:00-18:00）のマス目
   - 記号は ○空きあり / ×空きなし / －申込対象外 の3種類（△はここには出ない、日別一覧のみ）

この時間帯別の粒度（コート×時間帯）が監視・通知の最小単位になる。

## 監視対象

- 施設: 駒場体育館 > 駒場庭球場
- コート: A面, B面, C面, D面兼ゲートボール場（4面すべて）
- 曜日: 土・日のみ
- 期間: 巡回実行時点から2週間先まで
- 認証: 不要（ログインなしで閲覧可能なページのみ使用。ユーザーから提供されたログインID/パスワードはv1では未使用）

## アーキテクチャ

- リポジトリ: `~/github/tennis-booking` (GitHub: `i-cezuki/tennis-booking`)
- 言語: Python + Playwright (headless Chromium)
- 実行環境: GitHub Actions の `schedule` トリガー、5分間隔 (`cron: '*/5 * * * *'`)
  - 既知の制約: GitHub Actionsのscheduled workflowは負荷状況により実行が数分〜十数分遅延することがある
  - 既知の制約: リポジトリに60日間コミットが無いとscheduled workflowが自動的に無効化される
    （v1では対策せず、既知の制約として記録するのみ。空きが全く出ない期間が60日続いた場合は
    手動でworkflowを再度有効化する必要がある）

## コンポーネント構成

```
tennis-booking/
├── .github/workflows/watch.yml   # 5分毎にscraper.pyを実行するワークフロー
├── src/
│   ├── scraper.py                # Playwrightでのサイト巡回・パース（ナビゲーション実行、生データ抽出）
│   ├── diff.py                   # 前回状態との比較（純粋関数、テスト対象）
│   └── notify.py                 # Discord Webhook送信
├── requirements.txt               # playwright
├── state.json                    # 前回の空き状況のスナップショット（変化時のみコミット）
└── docs/superpowers/specs/       # 本ドキュメント
```

## データフロー

1. `scraper.py` がPlaywrightを起動し、上記ナビゲーションフローを実行
2. 直近2週間の土日の日付をすべて選択し、時間帯別空き状況ページへ遷移
3. 各日付の表をパースし、`{date: {court: {slot: "○"|"×"|"－"}}}` の構造に変換
4. `diff.py` が、リポジトリにコミットされている `state.json`（前回状態）と現在の結果を比較
   - 「新規空き」の定義: 前回 `×` または未記録で、今回 `○` になったマス
   - `－`（申込対象外）は無視する
5. 新規空きが1件以上あれば、`notify.py` がDiscord Webhookに通知を送信
   - 内容: 日付・面（A〜D）・時間帯・予約ページへのリンク（`WgR_ShisetsuKensaku` の直接URLはエラーになるため、
     トップページのURLと「スポーツ施設 > 駒場体育館」を辿る旨を案内文に含める）
   - 複数件ある場合は1メッセージにまとめる
6. 現在の状態を `state.json` に書き出す。前回コミットされていた内容と差分があれば
   `git commit && git push`（差分がなければコミットしない）

## エラーハンドリング

- サイト構造の変化・タイムアウト・ネットワークエラー等が発生した場合は例外をログ出力してexit 1
  - GitHub ActionsのRun一覧が失敗表示になることで気づける想定
  - v1ではDiscordへの失敗通知は行わない（YAGNI、必要になったらv2で追加）

## Secrets / 設定

- `DISCORD_WEBHOOK_URL`: GitHub Actions の Repository Secret として設定（ユーザーが別途Discordで作成してSecrets登録）
- ワークフローの `permissions: contents: write` を設定し、デフォルトの `GITHUB_TOKEN` でstate.jsonのpushを行う

## テスト方針

- `diff.py`（差分検出ロジック）はサンプルデータを使ったunit testを書く（pytest）
- `scraper.py` のサイトナビゲーション・セレクタは、今回Playwrightで手動検証済み
  （施設検索→駒場体育館選択→施設別空き状況→時間帯別空き状況の遷移、および
  ○/△/×/－の表示、A〜D面×5時間帯のテーブル構造を実際のサイトで確認した）
- 実装後、GitHub Actions上で実際に1回手動トリガー（`workflow_dispatch`）して動作確認する

## スコープ外（v1では実装しない）

- ログインしての自動予約・仮予約
- Discord以外の通知チャネル
- 駒場庭球場以外の施設・平日の監視
- 失敗時のDiscord通知
