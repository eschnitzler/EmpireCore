"""
Unit production and army management automation.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from empire_core.state.models import Castle

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class UnitType(IntEnum):
    """Common unit type IDs."""

    VETERANSABERSLASHER = 5
    VETERANSLINGSHOTMARKSMAN = 6
    OGERMACE_2 = 7
    OGERCROSSBOW_2 = 8
    ELITERANKREWARDMELEE = 9
    ELITERANKREWARDRANGE = 10
    ELITEFLAMETHROWER = 11
    ELITEARROWTHROWER = 12
    AUXILIARYMELEE = 13
    AUXILIARYRANGE = 14
    BERIMONDREWARDMELEE = 18
    BERIMONDREWARDRANGE = 19
    ELITEBERIMONDREWARDMELEE = 20
    ELITEBERIMONDREWARDRANGE = 21
    VALKYRIEMILEE = 22
    VALKYRIERANGE = 23
    SAMURAIATTACKERMELEE = 34
    SAMURAIATTACKERRANGE = 35
    SAMURAIDEFENDERMELEE = 36
    SAMURAIDEFENDERRANGE = 37
    SAMURAIDEFENDERMELEENPC = 38
    SAMURAIDEFENDERRANGENPC = 39
    RENEGADESKELETONSPEERMAN = 40
    RENEGADESKELETONBOWMAN = 41
    HALLOWEENMELEE = 42
    HALLOWEENRANGE = 43
    WINTERATTACKERMELEE = 48
    ELITETINOSWOLVES = 49
    WINTERATTACKERRANGE = 50
    ELITEWINTERATTACKERMELEE = 51
    ELITEWINTERATTACKERRANGE = 52
    RANKREWARDMELEEUSA = 58
    RANKREWARDRANGEUSA = 59
    OGERMACE = 68
    OGERCROSSBOW = 74
    ELITEKINGSMACE = 75
    ELITEKINGSCROSSBOWMAN = 76
    RENEGADEOGERMACE = 78
    RENEGADEOGERCROSSBOW = 79
    ELITESPRINGATTACKERMELEE = 83
    ELITESPRINGATTACKERRANGE = 84
    ELITESPRINGDEFENDERMELEE = 85
    ELITESPRINGDEFENDERRANGE = 86
    SHADOWRANKREWARDMELEE = 92
    SHADOWRANKREWARDRANGE = 93
    STPATRICKSDEFENDERMELEE = 100
    STPATRICKSDEFENDERRANGE = 101
    EASTERDEFENDERMELEE = 102
    EASTERDEFENDERRANGE = 103
    ALIENREROLLEDEFENDERMELEE = 146
    ALIENREROLLEDEFENDERRANGE = 147
    RELICAXE = 148
    RELICSHORTBOW = 149
    RELICHAMMER = 150
    RELICLONGBOW = 151
    MAYAMELEE = 183
    MAYARANGE = 184
    MAYAELITEMELEEE = 185
    MAYAELITERANGE = 186
    RENEGADEMAYAMELEE = 187
    RENEGADEMAYARANGE = 188
    RENEGADEMAYAELITEMELEEE = 189
    RENEGADEMAYAELITERANGE = 190
    CORRUPTEDASSASSIN = 191
    CORRUPTEDCROSSBOWMAN = 192
    CORRUPTEDELITEHALBERDIER = 193
    CORRUPTEDELITELONGBOWMAN = 194
    MEADSHIELDMAIDEN = 195
    MEADSHIELDMAIDEN_2 = 196
    MEADSHIELDMAIDEN_3 = 197
    MEADSHIELDMAIDEN_4 = 198
    MEADSHIELDMAIDEN_5 = 199
    MEADSHIELDMAIDEN_6 = 200
    MEADSHIELDMAIDEN_7 = 201
    MEADSHIELDMAIDEN_8 = 202
    MEADSHIELDMAIDEN_9 = 203
    MEADSHIELDMAIDEN_10 = 204
    MEADRANGER = 205
    MEADRANGER_2 = 206
    MEADRANGER_3 = 207
    MEADRANGER_4 = 208
    MEADRANGER_5 = 209
    MEADRANGER_6 = 210
    MEADRANGER_7 = 211
    MEADRANGER_8 = 212
    MEADRANGER_9 = 213
    MEADRANGER_10 = 214
    MEADSHIELDMAIDEN_11 = 215
    MEADRANGER_11 = 216
    MEADMACE = 217
    MEADMACE_2 = 218
    MEADMACE_3 = 219
    MEADMACE_4 = 220
    MEADMACE_5 = 221
    MEADMACE_6 = 222
    MEADMACE_7 = 223
    MEADMACE_8 = 224
    MEADMACE_9 = 225
    MEADMACE_10 = 226
    MEADMACE_11 = 227
    MEADBOW = 228
    MEADBOW_2 = 229
    MEADBOW_3 = 230
    MEADBOW_4 = 231
    MEADBOW_5 = 232
    MEADBOW_6 = 233
    MEADBOW_7 = 234
    MEADBOW_8 = 235
    MEADBOW_9 = 236
    MEADBOW_10 = 237
    MEADBOW_11 = 238
    ELITEHALBERD = 308
    ELITETWOHANDEDSWORD = 309
    ELITELONGBOWMAN = 311
    ELITEHEAVYCROSSBOWMAN = 312
    SWORDMAN = 601
    SPEERMAN = 602
    MACE = 603
    HALBERD = 604
    TWOHANDEDSWORD = 605
    ARCHER = 606
    CROSSBOWMAN = 607
    BOWMAN = 608
    HEAVYCROSSBOWMAN = 609
    LONGBOWMAN = 610
    SHADOWMACE = 612
    SHADOWCROSSBOWMAN = 613
    MILITIA = 620
    SWORDSMAN = 621
    SPEARMAN = 622
    KNIGHT = 623
    LIGHT_CAVALRY = 640
    HEAVY_CAVALRY = 641
    LANCER = 642
    PEASANT = 652
    BATTERING_RAM = 650
    CATAPULT = 651
    SIEGE_TOWER = 652
    EVENTKNIGHT = 655
    EVENTCROSSBOWMAN = 656
    NATIVEMELEE = 657
    NATIVERANGE = 658
    PRINCENOOB = 659
    MANTLET = 660
    WALL_DEFENDER = 661
    SKELETONSPEERMAN = 662
    SKELETONBOWMAN = 663
    KINGSCROSSBOWMAN = 664
    SOLDIERS = 665
    SHADOWTWOHANDEDSWORD = 667
    SHADOWHEAVYCROSSBOWMAN = 668
    SPY = 670
    AXEVIKING = 670
    COMMANDER = 680
    BOWVIKING = 671
    KINGSMACE = 672
    DRAGONCLAWS = 673
    DRAGONJAW = 674
    DESERTMELEE = 675
    DESERTRANGE = 676
    ICEMELEE = 677
    ICERANGE = 678
    FIREMELEE = 679
    FIRERANGE = 680
    MARAUDER = 684
    FIREDEVIL = 685
    KINGSSPEERMAN = 686
    KINGSBOWMAN = 687
    DESERTEVENTMELEE = 688
    DESERTEVENTRANGE = 689
    ICEEVENTMELEE = 690
    ICEEVENTRANGE = 691
    FIREEVENTMELEE = 692
    FIREEVENTRANGE = 693
    COWHALBERD = 698
    COWBOWMAN = 699
    BLUEMELEE = 710
    BLUERANGE = 711
    REDMELEE = 712
    REDRANGE = 713
    RANKREWARDMELEE = 714
    RANKREWARDRANGE = 715
    PIRATESPEERMAN = 716
    PIRATEBOWMAN = 717
    TENTACLE = 718
    OCTOPUSHEAD = 719
    TINOSWOLVES = 720
    CONAN = 721
    SLINGSHOTMARKSMAN = 727
    RENEGADEPIKEMAN = 728
    RENEGADESPEARTHROWER = 729
    CRUSADEMILEE = 753
    CRUSADERANGE = 754
    RENEGADEPIRATEMILEE = 759
    RENEGADEPIRATERANGE = 760
    ELITEMARAUDER = 765
    ELITEFIREDEVIL = 766
    RENEGADENATIVEMELEE = 767
    RENEGADENATIVERANGE = 768
    SAMURAIDEFENDERMELEENPC_2 = 820
    SAMURAIDEFENDERMELEENPC_3 = 821
    SAMURAIDEFENDERMELEENPC_4 = 822
    SAMURAIDEFENDERMELEENPC_5 = 823
    SAMURAIDEFENDERMELEENPC_6 = 824
    SAMURAIDEFENDERMELEENPC_7 = 825
    SAMURAIDEFENDERMELEENPC_8 = 826
    SAMURAIDEFENDERMELEENPC_9 = 827
    SAMURAIDEFENDERMELEENPC_10 = 828
    SAMURAIDEFENDERMELEENPC_11 = 829
    SAMURAIDEFENDERRANGENPC_2 = 830
    SAMURAIDEFENDERRANGENPC_3 = 831
    SAMURAIDEFENDERRANGENPC_4 = 832
    SAMURAIDEFENDERRANGENPC_5 = 833
    SAMURAIDEFENDERRANGENPC_6 = 834
    SAMURAIDEFENDERRANGENPC_7 = 835
    SAMURAIDEFENDERRANGENPC_8 = 836
    SAMURAIDEFENDERRANGENPC_9 = 837
    SAMURAIDEFENDERRANGENPC_10 = 838
    SAMURAIDEFENDERRANGENPC_11 = 839
    SAMURAIATTACKERMELEENPC = 860
    SAMURAIATTACKERMELEENPC_2 = 861
    SAMURAIATTACKERMELEENPC_3 = 862
    SAMURAIATTACKERMELEENPC_4 = 863
    SAMURAIATTACKERMELEENPC_5 = 864
    SAMURAIATTACKERMELEENPC_6 = 865
    SAMURAIATTACKERMELEENPC_7 = 866
    SAMURAIATTACKERMELEENPC_8 = 867
    SAMURAIATTACKERMELEENPC_9 = 868
    SAMURAIATTACKERMELEENPC_10 = 869
    SAMURAIATTACKERRANGENPC = 870
    SAMURAIATTACKERRANGENPC_2 = 871
    SAMURAIATTACKERRANGENPC_3 = 872
    SAMURAIATTACKERRANGENPC_4 = 873
    SAMURAIATTACKERRANGENPC_5 = 874
    SAMURAIATTACKERRANGENPC_6 = 875
    SAMURAIATTACKERRANGENPC_7 = 876
    SAMURAIATTACKERRANGENPC_8 = 877
    SAMURAIATTACKERRANGENPC_9 = 878
    SAMURAIATTACKERRANGENPC_10 = 879
    PIKEMAN = 900
    PIKEMAN_2 = 901
    PIKEMAN_3 = 902
    PIKEMAN_4 = 903
    PIKEMAN_5 = 904
    PIKEMAN_6 = 905
    PIKEMAN_7 = 906
    PIKEMAN_8 = 907
    PIKEMAN_9 = 908
    PIKEMAN_10 = 909
    SPEARTHROWER = 910
    SPEARTHROWER_2 = 911
    SPEARTHROWER_3 = 912
    SPEARTHROWER_4 = 913
    SPEARTHROWER_5 = 914
    SPEARTHROWER_6 = 915
    SPEARTHROWER_7 = 916
    SPEARTHROWER_8 = 917
    SPEARTHROWER_9 = 918
    SPEARTHROWER_10 = 919
    VETERANSABERSLASHER_2 = 940
    VETERANSABERSLASHER_3 = 941
    VETERANSABERSLASHER_4 = 942
    VETERANSABERSLASHER_5 = 943
    VETERANSABERSLASHER_6 = 944
    VETERANSABERSLASHER_7 = 945
    VETERANSABERSLASHER_8 = 946
    VETERANSABERSLASHER_9 = 947
    VETERANSABERSLASHER_10 = 948
    VETERANSABERSLASHER_11 = 949
    VETERANSLINGSHOTMARKSMAN_2 = 950
    VETERANSLINGSHOTMARKSMAN_3 = 951
    VETERANSLINGSHOTMARKSMAN_4 = 952
    VETERANSLINGSHOTMARKSMAN_5 = 953
    VETERANSLINGSHOTMARKSMAN_6 = 954
    VETERANSLINGSHOTMARKSMAN_7 = 955
    VETERANSLINGSHOTMARKSMAN_8 = 956
    VETERANSLINGSHOTMARKSMAN_9 = 957
    VETERANSLINGSHOTMARKSMAN_10 = 958
    VETERANSLINGSHOTMARKSMAN_11 = 959
    ELITESPRINGATTACKERMELEE_2 = 960
    ELITESPRINGATTACKERRANGE_2 = 961
    RENEGADEPIRATEMILEE_2 = 962
    RENEGADEPIRATERANGE_2 = 963
    QUICKATTACK = 1337
    ELITEHALBERD_2 = 2000
    ELITEHALBERD_3 = 2001
    ELITEHALBERD_4 = 2002
    ELITEHALBERD_5 = 2003
    ELITEHALBERD_6 = 2004
    ELITEHALBERD_7 = 2005
    ELITEHALBERD_8 = 2006
    ELITEHALBERD_9 = 2007
    ELITEHALBERD_10 = 2008
    ELITEHALBERD_11 = 2009
    ELITETWOHANDEDSWORD_2 = 2010
    ELITETWOHANDEDSWORD_3 = 2011
    ELITETWOHANDEDSWORD_4 = 2012
    ELITETWOHANDEDSWORD_5 = 2013
    ELITETWOHANDEDSWORD_6 = 2014
    ELITETWOHANDEDSWORD_7 = 2015
    ELITETWOHANDEDSWORD_8 = 2016
    ELITETWOHANDEDSWORD_9 = 2017
    ELITETWOHANDEDSWORD_10 = 2018
    ELITETWOHANDEDSWORD_11 = 2019
    RELICAXE_2 = 2020
    RELICAXE_3 = 2021
    RELICAXE_4 = 2022
    RELICAXE_5 = 2023
    RELICAXE_6 = 2024
    RELICAXE_7 = 2025
    RELICAXE_8 = 2026
    RELICAXE_9 = 2027
    RELICAXE_10 = 2028
    RELICAXE_11 = 2029
    RELICHAMMER_2 = 2030
    RELICHAMMER_3 = 2031
    RELICHAMMER_4 = 2032
    RELICHAMMER_5 = 2033
    RELICHAMMER_6 = 2034
    RELICHAMMER_7 = 2035
    RELICHAMMER_8 = 2036
    RELICHAMMER_9 = 2037
    RELICHAMMER_10 = 2038
    RELICHAMMER_11 = 2039
    ELITELONGBOWMAN_2 = 2040
    ELITELONGBOWMAN_3 = 2041
    ELITELONGBOWMAN_4 = 2042
    ELITELONGBOWMAN_5 = 2043
    ELITELONGBOWMAN_6 = 2044
    ELITELONGBOWMAN_7 = 2045
    ELITELONGBOWMAN_8 = 2046
    ELITELONGBOWMAN_9 = 2047
    ELITELONGBOWMAN_10 = 2048
    ELITELONGBOWMAN_11 = 2049
    ELITEHEAVYCROSSBOWMAN_2 = 2050
    ELITEHEAVYCROSSBOWMAN_3 = 2051
    ELITEHEAVYCROSSBOWMAN_4 = 2052
    ELITEHEAVYCROSSBOWMAN_5 = 2053
    ELITEHEAVYCROSSBOWMAN_6 = 2054
    ELITEHEAVYCROSSBOWMAN_7 = 2055
    ELITEHEAVYCROSSBOWMAN_8 = 2056
    ELITEHEAVYCROSSBOWMAN_9 = 2057
    ELITEHEAVYCROSSBOWMAN_10 = 2058
    ELITEHEAVYCROSSBOWMAN_11 = 2059
    RELICSHORTBOW_2 = 2060
    RELICSHORTBOW_3 = 2061
    RELICSHORTBOW_4 = 2062
    RELICSHORTBOW_5 = 2063
    RELICSHORTBOW_6 = 2064
    RELICSHORTBOW_7 = 2065
    RELICSHORTBOW_8 = 2066
    RELICSHORTBOW_9 = 2067
    RELICSHORTBOW_10 = 2068
    RELICSHORTBOW_11 = 2069
    RELICLONGBOW_2 = 2070
    RELICLONGBOW_3 = 2071
    RELICLONGBOW_4 = 2072
    RELICLONGBOW_5 = 2073
    RELICLONGBOW_6 = 2074
    RELICLONGBOW_7 = 2075
    RELICLONGBOW_8 = 2076
    RELICLONGBOW_9 = 2077
    RELICLONGBOW_10 = 2078
    RELICLONGBOW_11 = 2079


@dataclass
class RecruitmentTask:
    """A unit recruitment task."""

    castle_id: int
    unit_type: int
    count: int
    priority: int = 0


@dataclass
class UnitProductionTarget:
    """Target unit counts for a castle."""

    castle_id: int
    targets: Dict[int, int] = field(default_factory=dict)  # unit_type -> target_count


@dataclass
class ArmyStatus:
    """Current army status for a castle."""

    castle_id: int
    units: Dict[int, int] = field(default_factory=dict)  # unit_type -> count
    total_units: int = 0
    in_production: Dict[int, int] = field(default_factory=dict)


class UnitManager:
    """
    Manages unit production and army composition.

    Features:
    - Production queue management
    - Auto-recruitment based on targets
    - Army composition recommendations
    - Multi-castle coordination
    """

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self.queue: List[RecruitmentTask] = []
        self.targets: Dict[int, UnitProductionTarget] = {}  # castle_id -> targets
        self._auto_recruit_enabled = False
        self._running = False

    @property
    def castles(self) -> Dict[int, Castle]:
        """Get player's castles."""
        player = self.client.state.local_player
        if player:
            return player.castles
        return {}

    def set_target(self, castle_id: int, unit_type: int, count: int):
        """
        Set target unit count for a castle.

        Args:
            castle_id: Castle ID
            unit_type: Unit type ID
            count: Target number of units
        """
        if castle_id not in self.targets:
            self.targets[castle_id] = UnitProductionTarget(castle_id=castle_id)

        self.targets[castle_id].targets[unit_type] = count
        logger.info(f"Set target: Castle {castle_id}, Unit {unit_type}, Count {count}")

    def set_army_composition(
        self,
        castle_id: int,
        composition: Dict[int, int],
    ):
        """
        Set complete army composition target.

        Args:
            castle_id: Castle ID
            composition: Dict of {unit_type: count}
        """
        self.targets[castle_id] = UnitProductionTarget(
            castle_id=castle_id,
            targets=composition.copy(),
        )
        logger.info(f"Set army composition for castle {castle_id}")

    def clear_targets(self, castle_id: Optional[int] = None):
        """Clear production targets."""
        if castle_id:
            self.targets.pop(castle_id, None)
        else:
            self.targets.clear()

    def add_task(
        self,
        castle_id: int,
        unit_type: int,
        count: int,
        priority: int = 0,
    ) -> RecruitmentTask:
        """Add a recruitment task to the queue."""
        task = RecruitmentTask(
            castle_id=castle_id,
            unit_type=unit_type,
            count=count,
            priority=priority,
        )
        self.queue.append(task)
        self._sort_queue()
        logger.info(f"Added recruitment: {count}x Unit {unit_type} in Castle {castle_id}")
        return task

    def remove_task(self, castle_id: int, unit_type: int) -> bool:
        """Remove a task from the queue."""
        for i, task in enumerate(self.queue):
            if task.castle_id == castle_id and task.unit_type == unit_type:
                self.queue.pop(i)
                return True
        return False

    def clear_queue(self, castle_id: Optional[int] = None):
        """Clear recruitment queue."""
        if castle_id:
            self.queue = [t for t in self.queue if t.castle_id != castle_id]
        else:
            self.queue.clear()

    def get_army_status(self, castle_id: int) -> Optional[ArmyStatus]:
        """Get current army status for a castle."""
        # Get from state manager
        army = self.client.state.armies.get(castle_id)
        if not army:
            return ArmyStatus(castle_id=castle_id)

        units = army.units.copy()
        total = sum(units.values())

        return ArmyStatus(
            castle_id=castle_id,
            units=units,
            total_units=total,
        )

    def get_deficit(self, castle_id: int) -> Dict[int, int]:
        """
        Get unit deficit compared to targets.

        Returns:
            Dict of {unit_type: deficit_count}
        """
        deficit: Dict[int, int] = {}
        target = self.targets.get(castle_id)
        if not target:
            return deficit

        status = self.get_army_status(castle_id)
        current_units = status.units if status else {}

        for unit_type, target_count in target.targets.items():
            current = current_units.get(unit_type, 0)
            if current < target_count:
                deficit[unit_type] = target_count - current

        return deficit

    def calculate_recruitment_tasks(self, castle_id: Optional[int] = None) -> List[RecruitmentTask]:
        """
        Calculate recruitment tasks needed to meet targets.

        Args:
            castle_id: Specific castle or None for all

        Returns:
            List of RecruitmentTask objects
        """
        tasks = []
        castle_ids = [castle_id] if castle_id else list(self.targets.keys())

        for cid in castle_ids:
            deficit = self.get_deficit(cid)
            for unit_type, count in deficit.items():
                if count > 0:
                    tasks.append(
                        RecruitmentTask(
                            castle_id=cid,
                            unit_type=unit_type,
                            count=count,
                        )
                    )

        return tasks

    async def execute_task(self, task: RecruitmentTask) -> bool:
        """Execute a recruitment task."""
        try:
            success = await self.client.recruit_units(
                castle_id=task.castle_id,
                unit_id=task.unit_type,
                count=task.count,
            )

            if success:
                # Remove from queue
                self.queue = [
                    t for t in self.queue if not (t.castle_id == task.castle_id and t.unit_type == task.unit_type)
                ]
                logger.info(f"Started recruitment: {task.count}x Unit {task.unit_type} in Castle {task.castle_id}")

            return bool(success)
        except Exception as e:
            logger.error(f"Recruitment failed: {e}")
            return False

    async def process_queue(self) -> int:
        """Process the recruitment queue."""
        if not self.queue:
            return 0

        executed = 0
        for task in self.queue[:]:  # Copy to allow modification
            success = await self.execute_task(task)
            if success:
                executed += 1
            await asyncio.sleep(0.5)  # Rate limit

        return executed

    async def auto_recruit(self) -> int:
        """
        Automatically recruit units to meet targets.

        Returns:
            Number of recruitment tasks executed
        """
        # Calculate needed recruitments
        tasks = self.calculate_recruitment_tasks()

        if not tasks:
            logger.debug("No recruitment needed")
            return 0

        # Execute tasks
        executed = 0
        for task in tasks:
            success = await self.execute_task(task)
            if success:
                executed += 1
            await asyncio.sleep(0.5)

        logger.info(f"Auto-recruit: executed {executed} tasks")
        return executed

    async def start_auto_recruit(self, interval: int = 120):
        """
        Start automatic recruitment.

        Args:
            interval: Check interval in seconds
        """
        self._auto_recruit_enabled = True
        self._running = True

        logger.info(f"Auto-recruit started (interval: {interval}s)")

        while self._running and self._auto_recruit_enabled:
            try:
                await self.auto_recruit()
            except Exception as e:
                logger.error(f"Auto-recruit error: {e}")

            await asyncio.sleep(interval)

    def stop_auto_recruit(self):
        """Stop automatic recruitment."""
        self._auto_recruit_enabled = False
        self._running = False
        logger.info("Auto-recruit stopped")

    def get_summary(self) -> Dict[str, Any]:
        """Get recruitment summary."""
        return {
            "queue_length": len(self.queue),
            "castles_with_targets": len(self.targets),
            "total_deficit": sum(sum(self.get_deficit(cid).values()) for cid in self.targets),
        }

    def recommend_composition(self, focus: str = "balanced", size: int = 500) -> Dict[int, int]:
        """
        Recommend army composition.

        Args:
            focus: "balanced", "attack", "defense", "farming"
            size: Total army size

        Returns:
            Dict of {unit_type: count}
        """
        if focus == "attack":
            return {
                UnitType.SWORDSMAN: int(size * 0.3),
                UnitType.KNIGHT: int(size * 0.2),
                UnitType.CROSSBOWMAN: int(size * 0.2),
                UnitType.HEAVY_CAVALRY: int(size * 0.2),
                UnitType.CATAPULT: int(size * 0.1),
            }
        elif focus == "defense":
            return {
                UnitType.SPEARMAN: int(size * 0.3),
                UnitType.CROSSBOWMAN: int(size * 0.3),
                UnitType.WALL_DEFENDER: int(size * 0.2),
                UnitType.MANTLET: int(size * 0.2),
            }
        elif focus == "farming":
            return {
                UnitType.MILITIA: int(size * 0.5),
                UnitType.SWORDSMAN: int(size * 0.3),
                UnitType.BOWMAN: int(size * 0.2),
            }
        else:  # balanced
            return {
                UnitType.SWORDSMAN: int(size * 0.25),
                UnitType.SPEARMAN: int(size * 0.15),
                UnitType.CROSSBOWMAN: int(size * 0.2),
                UnitType.KNIGHT: int(size * 0.15),
                UnitType.LIGHT_CAVALRY: int(size * 0.15),
                UnitType.CATAPULT: int(size * 0.1),
            }

    def _sort_queue(self):
        """Sort queue by priority."""
        self.queue.sort(key=lambda t: t.priority, reverse=True)
