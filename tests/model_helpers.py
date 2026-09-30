"""Payload builders shared by the model tests."""


# =============================================================================
# Golden payloads
#
# The dicts below are written in the shape the live server sends, positional
# arrays included. They exist so a format drift shows up as a failing parse
# here rather than as a runtime crash in a consumer.
# =============================================================================


def gdi_location_row(
    location_type: int,
    x: int,
    y: int,
    location_id: int,
    owner_id: int,
    name: str,
    kingdom: int,
    capturer_capital: int = -1,
    capturer_outpost: int = -1,
) -> list:
    """A 20-field gdi/gcl location row as the live server sends it.

    Index map (see PlayerCastle): 0 type, 1 x, 2 y, 3 location id, 4 owner
    id, 10 name, 14 occupier of a capital or metropolis, 15 occupier of a
    castle, outpost or kingdom castle, 16 kingdom.
    """
    return [
        location_type,
        x,
        y,
        location_id,
        owner_id,
        1,
        1,
        1,
        0,
        0,
        name,
        0,
        0,
        -1,
        capturer_capital,
        capturer_outpost,
        kingdom,
        301,
        [],
        0,
    ]
