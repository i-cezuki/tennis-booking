# 駒場庭球場 空き監視 v2: GitHub Actions → AWS Lambda 移行 設計書

- Date: 2026-08-29
- Status: Approved
- 前提: [2026-08-16-meguro-tennis-watcher-design.md](2026-08-16-meguro-tennis-watcher-design.md)（v1）のロジック（scraper/diff/notify）はそのまま流用する

## 背景・目的

v1はGitHub Actionsの`schedule`トリガー（5分間隔）で運用していたが、実測したところ実行間隔が
数時間〜半日単位まで間延びする既知の問題が発生した（GitHub Actionsが低アクティビティな
publicリポジトリのscheduled workflowを負荷状況に応じてスロットリングするため）。

さらに、この間延びは副作用として誤通知も生んでいた: `diff.py`の「新規空き」判定は
「前回のstateに存在しなかった日付」を無条件に新規扱いするため、実行間隔が開いて
2週間ローリングウィンドウが一度に数日分シフトすると、たまたま元から空いていた
未追跡日の枠が「新規空き」として誤検知される（[main.py診断ログ追加時に実測確認済み]）。

根本原因は「トリガーの実行間隔が正確でない」ことなので、スケジューラをAWS EventBridge
Schedulerに置き換え、実行環境をAWS Lambdaに移行する。

## 制約

- **料金**: 実質無料で運用すること。AWSアカウントは既存のものを使う
- 既存のスクレイピングロジック（`src/scraper.py`, `src/diff.py`, `src/notify.py`）は変更しない
- Discord通知の内容・条件（誤検知バグの修正含む）は本移行のスコープ外。移行後の別タスクとする

## 検討した構成と却下理由

- **GitHub Actionsから`repository_dispatch`やHTTP経由でLambdaを毎回叩く**: トリガー自体が
  依然GitHub Actions側の`schedule`に依存するため、今回の根本問題を解決しない。却下
- **Step Functionsでスクレイピング/差分/通知をステップ分割**: この規模には過剰。Lambda呼び出し回数と
  管理コンポーネントが増えるだけでメリットがない。却下
- **単一Lambda + EventBridge Scheduler**（採用）: 既存の`main.py`のフローをほぼそのままLambda
  ハンドラに移すだけで済み、追加コンポーネントも最小限

## アーキテクチャ

```
EventBridge Scheduler (rate(5 minutes))
    → Lambda (コンテナイメージ, Playwright + Chromium同梱)
        1. SSM Parameter StoreからDISCORD_WEBHOOK_URLを取得
        2. S3から前回のstate.jsonを取得
        3. scraper.fetch_availability() でサイトを巡回・抽出
        4. diff.find_new_openings() で新規空きを判定
        5. あればnotify.send_discord_notification() で通知
        6. 新しいstateをS3に書き戻す
        7. [info]診断ログをCloudWatch Logsに出力

GitHub Actions (main pushトリガーのみ、cronなし)
    → Dockerビルド → ECRへpush → Lambda関数をイメージ更新
      AWS認証はOIDCフェデレーション（長期キーをGitHub Secretsに置かない）
```

**実行間隔は5分**とする。Lambdaの無料枠は月100万リクエスト＋40万GB秒（永続無料）。
5分間隔（月間約8,640回実行、1024MB×20秒/回と仮定して概算17.6万GB秒）は
無料枠内に収まる。1分間隔にすると概算88万GB秒となり無料枠(40万GB秒)を超過するため不採用。

## コンポーネント構成

```
tennis-booking/
├── .github/workflows/
│   ├── watch.yml          # scheduleトリガーを削除、workflow_dispatchのみ残す（手動デバッグ用）
│   └── deploy.yml          # 新規: mainへのpushでDockerビルド→ECR push→Lambda更新
├── infra/
│   └── terraform/          # 新規: Lambda, EventBridge Scheduler, S3, SSM, IAM, ECR
├── src/
│   ├── main.py             # lambda_handler(event, context) を追加、既存main()から共通化
│   ├── state.py            # S3版の読み書きを追加（STATE_BACKEND=s3|file で切替）
│   ├── scraper.py          # 無変更
│   ├── diff.py             # 無変更
│   └── notify.py           # 無変更
├── Dockerfile              # 新規: mcr.microsoft.com/playwright/python ベース + awslambdaric
└── requirements.txt
```

## データフロー・移行方針

- `state.py`に`load_state_s3(bucket, key)` / `save_state_s3(bucket, key, data)`を追加し、
  既存の`load_state`/`save_state`と同じデータ形式（JSON dict）を扱う。`main.py`側で
  `STATE_BACKEND`環境変数により呼び分ける（Lambda実行時は`s3`、ローカル/テスト実行時は`file`）
- 移行時、GitHub側に残っている最新の`state.json`（現在の空き状況）をそのままS3に初期アップロード
  し、空の状態からの再スタートによる誤通知を防ぐ
- S3バケットはバージョニング有効化（誤って空データで上書きした場合に過去バージョンへ復元できるように）

## Secrets / 設定

- `DISCORD_WEBHOOK_URL`: SSM Parameter Store（SecureString、無料）に保存。Secrets Manager
  は月額課金が発生するため使わない
- Lambda実行ロール: 対象S3バケットのみR/W、対象SSMパラメータのみRead、CloudWatch Logs書き込み
  に限定
- GitHub Actions用IAMロール: OIDCフェデレーションで信頼関係を設定し、ECR push と
  `lambda:UpdateFunctionCode`のみに権限を絞る

## エラーハンドリング・監視

- `main.py`の`[info]`診断ログ（取得日数/スロット数/open数/新規opening数/state変化有無）は
  そのままCloudWatch Logsに出力される
- Lambda実行時の例外はCloudWatch Logsにスタックトレースが残り、Lambda標準メトリクス（Errors）
  で追跡可能
- スクレイピング失敗時のスクリーンショット保存は、`/tmp`書き込み→S3アップロードに置き換える
- アラーム通知（CloudWatch Alarms → SNS等）は追加コストとスコープ増になるため今回は行わない
  （v1同様、失敗はCloudWatch上で確認する運用）

## テスト方針

- 既存の`tests/`（diff/state/notify/dates/scraper抽出）はロジック層のみを見ているため無変更で通る想定
- S3版`state.py`の新規関数は`moto`（AWS SDKモックライブラリ、無料）でS3を模擬してTDDで追加
- Lambdaコンテナ自体の動作確認は、ローカルで`docker run` + Lambda Runtime Interface Emulator (RIE)
  を使って擬似的にinvokeしてから実際にデプロイする

## 移行・切り戻し手順

1. Terraformでインフラ作成（Lambda, EventBridge Scheduler, S3, SSM, IAM, ECR, GitHub OIDCロール）
2. GitHub Actions (`deploy.yml`) で初回イメージビルド・push・Lambda更新
3. 現行の`state.json`をS3に初期投入
4. `aws lambda invoke`で手動起動して1回動作確認（通知が正しく飛ぶか、ログが正しく出るか）
5. 問題なければ`.github/workflows/watch.yml`の`schedule:`トリガーを削除してGitHub Actions側の
   cron実行を停止する（`workflow_dispatch`は手動デバッグ用に残す）
6. 旧cronと新Lambdaを並行稼働させず、切替と同時に旧cronを止める（二重通知を避けるため）

## 実装で判明した事項（教訓）

実装・検証（Task 7）で当初の想定と異なることが複数判明した。将来のメンテナンスで
「不要な変更に見えて実は必須」の設定を誤って戻さないよう記録する。

- **`src/scraper.py`は当初「変更しない」としていたが、Chromiumの起動引数のみ変更した**
  (`p.chromium.launch()`の`args=[...]`)。AWS LambdaのFirecrackerサンドボックスは
  Chromiumの通常のマルチプロセスモデルを正式にサポートしておらず、以下の完全なフラグ
  セットが必要:
  `--headless`, `--enable-features=NetworkService,NetworkServiceInProcess`,
  `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`, `--single-process`。
  特に`--single-process`が無いと`GPU process isn't usable. Goodbye.`で確実にクラッシュする
  (参考: [microsoft/playwright#14023](https://github.com/microsoft/playwright/issues/14023))。
  スクレイピング・パースロジック自体は無変更のまま。
- **Lambdaのメモリは1024MBでは不安定、2048MB以上が必要**。Lambdaはメモリ量に比例して
  CPU割り当てが決まるため、メモリ不足はChromium起動時のタイミング依存のクラッシュ
  (`TargetClosedError`)として現れる。2048MBで実測7/8回成功、安定稼働を確認。
- **GitHub ActionsのOIDCトークンの`sub`クレームは`repo:org/repo:ref:...`ではなく
  `repo:org@<id>/repo@<id>:ref:...`形式**（org・repoそれぞれに不変の数値IDが付与される）。
  IAMロールの信頼ポリシーは`StringLike`でワイルドカードを使い
  (`repo:i-cezuki@*/tennis-booking@*:ref:refs/heads/main`)、この形式を許容する必要がある。
  古典的な`org/repo`形式を前提にすると認証が常に失敗する。
- **`token.actions.githubusercontent.com`のOIDCプロバイダーはAWSアカウント内でURLごとに
  1つしか作成できない**。このAWSアカウントには既に別プロジェクトが作成済みのプロバイダーが
  存在したため、`resource "aws_iam_openid_connect_provider"`ではなく
  `data "aws_iam_openid_connect_provider"`で既存のものを参照する構成にした。
  アクセス制御自体はIAMロールの信頼ポリシーの`Condition`（org/repo/branch指定）で
  行われるため、プロバイダーリソースを自分で所有していなくても安全。

## スコープ外（本移行では対応しない）

- `diff.py`のローリングウィンドウ誤検知バグの修正（別タスク）
- 失敗時のDiscord通知・CloudWatch Alarms
- 駒場庭球場以外の施設・平日の監視・自動予約（v1のスコープ外を継承）
