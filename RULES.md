# StarWeb Game Rules

## Overview

StarWeb is a space strategy play-by-mail game where 2–8 players colonize and battle across a randomly generated 3D galaxy. Players control fleets, worlds, populations, and industries, competing for the highest score. The game ends when any player reaches the **ending score threshold (default 5,000 points)**.

---

## Character Types & Scoring

Each player chooses one of 6 character types, each with unique scoring:

| Type | Scoring |
|------|---------|
| **Empire Builder** | `population÷10 + industry + mines` per owned world per turn |
| **Merchant** | 10 pts for 1st CG unloaded/turn, then 8, 5, 3, 1 for subsequent |
| **Pirate** | +3 per fleet owned; +3 per fleet captured; +2 per ship destroyed |
| **Artifact Collector** | +30 for Ancient/Pyramid/Special artifacts; +15 for others; −10 for Plastic |
| **Berserker** | +5 per world with robots; +200 for PBB drops + 2×pop killed; +2 per person killed |
| **Apostle** | +5 per owned world; +0.1 per convert; +5 per world fully converted |

**Artifact Bonuses (non-Collectors):** +5 pts/turn for holding specific artifact categories:
- Empire Builder: Golden, Crown
- Merchant: Golden, Ring
- Pirate: Silver, Lodestar
- Apostle: Blessed, Sepulchre
- Berserker: Titanium, Sword

---

## World Mechanics

### Resources
- **Population** — Grows ~10%/turn (capped at `pop_limit`); workers for industry and mining
- **Industry** — Required for production (ships, buildings)
- **Mines** — Produce metal each turn; cap at 31; +1 mine every 7 turns owned consecutively
- **Metal** — Consumed to build; produced: `min(mines, available_population)`
- **I-Ships** — Defensive industry ships (destroyed before industry in attacks)
- **P-Ships** — Defensive population ships (destroyed before population in attacks)
- **Robots** — Berserker-exclusive; 1 robot kills 4 population; 4 population kill 1 robot

### Special World States
- **Black Holes** (~3% of worlds) — Destroy fleets that enter; fleet reappears at random world
- **Busted** — Destroyed by PBB; zero production forever
- **Plundered** — Pirate action; reduces population (max 3 times)

### Building Costs
| Item | Cost |
|------|------|
| Industry | 4 resources (Empire Builder) / 5 (others) |
| Pop-Limit | 5 resources per unit |
| Ships onto fleet | 1 metal + 1 industry + 1 population per ship |
| I-Ships / P-Ships | 1 metal + 1 industry each |
| Robots | 1 metal per pair (doubles existing) |

---

## Fleet Mechanics

### Properties
- **Ships** — Combat units with cargo capacity
- **Cargo Capacity** — `ships × 2` for Merchants; `ships × 1` for others
- **Fire Power** — Unloaded: `ships ÷ 2`; Loaded: `ships`

### Movement
- Fleets move along **hop links** (world connections)
- Max hop distance: **12.0 units** (3D Euclidean)
- Multi-hop waypoints allowed (one hop per turn phase)
- Passing through enemy-occupied worlds triggers **ambush**

### Ambush
- Enemy fleets at intermediate worlds fire at passing fleets
- Ambusher fire power is **doubled**
- 2 hits = 1 unloaded ship destroyed; 1 hit = 1 loaded ship destroyed
- Allies cannot ambush; NO_AMBUSH mode disables

### Special Fleet Actions
- **At Peace** — Cannot fire, defend, or be captured
- **PBB (Planet-Buster Base)** — Requires 25+ ships to build; destroys entire world

---

## Combat

### Fleet vs Fleet (`F###AF###`)
- Attacker fires at target fleet at same world
- If target moved this turn: hits halved
- Damage: 2 hits/ship (unloaded) or 1 hit/ship (loaded)

### Fire at Industry (`F###AI`)
- Destroys I-Ships first (2 hits each), then industry (2 hits each)

### Fire at Population (`F###AP`)
- Destroys P-Ships first (2 hits each), then population (2 hits each)
- Berserker: +2 score per person killed

### Robot Attack (`F###R##` — Berserker only)
- Convert N ships → 2N robots dropped
- Robots kill 4 population each; population counter-kills (4 pop per robot)
- Berserker: +2 per population killed

### PBB Drop (`F###D` — requires 25+ ships)
- Destroys all population, industry, mines, metal, ships at world
- World permanently busted
- Berserker: +200 + 2×population; Others: −50 score

---

## Orders Reference

### Movement
| Order | Description |
|-------|-------------|
| `F###W###` | Move fleet to adjacent world |
| `F###W###W###W###` | Multi-hop waypoints |

### Cargo
| Order | Description |
|-------|-------------|
| `F###L` / `F###L###` | Load all/qty metal |
| `F###U` / `F###U###` | Unload all/qty metal |
| `F###J` / `F###J###` | Jettison all/qty cargo |
| `F###N` / `F###N###` | Unload Consumer Goods (Merchant scoring) |

### Combat
| Order | Description |
|-------|-------------|
| `F###AF###` | Fire fleet at fleet |
| `F###AI` | Fire at industry |
| `F###AP` | Fire at population |
| `F###CF###` | Conditional fire (only if target present) |
| `F###B` | Build PBB (25+ ships) |
| `F###D` | Drop PBB |
| `F###R##` | Robot attack (Berserker) |

### Building
| Order | Description |
|-------|-------------|
| `W###B##F###` | Build ships onto fleet |
| `W###B##I` | Build I-Ships |
| `W###B##P` | Build P-Ships |
| `W###B##R` | Build robots (Berserker) |
| `W###I##I` | Build industry |
| `W###I##L` | Build pop-limit |

### Transfers & Migration
| Order | Description |
|-------|-------------|
| `F###T##F###` | Transfer ships between fleets |
| `P###M##W###` | Migrate population |
| `C###M##W###` | Migrate converts |
| `F###G=PLAYER` | Give fleet to player |
| `W###G=PLAYER` | Give world to player |

### Diplomacy
| Order | Description |
|-------|-------------|
| `A=PLAYER` | Declare ally |
| `N=PLAYER` | Revoke ally |
| `L=PLAYER` | Declare loader (allow loading from your worlds) |
| `X=PLAYER` | Revoke loader |
| `J=PLAYER` | Declare Jihad target (Apostle only) |
| `F###Q` | Set fleet at peace |
| `F###X` | Set fleet not at peace |
| `Z` / `Z###` | Disable ambush (all/specific world) |

### Artifacts
| Order | Description |
|-------|-------------|
| `V###F###` | Hook artifact to fleet |
| `V###W` | Unhook artifact (leave at world) |

---

## Artifacts

13 categories with ~60 total artifacts placed on unclaimed worlds at game start:

Golden, Ring, Silver, Blessed, Titanium, Ancient, Crown, Lance, Lodestar, Sepulchre, Sword, Pyramid, Plastic, Special

- Artifact Collectors score from all categories
- Other characters get +5/turn for their specific categories
- **Plastic** artifacts: −10 pts/turn (trap for non-Collectors)

---

## Galaxy Map

- **255 worlds** arranged in 3D space (flattened disc shape)
- Connections determined by **max hop distance of 12 units**
- Each world has up to **5 connections** (nearest neighbors within range)
- Full connectivity guaranteed (no isolated clusters)
- ~3% of worlds are **black holes**

---

## Victory

- First player to reach the **ending score** (default 5,000) wins
- Tie-breaker: highest total score
- Game checks victory after each turn's scoring phase
