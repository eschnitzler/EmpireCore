"""
Response awaiter for waiting on server responses to commands.
"""

import asyncio
import logging
import time
from typing import Any, Dict

from empire_core.exceptions import TimeoutError

logger = logging.getLogger(__name__)


class ResponseAwaiter:
    """
    Manages waiting for server responses to commands.

    Usage:
        awaiter = ResponseAwaiter()

        # Start waiting for a response
        response_future = awaiter.create_waiter('att')

        # Send command
        await connection.send(packet)

        # Wait for response
        response = await awaiter.wait_for('att', timeout=5.0)
    """

    def __init__(self):
        self.pending: Dict[str, asyncio.Future] = {}
        self.sequence = 0

    def create_waiter(self, command_id: str) -> str:
        """
        Create a waiter for a specific command response.

        Args:
            command_id: Command to wait for (e.g., 'att', 'tra', 'bui')

        Returns:
            str: Unique waiter ID
        """
        self.sequence += 1
        waiter_id = f"{command_id}_{self.sequence}_{time.time()}"

        future: asyncio.Future = asyncio.Future()
        self.pending[waiter_id] = future

        logger.debug(f"Created waiter: {waiter_id}")
        return waiter_id

    def set_response(self, command_id: str, response: Any) -> bool:
        """
        Set response for waiting command.

        Args:
            command_id: Command ID that responded
            response: Response data

        Returns:
            bool: True if waiter was found and notified
        """
        # Find matching waiter (most recent for this command)
        matching_waiters = [wid for wid in self.pending.keys() if wid.startswith(f"{command_id}_")]

        if not matching_waiters:
            logger.debug(f"No waiter found for response: {command_id}")
            return False

        # Get most recent waiter
        waiter_id = matching_waiters[-1]
        future = self.pending.pop(waiter_id)

        if not future.done():
            future.set_result(response)
            logger.debug(f"Set response for waiter: {waiter_id}")
            return True

        return False

    async def wait_for(self, command_id: str, timeout: float = 5.0) -> Any:
        """
        Wait for response to a specific command.

        Args:
            command_id: Command to wait for
            timeout: Max seconds to wait

        Returns:
            Response data

        Raises:
            TimeoutError: If timeout exceeded
        """
        # Find waiter
        matching_waiters = [wid for wid in self.pending.keys() if wid.startswith(f"{command_id}_")]

        if not matching_waiters:
            raise ValueError(f"No waiter created for command: {command_id}")

        waiter_id = matching_waiters[-1]
        future = self.pending[waiter_id]

        try:
            response = await asyncio.wait_for(future, timeout)
            logger.debug(f"Received response for: {waiter_id}")
            return response
        except asyncio.TimeoutError:
            # Clean up
            self.pending.pop(waiter_id, None)
            logger.warning(f"Timeout waiting for response: {command_id}")
            raise TimeoutError(f"No response received for command: {command_id} (timeout: {timeout}s)")

    def cancel_all(self):
        """Cancel all pending waiters."""
        for waiter_id, future in self.pending.items():
            if not future.done():
                future.cancel()
                logger.debug(f"Cancelled waiter: {waiter_id}")

        self.pending.clear()

    def cancel_command(self, command_id: str) -> int:
        """
        Cancel all waiters for a specific command.

        Args:
            command_id: Command to cancel waiters for

        Returns:
            int: Number of waiters cancelled
        """
        matching = [wid for wid in self.pending.keys() if wid.startswith(f"{command_id}_")]

        count = 0
        for waiter_id in matching:
            future = self.pending.pop(waiter_id)
            if not future.done():
                future.cancel()
                count += 1

        if count > 0:
            logger.debug(f"Cancelled {count} waiters for: {command_id}")

        return count

    @property
    def pending_count(self) -> int:
        """Get number of pending waiters."""
        return len(self.pending)
