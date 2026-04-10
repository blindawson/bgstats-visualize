"""
One-time script to strip BGStatsExport.json for public repo.

Keeps only:
  - All games (BGG metadata, no personal info)
  - Plays involving the core group only
  - The 5 core players with first names only

Removes:
  - All other players (names, usernames)
  - Locations (addresses)
  - userInfo (BGG/BGA usernames, device, address)
  - tags, groups, challenges, deletedObjects
  - Sensitive play fields (locationRefId, bggId, importPlayId, etc.)

Also produces data/avg_durations.json with per-game average durations
computed from the FULL dataset before stripping, so duration estimates
stay accurate even after non-group plays are removed.

Usage:
    python scripts/strip_export.py
"""

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "data" / "BGStatsExport.json"
AVG_DST = ROOT / "data" / "avg_durations.json"

CORE_IDS = frozenset([54, 582, 583, 77, 101])
CORE_NAMES = {54: "Brian", 582: "Annie", 583: "Ben", 77: "Kevin", 101: "Garrett"}

# Play fields to keep (everything else dropped)
PLAY_KEEP = {"uuid", "playDate", "durationMin", "ignored", "gameRefId",
             "rating", "usesTeams", "playerScores"}

# Player-score fields to keep
SCORE_KEEP = {"playerRefId", "score", "winner", "rank", "newPlayer", "startPlayer"}


def main():
    print(f"Reading {SRC} ...")
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)

    all_plays = data["plays"]
    print(f"  Total plays in export: {len(all_plays)}")

    # ------------------------------------------------------------------
    # 1. Pre-compute avg durations from the FULL dataset
    # ------------------------------------------------------------------
    totals: dict[int, list[int]] = defaultdict(list)
    for play in all_plays:
        d = play.get("durationMin") or 0
        if d > 0:
            totals[play["gameRefId"]].append(d)

    avgs: dict[str, int] = {
        str(gid): round(sum(durs) / len(durs))
        for gid, durs in totals.items()
    }
    all_durations = [d for durs in totals.values() for d in durs]
    avgs["_fallback"] = round(sum(all_durations) / len(all_durations)) if all_durations else 45

    with open(AVG_DST, "w", encoding="utf-8") as f:
        json.dump(avgs, f)
    print(f"  Saved avg_durations.json ({len(avgs) - 1} games)")

    # ------------------------------------------------------------------
    # 2. Filter plays to core group only + strip sensitive fields
    # ------------------------------------------------------------------
    core_plays = []
    for play in all_plays:
        if play.get("ignored"):
            continue
        player_ids = {ps["playerRefId"] for ps in play.get("playerScores", [])}
        if player_ids != CORE_IDS:
            continue

        stripped = {k: v for k, v in play.items() if k in PLAY_KEEP}
        stripped["playerScores"] = [
            {k: v for k, v in ps.items() if k in SCORE_KEEP}
            for ps in play.get("playerScores", [])
        ]
        core_plays.append(stripped)

    print(f"  Core group plays kept: {len(core_plays)}")

    # ------------------------------------------------------------------
    # 3. Minimal player entries — first names only, no usernames/emails
    # ------------------------------------------------------------------
    core_players = [
        {"id": pid, "name": name}
        for pid, name in CORE_NAMES.items()
    ]

    # ------------------------------------------------------------------
    # 4. Write stripped export (overwrites original)
    # ------------------------------------------------------------------
    stripped_export = {
        "games": data["games"],   # BGG metadata only, no personal info
        "plays": core_plays,
        "players": core_players,
    }

    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(stripped_export, f, ensure_ascii=False, indent=2)

    size_mb = SRC.stat().st_size / 1_000_000
    print(f"  Saved stripped BGStatsExport.json ({size_mb:.1f} MB)")
    print("Done.")


if __name__ == "__main__":
    main()
