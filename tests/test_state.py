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
