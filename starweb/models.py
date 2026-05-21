"""Core game models for StarWeb PBM."""

from __future__ import annotations

import enum
import random
from dataclasses import dataclass, field
from typing import Optional


class CharacterType(enum.Enum):
    EMPIRE_BUILDER = "empire_builder"
    MERCHANT = "merchant"
    PIRATE = "pirate"
    ARTIFACT_COLLECTOR = "artifact_collector"
    BERSERKER = "berserker"
    APOSTLE = "apostle"


class ArtifactCategory(enum.Enum):
    GOLDEN = "golden"
    RING = "ring"
    SILVER = "silver"
    BLESSED = "blessed"
    TITANIUM = "titanium"
    ANCIENT = "ancient"
    CROWN = "crown"
    LANCE = "lance"
    LODESTAR = "lodestar"
    SEPULCHRE = "sepulchre"
    SWORD = "sword"
    PYRAMID = "pyramid"
    PLASTIC = "plastic"
    SPECIAL = "special"


# Character type -> artifact categories that award 5pts/turn
CHARACTER_ARTIFACT_CATEGORIES = {
    CharacterType.EMPIRE_BUILDER: ["golden", "crown"],
    CharacterType.MERCHANT: ["golden", "ring"],
    CharacterType.PIRATE: ["silver", "lodestar"],
    CharacterType.APOSTLE: ["blessed", "sepulchre"],
    CharacterType.BERSERKER: ["titanium", "sword"],
    CharacterType.ARTIFACT_COLLECTOR: ["ancient", "pyramid"],
}


@dataclass
class Artifact:
    id: int
    name: str
    category: str  # e.g. "golden", "plastic", "special"
    location_type: str = "world"  # "world" or "fleet"
    location_id: int = 0


@dataclass
class Fleet:
    id: int
    owner: Optional[str] = None  # player code name, None = neutral
    ships: int = 0
    cargo: int = 0
    world_id: int = 0
    at_peace: bool = False
    has_pbb: bool = False
    artifacts: list[int] = field(default_factory=list)
    moved_this_turn: bool = False
    fired_this_turn: bool = False

    @property
    def is_neutral(self) -> bool:
        return self.owner is None

    def max_cargo(self, is_merchant: bool = False) -> int:
        return self.ships * (2 if is_merchant else 1)

    def fire_power(self, is_merchant: bool = False) -> int:
        if is_merchant:
            overloaded = max(0, self.cargo - self.ships)
            return self.ships - overloaded
        return self.ships


@dataclass
class World:
    id: int
    owner: Optional[str] = None
    population: int = 0
    pop_limit: int = 0
    industry: int = 0
    mines: int = 0
    metal: int = 0
    i_ships: int = 0
    p_ships: int = 0
    robots: int = 0
    converts: int = 0
    convert_owner: Optional[str] = None
    connections: list[int] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    turns_owned: int = 0
    plunder_count: int = 0
    plunder_recovery: int = 0
    cg_unloaded: int = 0
    busted: bool = False
    is_black_hole: bool = False
    artifacts: list[int] = field(default_factory=list)

    @property
    def effective_industry(self) -> int:
        if self.busted:
            return 0
        return self.industry

    @property
    def can_build(self) -> bool:
        return self.industry > 0 and self.population > 0 and self.metal > 0

    def production_capacity(self) -> int:
        """Metal produced per turn = min(mines, population available for mining)."""
        pop_for_mining = max(0, self.population - self.industry)
        return min(self.mines, pop_for_mining) if not self.busted else 0


@dataclass
class Player:
    code_name: str
    character_type: CharacterType
    score: int = 0
    home_world: int = 0
    allies: set[str] = field(default_factory=set)
    loaders: set[str] = field(default_factory=set)
    jihad_target: Optional[str] = None
    ending_score_vote: int = 5000
    is_ai: bool = False

    def is_ally(self, other: str) -> bool:
        return other in self.allies

    def is_loader(self, other: str) -> bool:
        return other in self.loaders


@dataclass
class GameState:
    game_id: str
    turn_number: int = 0
    worlds: dict[int, World] = field(default_factory=dict)
    fleets: dict[int, Fleet] = field(default_factory=dict)
    players: dict[str, Player] = field(default_factory=dict)
    artifacts: dict[int, Artifact] = field(default_factory=dict)
    ending_score: int = 5000
    game_over: bool = False
    winner: Optional[str] = None

    def get_player_fleets(self, player: str) -> list[Fleet]:
        return [f for f in self.fleets.values() if f.owner == player]

    def get_player_worlds(self, player: str) -> list[World]:
        return [w for w in self.worlds.values() if w.owner == player]

    def get_fleets_at_world(self, world_id: int) -> list[Fleet]:
        return [f for f in self.fleets.values() if f.world_id == world_id]

    def get_world_artifacts(self, world_id: int) -> list[Artifact]:
        return [a for a in self.artifacts.values()
                if a.location_type == "world" and a.location_id == world_id]

    def get_fleet_artifacts(self, fleet_id: int) -> list[Artifact]:
        return [a for a in self.artifacts.values()
                if a.location_type == "fleet" and a.location_id == fleet_id]
