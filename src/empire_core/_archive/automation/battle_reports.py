"""
Battle report automation for analyzing combat outcomes.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List

from empire_core.state.report_models import BattleReport, ReportManager

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class BattleReportService:
    """Service for battle report fetching and analysis."""

    def __init__(self, client: "EmpireClient"):
        self.client = client

    @property
    def reports_manager(self) -> ReportManager:
        """Get the report manager from state."""
        return self.client.state.reports

    async def fetch_recent_reports(self, count: int = 10) -> bool:
        """Fetch recent battle reports from server."""
        # Using client method
        return await self.client.get_battle_reports(count)

    async def fetch_report_details(self, report_id: int) -> bool:
        """Fetch detailed data for a specific battle report."""
        # Using client method
        return await self.client.get_battle_report_details(report_id)

    def get_recent_reports(self, count: int = 10) -> List[BattleReport]:
        """Get most recent battle reports."""
        return self.reports_manager.get_recent_reports(count)

    def get_unread_reports(self) -> List[BattleReport]:
        """Get all unread battle reports."""
        return self.reports_manager.get_unread_reports()

    def mark_report_read(self, report_id: int):
        """Mark a battle report as read."""
        self.reports_manager.mark_as_read(report_id)

    def get_report_summary(self, report: BattleReport) -> Dict[str, Any]:
        """Get a summary of a battle report."""
        summary = {
            "report_id": report.report_id,
            "timestamp": report.timestamp,
            "datetime": report.datetime.isoformat(),
            "is_read": report.is_read,
            "report_type": report.report_type,
            "target": {
                "name": report.target_name,
                "x": report.target_x,
                "y": report.target_y,
            },
            "winner": report.winner,
            "loot": report.loot,
        }

        # Add participant info if available
        if report.attacker:
            summary["attacker"] = {
                "player_id": report.attacker.player_id,
                "player_name": report.attacker.player_name,
                "alliance_name": report.attacker.alliance_name,
                "units_before": report.attacker.units_before,
                "units_after": report.attacker.units_after,
                "losses": report.attacker.losses,
            }

        if report.defender:
            summary["defender"] = {
                "player_id": report.defender.player_id,
                "player_name": report.defender.player_name,
                "alliance_name": report.defender.alliance_name,
                "units_before": report.defender.units_before,
                "units_after": report.defender.units_after,
                "losses": report.defender.losses,
            }

        return summary

    def analyze_battle_efficiency(self, report: BattleReport) -> Dict[str, Any]:
        """Analyze the efficiency of a battle."""
        loot_total = sum(report.loot.values())
        analysis = {
            "report_id": report.report_id,
            "victory": report.winner == "attacker",
            "loot_total": loot_total,
            "loot_breakdown": report.loot,
        }

        # Calculate losses if we have participant data
        if report.attacker and report.defender:
            attacker_losses = sum(report.attacker.losses.values())
            defender_losses = sum(report.defender.losses.values())

            analysis.update(
                {
                    "attacker_losses": attacker_losses,
                    "defender_losses": defender_losses,
                    "total_losses": attacker_losses + defender_losses,
                }
            )

            # Calculate efficiency metrics
            if attacker_losses > 0:
                loot_per_loss = loot_total / attacker_losses
                analysis["loot_per_attacker_loss"] = loot_per_loss

                # Simple efficiency rating (higher is better)
                if loot_per_loss > 100:
                    analysis["efficiency"] = "excellent"
                elif loot_per_loss > 50:
                    analysis["efficiency"] = "good"
                elif loot_per_loss > 20:
                    analysis["efficiency"] = "fair"
                else:
                    analysis["efficiency"] = "poor"

        return analysis

    def get_battle_stats(self, reports: List[BattleReport]) -> Dict[str, Any]:
        """Get aggregate statistics from multiple battle reports."""
        if not reports:
            return {"total_battles": 0}

        total_battles = len(reports)
        victories = 0
        defeats = 0
        total_loot = {"wood": 0, "stone": 0, "food": 0}
        total_losses = 0

        for report in reports:
            if report.winner == "attacker":
                victories += 1
            else:
                defeats += 1

            # Sum loot
            for resource, amount in report.loot.items():
                if resource in total_loot:
                    total_loot[resource] += amount

            # Sum losses (if available)
            if report.attacker:
                total_losses += sum(report.attacker.losses.values())

        win_rate = victories / total_battles if total_battles > 0 else 0

        return {
            "total_battles": total_battles,
            "victories": victories,
            "defeats": defeats,
            "total_loot": total_loot,
            "total_losses": total_losses,
            "win_rate": win_rate,
        }

    async def auto_fetch_and_analyze(self, count: int = 10, wait_time: float = 1.0) -> Dict[str, Any]:
        """
        Fetch recent reports and return analysis.

        Args:
            count: Number of reports to fetch
            wait_time: Time to wait for server response

        Returns:
            Dict with stats and analyses
        """
        import asyncio

        # Fetch reports
        await self.fetch_recent_reports(count)
        await asyncio.sleep(wait_time)  # Wait for response

        # Get reports
        reports = self.get_recent_reports(count)

        # Analyze each report
        analyses = [self.analyze_battle_efficiency(report) for report in reports]

        # Get aggregate stats
        stats = self.get_battle_stats(reports)

        return {
            "stats": stats,
            "reports_analyzed": len(analyses),
            "analyses": analyses[:5],  # Return top 5 analyses
        }
