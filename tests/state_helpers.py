"""Payload builders shared by the GameState tests."""

import time

from empire_core.state.manager import GameState


def gam_payload(mid: int, movement_type: int = 0, oid: int = 999, tid: int = 1, extra: dict | None = None) -> dict:
    m_data = {
        "MID": mid,
        "T": movement_type,  # 0 = ATTACK
        "PT": 0,
        "TT": 600,
        "D": 0,
        "OID": oid,
        "TID": tid,
        "KID": 0,
        "SID": -1,
    }
    if extra:
        m_data.update(extra)
    return {
        "M": [{"M": m_data}],
        "O": [{"OID": oid, "N": "Attacker", "AN": "EvilAlliance"}],
    }


def push_payload(mid: int, movement_type: int = 0, oid: int = 999, tt: int = 600, direction: int = 0) -> dict:
    """An abr/asr push: one movement wrapper under A, owner records under O."""
    return {
        "O": [],
        "A": {"M": {"MID": mid, "T": movement_type, "PT": 0, "TT": tt, "D": direction, "OID": oid, "TID": 1}},
    }


def arrive(state: GameState, mid: int) -> None:
    """Let a tracked movement's travel time run out, then let state notice."""
    mov = state.movements[mid]
    mov.last_updated = time.time() - (mov.total_time - mov.progress_time) - 1
    state.get_all_movements()


def gcl_payload(castles: list[tuple[int, str]], owner_id: int = 7, kingdom: int = 0, x: int = 10, y: int = 20) -> dict:
    """Build a gcl castle section listing `castles` as owned by `owner_id`."""
    return {
        "C": [
            {
                "KID": kingdom,
                "AI": [{"AI": [0, x, y, area_id, owner_id, 0, 0, 0, 0, 0, name]} for area_id, name in castles],
            }
        ]
    }


def wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False
