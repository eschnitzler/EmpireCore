"""
EmpireCore CLI
"""

import asyncio
import logging

import typer
from empire_core import accounts

# Configure logging for CLI
logging.basicConfig(level=logging.WARNING)  # cleaner output

app = typer.Typer(help="EmpireCore Command Line Interface")


@app.command()
def status():
    """Show configured accounts."""
    all_accounts = accounts.get_all()
    if not all_accounts:
        typer.echo("No accounts found in accounts.json or environment.")
        return

    typer.echo(f"Found {len(all_accounts)} accounts:")
    for acc in all_accounts:
        active = "✅" if acc.active else "❌"
        typer.echo(f"{active} {acc.username} ({acc.world}) [Tags: {', '.join(acc.tags)}]")


@app.command()
def login(username: str = typer.Option(None, help="Username to login with. Defaults to first.")):
    """Test login for an account."""

    async def _run():
        if username:
            acc = accounts.get_by_username(username)
        else:
            acc = accounts.get_default()

        if not acc:
            typer.echo("Account not found.")
            return

        typer.echo(f"Logging in as {acc.username}...")
        client = acc.get_client()

        try:
            await client.login()
            typer.echo("✅ Login successful!")

            # Show quick stats
            player = client.state.local_player
            if player:
                typer.echo(f"   Level: {player.level}")
                typer.echo(f"   Gold: {player.gold:,}")
                typer.echo(f"   Castles: {len(player.castles)}")

        except Exception as e:
            typer.echo(f"❌ Login failed: {e}")
        finally:
            await client.close()

    asyncio.run(_run())


if __name__ == "__main__":
    app()
