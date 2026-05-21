"""Turn narrative generator - creates prose descriptions of each turn's events."""

from collections import defaultdict


def generate_narrative(turn: int, events: list, players: dict = None) -> str:
    """Generate a prose narrative from a turn's events.
    
    Args:
        turn: Turn number
        events: List of event dicts from the turn log
        players: Optional dict of player_name -> Player object for character types
    
    Returns:
        Markdown-formatted narrative string
    """
    # Separate orders from outcomes
    orders = [e for e in events if e.get("type") == "order_submitted"]
    outcomes = [e for e in events if e.get("type") != "order_submitted"]

    # Group orders by player
    orders_by_player = defaultdict(list)
    for o in orders:
        orders_by_player[o["player"]].append(o)

    # Group outcomes by type
    movements = [e for e in outcomes if e["type"] == "movement"]
    loads = [e for e in outcomes if e["type"] == "load"]
    unloads = [e for e in outcomes if e["type"] == "unload"]
    builds_ships = [e for e in outcomes if e["type"] == "ships_built"]
    builds_industry = [e for e in outcomes if e["type"] == "industry_built"]
    captures = [e for e in outcomes if e["type"] == "world_captured"]
    combat = [e for e in outcomes if e["type"] in (
        "fire_population", "fire_industry", "fleet_destroyed",
        "fleet_damaged", "ambush", "robot_attack", "pbb_dropped"
    )]
    diplomacy = [e for e in outcomes if e["type"] == "message_delivered"]
    black_holes = [e for e in outcomes if e["type"] == "black_hole"]

    lines = []
    lines.append(f"# Turn {turn}\n")

    # Opening summary
    active_players = sorted(set(o["player"] for o in orders))
    lines.append(f"*{len(active_players)} commanders issued orders this turn.*\n")

    # Strategic Decisions section - what each player chose to do
    lines.append("## Strategic Decisions\n")
    for player in sorted(orders_by_player.keys()):
        porders = orders_by_player[player]
        char_type = ""
        if players and player in players:
            char_type = f" ({players[player].character_type.value.replace('_', ' ')})"

        lines.append(f"### {player}{char_type}\n")

        # Summarize order types
        order_types = defaultdict(int)
        for o in porders:
            order_types[o["order_type"]] += 1

        # Movement orders
        move_orders = [o for o in porders if o["order_type"] == "move"]
        if move_orders:
            dests = [f"W{o['waypoints'][-1]}" for o in move_orders if o.get("waypoints")]
            lines.append(f"Dispatched {len(move_orders)} fleets across the galaxy"
                        f" — targeting worlds {', '.join(dests[:5])}"
                        f"{'...' if len(dests) > 5 else ''}.\n")

        # Economic orders
        load_orders = [o for o in porders if o["order_type"] == "load"]
        unload_orders = [o for o in porders if o["order_type"] == "unload"]
        build_fleet_orders = [o for o in porders if o["order_type"] == "build_fleet"]
        build_ind_orders = [o for o in porders if o["order_type"] == "build_industry"]

        econ_parts = []
        if load_orders:
            econ_parts.append(f"loaded cargo onto {len(load_orders)} fleets")
        if unload_orders:
            econ_parts.append(f"unloaded at {len(unload_orders)} destinations")
        if build_fleet_orders:
            total_ships = sum(o.get("quantity", 0) for o in build_fleet_orders)
            econ_parts.append(f"commissioned {total_ships} new ships")
        if build_ind_orders:
            total_ind = sum(o.get("quantity", 0) for o in build_ind_orders)
            econ_parts.append(f"invested in {total_ind} units of industry")
        if econ_parts:
            lines.append(f"Economic activity: {'; '.join(econ_parts)}.\n")

        # Combat orders
        fire_orders = [o for o in porders if o["order_type"] in (
            "fire_fleet", "fire_population", "fire_industry", "robot_attack",
            "drop_pbb", "build_pbb"
        )]
        if fire_orders:
            fire_types = defaultdict(int)
            for o in fire_orders:
                fire_types[o["order_type"]] += 1
            parts = []
            if fire_types.get("fire_fleet"):
                parts.append(f"engaged {fire_types['fire_fleet']} enemy fleets")
            if fire_types.get("fire_population"):
                parts.append(f"bombarded {fire_types['fire_population']} worlds")
            if fire_types.get("fire_industry"):
                parts.append(f"targeted industry at {fire_types['fire_industry']} worlds")
            if fire_types.get("robot_attack"):
                parts.append(f"deployed robots at {fire_types['robot_attack']} worlds")
            if fire_types.get("drop_pbb"):
                parts.append("**unleashed a Planet Buster Bomb**")
            if fire_types.get("build_pbb"):
                parts.append("constructed a Planet Buster Bomb")
            lines.append(f"Military action: {'; '.join(parts)}.\n")

        # Diplomacy orders
        diplo_orders = [o for o in porders if o["order_type"] in (
            "declare_ally", "revoke_ally", "declare_loader", "declare_jihad"
        )]
        if diplo_orders:
            for o in diplo_orders:
                if o["order_type"] == "declare_ally":
                    lines.append(f"Extended an alliance offer to {o.get('target_player')}.\n")
                elif o["order_type"] == "declare_jihad":
                    lines.append(f"**Declared holy war against {o.get('target_player')}!**\n")

    # Consequences section
    lines.append("## Consequences\n")

    # Combat outcomes
    if combat:
        lines.append("### Combat\n")
        for e in combat:
            etype = e["type"]
            if etype == "fire_population":
                killed = e.get("pop_killed", 0)
                if killed > 0:
                    lines.append(f"- **{e['player']}** bombarded W{e['world']}"
                                f" — {killed} population killed.\n")
            elif etype == "fire_industry":
                destroyed = e.get("industry_killed", 0)
                if destroyed > 0:
                    lines.append(f"- **{e['player']}** bombarded W{e['world']}"
                                f" — {destroyed} industry destroyed.\n")
            elif etype == "fleet_destroyed":
                lines.append(f"- **{e.get('attacker', '?')}** destroyed Fleet {e.get('target_fleet')}"
                            f" ({e.get('ships_destroyed', '?')} ships lost).\n")
            elif etype == "fleet_damaged":
                lines.append(f"- **{e.get('attacker', '?')}** damaged Fleet {e.get('target_fleet')}"
                            f" — {e.get('ships_destroyed', '?')} ships hit.\n")
            elif etype == "ambush":
                lines.append(f"- Fleet {e.get('fleet')} of **{e['player']}** was ambushed at W{e.get('world')}"
                            f" by {e.get('ambusher')} — {e.get('ships_destroyed', 0)} ships destroyed!\n")
            elif etype == "robot_attack":
                lines.append(f"- **{e['player']}** dropped {e.get('robots_landed', 0)} robots on W{e['world']}"
                            f" — {e.get('people_killed', 0)} population slaughtered.\n")
            elif etype == "pbb_dropped":
                lines.append(f"- **{e['player']}** detonated a Planet Buster Bomb on W{e['world']}!"
                            f" {e.get('pop_killed', 0)} souls obliterated. The world is now a lifeless husk.\n")

    # Territorial changes
    if captures:
        lines.append("### Territorial Shifts\n")
        for e in captures:
            prev = e.get("from_player") or "neutral territory"
            lines.append(f"- **{e['player']}** seized control of W{e['world']}"
                        f" (previously {prev}).\n")

    # Movement summary
    if movements:
        lines.append("### Fleet Movements\n")
        moves_by_player = defaultdict(list)
        for e in movements:
            moves_by_player[e["player"]].append(e)
        for player in sorted(moves_by_player.keys()):
            pmoves = moves_by_player[player]
            if len(pmoves) <= 3:
                dests = ", ".join(f"F{m['fleet']}→W{m['destination']}" for m in pmoves)
                lines.append(f"- **{player}** moved: {dests}\n")
            else:
                lines.append(f"- **{player}** repositioned {len(pmoves)} fleets across the sector.\n")

    # Economic results
    if builds_ships or builds_industry:
        lines.append("### Production\n")
        if builds_ships:
            ships_by_player = defaultdict(int)
            for e in builds_ships:
                ships_by_player[e["player"]] += e.get("quantity", 0)
            for player, qty in sorted(ships_by_player.items()):
                lines.append(f"- **{player}** launched {qty} new ships.\n")
        if builds_industry:
            ind_by_player = defaultdict(int)
            for e in builds_industry:
                ind_by_player[e["player"]] += e.get("quantity", 0)
            for player, qty in sorted(ind_by_player.items()):
                lines.append(f"- **{player}** built {qty} industry.\n")

    # Black holes
    if black_holes:
        lines.append("### Disasters\n")
        for e in black_holes:
            lines.append(f"- Fleet {e.get('fleet')} of **{e['player']}** was swallowed"
                        f" by the black hole at W{e['world']}!\n")

    # Diplomacy
    if diplomacy:
        lines.append("### Diplomacy\n")
        for e in diplomacy:
            lines.append(f"- **{e.get('sender')}** sent a message to **{e['player']}**: "
                        f"*\"{e.get('subject', '...')}\"*\n")

    # If nothing notable happened
    if not combat and not captures and not movements and not builds_ships and not builds_industry:
        lines.append("A quiet turn — the galaxy holds its breath.\n")

    return "\n".join(lines)
