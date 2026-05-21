"""AI Player Agents for StarWeb.

Each agent implements a strategy based on its character type.
Agents analyze game state and produce orders automatically.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Optional

from .models import CharacterType, Fleet, GameState, Player, World
from .orders import Order, OrderType


class BaseAgent(ABC):
    """Base class for all AI player agents."""

    def __init__(self, player_name: str, state: GameState):
        self.player_name = player_name
        self.state = state
        self.player = state.players[player_name]

    @abstractmethod
    def generate_orders(self) -> list[Order]:
        """Generate orders for this turn."""
        ...

    def my_fleets(self) -> list[Fleet]:
        return self.state.get_player_fleets(self.player_name)

    def my_worlds(self) -> list[World]:
        return self.state.get_player_worlds(self.player_name)

    def worlds_with_presence(self) -> set[int]:
        """All worlds where we have fleets or ownership."""
        worlds = set(w.id for w in self.my_worlds())
        for f in self.my_fleets():
            worlds.add(f.world_id)
        return worlds

    def unexplored_adjacent(self) -> list[int]:
        """Worlds adjacent to any world where we have presence that we haven't visited."""
        presence = self.worlds_with_presence()
        adjacent = set()
        for wid in presence:
            w = self.state.worlds.get(wid)
            if w:
                for conn in w.connections:
                    if conn not in presence:
                        adjacent.add(conn)
        return list(adjacent)

    def enemy_fleets_at(self, world_id: int) -> list[Fleet]:
        return [f for f in self.state.get_fleets_at_world(world_id)
                if f.owner != self.player_name and f.owner is not None and f.ships > 0]

    def _explore_orders(self) -> list[Order]:
        """Send idle fleets to explore unknown adjacent worlds."""
        orders = []
        presence = self.worlds_with_presence()
        idle_fleets = [f for f in self.my_fleets()
                       if f.ships > 0 and not f.moved_this_turn]

        # Shuffle to vary exploration patterns
        random.shuffle(idle_fleets)
        used_targets = set()

        for fleet in idle_fleets:
            current_world = self.state.worlds.get(fleet.world_id)
            if not current_world:
                continue
            # Find a connection we haven't been to yet
            candidates = [c for c in current_world.connections
                          if c not in presence and c not in used_targets]
            if not candidates:
                # All adjacent explored — pick a random unvisited connection to keep moving
                candidates = [c for c in current_world.connections
                              if c not in used_targets]
            if candidates:
                target = random.choice(candidates)
                used_targets.add(target)
                orders.append(Order(OrderType.MOVE, self.player_name,
                                    fleet_id=fleet.id, waypoints=[target]))
        return orders

    def _load_metal_orders(self) -> list[Order]:
        """Load metal onto fleets at owned worlds."""
        orders = []
        for fleet in self.my_fleets():
            if fleet.ships == 0:
                continue
            world = self.state.worlds.get(fleet.world_id)
            if world and world.owner == self.player_name and world.metal > 0:
                if fleet.cargo < fleet.ships:
                    orders.append(Order(OrderType.LOAD, self.player_name,
                                        fleet_id=fleet.id))
        return orders

    def _unload_at_home_orders(self) -> list[Order]:
        """Unload cargo at homeworld or industrial worlds."""
        orders = []
        for fleet in self.my_fleets():
            if fleet.cargo > 0:
                world = self.state.worlds.get(fleet.world_id)
                if world and world.owner == self.player_name and world.industry > 5:
                    orders.append(Order(OrderType.UNLOAD, self.player_name,
                                        fleet_id=fleet.id))
        return orders

    def _build_orders(self) -> list[Order]:
        """Build ships at worlds with available resources."""
        orders = []
        for world in self.my_worlds():
            if world.can_build:
                # Build onto fleets at this world
                fleets_here = [f for f in self.my_fleets() if f.world_id == world.id]
                if fleets_here:
                    fleet = fleets_here[0]
                    build_qty = min(world.industry, world.metal, world.population)
                    if build_qty > 0:
                        orders.append(Order(OrderType.BUILD_FLEET, self.player_name,
                                            world_id=world.id, quantity=build_qty,
                                            target_fleet_id=fleet.id))
        return orders

    def _defensive_orders(self) -> list[Order]:
        """Fire at enemy fleets at our worlds."""
        orders = []
        for world in self.my_worlds():
            enemies = self.enemy_fleets_at(world.id)
            if enemies:
                my_fleets_here = [f for f in self.my_fleets()
                                  if f.world_id == world.id and f.ships > 0]
                for fleet in my_fleets_here:
                    target = enemies[0]
                    orders.append(Order(OrderType.FIRE_FLEET, self.player_name,
                                        fleet_id=fleet.id,
                                        target_fleet_id=target.id))
                    break
        return orders


class EmpireBuilderAgent(BaseAgent):
    """Expand territory, maximize industry and population."""

    def generate_orders(self) -> list[Order]:
        orders = []
        orders.extend(self._unload_at_home_orders())
        orders.extend(self._load_metal_orders())
        orders.extend(self._defensive_orders())

        # Prioritize building industry
        for world in self.my_worlds():
            if world.industry >= 4 and world.metal >= 4 and world.population >= 4:
                qty = min(world.industry // 4, world.metal // 4, world.population // 4, 2)
                if qty > 0:
                    orders.append(Order(OrderType.BUILD_INDUSTRY, self.player_name,
                                        world_id=world.id, quantity=qty))

        orders.extend(self._build_orders())
        orders.extend(self._explore_orders())
        return orders


class MerchantAgent(BaseAgent):
    """Trade metal to other players' worlds for points."""

    def generate_orders(self) -> list[Order]:
        orders = []
        orders.extend(self._load_metal_orders())

        # Find other players' worlds to unload on
        other_worlds = [w for w in self.state.worlds.values()
                        if w.owner and w.owner != self.player_name and w.industry > 0]

        for fleet in self.my_fleets():
            if fleet.cargo > 0:
                # Move toward nearest other-player world with industry
                current = self.state.worlds[fleet.world_id]
                for conn in current.connections:
                    target_world = self.state.worlds.get(conn)
                    if target_world and target_world.owner and \
                       target_world.owner != self.player_name and target_world.industry > 0:
                        orders.append(Order(OrderType.MOVE, self.player_name,
                                            fleet_id=fleet.id, waypoints=[conn]))
                        break
                else:
                    # Unload at any known other-player world we're already at
                    world = self.state.worlds.get(fleet.world_id)
                    if world and world.owner and world.owner != self.player_name:
                        orders.append(Order(OrderType.UNLOAD, self.player_name,
                                            fleet_id=fleet.id))

        orders.extend(self._build_orders())
        orders.extend(self._explore_orders())
        return orders


class PirateAgent(BaseAgent):
    """Plunder worlds and capture fleets."""

    def generate_orders(self) -> list[Order]:
        orders = []
        orders.extend(self._load_metal_orders())

        # Plunder owned worlds (if beneficial)
        for world in self.my_worlds():
            if world.population > 5 and world.plunder_count < 3:
                orders.append(Order(OrderType.PLUNDER, self.player_name,
                                    world_id=world.id))
                break  # Only plunder one per turn

        # Concentrate fleets for capture opportunities
        orders.extend(self._build_orders())
        orders.extend(self._defensive_orders())
        orders.extend(self._explore_orders())
        return orders


class ArtifactCollectorAgent(BaseAgent):
    """Collect artifacts, build museums."""

    def generate_orders(self) -> list[Order]:
        orders = []
        orders.extend(self._unload_at_home_orders())
        orders.extend(self._load_metal_orders())

        # Move toward worlds with artifacts
        artifact_worlds = set()
        for a in self.state.artifacts.values():
            if a.location_type == "world":
                world = self.state.worlds.get(a.location_id)
                if world and world.owner != self.player_name:
                    artifact_worlds.add(a.location_id)

        idle_fleets = [f for f in self.my_fleets()
                       if f.ships > 0 and not f.moved_this_turn]
        for fleet in idle_fleets:
            current = self.state.worlds[fleet.world_id]
            for conn in current.connections:
                if conn in artifact_worlds:
                    orders.append(Order(OrderType.MOVE, self.player_name,
                                        fleet_id=fleet.id, waypoints=[conn]))
                    break

        orders.extend(self._build_orders())
        orders.extend(self._defensive_orders())
        orders.extend(self._explore_orders())
        return orders


class BerserkerAgent(BaseAgent):
    """Kill all life, deploy robots."""

    def generate_orders(self) -> list[Order]:
        orders = []
        orders.extend(self._load_metal_orders())

        # Robot attacks on populated worlds
        for fleet in self.my_fleets():
            if fleet.ships >= 3:
                world = self.state.worlds.get(fleet.world_id)
                if world and world.population > 0 and world.owner != self.player_name:
                    robot_qty = min(fleet.ships // 2, 5)
                    orders.append(Order(OrderType.ROBOT_ATTACK, self.player_name,
                                        fleet_id=fleet.id, quantity=robot_qty))
                    break

        # Fire at population on enemy worlds
        for fleet in self.my_fleets():
            world = self.state.worlds.get(fleet.world_id)
            if world and world.population > 0 and world.owner != self.player_name:
                orders.append(Order(OrderType.FIRE_POPULATION, self.player_name,
                                    fleet_id=fleet.id))

        orders.extend(self._build_orders())
        orders.extend(self._explore_orders())
        return orders


class ApostleAgent(BaseAgent):
    """Convert populations, avoid combat."""

    def generate_orders(self) -> list[Order]:
        orders = []
        orders.extend(self._unload_at_home_orders())
        orders.extend(self._load_metal_orders())

        # Move fleets to populated worlds for conversion (passive)
        for fleet in self.my_fleets():
            if fleet.ships > 0 and not fleet.moved_this_turn:
                current = self.state.worlds[fleet.world_id]
                best_target = None
                best_pop = 0
                for conn in current.connections:
                    target = self.state.worlds.get(conn)
                    if target and target.population > best_pop and \
                       target.owner != self.player_name:
                        best_target = conn
                        best_pop = target.population
                if best_target:
                    orders.append(Order(OrderType.MOVE, self.player_name,
                                        fleet_id=fleet.id, waypoints=[best_target]))

        orders.extend(self._build_orders())
        return orders


# Agent factory
AGENT_CLASSES = {
    CharacterType.EMPIRE_BUILDER: EmpireBuilderAgent,
    CharacterType.MERCHANT: MerchantAgent,
    CharacterType.PIRATE: PirateAgent,
    CharacterType.ARTIFACT_COLLECTOR: ArtifactCollectorAgent,
    CharacterType.BERSERKER: BerserkerAgent,
    CharacterType.APOSTLE: ApostleAgent,
}


def create_agent(player_name: str, state: GameState) -> BaseAgent:
    """Factory: create the appropriate agent for a player's character type."""
    player = state.players[player_name]
    agent_class = AGENT_CLASSES[player.character_type]
    return agent_class(player_name, state)
