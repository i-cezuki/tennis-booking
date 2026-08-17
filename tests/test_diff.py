from src.diff import find_new_openings


def test_detects_transition_from_x_to_maru():
    old = {"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}
    new = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    assert find_new_openings(old, new) == [
        {"date": "2026-08-22", "court": "A面", "slot": "9:00〜11:00"}
    ]


def test_detects_opening_with_no_prior_record():
    old = {}
    new = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    assert find_new_openings(old, new) == [
        {"date": "2026-08-22", "court": "A面", "slot": "9:00〜11:00"}
    ]


def test_no_change_when_still_x():
    old = {"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}
    new = {"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}
    assert find_new_openings(old, new) == []


def test_no_duplicate_when_already_open():
    old = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    new = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    assert find_new_openings(old, new) == []


def test_ignores_moushikomi_taishougai():
    old = {"2026-08-22": {"A面": {"9:00〜11:00": "－"}}}
    new = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    assert find_new_openings(old, new) == []


def test_handles_multiple_dates_and_courts():
    old = {
        "2026-08-22": {"A面": {"9:00〜11:00": "×"}, "B面": {"9:00〜11:00": "×"}},
        "2026-08-23": {"A面": {"9:00〜11:00": "×"}},
    }
    new = {
        "2026-08-22": {"A面": {"9:00〜11:00": "○"}, "B面": {"9:00〜11:00": "×"}},
        "2026-08-23": {"A面": {"9:00〜11:00": "○"}},
    }
    result = find_new_openings(old, new)
    assert {"date": "2026-08-22", "court": "A面", "slot": "9:00〜11:00"} in result
    assert {"date": "2026-08-23", "court": "A面", "slot": "9:00〜11:00"} in result
    assert len(result) == 2
