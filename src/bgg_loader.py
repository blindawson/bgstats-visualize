"""
Load BGG play/game data into the same DataFrame schema produced by loader.py.

Data is fetched from the BGG XML API (via bgg_fetcher) and cached locally in
``data/bgg_cache.json``.  The cache is refreshed when it is older than
``cache_ttl_hours`` (default 6).

Setup
-----
Create ``data/bgg_config.json`` (see ``data/bgg_config.example.json``)::

    {
        "username": "YOUR_BGG_USERNAME",
        "cache_ttl_hours": 6,
        "player_names": {
            "Brian":   54,
            "Annie":   582,
            "Ben":     583,
            "Kevin":   77,
            "Garrett": 101
        }
    }

``player_names`` maps each player's BGG display name to the numeric ID used
throughout the app.  Adjust the keys if your BGG log uses different spellings.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from src import bgg_fetcher
from src.loader import (
    CORE_GROUP,
    CORE_IDS,
    _consolidate_magic_maze,
    _evaluate_score,
)

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).parent.parent
BGG_CONFIG_PATH = _ROOT / "data" / "bgg_config.json"
_CACHE_PATH = _ROOT / "data" / "bgg_cache.json"

# BGG object ID for Magic Maze
# https://boardgamegeek.com/boardgame/209778/magic-maze
MAGIC_MAZE_BGG_ID = 209778

# Default name map derived from CORE_GROUP: {"Brian": 54, "Annie": 582, …}
_DEFAULT_NAME_MAP: dict[str, int] = {name: pid for pid, name in CORE_GROUP.items()}


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

@st.cache_data(ttl=None, show_spinner=False)
def load_data_bgg() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Fetch BGG data and return ``(plays_df, scores_df, games_df)`` with the
    same schema as :func:`loader.load_data`.

    Uses a local JSON cache; fetches fresh data from BGG when stale.
    """
    cfg = _load_config()
    username: str = cfg["username"]
    ttl_hours: float = float(cfg.get("cache_ttl_hours", 6))
    name_map: dict[str, int] = cfg.get("player_names", _DEFAULT_NAME_MAP)

    raw = _get_cached_or_fetch(username, ttl_hours)

    plays_raw: list[dict] = raw["plays"]
    # games are stored in JSON with string keys; re-key by int
    games_meta: dict[int, dict] = {int(k): v for k, v in raw["games"].items()}

    games_df = _build_games_df(games_meta)
    global_avg_dur = _compute_avg_durations(plays_raw)
    plays_df, scores_df = _build_plays_dfs(plays_raw, games_df, global_avg_dur, name_map)
    plays_df, scores_df = _consolidate_magic_maze(plays_df, scores_df, game_id=MAGIC_MAZE_BGG_ID)

    return plays_df, scores_df, games_df


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    with open(BGG_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _get_cached_or_fetch(username: str, ttl_hours: float) -> dict:
    """Return file-cached data if fresh; otherwise fetch from BGG."""
    if _CACHE_PATH.exists():
        with open(_CACHE_PATH, encoding="utf-8") as f:
            cached = json.load(f)

        # Only use the cache if it belongs to the same username
        if cached.get("username") == username:
            fetched_at_str = cached.get("fetched_at", "2000-01-01T00:00:00+00:00")
            fetched_at = datetime.fromisoformat(fetched_at_str)
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            age_hours = (
                datetime.now(timezone.utc) - fetched_at
            ).total_seconds() / 3600
            if age_hours < ttl_hours:
                return cached

    return _fetch_and_cache(username)


def _fetch_and_cache(username: str) -> dict:
    """Fetch all plays + game details from BGG and persist to disk."""
    plays = bgg_fetcher.fetch_all_plays(username)
    bgg_ids = list({p["game_id"] for p in plays if p["game_id"]})
    games = bgg_fetcher.fetch_game_details(bgg_ids)

    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "username":   username,
        "plays":      plays,
        "games":      {str(k): v for k, v in games.items()},
    }
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return payload


def clear_cache() -> None:
    """Delete the on-disk BGG cache so the next load fetches fresh data."""
    if _CACHE_PATH.exists():
        _CACHE_PATH.unlink()
    load_data_bgg.clear()


# ---------------------------------------------------------------------------
# DataFrame builders
# ---------------------------------------------------------------------------

def _build_games_df(games_meta: dict[int, dict]) -> pd.DataFrame:
    rows = []
    for bgg_id, g in games_meta.items():
        rows.append({
            "game_id":      bgg_id,
            "name":         g.get("name", ""),
            "bgg_name":     g.get("name", ""),
            "bgg_id":       bgg_id,
            "cooperative":  bool(g.get("cooperative", False)),
            # BGG doesn't expose these scoring-mode flags; use safe defaults
            "highest_wins": True,
            "no_points":    False,
            "uses_teams":   False,
            "url_thumb":    g.get("url_thumb", ""),
            "url_image":    g.get("url_image", ""),
            "min_players":  g.get("min_players"),
            "max_players":  g.get("max_players"),
            "min_play_time": g.get("min_play_time"),
            "max_play_time": g.get("max_play_time"),
            "designers":    g.get("designers", ""),
            "bgg_year":     g.get("bgg_year"),
        })
    return pd.DataFrame(rows).set_index("game_id")


def _compute_avg_durations(plays: list[dict]) -> dict:
    """Average recorded duration per BGG game ID, with a global fallback."""
    totals: dict[int, list[int]] = defaultdict(list)
    for play in plays:
        d = play.get("length", 0) or 0
        if d > 0:
            totals[play["game_id"]].append(d)
    avgs: dict = {gid: round(sum(durs) / len(durs)) for gid, durs in totals.items()}
    all_durations = [d for durs in totals.values() for d in durs]
    avgs["_fallback"] = round(sum(all_durations) / len(all_durations)) if all_durations else 45
    return avgs


def _build_plays_dfs(
    plays: list[dict],
    games_df: pd.DataFrame,
    global_avg_dur: dict,
    name_map: dict[str, int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Filter plays to full-group sessions and build the plays/scores DataFrames.

    *name_map*: ``{"Brian": 54, "Annie": 582, …}`` — maps each player's BGG
    display name (case-insensitive) to their numeric player ID.
    """
    # Build a case-insensitive lookup: lower(name) → player_id
    name_lower: dict[str, int] = {k.lower(): v for k, v in name_map.items()}

    play_rows: list[dict] = []
    score_rows: list[dict] = []

    for play in plays:
        if play.get("incomplete"):
            continue

        # Resolve player names → IDs; skip players not in the name map
        players = play.get("players", [])
        resolved: list[tuple[int, dict]] = []
        for p in players:
            pid = name_lower.get(p["name"].strip().lower())
            if pid is not None:
                resolved.append((pid, p))

        player_ids = {pid for pid, _ in resolved}
        if player_ids != CORE_IDS:
            continue

        game_id = play["game_id"]
        if not game_id:
            continue

        play_date = pd.to_datetime(play["date"]) if play.get("date") else pd.NaT
        is_coop = bool(games_df.loc[game_id, "cooperative"]) if game_id in games_df.index else False

        raw_dur = play.get("length", 0) or 0
        if raw_dur == 0:
            estimated = True
            duration = global_avg_dur.get(game_id, global_avg_dur.get("_fallback", 45))
        else:
            estimated = False
            duration = raw_dur

        play_id = str(play["id"])

        play_rows.append({
            "play_id":           play_id,
            "play_date":         play_date,
            "game_id":           game_id,
            "duration_min":      duration,
            "duration_estimated": estimated,
            "location_id":       None,
            "cooperative":       is_coop,
            "rating":            0,
        })

        for pid, p in resolved:
            score_rows.append({
                "play_id":     play_id,
                "play_date":   play_date,
                "game_id":     game_id,
                "player_id":   pid,
                "player_name": CORE_GROUP[pid],
                "score":       _evaluate_score(p.get("score")),
                "winner":      bool(p.get("win", False)),
                # BGG play logs don't include finish rank; default to 0
                "rank":        0,
                "new_player":  bool(p.get("new", False)),
                # BGG startposition "1" → first player
                "start_player": p.get("startposition", "") == "1",
                "cooperative": is_coop,
            })

    plays_df = pd.DataFrame(play_rows)
    scores_df = pd.DataFrame(score_rows)

    if not plays_df.empty:
        plays_df["play_date"] = pd.to_datetime(plays_df["play_date"])
        plays_df = plays_df.sort_values("play_date").reset_index(drop=True)
    if not scores_df.empty:
        scores_df["play_date"] = pd.to_datetime(scores_df["play_date"])

    return plays_df, scores_df
