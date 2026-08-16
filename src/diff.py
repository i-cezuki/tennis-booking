def find_new_openings(old_state: dict, new_state: dict) -> list[dict]:
    """Return cells that are '○' in new_state but were not '○' in old_state.

    '－' (not applicable) cells never produce an opening, regardless of
    what they transitioned from or to.
    """
    openings = []
    for date_str, courts in new_state.items():
        for court, slots in courts.items():
            for slot, symbol in slots.items():
                if symbol != "○":
                    continue
                old_symbol = (
                    old_state.get(date_str, {}).get(court, {}).get(slot)
                )
                # '－' cells never produce an opening
                if old_symbol == "－":
                    continue
                if old_symbol != "○":
                    openings.append({"date": date_str, "court": court, "slot": slot})
    return openings
