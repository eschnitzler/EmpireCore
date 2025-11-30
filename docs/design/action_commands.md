# Action Command Implementation Plan

## Overview
This document outlines the implementation of game action commands (attack, transport, build, etc.)

## Packet Format Research

### Attack Command (`att`)
From Game.bundle.js analysis:
```
%xt%<zone>%att%<sequence>%<payload>%
```

Expected payload structure:
```json
{
  "OID": <origin_castle_id>,
  "TID": <target_area_id>,
  "UN": {<unit_id>: <count>, ...},
  "TT": <movement_type>,
  "KID": <kingdom_id>
}
```

### Transport Command (`tra`)
```
%xt%<zone>%tra%<sequence>%<payload>%
```

Expected payload structure:
```json
{
  "OID": <origin_castle_id>,
  "TID": <target_area_id>,
  "RES": {
    "1": <wood>,
    "2": <stone>,
    "3": <food>
  }
}
```

### Build/Upgrade Command (`bui`)
```
%xt%<zone>%bui%<sequence>%<payload>%
```

Expected payload structure:
```json
{
  "AID": <castle_id>,
  "BID": <building_id>,
  "BTYP": <building_type>
}
```

## Implementation Strategy

1. Create `actions.py` module with action methods
2. Add response handling for action confirmations
3. Implement validation (resources, units, distance)
4. Add error handling for common failures

## Next Steps
- Capture actual attack/transport packets from game
- Implement send_attack() method
- Add unit validation
- Test with real accounts
