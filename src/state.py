import json
import os
import boto3


def load_state(path: str) -> dict:
    """Return the parsed JSON at `path`, or {} if the file does not exist."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path: str, data: dict) -> None:
    """Write `data` to `path` as sorted, indented JSON with a trailing newline."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


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
