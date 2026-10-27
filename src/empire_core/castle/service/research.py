"""Research."""

from __future__ import annotations

from empire_core.castle.models.research import (
    ResearchInfoRequest,
    ResearchInfoResponse,
    SkipResearchRequest,
    StartResearchRequest,
)
from empire_core.enums import CollectableKind
from empire_core.gamedata import Currency, Research
from empire_core.services.base import ServiceMixin


class ResearchMixin(ServiceMixin):
    # =========================================================================
    # Research
    # =========================================================================

    def get_research(self, *, timeout: float = 5.0) -> ResearchInfoResponse:
        """
        Read your research; the reply also reaches :attr:`research`.

        Client: ``CastleResearchDialog.showLoaded`` (bundle line 16731) sends ``C2SResearchInfoVO``;
        ``REICommand.executeCommand`` (bundle line 126899)
        """
        return self.request(ResearchInfoRequest(), ResearchInfoResponse, timeout=timeout)

    def start_research(self, research: Research | int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Start a research, paying what it costs.

        Missing resources are never paid with rubies: the request sends ``PWR`` 0, as the research
        dialog does. Some researches cost rubies themselves (``ResearchDef.cost_rubies``), and the
        client sends the same request for them; this method refuses those unless ``spend_rubies`` is
        True. Other costs, legendary tokens included, are a normal game currency and are paid. The
        reply's research reaches ``client.state.get_research()``.

        Args:
            research: The research to start
            spend_rubies: Allow a research that costs rubies, on either kind of server
            timeout: Timeout in seconds

        Raises:
            GameDataNotLoadedError: the game data cannot be loaded
            ValueError: The game data has no such research, or it costs rubies and ``spend_rubies`` is False

        Client: ``ResearchInfo.buyResearch`` (bundle line 79704) sends ``C2SResearchStartVO`` whatever the
        costs; ``updateBuyArea`` shows the ruby overlay when ``getFinalCosts`` holds rubies (bundle lines
        79679-79680), and ``AResearchVO.getBaseCosts`` takes the Outer Realms' costs there (bundle
        line 61530); ``RESCommand`` (bundle line 126872)
        """
        game_data = self._require_game_data()
        row = game_data.researches.get(research)
        if row is None:
            raise ValueError(f"the game data has no research {research!r}")
        costs = (*row.costs, *row.outer_realms_costs)
        rubies = max((cost.amount for cost in costs if cost.kind is CollectableKind.RUBIES), default=0)
        if rubies > 0 and not spend_rubies:
            raise ValueError(f"research {research!r} costs {rubies} rubies; pass spend_rubies=True")
        self.execute(StartResearchRequest(research_id=research), timeout=timeout)

    def skip_research(self, minute_skip: Currency | str, *, timeout: float = 5.0) -> None:
        """
        Shorten the running research with a minute skip from your inventory.

        The reply's research reaches ``client.state.get_research()``.

        Args:
            minute_skip: The minute skip to use, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``;
                its key (``"MS1"``) also works, for a skip newer than the generated enum
            timeout: Timeout in seconds

        Raises:
            ValueError: ``minute_skip`` is no minute skip, or the special currencies hold none of it

        Client: ``ResearchMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 79784),
        ``CastleMinuteSkipDialog.showLoaded`` (bundle line 7671), ``MSRCommand`` (bundle line 125825)
        """
        self._require_minute_skip(minute_skip)
        self.execute(SkipResearchRequest(minute_skip=minute_skip), timeout=timeout)
