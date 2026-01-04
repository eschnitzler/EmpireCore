#!/usr/bin/env python3
"""
Movement Tracking Example

This example demonstrates how to:
1. Track all army movements (incoming, outgoing, returning)
2. Listen for movement events
3. Get alerts for incoming attacks
4. Monitor movements continuously
"""

import asyncio
import logging
import sys

sys.path.insert(0, "../src")

from empire_core import (
    EmpireClient,
    EmpireConfig,
    IncomingAttackEvent,
    MovementArrivedEvent,
    MovementHelper,
    # Events
    MovementStartedEvent,
    MovementType,
    ReturnArrivalEvent,
    accounts,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MovementTracker")


async def main():
    # Setup
    account = accounts.get_default()
    if not account:
        logger.error("No account found in accounts.json")
        return

    client = account.get_client()

    # Register event handlers
    @client.event
    async def on_movement_started(event: MovementStartedEvent):
        """Called when a new movement is detected."""
        direction = "incoming" if event.is_incoming else "outgoing"
        logger.info(
            f"New {direction} {event.movement_type_name} detected! ID: {event.movement_id}, Units: {event.unit_count}"
        )

    @client.event
    async def on_movement_arrived(event: MovementArrivedEvent):
        """Called when a movement arrives at its destination."""
        logger.info(
            f"Movement {event.movement_id} ({event.movement_type_name}) has arrived! Target: {event.target_area_id}"
        )

    @client.event
    async def on_incoming_attack(event: IncomingAttackEvent):
        """Called specifically for incoming attacks - HIGH PRIORITY!"""
        logger.warning(
            f"!!! INCOMING ATTACK !!!\n"
            f"  Movement ID: {event.movement_id}\n"
            f"  Attacker: {event.attacker_name or 'Unknown'} (ID: {event.attacker_id})\n"
            f"  Target Castle: {event.target_area_id}\n"
            f"  Time Remaining: {event.time_remaining}s\n"
            f"  Units: {event.unit_count}"
        )

    @client.event
    async def on_return_arrival(event: ReturnArrivalEvent):
        """Called when returning troops arrive with loot."""
        logger.info(
            f"Troops returned to castle {event.castle_id}!\n"
            f"  Loot: W:{event.resources_wood} S:{event.resources_stone} F:{event.resources_food}\n"
            f"  Total: {event.total_loot}"
        )

    try:
        # Login
        logger.info("Logging in...")
        await client.login()
        await asyncio.sleep(2)

        # Get initial state
        await client.get_detailed_castle_info()
        await asyncio.sleep(1)

        player = client.state.local_player
        if not player:
            logger.error("Failed to load player info.")
            return

        logger.info(f"Logged in as {player.name}, Level {player.level}")

        # Get initial movements
        logger.info("Fetching movements...")
        movements = await client.refresh_movements(wait=True)

        # Display current movements
        print("\n" + "=" * 60)
        print("Current Movements")
        print("=" * 60)

        if not movements:
            print("No active movements.")
        else:
            print(MovementHelper.format_movements_table(movements))

            # Show summary by type
            print("\nSummary by Type:")
            counts = MovementHelper.count_movements_by_type(client.movements)
            for type_name, count in counts.items():
                print(f"  {type_name}: {count}")

            # Show incoming attacks specifically
            attacks = client.get_incoming_attacks()
            if attacks:
                print("\n!!! INCOMING ATTACKS !!!")
                for attack in attacks:
                    print(f"  - ID {attack.MID}: {attack.format_time_remaining()} remaining")

            # Show next arrival
            next_arrival = client.get_next_arrival()
            if next_arrival:
                print(f"\nNext arrival: {next_arrival.movement_type_name} in {next_arrival.format_time_remaining()}")

        print("=" * 60 + "\n")

        # Continuously monitor movements
        logger.info("Starting movement monitor... Press Ctrl+C to stop")

        async def on_movements_updated(movements):
            """Callback for movement updates."""
            if movements:
                # Check for imminent attacks
                if MovementHelper.is_attack_imminent(client.movements, threshold_seconds=60):
                    logger.warning("ATTACK IMMINENT! Less than 60 seconds!")

        # Start watching movements (polls every 10 seconds)
        stop_event = asyncio.Event()

        try:
            await client.watch_movements(interval=10.0, callback=on_movements_updated, stop_event=stop_event)
        except KeyboardInterrupt:
            stop_event.set()

    except KeyboardInterrupt:
        logger.info("Stopping...")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.close()


async def demo_movement_queries():
    """
    Demonstrates various movement query methods.
    This is a reference for available queries.
    """
    config = EmpireConfig(username="demo", password="demo")
    client = EmpireClient(config)

    # Assuming client is logged in and has movements...

    # Get all movements
    all_movements = client.get_all_movements()

    # Get by direction
    client.get_incoming_movements()
    client.get_outgoing_movements()
    returning = client.get_returning_movements()

    # Get attacks specifically
    client.get_incoming_attacks()

    # Get movements for specific castle
    castle_id = 12345
    client.get_movements_to_castle(castle_id)
    client.get_movements_from_castle(castle_id)

    # Get specific movement by ID
    client.get_movement(movement_id=67890)

    # Get next arrival
    client.get_next_arrival()

    # Using MovementHelper for more complex queries
    movements_dict = client.movements

    # Get movements by type
    MovementHelper.get_movements_by_type(movements_dict, MovementType.ATTACK)
    MovementHelper.get_movements_by_type(movements_dict, MovementType.TRANSPORT)
    MovementHelper.get_movements_by_type(movements_dict, MovementType.SUPPORT)

    # Get movements arriving within 5 minutes
    MovementHelper.get_movements_arriving_within(movements_dict, seconds=300)

    # Get total units across all movements
    MovementHelper.get_total_units_in_movements(all_movements)

    # Get total resources in transports
    MovementHelper.get_total_resources_in_movements(returning)

    # Sort by arrival time
    MovementHelper.sort_by_arrival(all_movements)

    # Check if attack is imminent
    MovementHelper.is_attack_imminent(movements_dict, threshold_seconds=60)

    # Format for display
    print(client.format_movements_summary())
    print(MovementHelper.format_movements_table(all_movements))


if __name__ == "__main__":
    asyncio.run(main())
