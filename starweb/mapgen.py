"""Map generation for StarWeb games."""

from __future__ import annotations

import random
from dataclasses import dataclass

import networkx as nx

from .models import Artifact, Fleet, GameState, Player, World


@dataclass
class MapConfig:
    num_worlds: int = 32
    num_players: int = 8
    min_connections: int = 2
    max_connections: int = 5
    black_hole_ratio: float = 0.03
    artifact_count: int = 8
    max_hop_distance: float = 12.0  # Max distance for a connection
    galaxy_radius: float = 50.0    # Radius of the galaxy sphere


def _generate_3d_positions(n: int, radius: float) -> list[tuple[float, float, float]]:
    """Generate n points distributed in a 3D galaxy shape (flattened sphere)."""
    import math
    positions = []
    golden_ratio = (1 + math.sqrt(5)) / 2
    for i in range(n):
        # Fibonacci sphere with flattening for galaxy disc shape
        theta = 2 * math.pi * i / golden_ratio
        phi = math.acos(1 - 2 * (i + 0.5) / n)
        r = radius * (0.3 + 0.7 * (i / n) ** 0.5)  # Denser core
        x = r * math.sin(phi) * math.cos(theta)
        y = r * math.sin(phi) * math.sin(theta) * 0.3  # Flatten Y for disc
        z = r * math.cos(phi)
        # Add jitter
        x += random.uniform(-1.5, 1.5)
        y += random.uniform(-0.5, 0.5)
        z += random.uniform(-1.5, 1.5)
        positions.append((round(x, 2), round(y, 2), round(z, 2)))
    return positions


def generate_map(config: MapConfig, game_id: str) -> GameState:
    """Generate a randomized StarWeb galaxy map with 3D spatial positions."""
    import math
    state = GameState(game_id=game_id)

    # Generate 3D positions
    positions = _generate_3d_positions(config.num_worlds, config.galaxy_radius)

    # Designate black holes
    black_holes = set(random.sample(
        range(config.num_worlds),
        int(config.num_worlds * config.black_hole_ratio)
    ))

    # Create worlds with positions
    for i in range(config.num_worlds):
        world_id = i + 1
        is_bh = i in black_holes
        x, y, z = positions[i]

        world = World(
            id=world_id,
            connections=[],
            is_black_hole=is_bh,
            x=x, y=y, z=z,
            mines=0 if is_bh else random.randint(0, 6),
            pop_limit=0 if is_bh else random.randint(5, 50),
        )

        if not is_bh and world.mines > 0:
            world.population = random.randint(0, min(10, world.pop_limit))
            world.metal = random.randint(0, 5)
            if random.random() < 0.15:
                world.i_ships = random.randint(1, 5)
            if random.random() < 0.1:
                world.p_ships = random.randint(1, 3)

        state.worlds[world_id] = world

    # Build distance-based connections
    for i in range(config.num_worlds):
        w1 = state.worlds[i + 1]
        for j in range(i + 1, config.num_worlds):
            w2 = state.worlds[j + 1]
            dist = math.sqrt((w1.x - w2.x)**2 + (w1.y - w2.y)**2 + (w1.z - w2.z)**2)
            if dist <= config.max_hop_distance:
                w1.connections.append(w2.id)
                w2.connections.append(w1.id)

    # Ensure connectivity: connect isolated worlds to nearest neighbor
    for w in state.worlds.values():
        if not w.connections:
            nearest = None
            nearest_dist = float('inf')
            for other in state.worlds.values():
                if other.id == w.id:
                    continue
                dist = math.sqrt((w.x - other.x)**2 + (w.y - other.y)**2 + (w.z - other.z)**2)
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest = other
            if nearest:
                w.connections.append(nearest.id)
                nearest.connections.append(w.id)

    # Trim over-connected worlds to max_connections (keep shortest)
    for w in state.worlds.values():
        if len(w.connections) > config.max_connections:
            # Sort by distance, keep closest
            w.connections.sort(key=lambda cid: math.sqrt(
                (w.x - state.worlds[cid].x)**2 +
                (w.y - state.worlds[cid].y)**2 +
                (w.z - state.worlds[cid].z)**2
            ))
            removed = w.connections[config.max_connections:]
            w.connections = w.connections[:config.max_connections]
            # Clean up reverse connections
            for rid in removed:
                other = state.worlds[rid]
                if w.id in other.connections:
                    other.connections.remove(w.id)

    # Ensure graph is connected using BFS; bridge disconnected components
    visited = set()
    queue = [1]
    visited.add(1)
    while queue:
        node = queue.pop(0)
        for conn in state.worlds[node].connections:
            if conn not in visited:
                visited.add(conn)
                queue.append(conn)
    # Connect any unreachable worlds
    for wid in state.worlds:
        if wid not in visited:
            # Find nearest visited world
            w = state.worlds[wid]
            nearest = min(visited, key=lambda vid: math.sqrt(
                (w.x - state.worlds[vid].x)**2 +
                (w.y - state.worlds[vid].y)**2 +
                (w.z - state.worlds[vid].z)**2
            ))
            w.connections.append(nearest)
            state.worlds[nearest].connections.append(wid)
            visited.add(wid)

    # Place artifacts
    _place_artifacts(state, config)

    return state


def setup_players(state: GameState, player_configs: list[dict]) -> None:
    """Set up players with home worlds and starting fleets."""
    # Find suitable homeworlds (well-connected, not black holes, with mines)
    candidates = [
        w for w in state.worlds.values()
        if not w.is_black_hole and w.mines >= 2 and len(w.connections) >= 3
    ]
    random.shuffle(candidates)

    fleet_id = 1
    for i, pconfig in enumerate(player_configs):
        player = Player(
            code_name=pconfig["name"],
            character_type=pconfig["type"],
            is_ai=pconfig.get("is_ai", False),
        )

        # Assign homeworld
        hw = candidates[i]
        hw.owner = player.code_name
        hw.population = 25
        hw.pop_limit = 50
        hw.industry = 28
        hw.mines = 2
        hw.metal = 30
        hw.i_ships = 0
        hw.p_ships = 0
        player.home_world = hw.id

        # Clear adjacent worlds for fair start
        for adj_id in hw.connections:
            adj = state.worlds.get(adj_id)
            if adj and not adj.is_black_hole:
                adj.owner = None
                adj.population = 0

        # Starting fleets (2 fleets with varying ships)
        for j in range(2):
            fleet = Fleet(
                id=fleet_id,
                owner=player.code_name,
                ships=random.randint(3, 8),
                world_id=hw.id,
            )
            state.fleets[fleet_id] = fleet
            fleet_id += 1

        state.players[player.code_name] = player


def _place_artifacts(state: GameState, config: MapConfig) -> None:
    """Distribute artifacts across the galaxy."""
    categories = [
        ("golden", ["Golden Sword", "Golden Shield", "Golden Helm",
                    "Golden Ring", "Golden Chalice", "Golden Harp",
                    "Golden Crown", "Golden Lance", "Golden Orb"]),
        ("silver", ["Silver Sword", "Silver Shield", "Silver Helm",
                    "Silver Ring", "Silver Chalice", "Silver Harp",
                    "Silver Crown", "Silver Lance", "Silver Orb"]),
        ("ancient", ["Ancient Sword", "Ancient Shield", "Ancient Helm",
                     "Ancient Ring", "Ancient Chalice", "Ancient Harp",
                     "Ancient Crown", "Ancient Lance", "Ancient Orb"]),
        ("blessed", ["Blessed Sword", "Blessed Shield", "Blessed Helm",
                     "Blessed Ring", "Blessed Chalice", "Blessed Harp",
                     "Blessed Crown", "Blessed Lance", "Blessed Orb"]),
        ("titanium", ["Titanium Sword", "Titanium Shield", "Titanium Helm",
                      "Titanium Ring", "Titanium Chalice", "Titanium Harp",
                      "Titanium Crown", "Titanium Lance", "Titanium Orb"]),
        ("pyramid", ["Jade Pyramid", "Crystal Pyramid", "Obsidian Pyramid",
                     "Ruby Pyramid", "Emerald Pyramid", "Diamond Pyramid",
                     "Sapphire Pyramid", "Onyx Pyramid", "Ivory Pyramid"]),
        ("plastic", ["Plastic Crown", "Plastic Sword", "Plastic Pyramid",
                     "Plastic Ring", "Plastic Shield"]),
        ("special", ["Treasure of Polaris", "Slippers of Venus",
                     "Radioactive Isotope", "Lesser of Two Evils",
                     "Nebula Scroll Vol 1", "Nebula Scroll Vol 2",
                     "Nebula Scroll Vol 3", "Nebula Scroll Vol 4",
                     "Nebula Scroll Vol 5", "Black Box"]),
    ]

    eligible_worlds = [
        w.id for w in state.worlds.values()
        if not w.is_black_hole and w.owner is None
    ]
    random.shuffle(eligible_worlds)

    artifact_id = 1
    world_idx = 0
    placed = 0
    for category, names in categories:
        for name in names:
            if placed >= config.artifact_count:
                break
            if world_idx >= len(eligible_worlds):
                world_idx = 0
                random.shuffle(eligible_worlds)
            artifact = Artifact(
                id=artifact_id,
                name=name,
                category=category,
                location_type="world",
                location_id=eligible_worlds[world_idx],
            )
            state.artifacts[artifact_id] = artifact
            state.worlds[eligible_worlds[world_idx]].artifacts.append(artifact_id)
            artifact_id += 1
            world_idx += 1
            placed += 1
        if placed >= config.artifact_count:
            break
