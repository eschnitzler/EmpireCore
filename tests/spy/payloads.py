"""Client-shaped spy payloads, derived from a live session with names, ids and positions replaced."""

from __future__ import annotations

from typing import Any

CSM_REPLY: dict[str, Any] = {
    "A": {
        "M": {
            "MID": 5001,
            "PT": 0,
            "TT": 38,
            "D": 0,
            "TID": -211,
            "T": 3,
            "HBW": -1,
            "KID": 0,
            "TA": [2, 501, 297, -1, 0, -1, 0],
            "SID": 1001,
            "OID": 1001,
            "SA": [1, 500, 300, 2001, 1001, 2, 2, 2, 1, 0, "Spy Castle", 0, 0, -1, -1, -1, 0, 0, [], 0],
        },
        "S": {"SC": 2, "ST": 0, "SA": 100, "SR": 26},
    },
    "O": [
        {
            "OID": 1001,
            "DUM": False,
            "N": "Spy Player",
            "E": {
                "BGT": 0,
                "BGC1": 1122867,
                "BGC2": 4473924,
                "SPT": 1,
                "S1": 7,
                "SC1": 7829367,
                "S2": 7,
                "SC2": 11184810,
                "IS": 1,
            },
            "L": 20,
            "LL": 0,
            "H": 0,
            "AVP": 1500,
            "CF": 20,
            "HF": 20,
            "PRE": 0,
            "SUF": -1,
            "TOPX": -1,
            "MP": 4000,
            "R": 0,
            "AID": 301,
            "AR": 1,
            "AN": "Test Alliance",
            "aee": {"ACCA": {"ACLI": 1, "ACCS": [1]}, "ACFB": {}},
            "RPT": 0,
            "AP": [[0, 2001, 500, 300, 1], [0, 2002, 498, 301, 4]],
            "VP": [],
            "SA": 0,
            "VF": 0,
            "PF": 0,
            "RRD": 0,
            "TI": -1,
            "RNP": -1,
        }
    ],
}
