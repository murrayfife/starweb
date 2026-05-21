"""Turn processing engine for StarWeb.

Executes orders in the correct sequence per the rules:
1. Diplomacy declarations (allies, loaders, jihads)
2. Gifts
3. Unloads / Loads / Jettisons
4. Probes
5. Transfers
6. Building (industry, ships, PBBs)
7. Migration
8. Movement (with ambush resolution)
9. Combat (firing, conditional fire, robot attacks, PBB drops)
10. Pirate fleet capture
11. World capture
12. Population growth / mine growth
13. Scoring
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from .models import CharacterType, Fleet, GameState, Player, World
from .orders import Order, OrderType


@dataclass
class TurnLog:
    """Records all events for a turn for player printouts."""
    turn: int = 0
    events: list[dict] = field(default_factory=list)

    def log(self, event_type: str, **kwargs):
        self.events.append({"type": event_type, **kwargs})

    def get_player_events(self, player: str) -> list[dict]:
        return [e for e in self.events
                if e.get("player") == player or e.get("visible_to") == player
                or "all" in e.get("visible_to", [])]


class TurnProcessor:
    """Processes a complete turn of StarWeb."""

    def __init__(self, state: GameState):
        self.state = state
        self.log = TurnLog(turn=state.turn_number + 1)
        self._no_ambush_players: set[str] = set()
        self._no_ambush_worlds: dict[str, set[int]] = {}

    def process_turn(self, all_orders: dict[str, list[Order]]) -> TurnLog:
        """Process all orders for all players. Returns the turn log."""
        self.state.turn_number += 1
        self.log.turn = self.state.turn_number

        # Document all player orders submitted this turn
        for player_name, player_orders in all_orders.items():
            for order in player_orders:
                self.log.log("order_submitted",
                             player=player_name,
                             order_type=order.order_type.value,
                             fleet_id=order.fleet_id,
                             world_id=order.world_id,
                             target_fleet_id=order.target_fleet_id,
                             target_player=order.target_player,
                             target_world_id=order.target_world_id,
                             waypoints=order.waypoints,
                             quantity=order.quantity)

        # Flatten and categorize
        orders_by_type: dict[OrderType, list[Order]] = {}
        for player_orders in all_orders.values():
            for order in player_orders:
                orders_by_type.setdefault(order.order_type, []).append(order)

        # Phase 1: Diplomacy
        self._process_diplomacy(orders_by_type)

        # Phase 2: Gifts
        self._process_gifts(orders_by_type)

        # Phase 3: Cargo (unload, load, jettison, consumer goods)
        self._process_cargo(orders_by_type)

        # Phase 4: Probes
        self._process_probes(orders_by_type)

        # Phase 5: Transfers
        self._process_transfers(orders_by_type)

        # Phase 6: Building
        self._process_building(orders_by_type)

        # Phase 7: Migration
        self._process_migration(orders_by_type)

        # Phase 8: Movement & Ambush
        self._process_movement(orders_by_type)

        # Phase 9: Combat
        self._process_combat(orders_by_type)

        # Phase 10: Pirate capture
        self._process_pirate_capture()

        # Phase 11: World capture
        self._process_world_capture()

        # Phase 12: Population & mine growth
        self._process_growth()

        # Phase 13: Scoring
        self._process_scoring()

        # Check victory
        self._check_victory()

        return self.log

    def _process_diplomacy(self, orders_by_type: dict):
        for order in orders_by_type.get(OrderType.DECLARE_ALLY, []):
            player = self.state.players[order.player]
            player.allies.add(order.target_player)
            self.log.log("ally_declared", player=order.player, target=order.target_player)

        for order in orders_by_type.get(OrderType.DECLARE_NON_ALLY, []):
            player = self.state.players[order.player]
            player.allies.discard(order.target_player)

        for order in orders_by_type.get(OrderType.DECLARE_LOADER, []):
            player = self.state.players[order.player]
            player.loaders.add(order.target_player)

        for order in orders_by_type.get(OrderType.DECLARE_NON_LOADER, []):
            player = self.state.players[order.player]
            player.loaders.discard(order.target_player)

        for order in orders_by_type.get(OrderType.DECLARE_JIHAD, []):
            player = self.state.players[order.player]
            if player.character_type == CharacterType.APOSTLE:
                player.jihad_target = order.target_player
                self.log.log("jihad_declared", player=order.player, target=order.target_player)

        # Ambush control
        for order in orders_by_type.get(OrderType.NO_AMBUSH, []):
            self._no_ambush_players.add(order.player)

        for order in orders_by_type.get(OrderType.NO_AMBUSH_WORLD, []):
            self._no_ambush_worlds.setdefault(order.player, set()).add(order.world_id)

        # At peace / not at peace
        for order in orders_by_type.get(OrderType.AT_PEACE, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if fleet and fleet.owner == order.player:
                fleet.at_peace = True

        for order in orders_by_type.get(OrderType.NOT_AT_PEACE, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if fleet and fleet.owner == order.player:
                fleet.at_peace = False

    def _process_gifts(self, orders_by_type: dict):
        for order in orders_by_type.get(OrderType.GIVE_FLEET, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if fleet and fleet.owner == order.player:
                fleet.owner = order.target_player
                self.log.log("fleet_gifted", player=order.player,
                             fleet=order.fleet_id, recipient=order.target_player)

        for order in orders_by_type.get(OrderType.GIVE_WORLD, []):
            world = self.state.worlds.get(order.world_id)
            if world and world.owner == order.player:
                world.owner = order.target_player
                world.turns_owned = 0
                self.log.log("world_gifted", player=order.player,
                             world=order.world_id, recipient=order.target_player)

    def _process_cargo(self, orders_by_type: dict):
        # Unloads first
        for order in orders_by_type.get(OrderType.UNLOAD, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if not fleet or fleet.owner != order.player:
                continue
            world = self.state.worlds.get(fleet.world_id)
            qty = order.quantity if order.quantity else fleet.cargo
            qty = min(qty, fleet.cargo)
            fleet.cargo -= qty
            world.metal += qty
            self.log.log("unload", player=order.player, fleet=order.fleet_id,
                         world=fleet.world_id, quantity=qty)

        # Consumer goods
        for order in orders_by_type.get(OrderType.UNLOAD_CG, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if not fleet or fleet.owner != order.player:
                continue
            world = self.state.worlds.get(fleet.world_id)
            qty = order.quantity if order.quantity else fleet.cargo
            qty = min(qty, fleet.cargo)
            fleet.cargo -= qty
            world.cg_unloaded += 1
            # CG scoring for merchants
            player = self.state.players[order.player]
            if player.character_type == CharacterType.MERCHANT:
                cg_points = [10, 8, 5, 3, 1]
                idx = min(world.cg_unloaded - 1, len(cg_points) - 1)
                player.score += cg_points[idx]
            # CG converts back to normal (50% chance each)
            if world.converts > 0:
                converted_back = sum(1 for _ in range(qty) if random.random() < 0.5)
                converted_back = min(converted_back, world.converts)
                world.converts -= converted_back
                world.population += converted_back
            self.log.log("cg_unloaded", player=order.player, fleet=order.fleet_id,
                         world=fleet.world_id, quantity=qty)

        # Jettisons
        for order in orders_by_type.get(OrderType.JETTISON, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if not fleet or fleet.owner != order.player:
                continue
            qty = order.quantity if order.quantity else fleet.cargo
            fleet.cargo -= min(qty, fleet.cargo)

        # Loads
        for order in orders_by_type.get(OrderType.LOAD, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if not fleet or fleet.owner != order.player:
                continue
            world = self.state.worlds.get(fleet.world_id)
            player = self.state.players[order.player]
            is_merchant = player.character_type == CharacterType.MERCHANT

            # Check loading permission
            if world.owner != order.player:
                if world.owner and not self.state.players[world.owner].is_loader(order.player):
                    continue

            capacity = fleet.max_cargo(is_merchant) - fleet.cargo
            available = world.metal
            qty = order.quantity if order.quantity else capacity
            loaded = min(qty, capacity, available)
            fleet.cargo += loaded
            world.metal -= loaded
            self.log.log("load", player=order.player, fleet=order.fleet_id,
                         world=fleet.world_id, quantity=loaded)

    def _process_probes(self, orders_by_type: dict):
        for otype in [OrderType.PROBE_FLEET, OrderType.PROBE_ISHIP, OrderType.PROBE_PSHIP]:
            for order in orders_by_type.get(otype, []):
                if otype == OrderType.PROBE_FLEET:
                    fleet = self.state.fleets.get(order.fleet_id)
                    if not fleet or fleet.owner != order.player or fleet.ships < 1:
                        continue
                    fleet.ships -= 1
                elif otype == OrderType.PROBE_ISHIP:
                    world = self.state.worlds.get(order.world_id)
                    if not world or world.owner != order.player or world.i_ships < 1:
                        continue
                    world.i_ships -= 1
                else:
                    world = self.state.worlds.get(order.world_id)
                    if not world or world.owner != order.player or world.p_ships < 1:
                        continue
                    world.p_ships -= 1

                self.log.log("probe", player=order.player,
                             target_world=order.target_world_id)

    def _process_transfers(self, orders_by_type: dict):
        for order in orders_by_type.get(OrderType.TRANSFER_SHIPS, []):
            src = self.state.fleets.get(order.fleet_id)
            dst = self.state.fleets.get(order.target_fleet_id)
            if not src or not dst or src.owner != order.player:
                continue
            if src.world_id != dst.world_id:
                continue
            qty = min(order.quantity, src.ships)
            src.ships -= qty
            dst.ships += qty
            # If dst was neutral and now only one player there, capture
            if dst.is_neutral and dst.ships > 0:
                pass  # handled in world capture phase

    def _process_building(self, orders_by_type: dict):
        # PBB building
        for order in orders_by_type.get(OrderType.BUILD_PBB, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if not fleet or fleet.owner != order.player:
                continue
            if fleet.ships > 25 and not fleet.has_pbb:
                fleet.ships -= 25
                fleet.has_pbb = True
                self.log.log("pbb_built", player=order.player, fleet=order.fleet_id)

        # Industry building at worlds
        for order in orders_by_type.get(OrderType.BUILD_INDUSTRY, []):
            world = self.state.worlds.get(order.world_id)
            if not world or world.owner != order.player:
                continue
            player = self.state.players[order.player]
            cost_per = 4 if player.character_type == CharacterType.EMPIRE_BUILDER else 5
            can_build = min(order.quantity, world.industry // cost_per,
                            world.metal // cost_per, world.population // cost_per)
            world.industry += can_build
            world.metal -= can_build * cost_per
            self.log.log("industry_built", player=order.player,
                         world=order.world_id, quantity=can_build)

        # Pop limit increase
        for order in orders_by_type.get(OrderType.BUILD_POP_LIMIT, []):
            world = self.state.worlds.get(order.world_id)
            if not world or world.owner != order.player:
                continue
            can_build = min(order.quantity, world.industry // 5,
                            world.metal // 5)
            world.pop_limit += can_build
            world.metal -= can_build * 5

        # Build ships onto fleets
        for order in orders_by_type.get(OrderType.BUILD_FLEET, []):
            world = self.state.worlds.get(order.world_id)
            fleet = self.state.fleets.get(order.target_fleet_id)
            if not world or not fleet or world.owner != order.player:
                continue
            if fleet.world_id != world.id:
                continue
            can_build = min(order.quantity, world.industry, world.metal, world.population)
            fleet.ships += can_build
            world.metal -= can_build
            self.log.log("ships_built", player=order.player,
                         world=order.world_id, fleet=order.target_fleet_id, quantity=can_build)

        # Build ISHIPS (default if not otherwise ordered)
        for order in orders_by_type.get(OrderType.BUILD_ISHIPS, []):
            world = self.state.worlds.get(order.world_id)
            if not world or world.owner != order.player:
                continue
            can_build = min(order.quantity, world.industry, world.metal, world.population)
            world.i_ships += can_build
            world.metal -= can_build

        # Build PSHIPS
        for order in orders_by_type.get(OrderType.BUILD_PSHIPS, []):
            world = self.state.worlds.get(order.world_id)
            if not world or world.owner != order.player:
                continue
            can_build = min(order.quantity, world.industry, world.metal, world.population)
            world.p_ships += can_build
            world.metal -= can_build

        # Build robots (berserker only)
        for order in orders_by_type.get(OrderType.BUILD_ROBOTS, []):
            world = self.state.worlds.get(order.world_id)
            if not world or world.owner != order.player:
                continue
            player = self.state.players[order.player]
            if player.character_type != CharacterType.BERSERKER:
                continue
            if world.robots == 0 and world.population > 0:
                continue  # can only build robots at robot worlds
            can_build = min(order.quantity, world.industry, world.metal)
            world.robots += can_build * 2
            world.metal -= can_build

    def _process_migration(self, orders_by_type: dict):
        for order in orders_by_type.get(OrderType.MIGRATE_POP, []):
            world = self.state.worlds.get(order.world_id)
            target = self.state.worlds.get(order.target_world_id)
            if not world or not target or world.owner != order.player:
                continue
            if order.target_world_id not in world.connections:
                continue
            qty = min(order.quantity, world.industry, world.metal, world.population)
            world.population -= qty
            world.metal -= qty
            target.population += qty
            self.log.log("migration", player=order.player,
                         from_world=order.world_id, to_world=order.target_world_id,
                         quantity=qty)

        for order in orders_by_type.get(OrderType.MIGRATE_CONVERTS, []):
            world = self.state.worlds.get(order.world_id)
            target = self.state.worlds.get(order.target_world_id)
            if not world or not target or world.owner != order.player:
                continue
            if order.target_world_id not in world.connections:
                continue
            qty = min(order.quantity, world.industry, world.metal, world.converts)
            world.converts -= qty
            world.metal -= qty
            target.converts += qty
            self.log.log("convert_migration", player=order.player,
                         from_world=order.world_id, to_world=order.target_world_id,
                         quantity=qty)

    def _process_movement(self, orders_by_type: dict):
        move_orders = orders_by_type.get(OrderType.MOVE, [])
        for order in move_orders:
            fleet = self.state.fleets.get(order.fleet_id)
            if not fleet or fleet.owner != order.player:
                continue
            if fleet.fired_this_turn:
                continue

            # Validate path connectivity
            origin = fleet.world_id
            current = fleet.world_id
            valid = True
            path = []
            for wp in order.waypoints:
                world = self.state.worlds.get(current)
                if wp not in world.connections:
                    valid = False
                    break
                path.append(wp)
                current = wp

            if not valid:
                continue

            # Check for ambush at intermediate worlds
            for wp in path[:-1]:
                ambush_damage = self._resolve_ambush(fleet, wp)
                if fleet.ships <= 0:
                    fleet.world_id = wp
                    break

            if fleet.ships > 0:
                dest = path[-1]
                # Black hole check
                dest_world = self.state.worlds.get(dest)
                if dest_world and dest_world.is_black_hole:
                    self.log.log("black_hole", player=order.player,
                                 fleet=order.fleet_id, world=dest)
                    fleet.ships = 0
                    fleet.cargo = 0
                    # Key survives, reappears randomly
                    new_world = random.choice(
                        [w.id for w in self.state.worlds.values() if not w.is_black_hole]
                    )
                    fleet.world_id = new_world
                else:
                    fleet.world_id = dest

            fleet.moved_this_turn = True
            self.log.log("movement", player=order.player,
                         fleet=order.fleet_id, from_world=origin,
                         destination=fleet.world_id)

    def _resolve_ambush(self, moving_fleet: Fleet, world_id: int) -> int:
        """Resolve ambush at a world. Returns damage dealt."""
        damage = 0
        ambushers = [
            f for f in self.state.fleets.values()
            if f.world_id == world_id and f.owner != moving_fleet.owner
            and f.ships > 0 and not f.moved_this_turn
        ]

        for ambusher in ambushers:
            owner = ambusher.owner
            if owner in self._no_ambush_players:
                continue
            if world_id in self._no_ambush_worlds.get(owner, set()):
                continue
            # Check ally
            if owner and self.state.players.get(owner):
                if self.state.players[owner].is_ally(moving_fleet.owner):
                    continue

            # Ambush: ships doubled
            hits = ambusher.ships * 2
            # Each 2 hits destroys 1 unloaded ship or 2 loaded ships
            if moving_fleet.cargo > 0:
                destroyed = hits  # loaded ships: 1 hit = 1 ship
            else:
                destroyed = hits // 2

            destroyed = min(destroyed, moving_fleet.ships)
            moving_fleet.ships -= destroyed
            damage += destroyed
            self.log.log("ambush", ambusher=owner, target_fleet=moving_fleet.id,
                         world=world_id, ships_destroyed=destroyed)

        return damage

    def _process_combat(self, orders_by_type: dict):
        # PBB drops
        for order in orders_by_type.get(OrderType.DROP_PBB, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if not fleet or fleet.owner != order.player or not fleet.has_pbb:
                continue
            world = self.state.worlds.get(fleet.world_id)
            pop_killed = world.population + world.converts + world.robots
            world.population = 0
            world.converts = 0
            world.robots = 0
            world.industry = 0
            world.mines = 0
            world.metal = 0
            world.i_ships = 0
            world.p_ships = 0
            world.pop_limit = 0
            world.busted = True
            fleet.has_pbb = False

            player = self.state.players[order.player]
            if player.character_type == CharacterType.BERSERKER:
                player.score += 200 + (pop_killed * 2)
            else:
                player.score -= 50
            self.log.log("pbb_dropped", player=order.player,
                         world=fleet.world_id, pop_killed=pop_killed)

        # Robot attacks
        for order in orders_by_type.get(OrderType.ROBOT_ATTACK, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if not fleet or fleet.owner != order.player:
                continue
            player = self.state.players[order.player]
            if player.character_type != CharacterType.BERSERKER:
                continue
            qty = min(order.quantity, fleet.ships)
            robots = qty * 2
            fleet.ships -= qty
            world = self.state.worlds.get(fleet.world_id)
            # Robots kill people: 1 robot kills 4 people
            people_killed = min(robots * 4, world.population)
            # People kill robots: 4 people kill 1 robot (rounded up)
            robots_killed = min(math.ceil(world.population / 4), robots)
            world.population -= people_killed
            robots_surviving = robots - robots_killed
            world.robots += robots_surviving
            player.score += people_killed * 2
            self.log.log("robot_attack", player=order.player,
                         world=fleet.world_id, robots_landed=robots,
                         people_killed=people_killed)

        # Fleet-to-fleet combat
        for order in orders_by_type.get(OrderType.FIRE_FLEET, []):
            self._resolve_fire_fleet(order)

        # Fire at industry
        for order in orders_by_type.get(OrderType.FIRE_INDUSTRY, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if not fleet or fleet.owner != order.player:
                continue
            world = self.state.worlds.get(fleet.world_id)
            shots = fleet.fire_power()
            # Destroy ISHPS first (2 hits each)
            iships_destroyed = min(world.i_ships, shots // 2)
            shots -= iships_destroyed * 2
            world.i_ships -= iships_destroyed
            # Then industry (2 hits each)
            industry_destroyed = min(world.industry, shots // 2)
            world.industry -= industry_destroyed
            fleet.fired_this_turn = True
            self.log.log("fire_industry", player=order.player,
                         world=fleet.world_id, iships_killed=iships_destroyed,
                         industry_killed=industry_destroyed)

        # Fire at population
        for order in orders_by_type.get(OrderType.FIRE_POPULATION, []):
            fleet = self.state.fleets.get(order.fleet_id)
            if not fleet or fleet.owner != order.player:
                continue
            world = self.state.worlds.get(fleet.world_id)
            shots = fleet.fire_power()
            # Destroy PSHPS first (2 hits each)
            pships_destroyed = min(world.p_ships, shots // 2)
            shots -= pships_destroyed * 2
            world.p_ships -= pships_destroyed
            # Then population (2 hits per 1 pop)
            pop_killed = min(world.population + world.converts, shots // 2)
            world.population = max(0, world.population - pop_killed)
            fleet.fired_this_turn = True

            player = self.state.players[order.player]
            if player.character_type == CharacterType.BERSERKER:
                player.score += pop_killed * 2
            elif player.character_type != CharacterType.APOSTLE or not player.jihad_target:
                player.score -= pop_killed
            self.log.log("fire_population", player=order.player,
                         world=fleet.world_id, pop_killed=pop_killed)

    def _resolve_fire_fleet(self, order: Order):
        fleet = self.state.fleets.get(order.fleet_id)
        target = self.state.fleets.get(order.target_fleet_id)
        if not fleet or not target or fleet.owner != order.player:
            return
        if fleet.world_id != target.world_id:
            return

        player = self.state.players[order.player]
        is_merchant = player.character_type == CharacterType.MERCHANT
        shots = fleet.fire_power(is_merchant)

        # If target is fleeing, half hits
        if target.moved_this_turn:
            shots //= 2

        # 2 shots = 1 unloaded ship, or 2 loaded ships
        if target.cargo > 0:
            destroyed = shots
        else:
            destroyed = shots // 2

        destroyed = min(destroyed, target.ships)
        target.ships -= destroyed
        fleet.fired_this_turn = True

        if target.ships <= 0:
            if player.character_type == CharacterType.BERSERKER:
                player.score += destroyed * 2
            self.log.log("fleet_destroyed", player=order.player,
                         target_fleet=order.target_fleet_id, ships_destroyed=destroyed)
        else:
            self.log.log("fleet_damaged", player=order.player,
                         target_fleet=order.target_fleet_id, ships_destroyed=destroyed)

    def _process_pirate_capture(self):
        """Pirates capture all enemy fleets if they outnumber by >3:1."""
        pirates = [p for p in self.state.players.values()
                   if p.character_type == CharacterType.PIRATE]
        for pirate in pirates:
            pirate_fleets = self.state.get_player_fleets(pirate.code_name)
            for world_id in set(f.world_id for f in pirate_fleets):
                my_ships = sum(f.ships for f in pirate_fleets if f.world_id == world_id)
                enemy_fleets = [
                    f for f in self.state.get_fleets_at_world(world_id)
                    if f.owner != pirate.code_name and f.owner is not None
                    and not pirate.is_ally(f.owner)
                ]
                enemy_ships = sum(f.ships for f in enemy_fleets)
                if enemy_ships > 0 and my_ships > enemy_ships * 3:
                    for ef in enemy_fleets:
                        ef.owner = pirate.code_name
                        pirate.score += 3  # 3 pts per key
                        self.log.log("pirate_capture", player=pirate.code_name,
                                     fleet=ef.id, world=world_id)

    def _process_world_capture(self):
        """Determine world ownership based on presence."""
        for world in self.state.worlds.values():
            if world.is_black_hole or world.busted:
                continue
            fleets_here = self.state.get_fleets_at_world(world.id)
            players_with_ships = set()
            for f in fleets_here:
                if f.owner and f.ships > 0 and not f.at_peace:
                    players_with_ships.add(f.owner)

            if len(players_with_ships) == 1:
                sole_player = list(players_with_ships)[0]
                if world.owner != sole_player:
                    # Check ally protection
                    if world.owner:
                        owner_player = self.state.players.get(world.owner)
                        capturer = self.state.players.get(sole_player)
                        if capturer and capturer.is_ally(world.owner):
                            continue
                    if world.population > 0 or world.robots > 0:
                        old_owner = world.owner
                        world.owner = sole_player
                        world.turns_owned = 1
                        self.log.log("world_captured", player=sole_player,
                                     world=world.id, from_player=old_owner)

    def _process_growth(self):
        """Population growth (~10%) and mine increase (every 7 turns)."""
        for world in self.state.worlds.values():
            if not world.owner or world.busted:
                continue

            # Population growth (10%)
            if world.population > 0 and world.population < world.pop_limit:
                growth = max(1, world.population // 10)
                world.population = min(world.pop_limit, world.population + growth)
                # Apostle: new pop = converts
                owner = self.state.players.get(world.owner)
                if owner and owner.character_type == CharacterType.APOSTLE:
                    world.converts += growth

            # Mine production
            pop_available = world.population
            produced = min(world.mines, pop_available)
            world.metal += produced

            # Mine growth (every 7 turns)
            if world.mines > 0:
                world.turns_owned += 1
                if world.turns_owned >= 7:
                    world.mines = min(31, world.mines + 1)
                    world.turns_owned = 0

    def _process_scoring(self):
        """Calculate per-turn scoring for each character type."""
        for player in self.state.players.values():
            worlds = self.state.get_player_worlds(player.code_name)

            if player.character_type == CharacterType.EMPIRE_BUILDER:
                for w in worlds:
                    player.score += w.population // 10
                    player.score += w.industry
                    player.score += w.mines

            elif player.character_type == CharacterType.PIRATE:
                fleets = self.state.get_player_fleets(player.code_name)
                player.score += len(fleets) * 3  # 3 per key

            elif player.character_type == CharacterType.BERSERKER:
                for w in worlds:
                    if w.robots > 0:
                        player.score += 5

            elif player.character_type == CharacterType.APOSTLE:
                player.score += len(worlds) * 5
                total_converts = sum(w.converts for w in self.state.worlds.values()
                                     if w.convert_owner == player.code_name)
                player.score += total_converts // 10
                for w in worlds:
                    if w.converts > 0 and w.population == 0:
                        player.score += 5

            elif player.character_type == CharacterType.ARTIFACT_COLLECTOR:
                for a in self.state.artifacts.values():
                    if self._artifact_owner(a) == player.code_name:
                        if a.category == "ancient" or a.category == "pyramid":
                            player.score += 30
                        elif a.category == "plastic":
                            pass
                        elif a.category == "special":
                            player.score += 30
                        else:
                            player.score += 15

            # Artifact scoring for non-collectors
            if player.character_type != CharacterType.ARTIFACT_COLLECTOR:
                cats = CHARACTER_ARTIFACT_CATEGORIES.get(player.character_type, [])
                for a in self.state.artifacts.values():
                    if self._artifact_owner(a) == player.code_name:
                        if a.category in cats:
                            player.score += 5
                        if a.category == "plastic":
                            player.score -= 10

    def _artifact_owner(self, artifact) -> Optional[str]:
        if artifact.location_type == "world":
            world = self.state.worlds.get(artifact.location_id)
            return world.owner if world else None
        elif artifact.location_type == "fleet":
            fleet = self.state.fleets.get(artifact.location_id)
            return fleet.owner if fleet else None
        return None

    def _check_victory(self):
        for player in self.state.players.values():
            if player.score >= self.state.ending_score:
                self.state.game_over = True
                # Winner = highest score
                winner = max(self.state.players.values(), key=lambda p: p.score)
                self.state.winner = winner.code_name
                self.log.log("game_over", winner=winner.code_name, score=winner.score)
                break


# Import here to avoid circular
from .models import CHARACTER_ARTIFACT_CATEGORIES
