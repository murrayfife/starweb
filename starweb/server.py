"""Web server for StarWeb game monitoring UI and API."""

from __future__ import annotations

import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .orchestrator import GameOrchestrator, GameConfig


class StarWebAPI(SimpleHTTPRequestHandler):
    """HTTP API handler for the monitoring UI."""

    orchestrator: Optional[GameOrchestrator] = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/game/summary":
            self._json_response(self.orchestrator.get_game_summary())

        elif path == "/api/game/players":
            summary = self.orchestrator.get_game_summary()
            self._json_response(summary.get("players", []))

        elif path == "/api/game/player":
            player = params.get("name", [None])[0]
            if player:
                self._json_response(self.orchestrator.get_player_report(player))
            else:
                self._error_response(400, "Missing 'name' parameter")

        elif path == "/api/game/worlds":
            state = self.orchestrator.state
            worlds = []
            for w in state.worlds.values():
                worlds.append({
                    "id": w.id, "owner": w.owner, "population": w.population,
                    "industry": w.industry, "mines": w.mines, "metal": w.metal,
                    "connections": w.connections, "is_black_hole": w.is_black_hole,
                    "busted": w.busted,
                    "x": w.x, "y": w.y, "z": w.z,
                })
            self._json_response(worlds)

        elif path == "/api/game/fleets":
            state = self.orchestrator.state
            fleets = []
            for f in state.fleets.values():
                fleets.append({
                    "id": f.id, "owner": f.owner, "ships": f.ships,
                    "cargo": f.cargo, "world_id": f.world_id,
                    "at_peace": f.at_peace, "has_pbb": f.has_pbb,
                })
            self._json_response(fleets)

        elif path == "/api/board/posts":
            board_type = params.get("board", ["public"])[0]
            from .bulletin import BoardType
            try:
                bt = BoardType(board_type)
            except ValueError:
                bt = BoardType.PUBLIC
            posts = self.orchestrator.board.get_board(bt, "GM")
            self._json_response([p.to_dict() for p in posts])

        elif path == "/api/comms/stats":
            self._json_response(self.orchestrator.comms.get_stats())

        elif path == "/api/comms/messages":
            # Get all messages, optionally filtered by player or type
            player = params.get("player", [None])[0]
            msg_type = params.get("type", [None])[0]
            comms = self.orchestrator.comms
            messages = comms._messages
            if player:
                messages = [m for m in messages
                            if m.sender == player or m.recipient == player]
            if msg_type:
                messages = [m for m in messages
                            if m.message_type.value == msg_type]
            self._json_response([m.to_dict() for m in sorted(messages, key=lambda m: m.turn_sent)])

        elif path == "/api/game/history":
            # Return all turn logs with events
            turn = params.get("turn", [None])[0]
            state_dir = self.orchestrator._state_dir
            if turn:
                # Single turn
                log_file = state_dir / f"turn_{int(turn):04d}.json"
                if log_file.exists():
                    self._json_response(json.loads(log_file.read_text()))
                else:
                    self._error_response(404, f"No log for turn {turn}")
            else:
                # All turns summary
                logs = []
                for t in range(1, self.orchestrator.state.turn_number + 1):
                    log_file = state_dir / f"turn_{t:04d}.json"
                    if log_file.exists():
                        data = json.loads(log_file.read_text())
                        events = data.get("events", [])
                        logs.append({
                            "turn": t,
                            "total_events": len(events),
                            "combat": len([e for e in events if "fire" in e.get("type", "") or "ambush" in e.get("type", "")]),
                            "movements": len([e for e in events if e.get("type") == "movement"]),
                            "builds": len([e for e in events if "built" in e.get("type", "")]),
                            "captures": len([e for e in events if "capture" in e.get("type", "")]),
                            "loads": len([e for e in events if e.get("type") == "load"]),
                        })
                self._json_response(logs)

        elif path == "/api/turn/log":
            # Detailed turn log with player filter
            turn = int(params.get("turn", [self.orchestrator.state.turn_number])[0])
            player = params.get("player", [None])[0]
            state_dir = self.orchestrator._state_dir
            log_file = state_dir / f"turn_{turn:04d}.json"
            if not log_file.exists():
                self._error_response(404, f"No log for turn {turn}")
            else:
                data = json.loads(log_file.read_text())
                events = data.get("events", [])
                if player:
                    events = [e for e in events if e.get("player") == player]
                self._json_response({"turn": turn, "events": events})

        elif path == "/api/turn/narrative":
            # Human-readable narrative of a turn
            turn = int(params.get("turn", [self.orchestrator.state.turn_number])[0])
            state_dir = self.orchestrator._state_dir
            log_file = state_dir / f"turn_{turn:04d}.json"
            if not log_file.exists():
                self._error_response(404, f"No log for turn {turn}")
            else:
                data = json.loads(log_file.read_text())
                # Use stored narrative if available, otherwise generate
                narrative = data.get("narrative")
                if not narrative:
                    from .narrative import generate_narrative
                    narrative = generate_narrative(turn, data.get("events", []),
                                                  self.orchestrator.state.players)
                self._json_response({"turn": turn, "narrative": narrative})

        elif path == "/api/turn/process":
            log = self.orchestrator.process_turn()
            self._json_response({"turn": log.turn, "events_count": len(log.events)})

        elif path == "/":
            self._serve_ui()

        else:
            self._error_response(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length else "{}"
        data = json.loads(body) if body else {}

        if path == "/api/orders/submit":
            player = data.get("player")
            orders_text = data.get("orders", "")
            if player:
                orders = self.orchestrator.submit_orders(player, orders_text)
                self._json_response({"player": player, "orders_parsed": len(orders)})
            else:
                self._error_response(400, "Missing 'player' field")

        elif path == "/api/turn/advance":
            num_turns = data.get("turns", 1)
            logs = self.orchestrator.run_auto(num_turns)
            self._json_response({
                "turns_processed": len(logs),
                "current_turn": self.orchestrator.state.turn_number,
                "game_over": self.orchestrator.state.game_over,
            })

        elif path == "/api/board/post":
            from .bulletin import BoardType
            board = BoardType(data.get("board", "public"))
            author = data.get("author", "Anonymous")
            subject = data.get("subject", "")
            body_text = data.get("body", "")
            post = self.orchestrator.board.post(
                board, author, subject, body_text,
                self.orchestrator.state.turn_number
            )
            self._json_response(post.to_dict())

        elif path == "/api/comms/send":
            from .comms import MessageType
            sender = data.get("sender")
            recipient = data.get("recipient")
            msg_type = MessageType(data.get("type", "diplomatic"))
            subject = data.get("subject", "")
            body_text = data.get("body", "")
            msg = self.orchestrator.comms.send_message(
                sender, recipient, msg_type, subject, body_text,
                self.orchestrator.state.turn_number
            )
            self._json_response(msg.to_dict())

        else:
            self._error_response(404, "Not found")

    def _json_response(self, data):
        response = json.dumps(data, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response)

    def _error_response(self, code: int, message: str):
        response = json.dumps({"error": message}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _serve_ui(self):
        ui_path = Path(__file__).parent.parent / "ui" / "monitor.html"
        if ui_path.exists():
            content = ui_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self._error_response(404, "UI not found")

    def _build_narrative(self, turn: int, events: list, player_filter: str = None) -> list[dict]:
        """Build human-readable narrative from raw events."""
        # Group events by player
        by_player = {}
        for e in events:
            p = e.get("player", "SYSTEM")
            by_player.setdefault(p, []).append(e)

        narratives = []
        players_to_show = [player_filter] if player_filter else sorted(by_player.keys())

        for player in players_to_show:
            player_events = by_player.get(player, [])
            if not player_events:
                continue

            moves = []
            for e in player_events:
                etype = e.get("type", "")
                if etype == "order_submitted":
                    ot = e.get("order_type", "")
                    if ot == "move":
                        wps = e.get("waypoints", [])
                        dest = wps[-1] if wps else "?"
                        moves.append(f"  Orders Fleet {e.get('fleet_id')} to move to W{dest}")
                    elif ot == "load":
                        moves.append(f"  Orders Fleet {e.get('fleet_id')} to load metal")
                    elif ot == "unload":
                        moves.append(f"  Orders Fleet {e.get('fleet_id')} to unload cargo")
                    elif ot == "build_fleet":
                        moves.append(f"  Orders build ships at W{e.get('world_id')} onto Fleet {e.get('target_fleet_id')}")
                    elif ot == "build_industry":
                        moves.append(f"  Orders build industry at W{e.get('world_id')}")
                    elif ot == "fire_fleet":
                        moves.append(f"  Orders Fleet {e.get('fleet_id')} to fire on Fleet {e.get('target_fleet_id')}")
                    elif ot == "fire_population":
                        moves.append(f"  Orders Fleet {e.get('fleet_id')} to bombard population")
                    elif ot == "fire_industry":
                        moves.append(f"  Orders Fleet {e.get('fleet_id')} to bombard industry")
                    elif ot == "robot_attack":
                        moves.append(f"  Orders Fleet {e.get('fleet_id')} to deploy {e.get('quantity',0)} robots")
                    elif ot == "plunder":
                        moves.append(f"  Orders plunder of W{e.get('world_id')}")
                    elif ot == "build_pbb":
                        moves.append(f"  Orders Fleet {e.get('fleet_id')} to build Planet Buster Bomb")
                    elif ot == "drop_pbb":
                        moves.append(f"  Orders Fleet {e.get('fleet_id')} to drop Planet Buster Bomb")
                    elif ot == "declare_ally":
                        moves.append(f"  Declares {e.get('target_player')} as ally")
                    elif ot == "declare_jihad":
                        moves.append(f"  Declares jihad on {e.get('target_player')}")
                    elif ot:
                        moves.append(f"  Orders: {ot.replace('_', ' ')} (Fleet {e.get('fleet_id') or '-'}, W{e.get('world_id') or '-'})")
                elif etype == "movement":
                    moves.append(f"  [RESULT] Fleet {e.get('fleet')} arrives at W{e.get('destination')}")
                elif etype == "load":
                    moves.append(f"  [RESULT] Fleet {e.get('fleet')} loads {e.get('quantity')} metal at W{e.get('world')}")
                elif etype == "unload":
                    moves.append(f"  [RESULT] Fleet {e.get('fleet')} unloads {e.get('quantity')} metal at W{e.get('world')}")
                elif etype == "ships_built":
                    moves.append(f"  [RESULT] {e.get('quantity')} ships built at W{e.get('world')} → Fleet {e.get('fleet')}")
                elif etype == "industry_built":
                    moves.append(f"  [RESULT] {e.get('quantity')} industry built at W{e.get('world')}")
                elif etype == "world_captured":
                    moves.append(f"  [RESULT] *** CAPTURED W{e.get('world')} from {e.get('from_player') or 'neutral'} ***")
                elif etype == "ambush":
                    moves.append(f"  [COMBAT] Ambushed by {e.get('ambusher')} at W{e.get('world')}! {e.get('ships_destroyed')} ships lost")
                elif etype == "fleet_destroyed":
                    moves.append(f"  [COMBAT] Destroyed Fleet {e.get('target_fleet')} ({e.get('ships_destroyed')} ships)")
                elif etype == "fleet_damaged":
                    moves.append(f"  [COMBAT] Damaged Fleet {e.get('target_fleet')} ({e.get('ships_destroyed')} ships hit)")
                elif etype == "pirate_capture":
                    moves.append(f"  [CAPTURE] Seized Fleet {e.get('fleet')} at W{e.get('world')}")
                elif etype == "pbb_dropped":
                    moves.append(f"  [DEVASTATION] Planet Buster Bomb dropped on W{e.get('world')}! {e.get('pop_killed')} killed")
                elif etype == "robot_attack":
                    moves.append(f"  [COMBAT] Robot attack at W{e.get('world')}: {e.get('robots_landed')} robots, {e.get('people_killed')} killed")
                elif etype == "fire_population":
                    moves.append(f"  [COMBAT] Bombards W{e.get('world')}: {e.get('pop_killed')} population killed")
                elif etype == "fire_industry":
                    moves.append(f"  [COMBAT] Bombards W{e.get('world')}: {e.get('industry_killed')} industry destroyed")
                elif etype == "black_hole":
                    moves.append(f"  [DISASTER] Fleet {e.get('fleet')} fell into black hole at W{e.get('world')}!")
                elif etype == "migration":
                    moves.append(f"  [RESULT] {e.get('quantity')} population migrated W{e.get('from_world')} → W{e.get('to_world')}")
                elif etype == "probe":
                    moves.append(f"  [RESULT] Probe sent to W{e.get('target_world')}")

            if moves:
                narratives.append({
                    "player": player,
                    "actions": moves
                })

        return narratives

    def log_message(self, format, *args):
        pass  # Suppress default logging


def start_server(orchestrator: GameOrchestrator, port: int = 8080):
    """Start the monitoring web server."""
    StarWebAPI.orchestrator = orchestrator
    server = HTTPServer(("0.0.0.0", port), StarWebAPI)
    print(f"StarWeb Monitor running at http://localhost:{port}")
    server.serve_forever()
