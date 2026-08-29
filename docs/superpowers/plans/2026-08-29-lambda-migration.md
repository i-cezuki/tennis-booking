# 駒場庭球場 空き監視 v2: Lambda移行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GitHub Actionsの`schedule`トリガー（不安定・数時間単位に間延びする）を、AWS Lambda + EventBridge Schedulerに置き換え、5分間隔の正確な実行を実質無料コストで実現する。

**Architecture:** 既存の`src/scraper.py`・`src/diff.py`・`src/notify.py`は無変更。`src/state.py`にS3バックエンドを追加し、`src/main.py`にLambdaハンドラを追加する。Playwright+ChromiumをコンテナイメージとしてビルドしECRへpush、Lambda(package_type=Image)として実行する。トリガーはEventBridge Scheduler(`rate(5 minutes)`)。デプロイはmainへのpushをトリガーとするGitHub Actions(OIDCフェデレーション)。インフラはTerraformで管理。

**Tech Stack:** Python 3.12, Playwright 1.47.0, boto3, Terraform >= 1.5, Docker, AWS Lambda(Image), EventBridge Scheduler, S3, SSM Parameter Store, ECR, GitHub Actions(OIDC)

**Spec:** [docs/superpowers/specs/2026-08-29-lambda-migration-design.md](../specs/2026-08-29-lambda-migration-design.md)

## Global Constraints

- 実行間隔は5分固定（`rate(5 minutes)`）。Lambda無料枠（月40万GB秒）を超えないための制約であり、1分間隔にしない
- Secrets Managerは使わない（月額課金が発生するため）。シークレットは全てSSM Parameter Store(SecureString、無料)に保存する
- IaCツールはTerraform。`infra/terraform/` 配下に置く
- GitHub Actionsからaws認証する際は長期アクセスキーをGitHub Secretsに置かず、OIDCフェデレーションを使う
- `src/scraper.py`・`src/diff.py`・`src/notify.py` は変更しない
- Playwrightのバージョンは`requirements.txt`の`playwright==1.47.0`に固定し、Dockerベースイメージのタグ(`v1.47.0-jammy`)をこれに一致させる
- AWSリージョンは `ap-northeast-1`(東京)をデフォルトとする
- Terraformのstateはローカルファイルのみ(リモートbackendは使わない)。`infra/terraform/terraform.tfstate*` と `.terraform/` は`.gitignore`に追加し、絶対にコミットしない(Discord Webhook URLの値が平文で入るため)

---

## Task 1: S3バックエンドのstate読み書き

**Files:**
- Modify: `src/state.py`
- Modify: `requirements.txt`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: なし(このタスクが最初)
- Produces: `load_state_s3(bucket: str, key: str) -> dict`, `save_state_s3(bucket: str, key: str, data: dict) -> None`（Task 2の`src/main.py`が使う）

- [ ] **Step 1: `requirements.txt`にboto3とmotoを追加**

```
playwright==1.47.0
requests==2.32.3
pytest==8.3.3
boto3==1.34.162
moto==5.0.13
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_state.py` の末尾に追記:

```python
import boto3
from moto import mock_aws
from src.state import load_state_s3, save_state_s3


@mock_aws
def test_load_state_s3_missing_key_returns_empty_dict():
    s3 = boto3.client("s3", region_name="ap-northeast-1")
    s3.create_bucket(
        Bucket="test-bucket",
        CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
    )

    assert load_state_s3("test-bucket", "state.json") == {}


@mock_aws
def test_save_state_s3_then_load_state_s3_round_trips():
    s3 = boto3.client("s3", region_name="ap-northeast-1")
    s3.create_bucket(
        Bucket="test-bucket",
        CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
    )
    data = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}

    save_state_s3("test-bucket", "state.json", data)

    assert load_state_s3("test-bucket", "state.json") == data


@mock_aws
def test_save_state_s3_output_is_sorted_indented_json_with_trailing_newline():
    s3 = boto3.client("s3", region_name="ap-northeast-1")
    s3.create_bucket(
        Bucket="test-bucket",
        CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
    )

    save_state_s3("test-bucket", "state.json", {"b": 1, "a": 2})

    body = s3.get_object(Bucket="test-bucket", Key="state.json")["Body"].read().decode("utf-8")
    assert body == '{\n  "a": 2,\n  "b": 1\n}\n'
```

- [ ] **Step 3: テストを実行して失敗を確認**

Run: `./venv/bin/python -m pytest tests/test_state.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_state_s3'`

- [ ] **Step 4: `src/state.py`に実装を追加**

`src/state.py` の末尾に追記(先頭の`import json`/`import os`はそのまま、`import boto3`を追加):

```python
import boto3


def load_state_s3(bucket: str, key: str) -> dict:
    """Return the parsed JSON at s3://bucket/key, or {} if the key does not exist."""
    s3 = boto3.client("s3")
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except s3.exceptions.NoSuchKey:
        return {}
    return json.loads(response["Body"].read())


def save_state_s3(bucket: str, key: str, data: dict) -> None:
    """Write `data` to s3://bucket/key as sorted, indented JSON with a trailing newline."""
    s3 = boto3.client("s3")
    body = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"))
```

- [ ] **Step 5: 依存関係をインストールしてテストを実行し、成功を確認**

Run:
```bash
./venv/bin/python -m pip install boto3==1.34.162 moto==5.0.13
./venv/bin/python -m pytest tests/test_state.py -v
```
Expected: PASS (7 tests: 既存4件 + 新規3件)

- [ ] **Step 6: コミット**

```bash
git add src/state.py tests/test_state.py requirements.txt
git commit -m "feat: add S3-backed state load/save for Lambda deployment"
```

---

## Task 2: main.pyにLambdaハンドラとバックエンド切替を追加

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `load_state_s3`, `save_state_s3`(Task 1で作成)
- Produces: `lambda_handler(event, context) -> dict`(Task 3のDockerfileの`CMD`が参照する: `src.main.lambda_handler`)。環境変数`STATE_BACKEND=s3|file`(未設定time="file")、`STATE_BUCKET`、`STATE_KEY`(デフォルト`"state.json"`)、`DISCORD_WEBHOOK_SSM_PARAM`(設定されていればSSMから、無ければ`DISCORD_WEBHOOK_URL`から直接webhook URLを読む)

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_main.py` の末尾に追記:

```python
def test_main_uses_s3_state_backend_when_configured(monkeypatch):
    import boto3
    from moto import mock_aws

    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket="test-bucket",
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        s3.put_object(
            Bucket="test-bucket",
            Key="state.json",
            Body=json.dumps({"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}).encode(),
        )

        monkeypatch.setenv("STATE_BACKEND", "s3")
        monkeypatch.setenv("STATE_BUCKET", "test-bucket")
        monkeypatch.setenv("STATE_KEY", "state.json")
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
        monkeypatch.setattr(
            main_module, "weekend_dates_in_range",
            lambda start, num_days: [date(2026, 8, 22)],
        )
        monkeypatch.setattr(
            main_module, "fetch_availability",
            lambda dates: {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}},
        )
        sent = {}
        monkeypatch.setattr(
            main_module, "send_discord_notification",
            lambda url, msg: sent.update(url=url, msg=msg),
        )

        main_module.main()

        assert "A面" in sent["msg"]
        stored = json.loads(
            s3.get_object(Bucket="test-bucket", Key="state.json")["Body"].read()
        )
        assert stored == {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}


def test_main_resolves_webhook_url_from_ssm_when_param_set(tmp_path, monkeypatch):
    import boto3
    from moto import mock_aws

    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
        ssm = boto3.client("ssm", region_name="ap-northeast-1")
        ssm.put_parameter(
            Name="/watcher/discord_webhook_url",
            Value="https://discord.example/from-ssm",
            Type="SecureString",
        )

        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}))
        monkeypatch.setenv("STATE_PATH", str(state_path))
        monkeypatch.setenv("DISCORD_WEBHOOK_SSM_PARAM", "/watcher/discord_webhook_url")
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.setattr(
            main_module, "weekend_dates_in_range",
            lambda start, num_days: [date(2026, 8, 22)],
        )
        monkeypatch.setattr(
            main_module, "fetch_availability",
            lambda dates: {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}},
        )
        sent = {}
        monkeypatch.setattr(
            main_module, "send_discord_notification",
            lambda url, msg: sent.update(url=url, msg=msg),
        )

        main_module.main()

        assert sent["url"] == "https://discord.example/from-ssm"


def test_lambda_handler_calls_main_and_returns_status_ok(monkeypatch):
    called = []
    monkeypatch.setattr(main_module, "main", lambda: called.append(True))

    result = main_module.lambda_handler({}, None)

    assert called == [True]
    assert result == {"statusCode": 200}


def test_main_uploads_failure_screenshot_to_s3_when_scrape_raises(tmp_path, monkeypatch):
    import boto3
    from moto import mock_aws

    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket="test-bucket",
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        monkeypatch.chdir(tmp_path)
        (tmp_path / "failure.png").write_bytes(b"fake-png-bytes")

        monkeypatch.setenv("STATE_BACKEND", "s3")
        monkeypatch.setenv("STATE_BUCKET", "test-bucket")
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
        monkeypatch.setattr(
            main_module, "weekend_dates_in_range",
            lambda start, num_days: [date(2026, 8, 22)],
        )

        def raise_scrape_error(dates):
            raise RuntimeError("scrape failed")

        monkeypatch.setattr(main_module, "fetch_availability", raise_scrape_error)

        try:
            main_module.main()
            raised = False
        except RuntimeError:
            raised = True

        assert raised
        uploaded = s3.get_object(Bucket="test-bucket", Key="failures/failure.png")["Body"].read()
        assert uploaded == b"fake-png-bytes"


def test_main_does_not_upload_when_no_failure_screenshot_exists(tmp_path, monkeypatch):
    import boto3
    from moto import mock_aws

    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket="test-bucket",
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        monkeypatch.chdir(tmp_path)

        monkeypatch.setenv("STATE_BACKEND", "s3")
        monkeypatch.setenv("STATE_BUCKET", "test-bucket")
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
        monkeypatch.setattr(
            main_module, "weekend_dates_in_range",
            lambda start, num_days: [date(2026, 8, 22)],
        )
        monkeypatch.setattr(
            main_module, "fetch_availability",
            lambda dates: (_ for _ in ()).throw(RuntimeError("scrape failed")),
        )

        try:
            main_module.main()
        except RuntimeError:
            pass

        listed = s3.list_objects_v2(Bucket="test-bucket", Prefix="failures/")
        assert listed.get("KeyCount", 0) == 0
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `./venv/bin/python -m pytest tests/test_main.py -v`
Expected: FAIL — `test_main_uses_s3_state_backend_when_configured`はKeyError(`STATE_BUCKET`が既存コードで参照されず、file backendとして`STATE_PATH`未設定のまま`state.json`を相対パスで開こうとして失敗)、`test_lambda_handler_...`は`AttributeError: module has no attribute 'lambda_handler'`、`test_main_uploads_failure_screenshot_to_s3_when_scrape_raises`は`RuntimeError`は起きるがfailures/配下にオブジェクトが無くS3の`get_object`が`NoSuchKey`で失敗

- [ ] **Step 3: `src/main.py`を書き換え**

```python
import os
from datetime import date

import boto3

from src.dates import weekend_dates_in_range
from src.state import load_state, save_state, load_state_s3, save_state_s3
from src.diff import find_new_openings
from src.notify import build_message, send_discord_notification
from src.scraper import fetch_availability


def _load_state() -> dict:
    if os.environ.get("STATE_BACKEND") == "s3":
        return load_state_s3(os.environ["STATE_BUCKET"], os.environ.get("STATE_KEY", "state.json"))
    return load_state(os.environ.get("STATE_PATH", "state.json"))


def _save_state(data: dict) -> None:
    if os.environ.get("STATE_BACKEND") == "s3":
        save_state_s3(os.environ["STATE_BUCKET"], os.environ.get("STATE_KEY", "state.json"), data)
    else:
        save_state(os.environ.get("STATE_PATH", "state.json"), data)


def _get_webhook_url() -> str:
    param_name = os.environ.get("DISCORD_WEBHOOK_SSM_PARAM")
    if param_name:
        ssm = boto3.client("ssm")
        return ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]
    return os.environ["DISCORD_WEBHOOK_URL"]


def _upload_failure_screenshot() -> None:
    """Best-effort upload of scraper.py's failure.png (written to cwd) to S3.

    scraper.py writes a relative "failure.png" on scrape failure and is not
    modified by this migration. In the Lambda container the working
    directory is /tmp (writable), so this just needs to pick that file up
    and ship it somewhere retrievable after the invocation ends.
    """
    bucket = os.environ.get("STATE_BUCKET")
    if not bucket or not os.path.exists("failure.png"):
        return
    s3 = boto3.client("s3")
    s3.upload_file("failure.png", bucket, "failures/failure.png")
    print("[info] uploaded failure.png to s3://" + bucket + "/failures/failure.png")


def main() -> None:
    webhook_url = _get_webhook_url()
    old_state = _load_state()

    target_dates = weekend_dates_in_range(date.today(), 14)
    try:
        new_state = fetch_availability(target_dates)
    except Exception:
        _upload_failure_screenshot()
        raise

    total_slots = sum(len(slots) for courts in new_state.values() for slots in courts.values())
    open_slots = sum(
        1
        for courts in new_state.values()
        for slots in courts.values()
        for symbol in slots.values()
        if symbol == "○"
    )
    print(
        f"[info] fetched {len(new_state)} dates, {total_slots} slots, "
        f"{open_slots} open"
    )

    openings = find_new_openings(old_state, new_state)
    print(f"[info] {len(openings)} new opening(s)")
    if openings:
        message = build_message(openings)
        send_discord_notification(webhook_url, message)

    print(f"[info] state {'changed' if new_state != old_state else 'unchanged'}")

    _save_state(new_state)


def lambda_handler(event, context):
    main()
    return {"statusCode": 200}


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `./venv/bin/python -m pytest tests/test_main.py -v`
Expected: PASS (全件)

- [ ] **Step 5: 全テストスイートを実行(playwright抜き)して既存分含め回帰がないことを確認**

Run: `./venv/bin/python -m pytest tests/ -q --ignore=tests/test_scraper_extract.py`
Expected: PASS (全件)

- [ ] **Step 6: コミット**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: add lambda_handler and S3/SSM-backed config for Lambda deployment"
```

---

## Task 3: Dockerfile とローカルRIEスモークテスト

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `src.main.lambda_handler`(Task 2)
- Produces: ローカルでbuildしたイメージ`meguro-tennis-watcher:local`(Task 4のGitHub Actionsが同じDockerfileでECR向けにビルドする)

- [ ] **Step 1: `.dockerignore`を作成**

```
venv/
.pytest_cache/
tests/
docs/
.git/
.github/
infra/
*.md
state.json
```

- [ ] **Step 2: `Dockerfile`を作成**

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /var/task

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt awslambdaric

COPY src ./src

# scraper.py writes a relative "failure.png" on scrape failure and is not
# modified by this migration. /var/task is read-only at runtime, so the
# working directory is switched to /tmp (the only writable path in Lambda)
# while keeping the code importable via PYTHONPATH.
ENV PYTHONPATH=/var/task
WORKDIR /tmp

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["src.main.lambda_handler"]
```

- [ ] **Step 3: イメージをローカルビルド**

Run: `docker build -t meguro-tennis-watcher:local .`
Expected: ビルド成功。`mcr.microsoft.com/playwright/python:v1.47.0-jammy`にはChromiumが同梱済みなので`playwright install`は不要

- [ ] **Step 4: Lambda Runtime Interface Emulator (RIE) を取得**

Run:
```bash
mkdir -p ~/.aws-lambda-rie
curl -Lo ~/.aws-lambda-rie/aws-lambda-rie \
  https://github.com/aws/aws-lambda-runtime-interface-emulator/releases/latest/download/aws-lambda-rie
chmod +x ~/.aws-lambda-rie/aws-lambda-rie
```
Expected: `~/.aws-lambda-rie/aws-lambda-rie` バイナリが実行可能な状態で存在する

- [ ] **Step 5: RIE経由でコンテナを起動しinvokeする**

Run:
```bash
docker run -d --name watcher-rie-test \
  -v ~/.aws-lambda-rie:/aws-lambda \
  --entrypoint /aws-lambda/aws-lambda-rie \
  -p 9000:8080 \
  -e STATE_PATH=/tmp/state.json \
  -e DISCORD_WEBHOOK_URL="$DISCORD_WEBHOOK_URL" \
  meguro-tennis-watcher:local \
  /usr/local/bin/python -m awslambdaric src.main.lambda_handler

sleep 2
curl -s -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{}'
echo
docker logs watcher-rie-test
docker rm -f watcher-rie-test
```

`$DISCORD_WEBHOOK_URL`には実際に使っているwebhook URLを指定する(これは実際のサイトに対して本番と同じスクレイピングを1回実行する。既に運用中の`workflow_dispatch`手動実行と同じ性質のテストで、新規空きがあれば実際に通知が届く)。

Expected: curlの応答が`{"statusCode": 200}`。`docker logs`に`[info] fetched N dates, ...`などの診断ログが出力されている

- [ ] **Step 6: コミット**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add Dockerfile for Lambda container image"
```

---

## Task 4: Terraformベースインフラ(ECR, S3, SSM, IAMロール)

**Files:**
- Create: `infra/terraform/providers.tf`
- Create: `infra/terraform/variables.tf`
- Create: `infra/terraform/ecr.tf`
- Create: `infra/terraform/state_store.tf`
- Create: `infra/terraform/iam.tf`
- Create: `infra/terraform/outputs.tf`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: なし
- Produces: `aws_ecr_repository.watcher`(Task 5がpush先として使う)、`aws_iam_role.github_deploy`(Task 5がOIDCで引き受ける)、`aws_s3_bucket.state`・`aws_ssm_parameter.discord_webhook_url`・`aws_iam_role.lambda_exec`(Task 6のLambda関数が使う)

- [ ] **Step 1: `.gitignore`にTerraformの生成物を追加**

`.gitignore` に追記:
```
infra/terraform/.terraform/
infra/terraform/terraform.tfstate
infra/terraform/terraform.tfstate.backup
infra/terraform/*.tfplan
```

- [ ] **Step 2: `infra/terraform/providers.tf`を作成**

```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
```

- [ ] **Step 3: `infra/terraform/variables.tf`を作成**

```hcl
variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-northeast-1"
}

variable "project_name" {
  description = "Prefix used for naming all resources"
  type        = string
  default     = "meguro-tennis-watcher"
}

variable "github_repo" {
  description = "GitHub repo allowed to assume the deploy role, as owner/repo"
  type        = string
  default     = "i-cezuki/tennis-booking"
}

variable "discord_webhook_url" {
  description = "Discord webhook URL, stored in SSM as SecureString. Set via TF_VAR_discord_webhook_url env var, never commit it."
  type        = string
  sensitive   = true
}

variable "schedule_rate_minutes" {
  description = "How often EventBridge Scheduler invokes the watcher Lambda"
  type        = number
  default     = 5
}
```

- [ ] **Step 4: `infra/terraform/ecr.tf`を作成**

```hcl
resource "aws_ecr_repository" "watcher" {
  name                 = var.project_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "watcher" {
  repository = aws_ecr_repository.watcher.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the 5 most recent images to limit storage cost"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}
```

- [ ] **Step 5: `infra/terraform/state_store.tf`を作成**

```hcl
resource "aws_s3_bucket" "state" {
  bucket = "${var.project_name}-state-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_ssm_parameter" "discord_webhook_url" {
  name  = "/${var.project_name}/discord_webhook_url"
  type  = "SecureString"
  value = var.discord_webhook_url
}
```

- [ ] **Step 6: `infra/terraform/iam.tf`を作成**

```hcl
# --- Lambda execution role ---

resource "aws_iam_role" "lambda_exec" {
  name = "${var.project_name}-lambda-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda_exec" {
  name = "${var.project_name}-lambda-exec"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = [
          "${aws_s3_bucket.state.arn}/state.json",
          "${aws_s3_bucket.state.arn}/failures/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = aws_ssm_parameter.discord_webhook_url.arn
      }
    ]
  })
}

# --- GitHub Actions OIDC deploy role ---

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "github_deploy" {
  name = "${var.project_name}-github-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_deploy" {
  name = "${var.project_name}-github-deploy"
  role = aws_iam_role.github_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = aws_ecr_repository.watcher.arn
      },
      {
        Effect   = "Allow"
        Action   = ["lambda:UpdateFunctionCode"]
        Resource = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}"
      }
    ]
  })
}
```

- [ ] **Step 7: `infra/terraform/outputs.tf`を作成**

```hcl
output "ecr_repository_url" {
  value = aws_ecr_repository.watcher.repository_url
}

output "state_bucket_name" {
  value = aws_s3_bucket.state.bucket
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}

output "aws_account_id" {
  value = data.aws_caller_identity.current.account_id
}
```

- [ ] **Step 8: AWS再認証**

このマシンのAWSセッションは期限切れになっている。以下を実行して再認証する(組織のSSO方式に従う。`aws sts get-caller-identity`が成功すればOK):

Run: `aws sts get-caller-identity`
Expected: セッションが切れていれば案内に従い再認証(例: `aws sso login` 等)してから再実行し、Account/Arnが返ること

- [ ] **Step 9: Terraform初期化・apply**

Run:
```bash
cd infra/terraform
terraform init
export TF_VAR_discord_webhook_url='<実際に使っているDiscord Webhook URL>'
terraform plan
terraform apply
```
Expected: `terraform apply`が承認プロンプトで`yes`入力後、`aws_ecr_repository.watcher`・`aws_s3_bucket.state`・`aws_ssm_parameter.discord_webhook_url`・`aws_iam_role.lambda_exec`・`aws_iam_role.github_deploy`・`aws_iam_openid_connect_provider.github`が作成される。末尾に`outputs`が表示される(`ecr_repository_url`, `state_bucket_name`, `github_deploy_role_arn`, `aws_account_id`)。この4つの値を控えておく(以降のタスクで使う)

- [ ] **Step 10: コミット**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add infra/terraform/ .gitignore
git commit -m "feat: add Terraform for ECR, S3 state bucket, SSM parameter, IAM roles"
```

---

## Task 5: GitHub Actionsデプロイワークフローと初回イメージpush

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: `Dockerfile`(Task 3), `aws_ecr_repository.watcher`・`aws_iam_role.github_deploy`(Task 4)
- Produces: ECR上の`<repo>:latest`イメージ(Task 6のLambda関数がこれを参照する)

- [ ] **Step 1: GitHub repository variableを設定**

Run(Task 4のoutputで得た`aws_account_id`を使う):
```bash
gh variable set AWS_ACCOUNT_ID --repo i-cezuki/tennis-booking --body '<aws_account_id の値>'
```
Expected: `Updated variable AWS_ACCOUNT_ID`

- [ ] **Step 2: `.github/workflows/deploy.yml`を作成**

```yaml
name: Build and deploy watcher Lambda

on:
  push:
    branches: [main]
    paths:
      - "src/**"
      - "Dockerfile"
      - "requirements.txt"
      - ".github/workflows/deploy.yml"

permissions:
  id-token: write
  contents: read

env:
  AWS_REGION: ap-northeast-1
  ECR_REPOSITORY: meguro-tennis-watcher
  LAMBDA_FUNCTION_NAME: meguro-tennis-watcher

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/meguro-tennis-watcher-github-deploy
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push image
        env:
          ECR_REGISTRY: ${{ steps.ecr-login.outputs.registry }}
        run: |
          docker build -t "$ECR_REGISTRY/$ECR_REPOSITORY:latest" .
          docker push "$ECR_REGISTRY/$ECR_REPOSITORY:latest"

      - name: Update Lambda function code
        env:
          ECR_REGISTRY: ${{ steps.ecr-login.outputs.registry }}
        run: |
          aws lambda update-function-code \
            --function-name "$LAMBDA_FUNCTION_NAME" \
            --image-uri "$ECR_REGISTRY/$ECR_REPOSITORY:latest"
```

- [ ] **Step 3: コミットしてpush**

```bash
git add .github/workflows/deploy.yml
git commit -m "feat: add GitHub Actions workflow to build/push image and deploy to Lambda"
git pull origin main --rebase
git push origin main
```

- [ ] **Step 4: ワークフローの実行結果を確認**

Run: `gh run watch --repo i-cezuki/tennis-booking $(gh run list --repo i-cezuki/tennis-booking --workflow deploy.yml --limit 1 --json databaseId -q '.[0].databaseId')`

Expected: `Login to ECR`・`Build and push image`のステップは成功する。`Update Lambda function code`のステップは**この時点ではLambda関数がまだ存在しないため失敗する(想定通り)**。ここで確認したいのは「ECRに`:latest`タグでイメージがpushされたこと」のみ

Run(確認): `aws ecr describe-images --repository-name meguro-tennis-watcher --region ap-northeast-1`
Expected: 1件以上のイメージが返る

---

## Task 6: TerraformでLambda関数とEventBridge Scheduler

**Files:**
- Create: `infra/terraform/lambda.tf`
- Modify: `infra/terraform/outputs.tf`

**Interfaces:**
- Consumes: ECR上の`<repo>:latest`イメージ(Task 5), `aws_iam_role.lambda_exec`・`aws_s3_bucket.state`・`aws_ssm_parameter.discord_webhook_url`(Task 4)
- Produces: `aws_lambda_function.watcher`(Task 7が手動invokeする), `aws_scheduler_schedule.watcher`(DISABLEDで作成、Task 8で有効化してから5分毎にLambdaを起動する)

- [ ] **Step 1: `infra/terraform/lambda.tf`を作成**

```hcl
resource "aws_cloudwatch_log_group" "watcher" {
  name              = "/aws/lambda/${var.project_name}"
  retention_in_days = 30
}

resource "aws_lambda_function" "watcher" {
  function_name = var.project_name
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.watcher.repository_url}:latest"
  timeout       = 60
  memory_size   = 1024

  environment {
    variables = {
      STATE_BACKEND             = "s3"
      STATE_BUCKET               = aws_s3_bucket.state.bucket
      STATE_KEY                  = "state.json"
      DISCORD_WEBHOOK_SSM_PARAM  = aws_ssm_parameter.discord_webhook_url.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.watcher]
}

resource "aws_iam_role" "scheduler_invoke" {
  name = "${var.project_name}-scheduler-invoke"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  name = "${var.project_name}-scheduler-invoke"
  role = aws_iam_role.scheduler_invoke.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.watcher.arn
    }]
  })
}

resource "aws_scheduler_schedule" "watcher" {
  name       = "${var.project_name}-schedule"
  group_name = "default"
  # Created disabled: Task 7 verifies the Lambda via manual `aws lambda
  # invoke` first. Task 8 flips this to ENABLED at the same time the old
  # GitHub Actions cron is removed, so the two triggers never run in
  # parallel and never double-notify Discord for the same opening.
  state = "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(${var.schedule_rate_minutes} minutes)"

  target {
    arn      = aws_lambda_function.watcher.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}
```

- [ ] **Step 2: `infra/terraform/outputs.tf`にLambda関連の出力を追記**

```hcl
output "lambda_function_name" {
  value = aws_lambda_function.watcher.function_name
}

output "schedule_name" {
  value = aws_scheduler_schedule.watcher.name
}
```

- [ ] **Step 3: apply**

Run:
```bash
cd infra/terraform
export TF_VAR_discord_webhook_url='<Task4と同じDiscord Webhook URL>'
terraform plan
terraform apply
```
Expected: `aws_lambda_function.watcher`・`aws_scheduler_schedule.watcher`(state: DISABLEDで作成、Task 8で有効化する)・`aws_iam_role.scheduler_invoke`が作成される。`lambda_function_name`が`meguro-tennis-watcher`として出力される

- [ ] **Step 4: コミット**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add infra/terraform/lambda.tf infra/terraform/outputs.tf
git commit -m "feat: add Lambda function and EventBridge Scheduler (5 min interval)"
```

---

## Task 7: state.json移行とLambda動作確認

**Files:**
- なし(既存の`state.json`をS3へコピーするのみ)

**Interfaces:**
- Consumes: `aws_lambda_function.watcher`(Task 6), `aws_s3_bucket.state`(Task 4)
- Produces: なし(検証タスク)

- [ ] **Step 1: 現在のGitHub上のstate.jsonをS3へ初期投入**

Run:
```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git pull origin main
aws s3 cp state.json s3://<Task4のstate_bucket_nameの値>/state.json
```
Expected: `upload: ./state.json to s3://.../state.json`

- [ ] **Step 2: Lambdaを手動invoke**

Run:
```bash
aws lambda invoke --function-name meguro-tennis-watcher --payload '{}' \
  --cli-binary-format raw-in-base64-out /tmp/lambda-response.json
cat /tmp/lambda-response.json
```
Expected: `{"statusCode": 200}` が返る

- [ ] **Step 3: CloudWatch Logsで診断ログを確認**

Run: `aws logs tail /aws/lambda/meguro-tennis-watcher --since 5m`
Expected: `[info] fetched N dates, M slots, K open` などのログが出力されている。エラーのスタックトレースが無いこと

- [ ] **Step 4: S3のstate.jsonが更新されていることを確認**

Run: `aws s3 cp s3://<state_bucket_name>/state.json - | head -20`
Expected: Step1でuploadした内容と(空き状況に変化がなければ)同じか、変化があれば更新された内容が返る

---

## Task 8: 切替(GitHub Actionsのcron停止)

**Files:**
- Modify: `.github/workflows/watch.yml`

**Interfaces:**
- Consumes: Task 7で動作確認済みのLambda
- Produces: なし(最終切替)

- [ ] **Step 1: `infra/terraform/lambda.tf`のEventBridge Scheduleを有効化**

`aws_scheduler_schedule.watcher`の`state = "DISABLED"`を`state = "ENABLED"`に変更(コメント行も削除):

```hcl
resource "aws_scheduler_schedule" "watcher" {
  name       = "${var.project_name}-schedule"
  group_name = "default"
  state      = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(${var.schedule_rate_minutes} minutes)"
```
(以降の`target`ブロックは変更しない)

- [ ] **Step 2: apply**

Run:
```bash
cd infra/terraform
export TF_VAR_discord_webhook_url='<Task4と同じDiscord Webhook URL>'
terraform apply
```
Expected: `aws_scheduler_schedule.watcher`が更新され、`State`が`ENABLED`になる

- [ ] **Step 3: `watch.yml`から`schedule`トリガーを削除**

`.github/workflows/watch.yml`の`on:`ブロックを次のように変更(`schedule:`ブロックを削除、`workflow_dispatch`は手動デバッグ用に残す):

```yaml
on:
  workflow_dispatch: {}
```

- [ ] **Step 4: EventBridge Scheduleが有効であることを確認**

Run: `aws scheduler get-schedule --name meguro-tennis-watcher-schedule --group-name default`
Expected: `"State": "ENABLED"`

- [ ] **Step 5: コミットしてpush**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add .github/workflows/watch.yml infra/terraform/lambda.tf
git commit -m "chore: enable EventBridge Scheduler and stop GitHub Actions cron trigger"
git pull origin main --rebase
git push origin main
```

- [ ] **Step 6: 10分程度待ち、EventBridge Scheduler経由の実行が記録されていることを確認**

Run: `aws logs tail /aws/lambda/meguro-tennis-watcher --since 15m`
Expected: 5分間隔で複数回`[info]`ログが記録されている(GitHub Actions側の`schedule`実行は今後発生しない)
