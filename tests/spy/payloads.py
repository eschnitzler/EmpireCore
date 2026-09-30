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


SPY_OWNER_RECORD: dict[str, Any] = CSM_REPLY["O"][0]
"""The spy owner's record, as csm and bsd send it."""

BSD_NPC_CAMP_REPORT: dict[str, Any] = {
    "B": {
        "DLID": -21,
        "GID": 115,
        "GEM": [],
        "E": [[10, [15.0], "EQ"], [11, [15.0], "EQ"]],
        "AE": [],
        "GASAIDS": [],
        "SIDS": [],
    },
    "S": [[[652, 1]], [[652, 1]], [[652, 1]], [[652, 1]], [], [], []],
    "AS": 0,
    "CID": -1,
    "OI": {"OID": -211, "DUM": True, "RNP": -1},
    "MID": 9001,
    "SA": 100,
    "SR": 26,
    "GC": 0,
    "SC": 2,
    "PID": -211,
    "SID": 1001,
    "RS": -3023358,
    "SO": SPY_OWNER_RECORD,
    "AI": {
        "N": "",
        "DP": -211,
        "AT": 2,
        "K": 0,
        "X": 501,
        "Y": 297,
        "DL": 2,
        "KL": 0,
        "WL": 0,
        "GL": 0,
        "TL": 0,
        "ML": 0,
        "RT": 0,
        "MID": -1,
        "NID": -1,
        "EID": 0,
        "SPC": -1,
    },
}
"""A live bsd report for a robber baron camp spied with CSM_REPLY's mission."""

SSI_NPC_CAMP: dict[str, Any] = {
    "TX": 501.0,
    "TY": 297.0,
    "gaa": {"KID": 0, "uap": {"KID": 0, "NS": -1, "PMS": -1, "PMT": 0}, "OI": [], "AI": [[2, 501, 297, -1, 0, -1, 0]]},
    "AS": 2,
    "APM": 0,
    "TPM": 0,
    "GC": 0,
}
"""A live ssi reply for CSM_REPLY's robber baron camp."""
