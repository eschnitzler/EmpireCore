import asyncio
import logging
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.events.base import PacketEvent
from empire_core.protocol.packet import Packet

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("EventTest")


async def test_events():
    config = EmpireConfig()  # Use defaults
    client = EmpireClient(config)

    received_events = []

    @client.event
    async def on_packet(event: PacketEvent):
        logger.info(f"Handler received: {event.command_id}")
        received_events.append(event)

    # Simulate packet arrival
    packet = Packet(raw_data="mock", is_xml=False, command_id="test_cmd", payload={"foo": "bar"})

    logger.info("Injecting packet...")
    await client._on_packet(packet)

    # Allow async tasks to run
    await asyncio.sleep(0.1)

    if len(received_events) == 1:
        logger.info("TEST PASSED: Event received.")
        assert received_events[0].command_id == "test_cmd"
        assert received_events[0].payload == {"foo": "bar"}
    else:
        logger.error(f"TEST FAILED: Expected 1 event, got {len(received_events)}")


if __name__ == "__main__":
    asyncio.run(test_events())
