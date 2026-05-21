"""Order parsing and representation for StarWeb."""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Optional


class OrderType(enum.Enum):
    # Movement
    MOVE = "move"
    # Transfers
    TRANSFER_SHIPS = "transfer_ships"
    # Cargo
    LOAD = "load"
    UNLOAD = "unload"
    JETTISON = "jettison"
    UNLOAD_CG = "unload_cg"
    # Combat
    FIRE_FLEET = "fire_fleet"
    FIRE_INDUSTRY = "fire_industry"
    FIRE_POPULATION = "fire_population"
    FIRE_HOMEFLEET = "fire_homefleet"
    FIRE_CONVERTS = "fire_converts"
    CONDITIONAL_FIRE = "conditional_fire"
    # Ambush
    AMBUSH = "ambush"
    NO_AMBUSH = "no_ambush"
    NO_AMBUSH_WORLD = "no_ambush_world"
    # Building
    BUILD_ISHIPS = "build_iships"
    BUILD_PSHIPS = "build_pships"
    BUILD_FLEET = "build_fleet"
    BUILD_INDUSTRY = "build_industry"
    BUILD_POP_LIMIT = "build_pop_limit"
    BUILD_ROBOTS = "build_robots"
    # Migration
    MIGRATE_POP = "migrate_pop"
    MIGRATE_CONVERTS = "migrate_converts"
    # Probes
    PROBE_FLEET = "probe_fleet"
    PROBE_ISHIP = "probe_iship"
    PROBE_PSHIP = "probe_pship"
    # Artifacts
    HOOK_ARTIFACT = "hook_artifact"
    UNHOOK_ARTIFACT = "unhook_artifact"
    # Diplomacy
    DECLARE_ALLY = "declare_ally"
    DECLARE_NON_ALLY = "declare_non_ally"
    DECLARE_LOADER = "declare_loader"
    DECLARE_NON_LOADER = "declare_non_loader"
    DECLARE_JIHAD = "declare_jihad"
    GIVE_FLEET = "give_fleet"
    GIVE_WORLD = "give_world"
    # Misc
    PLUNDER = "plunder"
    AT_PEACE = "at_peace"
    NOT_AT_PEACE = "not_at_peace"
    BUILD_PBB = "build_pbb"
    DROP_PBB = "drop_pbb"
    ROBOT_ATTACK = "robot_attack"


@dataclass
class Order:
    order_type: OrderType
    player: str
    fleet_id: Optional[int] = None
    world_id: Optional[int] = None
    target_fleet_id: Optional[int] = None
    target_world_id: Optional[int] = None
    quantity: Optional[int] = None
    target_player: Optional[str] = None
    waypoints: list[int] = None
    artifact_id: Optional[int] = None

    def __post_init__(self):
        if self.waypoints is None:
            self.waypoints = []


class OrderParser:
    """Parse StarWeb order strings into Order objects."""

    # Patterns for order recognition
    PATTERNS = [
        # Fleet move: FnnnWmmmWoooWppp
        (r"F(\d+)W(\d+)(?:W(\d+))?(?:W(\d+))?$", "_parse_move"),
        # Transfer ships: FnnnTqqqFmmm
        (r"F(\d+)T(\d+)F(\d+)$", "_parse_transfer"),
        # Unload all: FnnnU
        (r"F(\d+)U$", "_parse_unload_all"),
        # Unload qty: FnnnUqqq
        (r"F(\d+)U(\d+)$", "_parse_unload_qty"),
        # Load all: FnnnL
        (r"F(\d+)L$", "_parse_load_all"),
        # Load qty: FnnnLqqq
        (r"F(\d+)L(\d+)$", "_parse_load_qty"),
        # Jettison all: FnnnJ
        (r"F(\d+)J$", "_parse_jettison_all"),
        # Jettison qty: FnnnJqqq
        (r"F(\d+)J(\d+)$", "_parse_jettison_qty"),
        # Consumer goods: FnnnN / FnnnNqqq
        (r"F(\d+)N$", "_parse_cg_all"),
        (r"F(\d+)N(\d+)$", "_parse_cg_qty"),
        # Fire at fleet: FnnnAFmmm
        (r"F(\d+)AF(\d+)$", "_parse_fire_fleet"),
        # Fire at industry: FnnnAI
        (r"F(\d+)AI$", "_parse_fire_industry"),
        # Fire at population: FnnnAP
        (r"F(\d+)AP$", "_parse_fire_pop"),
        # Fire at home fleet: FnnnAH
        (r"F(\d+)AH$", "_parse_fire_homefleet"),
        # ISHPS fire: InnnAFmmm / InnnAC
        (r"I(\d+)AF(\d+)$", "_parse_iship_fire_fleet"),
        (r"I(\d+)AC$", "_parse_iship_fire_converts"),
        # PSHPS fire: PnnnAFmmm / PnnnAC
        (r"P(\d+)AF(\d+)$", "_parse_pship_fire_fleet"),
        (r"P(\d+)AC$", "_parse_pship_fire_converts"),
        # Conditional fire: FnnnCFmmm
        (r"F(\d+)CF(\d+)$", "_parse_cond_fire"),
        # Build: WnnnBqqqI / WnnnBqqqP / WnnnBqqqFmmm
        (r"W(\d+)B(\d+)I$", "_parse_build_iships"),
        (r"W(\d+)B(\d+)P$", "_parse_build_pships"),
        (r"W(\d+)B(\d+)F(\d+)$", "_parse_build_fleet"),
        # Build industry / pop limit
        (r"W(\d+)I(\d+)I$", "_parse_build_industry"),
        (r"W(\d+)I(\d+)L$", "_parse_build_poplimit"),
        # Build robots
        (r"W(\d+)B(\d+)R$", "_parse_build_robots"),
        # Migrate: PnnnMqqqWmmm / CnnnMqqqWmmm
        (r"P(\d+)M(\d+)W(\d+)$", "_parse_migrate_pop"),
        (r"C(\d+)M(\d+)W(\d+)$", "_parse_migrate_converts"),
        # Probe: FnnnPmmm / InnnPmmm / PnnnPmmm
        (r"F(\d+)P(\d+)$", "_parse_probe_fleet"),
        (r"I(\d+)P(\d+)$", "_parse_probe_iship"),
        (r"P(\d+)P(\d+)$", "_parse_probe_pship"),
        # Artifacts: VnnnFmmm / VnnnW
        (r"V(\d+)F(\d+)$", "_parse_hook_artifact"),
        (r"V(\d+)W$", "_parse_unhook_artifact"),
        # Alliances
        (r"A=(\w+)$", "_parse_ally"),
        (r"N=(\w+)$", "_parse_non_ally"),
        (r"L=(\w+)$", "_parse_loader"),
        (r"X=(\w+)$", "_parse_non_loader"),
        (r"J=(\w+)$", "_parse_jihad"),
        # Gifts
        (r"F(\d+)G=(\w+)$", "_parse_give_fleet"),
        (r"W(\d+)G=(\w+)$", "_parse_give_world"),
        # Misc
        (r"W(\d+)X$", "_parse_plunder"),
        (r"F(\d+)Q$", "_parse_at_peace"),
        (r"F(\d+)X$", "_parse_not_at_peace"),
        (r"F(\d+)B$", "_parse_build_pbb"),
        (r"F(\d+)D$", "_parse_drop_pbb"),
        (r"F(\d+)R(\d+)$", "_parse_robot_attack"),
        # No ambush
        (r"Z$", "_parse_no_ambush_all"),
        (r"Z(\d+)$", "_parse_no_ambush_world"),
    ]

    def parse(self, order_str: str, player: str) -> Optional[Order]:
        """Parse a single order string. Returns None if unrecognized."""
        order_str = order_str.strip().upper()
        for pattern, method_name in self.PATTERNS:
            match = re.match(pattern, order_str)
            if match:
                method = getattr(self, method_name)
                return method(match, player)
        return None

    def parse_turn(self, orders_text: str, player: str) -> list[Order]:
        """Parse a full turn's worth of orders (one per line or comma-separated)."""
        raw = re.split(r"[,\n;]+", orders_text)
        results = []
        for raw_order in raw:
            raw_order = raw_order.strip()
            if not raw_order:
                continue
            order = self.parse(raw_order, player)
            if order:
                results.append(order)
        return results

    # --- Parse methods ---

    def _parse_move(self, m, player) -> Order:
        waypoints = [int(m.group(2))]
        if m.group(3):
            waypoints.append(int(m.group(3)))
        if m.group(4):
            waypoints.append(int(m.group(4)))
        return Order(OrderType.MOVE, player, fleet_id=int(m.group(1)), waypoints=waypoints)

    def _parse_transfer(self, m, player) -> Order:
        return Order(OrderType.TRANSFER_SHIPS, player,
                     fleet_id=int(m.group(1)), quantity=int(m.group(2)),
                     target_fleet_id=int(m.group(3)))

    def _parse_unload_all(self, m, player) -> Order:
        return Order(OrderType.UNLOAD, player, fleet_id=int(m.group(1)))

    def _parse_unload_qty(self, m, player) -> Order:
        return Order(OrderType.UNLOAD, player, fleet_id=int(m.group(1)), quantity=int(m.group(2)))

    def _parse_load_all(self, m, player) -> Order:
        return Order(OrderType.LOAD, player, fleet_id=int(m.group(1)))

    def _parse_load_qty(self, m, player) -> Order:
        return Order(OrderType.LOAD, player, fleet_id=int(m.group(1)), quantity=int(m.group(2)))

    def _parse_jettison_all(self, m, player) -> Order:
        return Order(OrderType.JETTISON, player, fleet_id=int(m.group(1)))

    def _parse_jettison_qty(self, m, player) -> Order:
        return Order(OrderType.JETTISON, player, fleet_id=int(m.group(1)), quantity=int(m.group(2)))

    def _parse_cg_all(self, m, player) -> Order:
        return Order(OrderType.UNLOAD_CG, player, fleet_id=int(m.group(1)))

    def _parse_cg_qty(self, m, player) -> Order:
        return Order(OrderType.UNLOAD_CG, player, fleet_id=int(m.group(1)), quantity=int(m.group(2)))

    def _parse_fire_fleet(self, m, player) -> Order:
        return Order(OrderType.FIRE_FLEET, player, fleet_id=int(m.group(1)),
                     target_fleet_id=int(m.group(2)))

    def _parse_fire_industry(self, m, player) -> Order:
        return Order(OrderType.FIRE_INDUSTRY, player, fleet_id=int(m.group(1)))

    def _parse_fire_pop(self, m, player) -> Order:
        return Order(OrderType.FIRE_POPULATION, player, fleet_id=int(m.group(1)))

    def _parse_fire_homefleet(self, m, player) -> Order:
        return Order(OrderType.FIRE_HOMEFLEET, player, fleet_id=int(m.group(1)))

    def _parse_iship_fire_fleet(self, m, player) -> Order:
        return Order(OrderType.FIRE_FLEET, player, world_id=int(m.group(1)),
                     target_fleet_id=int(m.group(2)))

    def _parse_iship_fire_converts(self, m, player) -> Order:
        return Order(OrderType.FIRE_CONVERTS, player, world_id=int(m.group(1)))

    def _parse_pship_fire_fleet(self, m, player) -> Order:
        return Order(OrderType.FIRE_FLEET, player, world_id=int(m.group(1)),
                     target_fleet_id=int(m.group(2)))

    def _parse_pship_fire_converts(self, m, player) -> Order:
        return Order(OrderType.FIRE_CONVERTS, player, world_id=int(m.group(1)))

    def _parse_cond_fire(self, m, player) -> Order:
        return Order(OrderType.CONDITIONAL_FIRE, player, fleet_id=int(m.group(1)),
                     target_fleet_id=int(m.group(2)))

    def _parse_build_iships(self, m, player) -> Order:
        return Order(OrderType.BUILD_ISHIPS, player, world_id=int(m.group(1)),
                     quantity=int(m.group(2)))

    def _parse_build_pships(self, m, player) -> Order:
        return Order(OrderType.BUILD_PSHIPS, player, world_id=int(m.group(1)),
                     quantity=int(m.group(2)))

    def _parse_build_fleet(self, m, player) -> Order:
        return Order(OrderType.BUILD_FLEET, player, world_id=int(m.group(1)),
                     quantity=int(m.group(2)), target_fleet_id=int(m.group(3)))

    def _parse_build_industry(self, m, player) -> Order:
        return Order(OrderType.BUILD_INDUSTRY, player, world_id=int(m.group(1)),
                     quantity=int(m.group(2)))

    def _parse_build_poplimit(self, m, player) -> Order:
        return Order(OrderType.BUILD_POP_LIMIT, player, world_id=int(m.group(1)),
                     quantity=int(m.group(2)))

    def _parse_build_robots(self, m, player) -> Order:
        return Order(OrderType.BUILD_ROBOTS, player, world_id=int(m.group(1)),
                     quantity=int(m.group(2)))

    def _parse_migrate_pop(self, m, player) -> Order:
        return Order(OrderType.MIGRATE_POP, player, world_id=int(m.group(1)),
                     quantity=int(m.group(2)), target_world_id=int(m.group(3)))

    def _parse_migrate_converts(self, m, player) -> Order:
        return Order(OrderType.MIGRATE_CONVERTS, player, world_id=int(m.group(1)),
                     quantity=int(m.group(2)), target_world_id=int(m.group(3)))

    def _parse_probe_fleet(self, m, player) -> Order:
        return Order(OrderType.PROBE_FLEET, player, fleet_id=int(m.group(1)),
                     target_world_id=int(m.group(2)))

    def _parse_probe_iship(self, m, player) -> Order:
        return Order(OrderType.PROBE_ISHIP, player, world_id=int(m.group(1)),
                     target_world_id=int(m.group(2)))

    def _parse_probe_pship(self, m, player) -> Order:
        return Order(OrderType.PROBE_PSHIP, player, world_id=int(m.group(1)),
                     target_world_id=int(m.group(2)))

    def _parse_hook_artifact(self, m, player) -> Order:
        return Order(OrderType.HOOK_ARTIFACT, player, artifact_id=int(m.group(1)),
                     fleet_id=int(m.group(2)))

    def _parse_unhook_artifact(self, m, player) -> Order:
        return Order(OrderType.UNHOOK_ARTIFACT, player, artifact_id=int(m.group(1)))

    def _parse_ally(self, m, player) -> Order:
        return Order(OrderType.DECLARE_ALLY, player, target_player=m.group(1))

    def _parse_non_ally(self, m, player) -> Order:
        return Order(OrderType.DECLARE_NON_ALLY, player, target_player=m.group(1))

    def _parse_loader(self, m, player) -> Order:
        return Order(OrderType.DECLARE_LOADER, player, target_player=m.group(1))

    def _parse_non_loader(self, m, player) -> Order:
        return Order(OrderType.DECLARE_NON_LOADER, player, target_player=m.group(1))

    def _parse_jihad(self, m, player) -> Order:
        return Order(OrderType.DECLARE_JIHAD, player, target_player=m.group(1))

    def _parse_give_fleet(self, m, player) -> Order:
        return Order(OrderType.GIVE_FLEET, player, fleet_id=int(m.group(1)),
                     target_player=m.group(2))

    def _parse_give_world(self, m, player) -> Order:
        return Order(OrderType.GIVE_WORLD, player, world_id=int(m.group(1)),
                     target_player=m.group(2))

    def _parse_plunder(self, m, player) -> Order:
        return Order(OrderType.PLUNDER, player, world_id=int(m.group(1)))

    def _parse_at_peace(self, m, player) -> Order:
        return Order(OrderType.AT_PEACE, player, fleet_id=int(m.group(1)))

    def _parse_not_at_peace(self, m, player) -> Order:
        return Order(OrderType.NOT_AT_PEACE, player, fleet_id=int(m.group(1)))

    def _parse_build_pbb(self, m, player) -> Order:
        return Order(OrderType.BUILD_PBB, player, fleet_id=int(m.group(1)))

    def _parse_drop_pbb(self, m, player) -> Order:
        return Order(OrderType.DROP_PBB, player, fleet_id=int(m.group(1)))

    def _parse_robot_attack(self, m, player) -> Order:
        return Order(OrderType.ROBOT_ATTACK, player, fleet_id=int(m.group(1)),
                     quantity=int(m.group(2)))

    def _parse_no_ambush_all(self, m, player) -> Order:
        return Order(OrderType.NO_AMBUSH, player)

    def _parse_no_ambush_world(self, m, player) -> Order:
        return Order(OrderType.NO_AMBUSH_WORLD, player, world_id=int(m.group(1)))
