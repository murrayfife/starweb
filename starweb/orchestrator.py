"""Game orchestrator - ties together all systems for automated play."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .agents import create_agent
from .bulletin import BoardType, BulletinBoard
from .comms import CommunicationSystem, MessageType
from .engine import TurnLog, TurnProcessor
from .mapgen import MapConfig, generate_map, setup_players
from .models import CharacterType, GameState
from .narrative import generate_narrative
from .orders import Order, OrderParser


@dataclass
class GameConfig:
    game_id: str
    num_players: int = 8
    num_ai_players: int = 6
    num_human_players: int = 2
    map_config: MapConfig = field(default_factory=MapConfig)
    auto_process: bool = True
    turn_deadline_seconds: int = 86400  # 24 hours per turn
    storage_dir: Path = field(default_factory=lambda: Path("games"))


class GameOrchestrator:
    """Main orchestrator for running a StarWeb game."""

    def __init__(self, config: GameConfig):
        self.config = config
        self.state: Optional[GameState] = None
        self.board: Optional[BulletinBoard] = None
        self.comms: Optional[CommunicationSystem] = None
        self.turn_logs: list[TurnLog] = []
        self._pending_orders: dict[str, list[Order]] = {}
        self._parser = OrderParser()
        self._state_dir = config.storage_dir / config.game_id
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def new_game(self, player_configs: list[dict]) -> GameState:
        """Initialize a new game with the given players."""
        self.state = generate_map(self.config.map_config, self.config.game_id)
        setup_players(self.state, player_configs)

        # Average ending score votes
        votes = [p.ending_score_vote for p in self.state.players.values()]
        self.state.ending_score = sum(votes) // len(votes) if votes else 5000

        # Initialize subsystems
        self.board = BulletinBoard(self.config.game_id, self.config.storage_dir)
        self.comms = CommunicationSystem(self.config.game_id, self.config.storage_dir)

        # Post game start announcement
        self.board.post(
            BoardType.ANNOUNCEMENTS, "GM",
            "Game Started",
            f"StarWeb Game {self.config.game_id} has begun with {len(player_configs)} players.\n"
            f"May the stars guide your path.",
            turn=0
        )

        self._save_state()
        return self.state

    def load_game(self) -> GameState:
        """Load an existing game from storage."""
        state_file = self._state_dir / "state.json"
        if not state_file.exists():
            raise FileNotFoundError(f"No game found at {state_file}")
        self.state = self._deserialize_state(json.loads(state_file.read_text()))
        self.board = BulletinBoard(self.config.game_id, self.config.storage_dir)
        self.comms = CommunicationSystem(self.config.game_id, self.config.storage_dir)
        # Migrate: assign 3D coords if missing
        self._migrate_3d_coords()
        return self.state

    def submit_orders(self, player: str, orders_text: str) -> list[Order]:
        """Submit orders for a human player (text format)."""
        orders = self._parser.parse_turn(orders_text, player)
        self._pending_orders[player] = orders
        return orders

    def generate_ai_orders(self) -> dict[str, list[Order]]:
        """Generate orders for all AI players."""
        ai_orders = {}
        for player in self.state.players.values():
            if player.is_ai:
                agent = create_agent(player.code_name, self.state)
                orders = agent.generate_orders()
                ai_orders[player.code_name] = orders
                self._pending_orders[player.code_name] = orders
        return ai_orders

    def process_turn(self) -> TurnLog:
        """Process the current turn with all submitted orders."""
        if not self.state:
            raise RuntimeError("No game loaded")

        # Generate AI orders if not already done
        for player in self.state.players.values():
            if player.is_ai and player.code_name not in self._pending_orders:
                agent = create_agent(player.code_name, self.state)
                self._pending_orders[player.code_name] = agent.generate_orders()

        # Process the turn
        processor = TurnProcessor(self.state)
        log = processor.process_turn(self._pending_orders)
        self.turn_logs.append(log)

        # Deliver queued messages
        delivered = self.comms.deliver_messages(self.state.turn_number)
        for msg in delivered:
            log.log("message_delivered", player=msg.recipient,
                    sender=msg.sender, subject=msg.subject)

        # AI diplomacy: agents may send messages based on game state
        self._ai_diplomacy()

        # Post turn summary to bulletin board
        self._post_turn_summary(log)

        # Clear pending orders
        self._pending_orders.clear()

        # Reset fleet flags
        for fleet in self.state.fleets.values():
            fleet.moved_this_turn = False
            fleet.fired_this_turn = False

        # Save
        self._save_state()
        self._save_log(log)

        return log

    def run_auto(self, num_turns: int = 1) -> list[TurnLog]:
        """Run multiple turns automatically (all AI)."""
        logs = []
        for _ in range(num_turns):
            if self.state.game_over:
                break
            log = self.process_turn()
            logs.append(log)
        return logs

    def get_player_report(self, player: str) -> dict:
        """Generate the turn report for a player (what they can see)."""
        if not self.state:
            return {}

        player_obj = self.state.players[player]
        visible_worlds = set()

        # Worlds owned
        for w in self.state.get_player_worlds(player):
            visible_worlds.add(w.id)
            for conn in w.connections:
                visible_worlds.add(conn)

        # Worlds with fleets
        for f in self.state.get_player_fleets(player):
            visible_worlds.add(f.world_id)
            w = self.state.worlds.get(f.world_id)
            if w:
                for conn in w.connections:
                    visible_worlds.add(conn)

        # Home world always visible
        visible_worlds.add(player_obj.home_world)

        worlds_report = {}
        for wid in visible_worlds:
            w = self.state.worlds.get(wid)
            if w:
                worlds_report[wid] = {
                    "owner": w.owner,
                    "population": w.population,
                    "industry": w.industry,
                    "mines": w.mines,
                    "metal": w.metal,
                    "i_ships": w.i_ships,
                    "p_ships": w.p_ships,
                    "connections": w.connections,
                    "fleets": [
                        {"id": f.id, "owner": f.owner, "ships": f.ships,
                         "cargo": f.cargo if f.owner == player else None}
                        for f in self.state.get_fleets_at_world(wid)
                    ],
                }

        return {
            "game_id": self.config.game_id,
            "turn": self.state.turn_number,
            "player": player,
            "score": player_obj.score,
            "character_type": player_obj.character_type.value,
            "worlds": worlds_report,
            "fleets": [
                {"id": f.id, "ships": f.ships, "cargo": f.cargo,
                 "world_id": f.world_id, "at_peace": f.at_peace}
                for f in self.state.get_player_fleets(player)
            ],
            "messages": [
                m.to_dict() for m in self.comms.get_inbox(player)
            ] if self.comms else [],
        }

    def get_game_summary(self) -> dict:
        """Get full game summary for monitoring UI."""
        if not self.state:
            return {}

        players_summary = []
        for p in self.state.players.values():
            players_summary.append({
                "name": p.code_name,
                "type": p.character_type.value,
                "score": p.score,
                "is_ai": p.is_ai,
                "worlds_owned": len(self.state.get_player_worlds(p.code_name)),
                "fleets": len(self.state.get_player_fleets(p.code_name)),
                "total_ships": sum(f.ships for f in self.state.get_player_fleets(p.code_name)),
            })

        return {
            "game_id": self.config.game_id,
            "turn": self.state.turn_number,
            "game_over": self.state.game_over,
            "winner": self.state.winner,
            "ending_score": self.state.ending_score,
            "players": sorted(players_summary, key=lambda p: -p["score"]),
            "total_worlds": len(self.state.worlds),
            "owned_worlds": sum(1 for w in self.state.worlds.values() if w.owner),
            "total_fleets": len(self.state.fleets),
            "board_stats": self.board.get_stats() if self.board else {},
            "comms_stats": self.comms.get_stats() if self.comms else {},
        }

    def _ai_diplomacy(self):
        """AI agents perform diplomacy based on game state."""
        for player in self.state.players.values():
            if not player.is_ai:
                continue
            # Simple diplomacy: propose alliances with nearby non-threatening players
            my_worlds = set(w.id for w in self.state.get_player_worlds(player.code_name))
            for other in self.state.players.values():
                if other.code_name == player.code_name:
                    continue
                if other.code_name in player.allies:
                    continue
                # Check proximity
                other_worlds = set(w.id for w in self.state.get_player_worlds(other.code_name))
                adjacent = False
                for w in self.state.get_player_worlds(player.code_name):
                    if any(c in other_worlds for c in w.connections):
                        adjacent = True
                        break
                if adjacent and player.score < other.score * 1.5:
                    # Consider alliance
                    if hash((player.code_name, other.code_name, self.state.turn_number)) % 10 < 3:
                        self.comms.propose_alliance(
                            player.code_name, other.code_name, self.state.turn_number
                        )

    def _post_turn_summary(self, log: TurnLog):
        """Post turn summary to the bulletin board."""
        events = log.events
        combat_events = [e for e in events if "fire" in e.get("type", "") or "ambush" in e.get("type", "")]
        captures = [e for e in events if e.get("type") == "world_captured"]

        summary_lines = [f"Turn {log.turn} Summary:", ""]
        if combat_events:
            summary_lines.append(f"  Combat actions: {len(combat_events)}")
        if captures:
            summary_lines.append(f"  Worlds captured: {len(captures)}")
        summary_lines.append(f"  Active players: {len(self.state.players)}")

        self.board.post(
            BoardType.ANNOUNCEMENTS, "GM",
            f"Turn {log.turn} Complete",
            "\n".join(summary_lines),
            turn=log.turn
        )

    def _save_state(self):
        state_file = self._state_dir / "state.json"
        state_file.write_text(json.dumps(self._serialize_state(), indent=2))

    def _save_log(self, log: TurnLog):
        log_file = self._state_dir / f"turn_{log.turn:04d}.json"
        narrative = generate_narrative(log.turn, log.events, self.state.players)
        log_file.write_text(json.dumps(
            {"turn": log.turn, "events": log.events, "narrative": narrative},
            indent=2
        ))

    def _serialize_state(self) -> dict:
        s = self.state
        return {
            "game_id": s.game_id,
            "turn_number": s.turn_number,
            "ending_score": s.ending_score,
            "game_over": s.game_over,
            "winner": s.winner,
            "players": {
                name: {
                    "code_name": p.code_name,
                    "character_type": p.character_type.value,
                    "score": p.score,
                    "home_world": p.home_world,
                    "allies": list(p.allies),
                    "loaders": list(p.loaders),
                    "jihad_target": p.jihad_target,
                    "ending_score_vote": p.ending_score_vote,
                    "is_ai": p.is_ai,
                } for name, p in s.players.items()
            },
            "worlds": {
                str(wid): {
                    "id": w.id, "owner": w.owner, "population": w.population,
                    "pop_limit": w.pop_limit, "industry": w.industry, "mines": w.mines,
                    "metal": w.metal, "i_ships": w.i_ships, "p_ships": w.p_ships,
                    "robots": w.robots, "converts": w.converts,
                    "convert_owner": w.convert_owner, "connections": w.connections,
                    "turns_owned": w.turns_owned, "plunder_count": w.plunder_count,
                    "plunder_recovery": w.plunder_recovery, "cg_unloaded": w.cg_unloaded,
                    "busted": w.busted, "is_black_hole": w.is_black_hole,
                    "artifacts": w.artifacts,
                } for wid, w in s.worlds.items()
            },
            "fleets": {
                str(fid): {
                    "id": f.id, "owner": f.owner, "ships": f.ships, "cargo": f.cargo,
                    "world_id": f.world_id, "at_peace": f.at_peace,
                    "has_pbb": f.has_pbb, "artifacts": f.artifacts,
                } for fid, f in s.fleets.items()
            },
            "artifacts": {
                str(aid): {
                    "id": a.id, "name": a.name, "category": a.category,
                    "location_type": a.location_type, "location_id": a.location_id,
                } for aid, a in s.artifacts.items()
            },
        }

    def _deserialize_state(self, data: dict) -> GameState:
        from .models import Artifact, Fleet, Player, World
        state = GameState(
            game_id=data["game_id"],
            turn_number=data["turn_number"],
            ending_score=data["ending_score"],
            game_over=data["game_over"],
            winner=data.get("winner"),
        )
        for name, pdata in data["players"].items():
            state.players[name] = Player(
                code_name=pdata["code_name"],
                character_type=CharacterType(pdata["character_type"]),
                score=pdata["score"],
                home_world=pdata["home_world"],
                allies=set(pdata.get("allies", [])),
                loaders=set(pdata.get("loaders", [])),
                jihad_target=pdata.get("jihad_target"),
                ending_score_vote=pdata.get("ending_score_vote", 5000),
                is_ai=pdata.get("is_ai", False),
            )
        for wid_str, wdata in data["worlds"].items():
            w = World(**{k: v for k, v in wdata.items()})
            state.worlds[w.id] = w
        for fid_str, fdata in data["fleets"].items():
            f = Fleet(**{k: v for k, v in fdata.items()})
            state.fleets[f.id] = f
        for aid_str, adata in data["artifacts"].items():
            a = Artifact(**{k: v for k, v in adata.items()})
            state.artifacts[a.id] = a
        return state

    def _migrate_3d_coords(self):
        """Assign 3D spatial coordinates to worlds if they don't have them."""
        has_coords = any(w.x != 0 or w.y != 0 or w.z != 0 for w in self.state.worlds.values())
        if has_coords:
            return

        import math
        import random as rng
        rng.seed(42)

        n = len(self.state.worlds)
        radius = 50.0
        golden_ratio = (1 + math.sqrt(5)) / 2

        positions = []
        for i in range(n):
            theta = 2 * math.pi * i / golden_ratio
            phi = math.acos(1 - 2 * (i + 0.5) / n)
            r = radius * (0.3 + 0.7 * (i / n) ** 0.5)
            x = r * math.sin(phi) * math.cos(theta)
            y = r * math.sin(phi) * math.sin(theta) * 0.3
            z = r * math.cos(phi)
            x += rng.uniform(-1.5, 1.5)
            y += rng.uniform(-0.5, 0.5)
            z += rng.uniform(-1.5, 1.5)
            positions.append((round(x, 2), round(y, 2), round(z, 2)))

        for i, w in enumerate(sorted(self.state.worlds.values(), key=lambda w: w.id)):
            if i < len(positions):
                w.x, w.y, w.z = positions[i]

        # Rebuild connections based on distance
        max_hop_dist = 12.0
        max_conns = 5
        for w in self.state.worlds.values():
            w.connections = []

        worlds_list = list(self.state.worlds.values())
        for i, w1 in enumerate(worlds_list):
            for w2 in worlds_list[i+1:]:
                dist = math.sqrt((w1.x - w2.x)**2 + (w1.y - w2.y)**2 + (w1.z - w2.z)**2)
                if dist <= max_hop_dist:
                    w1.connections.append(w2.id)
                    w2.connections.append(w1.id)

        # Ensure no isolated worlds
        for w in self.state.worlds.values():
            if not w.connections:
                nearest = min(
                    (o for o in self.state.worlds.values() if o.id != w.id),
                    key=lambda o: math.sqrt((w.x - o.x)**2 + (w.y - o.y)**2 + (w.z - o.z)**2)
                )
                w.connections.append(nearest.id)
                nearest.connections.append(w.id)

        # Trim over-connected
        for w in self.state.worlds.values():
            if len(w.connections) > max_conns:
                w.connections.sort(key=lambda cid: math.sqrt(
                    (w.x - self.state.worlds[cid].x)**2 +
                    (w.y - self.state.worlds[cid].y)**2 +
                    (w.z - self.state.worlds[cid].z)**2
                ))
                w.connections = w.connections[:max_conns]

        # Ensure full connectivity via BFS
        visited = set()
        queue = [worlds_list[0].id]
        visited.add(worlds_list[0].id)
        while queue:
            node = queue.pop(0)
            for conn in self.state.worlds[node].connections:
                if conn not in visited:
                    visited.add(conn)
                    queue.append(conn)
        for w in self.state.worlds.values():
            if w.id not in visited:
                nearest = min(visited, key=lambda vid: math.sqrt(
                    (w.x - self.state.worlds[vid].x)**2 +
                    (w.y - self.state.worlds[vid].y)**2 +
                    (w.z - self.state.worlds[vid].z)**2
                ))
                w.connections.append(nearest)
                self.state.worlds[nearest].connections.append(w.id)
                visited.add(w.id)

        self._save_state()
