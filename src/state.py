import json
import os


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
