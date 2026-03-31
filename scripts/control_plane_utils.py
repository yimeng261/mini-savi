from typing import Dict, Iterable, List, Tuple


def compute_link_state_updates(
    isls_origin: Dict[int, Dict[int, object]],
    isl_delays: Dict[int, Dict[int, float]],
    sats_per_plane: int,
    link_states: Dict[Tuple[int, int], str],
) -> Tuple[List[Tuple[int, int, str]], Dict[Tuple[int, int], str]]:
    updates: List[Tuple[int, int, str]] = []
    next_states = dict(link_states)

    if sats_per_plane <= 0:
        return updates, next_states

    for i, neighbors in isls_origin.items():
        for j in neighbors:
            if not ((i + sats_per_plane == j) or (i - sats_per_plane == j)):
                continue

            delay = isl_delays.get(i, {}).get(j, 0)
            new_state = "up" if delay != 0 else "down"
            link_key = tuple(sorted((i, j)))
            if next_states.get(link_key) == new_state:
                continue

            next_states[link_key] = new_state
            updates.append((i, j, new_state))

    return updates, next_states
