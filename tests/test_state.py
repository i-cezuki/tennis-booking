import json
from src.state import load_state, save_state


def test_load_state_missing_file_returns_empty_dict(tmp_path):
    path = tmp_path / "does_not_exist.json"
    assert load_state(str(path)) == {}


def test_load_state_reads_existing_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}))
    assert load_state(str(path)) == {"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}


def test_save_state_writes_readable_json(tmp_path):
    path = tmp_path / "state.json"
    data = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    save_state(str(path), data)
    assert json.loads(path.read_text()) == data


def test_save_state_output_ends_with_newline(tmp_path):
    path = tmp_path / "state.json"
    save_state(str(path), {"a": 1})
    assert path.read_text().endswith("\n")


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
