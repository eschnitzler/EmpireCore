# Response Validation Implementation Plan

## Overview
Currently, action commands send packets but don't wait for server confirmation.
This document outlines adding response validation for actions.

## Current Limitation

```python
await client.send_attack(...)  # Sends packet, returns immediately
# No confirmation that attack was accepted!
```

## Proposed Solution

### 1. Response Awaiting System

Add ability to wait for specific response packets:

```python
class ResponseAwaiter:
    """Wait for specific packet responses."""
    
    def __init__(self):
        self.pending = {}  # {response_id: Future}
    
    async def wait_for_response(self, command_id: str, timeout: float = 5.0):
        """Wait for response to specific command."""
        future = asyncio.Future()
        response_id = f"{command_id}_{time.time()}"
        self.pending[response_id] = future
        
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"No response for {command_id}")
```

### 2. Response Packet Handlers

Add handlers for action response packets:

- `att` command → expect `att` response with success/failure
- `tra` command → expect `tra` response
- `bui` command → expect `bui` response
- `rcu` command → expect `rcu` response

### 3. Enhanced Action Methods

```python
async def send_attack(self, ..., wait_for_response=True):
    # Send packet
    await self.connection.send(packet)
    
    if wait_for_response:
        # Wait for confirmation
        response = await self.response_awaiter.wait_for('att')
        return self._parse_attack_response(response)
    
    return True
```

## Expected Response Formats

### Attack Response
```json
{
  "success": true,
  "MID": <movement_id>,
  "ETA": <arrival_time>
}
```

### Transport Response
```json
{
  "success": true,
  "MID": <movement_id>
}
```

### Building Response
```json
{
  "success": true,
  "AID": <castle_id>,
  "BID": <building_id>,
  "level": <new_level>,
  "finish_time": <timestamp>
}
```

## Implementation Steps

1. Create `response_awaiter.py` module
2. Integrate with EmpireClient
3. Update action methods with wait_for_response parameter
4. Add response parsers
5. Update documentation

## Benefits

- Verify actions succeeded
- Get confirmation data (movement IDs, finish times)
- Better error handling
- Reliable automation

## Testing Strategy

1. Test with valid actions
2. Test with invalid actions (insufficient resources)
3. Test timeout scenarios
4. Test concurrent actions

