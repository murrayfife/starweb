"""CLI interface for StarWeb game management."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .models import CharacterType
from .orchestrator import GameConfig, GameOrchestrator


DEFAULT_PLAYERS = [
    {"name": "SOLARIS", "type": CharacterType.EMPIRE_BUILDER, "is_ai": True},
    {"name": "TRADER", "type": CharacterType.MERCHANT, "is_ai": True},
    {"name": "REAVER", "type": CharacterType.PIRATE, "is_ai": True},
    {"name": "CURATOR", "type": CharacterType.ARTIFACT_COLLECTOR, "is_ai": True},
    {"name": "OMEGA", "type": CharacterType.BERSERKER, "is_ai": True},
    {"name": "PROPHET", "type": CharacterType.APOSTLE, "is_ai": True},
    {"name": "TERRAN", "type": CharacterType.EMPIRE_BUILDER, "is_ai": True},
    {"name": "NOMAD", "type": CharacterType.MERCHANT, "is_ai": True},
]


def cmd_new(args):
    """Create a new game."""
    config = GameConfig(
        game_id=args.game_id,
        storage_dir=Path(args.storage),
    )
    orch = GameOrchestrator(config)
    players = DEFAULT_PLAYERS[:args.players]
    state = orch.new_game(players)
    print(f"Game '{args.game_id}' created with {len(players)} players.")
    print(f"Map: {len(state.worlds)} worlds, {len(state.artifacts)} artifacts")
    print(f"Ending score target: {state.ending_score}")
    print(f"Storage: {config.storage_dir / args.game_id}")


def cmd_run(args):
    """Run turns automatically."""
    config = GameConfig(
        game_id=args.game_id,
        storage_dir=Path(args.storage),
    )
    orch = GameOrchestrator(config)
    orch.load_game()
    print(f"Loaded game '{args.game_id}' at turn {orch.state.turn_number}")

    logs = orch.run_auto(args.turns)
    print(f"Processed {len(logs)} turns.")

    if orch.state.game_over:
        print(f"\nGAME OVER! Winner: {orch.state.winner}")

    print(f"\nScoreboard (Turn {orch.state.turn_number}):")
    players = sorted(orch.state.players.values(), key=lambda p: -p.score)
    for i, p in enumerate(players, 1):
        marker = " *" if p.code_name == orch.state.winner else ""
        print(f"  {i}. {p.code_name:<12} ({p.character_type.value:<20}) {p.score:>6} pts{marker}")


def cmd_status(args):
    """Show game status."""
    config = GameConfig(
        game_id=args.game_id,
        storage_dir=Path(args.storage),
    )
    orch = GameOrchestrator(config)
    orch.load_game()
    summary = orch.get_game_summary()

    print(f"Game: {summary['game_id']}")
    print(f"Turn: {summary['turn']}")
    print(f"Target Score: {summary['ending_score']}")
    print(f"Worlds: {summary['owned_worlds']}/{summary['total_worlds']} owned")
    print(f"Fleets: {summary['total_fleets']}")
    print(f"\nPlayers:")
    for p in summary["players"]:
        ai_tag = "[AI]" if p["is_ai"] else "[Human]"
        print(f"  {p['name']:<12} {p['type']:<20} {p['score']:>6} pts  "
              f"{p['worlds_owned']} worlds  {p['total_ships']} ships  {ai_tag}")


def cmd_serve(args):
    """Start the monitoring web server."""
    config = GameConfig(
        game_id=args.game_id,
        storage_dir=Path(args.storage),
    )
    orch = GameOrchestrator(config)
    orch.load_game()

    from .server import start_server
    print(f"Starting monitor for game '{args.game_id}' on port {args.port}...")
    start_server(orch, port=args.port)


def cmd_board(args):
    """View or post to bulletin boards."""
    config = GameConfig(
        game_id=args.game_id,
        storage_dir=Path(args.storage),
    )
    orch = GameOrchestrator(config)
    orch.load_game()

    from .bulletin import BoardType
    board_type = BoardType(args.board)
    posts = orch.board.get_board(board_type, args.player or "GM")

    if not posts:
        print(f"No posts on {args.board} board.")
        return

    for post in posts[:20]:
        pin = "[PINNED] " if post.pinned else ""
        print(f"  #{post.id} {pin}[Turn {post.turn}] {post.author}: {post.subject}")
        if args.verbose:
            print(f"    {post.body[:100]}")
            print()


def main():
    parser = argparse.ArgumentParser(description="StarWeb PBM Game Manager")
    parser.add_argument("--storage", default="games", help="Storage directory")
    sub = parser.add_subparsers(dest="command")

    # New game
    p_new = sub.add_parser("new", help="Create a new game")
    p_new.add_argument("game_id", help="Unique game identifier")
    p_new.add_argument("--players", type=int, default=8, help="Number of players (max 8)")

    # Run turns
    p_run = sub.add_parser("run", help="Run turns automatically")
    p_run.add_argument("game_id", help="Game identifier")
    p_run.add_argument("--turns", type=int, default=1, help="Number of turns to process")

    # Status
    p_status = sub.add_parser("status", help="Show game status")
    p_status.add_argument("game_id", help="Game identifier")

    # Serve UI
    p_serve = sub.add_parser("serve", help="Start monitoring web server")
    p_serve.add_argument("game_id", help="Game identifier")
    p_serve.add_argument("--port", type=int, default=8080, help="Port number")

    # Bulletin board
    p_board = sub.add_parser("board", help="View bulletin boards")
    p_board.add_argument("game_id", help="Game identifier")
    p_board.add_argument("--board", default="public", help="Board type")
    p_board.add_argument("--player", help="View as player")
    p_board.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if args.command == "new":
        cmd_new(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "board":
        cmd_board(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
