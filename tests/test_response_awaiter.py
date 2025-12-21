#!/usr/bin/env python3
"""
Test response awaiter functionality
"""

import asyncio
import logging
import sys

sys.path.insert(0, "src")

from empire_core.exceptions import TimeoutError as EmpireTimeoutError
from empire_core.utils.response_awaiter import ResponseAwaiter

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ResponseAwaiterTest")


async def test_basic_response():
    """Test basic response waiting."""
    logger.info("Test 1: Basic response waiting")

    awaiter = ResponseAwaiter()

    # Create waiter
    waiter_id = awaiter.create_waiter("test_cmd")
    logger.info(f"✅ Created waiter: {waiter_id}")

    # Simulate response in background
    async def send_response():
        await asyncio.sleep(0.5)
        awaiter.set_response("test_cmd", {"status": "success"})
        logger.info("✅ Response sent")

    # Start response task
    asyncio.create_task(send_response())

    # Wait for response
    response = await awaiter.wait_for("test_cmd", timeout=2.0)
    logger.info(f"✅ Received response: {response}")

    assert response == {"status": "success"}
    logger.info("✅ Test 1 PASSED\n")


async def test_timeout():
    """Test timeout behavior."""
    logger.info("Test 2: Timeout handling")

    awaiter = ResponseAwaiter()

    # Create waiter
    waiter_id = awaiter.create_waiter("timeout_cmd")
    logger.info(f"✅ Created waiter: {waiter_id}")

    # Don't send response - should timeout
    try:
        await awaiter.wait_for("timeout_cmd", timeout=1.0)
        logger.error("❌ Should have timed out!")
        raise AssertionError()
    except EmpireTimeoutError as e:
        logger.info(f"✅ Correctly timed out: {e}")
        logger.info("✅ Test 2 PASSED\n")


async def test_multiple_commands():
    """Test multiple concurrent command waiting."""
    logger.info("Test 3: Multiple concurrent commands")

    awaiter = ResponseAwaiter()

    # Create multiple waiters
    awaiter.create_waiter("cmd1")
    awaiter.create_waiter("cmd2")
    awaiter.create_waiter("cmd3")

    logger.info(f"✅ Created 3 waiters, pending: {awaiter.pending_count}")

    # Send responses in random order
    async def send_responses():
        await asyncio.sleep(0.2)
        awaiter.set_response("cmd2", {"id": 2})
        await asyncio.sleep(0.1)
        awaiter.set_response("cmd1", {"id": 1})
        await asyncio.sleep(0.1)
        awaiter.set_response("cmd3", {"id": 3})

    asyncio.create_task(send_responses())

    # Wait for all responses
    r2 = await awaiter.wait_for("cmd2", timeout=2.0)
    r1 = await awaiter.wait_for("cmd1", timeout=2.0)
    r3 = await awaiter.wait_for("cmd3", timeout=2.0)

    logger.info(f"✅ Received cmd1: {r1}")
    logger.info(f"✅ Received cmd2: {r2}")
    logger.info(f"✅ Received cmd3: {r3}")

    assert r1 == {"id": 1}
    assert r2 == {"id": 2}
    assert r3 == {"id": 3}
    logger.info("✅ Test 3 PASSED\n")


async def test_cancel():
    """Test cancellation."""
    logger.info("Test 4: Cancellation")

    awaiter = ResponseAwaiter()

    awaiter.create_waiter("cancel_cmd")
    logger.info(f"✅ Created waiter, pending: {awaiter.pending_count}")

    # Cancel it
    cancelled = awaiter.cancel_command("cancel_cmd")
    logger.info(f"✅ Cancelled {cancelled} waiters, pending: {awaiter.pending_count}")

    assert cancelled == 1
    assert awaiter.pending_count == 0
    logger.info("✅ Test 4 PASSED\n")


async def main():
    logger.info("=" * 70)
    logger.info("RESPONSE AWAITER TESTS")
    logger.info("=" * 70 + "\n")

    try:
        await test_basic_response()
        await test_timeout()
        await test_multiple_commands()
        await test_cancel()

        logger.info("=" * 70)
        logger.info("✅ ALL TESTS PASSED!")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
