# StarWeb PBM

A space strategy Play-by-Mail game engine with AI agents, bulletin boards, and diplomacy. Players colonize and battle across a randomly generated 3D galaxy, competing for the highest score.

## Features

- **6 Character Types** — Empire Builder, Merchant, Pirate, Artifact Collector, Berserker, Apostle — each with unique scoring mechanics
- **AI Agents** — Strategy-driven bots that generate orders automatically based on character type
- **3D Galaxy Maps** — Procedurally generated star maps with hop-link connections, black holes, and artifacts
- **Combat System** — Fleet-to-fleet battles, ambushes, planet-buster bombs, and robot attacks
- **Diplomacy & Comms** — Alliance proposals, trade offers, ceasefires, and war declarations delivered per-turn
- **Bulletin Boards** — Public announcements, alliance boards, and a trading post
- **Turn Narratives** — Prose descriptions generated from each turn's events
- **Web Monitor UI** — Browser-based dashboard for observing game state in real-time

## Requirements

- Python 3.11+
- Dependencies: `pydantic`, `rich`, `networkx`

## Installation

```bash
pip install -e .
```

## CLI Usage

```bash
# Create a new game with 8 AI players
starweb new mygame --players 8

# Run 10 turns automatically
starweb run mygame --turns 10

# Check game status and scoreboard
starweb status mygame

# Start the web monitoring server
starweb serve mygame --port 8080

# View the public bulletin board
starweb board mygame --board public
```

## Web Server API

Start with `starweb serve <game_id>` then open `http://localhost:8080` for the monitor UI.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/game/summary` | Game overview (turn, scores, world count) |
| GET | `/api/game/players` | All player stats |
| GET | `/api/game/worlds` | World data with coordinates |
| GET | `/api/game/fleets` | All fleet positions and cargo |
| GET | `/api/game/history` | Turn-by-turn event summaries |
| GET | `/api/turn/log?turn=N` | Detailed events for a turn |
| GET | `/api/turn/narrative?turn=N` | Prose narrative of a turn |
| GET | `/api/board/posts?board=public` | Bulletin board posts |
| GET | `/api/comms/stats` | Communication statistics |
| POST | `/api/orders/submit` | Submit player orders |
| POST | `/api/turn/advance` | Process N turns |
| POST | `/api/board/post` | Post to a bulletin board |
| POST | `/api/comms/send` | Send a diplomatic message |

## Project Structure

```
starweb/
├── models.py        # Core data models (World, Fleet, Player, Artifact, GameState)
├── engine.py        # Turn processor — executes orders and resolves combat
├── mapgen.py        # Procedural 3D galaxy generation
├── orders.py        # Order parsing (movement, attack, build, load/unload)
├── agents.py        # AI player strategy agents
├── orchestrator.py  # Game orchestrator tying all systems together
├── bulletin.py      # Bulletin board system
├── comms.py         # Diplomatic messaging system
├── narrative.py     # Turn narrative prose generator
├── server.py        # HTTP API and monitoring UI server
├── cli.py           # Command-line interface
ui/
└── monitor.html     # Browser-based game monitor dashboard
games/               # Game state storage (per-game directories)
RULES.md             # Complete game rules reference
```

## Game Rules

See [RULES.md](RULES.md) for the full ruleset covering character types, world mechanics, fleet operations, combat, and scoring.
