"""
Load and preprocess BGStatsExport.json into dataframes scoped to the core group.

Core group (all 5 must be present, no other players):
    Brian   = 54
    Annie   = 582
    Ben     = 583
    Kevin   = 77
    Garrett = 101

Special handling:
  - Zero-duration plays get the game's global average duration (marked duration_estimated=True).
  - Magic Maze (game_id=150) plays are consolidated into one row per calendar date,
    with durations summed (it's a co-op game played in short sequential runs).
"""

import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_PATH = Path(__file__).parent.parent / "data" / "BGStatsExport.json"
AVG_DUR_PATH = Path(__file__).parent.parent / "data" / "avg_durations.json"
RANKINGS_PATH = Path(__file__).parent.parent / "data" / "MB rankings.csv"

# Known name aliases: normalized BGStats name → normalized CSV name
_RANK_ALIASES: dict[str, str] = {
    "6 nimmt": "take 5",                        # German vs English name for the same game
    "6 nimmt!": "take 5",
    "modern art the card game": "modern art card game",  # BGStats adds "The" in title
}

CORE_GROUP: dict[int, str] = {
    54: "Brian",
    582: "Annie",
    583: "Ben",
    77: "Kevin",
    101: "Garrett",
}
CORE_IDS = frozenset(CORE_GROUP.keys())
ANNIE_ID = 582
MAGIC_MAZE_ID = 150


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Returns:
        plays_df   — one row per qualifying play (Magic Maze consolidated)
        scores_df  — one row per player per qualifying play
        games_df   — all games (for metadata lookups)
    """
    _cache_version = 3  # increment to bust stale cache
    with open(DATA_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    games_df = _build_games_df(raw["games"])
    global_avg_dur = _compute_global_avg_durations(raw["plays"])
    plays_df, scores_df = _build_plays_dfs(raw["plays"], games_df, global_avg_dur)
    plays_df, scores_df = _consolidate_magic_maze(plays_df, scores_df)
    return plays_df, scores_df, games_df


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _build_games_df(games: list[dict]) -> pd.DataFrame:
    rows = []
    for g in games:
        rows.append({
            "game_id": g["id"],
            "name": g["name"],
            "bgg_name": g.get("bggName") or g["name"],
            "bgg_id": g.get("bggId"),
            "cooperative": bool(g.get("cooperative", False)),
            "highest_wins": bool(g.get("highestWins", True)),
            "no_points": bool(g.get("noPoints", False)),
            "uses_teams": bool(g.get("usesTeams", False)),
            "url_thumb": g.get("urlThumb", ""),
            "url_image": g.get("urlImage", ""),
            "min_players": g.get("minPlayerCount"),
            "max_players": g.get("maxPlayerCount"),
            "min_play_time": g.get("minPlayTime"),
            "max_play_time": g.get("maxPlayTime"),
            "designers": g.get("designers", ""),
            "bgg_year": g.get("bggYear"),
        })
    return pd.DataFrame(rows).set_index("game_id")


def _compute_global_avg_durations(all_plays: list[dict]) -> dict[int, int]:
    """Average duration per game. Loads from pre-computed file if available
    (produced by scripts/strip_export.py from the full dataset), otherwise
    computes from whatever plays are in the export."""
    if AVG_DUR_PATH.exists():
        with open(AVG_DUR_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        return {(int(k) if k != "_fallback" else k): v for k, v in raw.items()}

    totals: dict[int, list[int]] = defaultdict(list)
    for play in all_plays:
        d = play.get("durationMin") or 0
        if d > 0:
            totals[play["gameRefId"]].append(d)
    avgs = {gid: round(sum(durs) / len(durs)) for gid, durs in totals.items()}
    all_durations = [d for durs in totals.values() for d in durs]
    avgs["_fallback"] = round(sum(all_durations) / len(all_durations)) if all_durations else 45
    return avgs


def _evaluate_score(raw) -> int | float | None:
    """
    Evaluate a BGStats score expression to a single number.

    BGStats stores scores as plain numbers OR as arithmetic strings entered
    during play, e.g.:
      "66-5-0-11-17"  → 33   (6 nimmt: start 66, subtract penalty rounds)
      "31+3+1+8+7"    → 50   (MLEM: sum of earned points)
      "-110"          → -110 (plain negative number)

    Only + and - expressions are supported (no *, /, parens).
    Returns None for empty/None input or unrecognised formats.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    # Normalise unicode minus/dash variants to ASCII hyphen
    clean = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-").replace(" ", "")

    # Validate: optional leading sign, then digits, then any number of (sign + digits)
    if re.fullmatch(r"[-+]?\d+([+-]\d+)*", clean):
        return sum(int(t) for t in re.findall(r"[-+]?\d+", clean))

    # Fallback: try plain float → int where lossless, round near-integers
    try:
        val = float(clean)
        rounded = round(val)
        if abs(val - rounded) < 1e-6:
            return rounded
        return val
    except ValueError:
        return None


def _build_plays_dfs(
    plays: list[dict],
    games_df: pd.DataFrame,
    global_avg_dur: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    play_rows = []
    score_rows = []

    for play in plays:
        if play.get("ignored"):
            continue

        player_scores = play.get("playerScores", [])
        player_ids = {ps["playerRefId"] for ps in player_scores}

        if player_ids != CORE_IDS:
            continue

        play_date = pd.to_datetime(play["playDate"]) if play.get("playDate") else pd.NaT
        game_id = play["gameRefId"]
        is_coop = bool(games_df.loc[game_id, "cooperative"]) if game_id in games_df.index else False

        raw_dur = play.get("durationMin") or 0
        if raw_dur == 0:
            estimated = True
            duration = global_avg_dur.get(game_id, global_avg_dur["_fallback"])
        else:
            estimated = False
            duration = raw_dur

        play_rows.append({
            "play_id": play["uuid"],
            "play_date": play_date,
            "game_id": game_id,
            "duration_min": duration,
            "duration_estimated": estimated,
            "location_id": play.get("locationRefId"),
            "cooperative": is_coop,
            "rating": play.get("rating") or 0,
        })

        for ps in player_scores:
            score_rows.append({
                "play_id": play["uuid"],
                "play_date": play_date,
                "game_id": game_id,
                "player_id": ps["playerRefId"],
                "player_name": CORE_GROUP[ps["playerRefId"]],
                "score": _evaluate_score(ps.get("score")),
                "winner": bool(ps.get("winner", False)),
                "rank": ps.get("rank") or 0,
                "new_player": bool(ps.get("newPlayer", False)),
                "start_player": bool(ps.get("startPlayer", False)),
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


def _consolidate_magic_maze(
    plays_df: pd.DataFrame,
    scores_df: pd.DataFrame,
    game_id: int = MAGIC_MAZE_ID,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Collapse all Magic Maze plays on the same date into one row.
    Duration is summed; marked estimated if any constituent was estimated.

    *game_id* defaults to ``MAGIC_MAZE_ID`` (BGStats internal ID) but can be
    overridden with the BGG object ID when loading data from BGG.
    """
    mm = plays_df[plays_df["game_id"] == game_id].copy()
    other = plays_df[plays_df["game_id"] != game_id]

    if mm.empty:
        return plays_df, scores_df

    mm["date_key"] = mm["play_date"].dt.date
    consolidated_plays = []
    keep_play_ids: set[str] = set()

    for date_key, group in mm.groupby("date_key"):
        first = group.iloc[0]
        combined_id = first["play_id"]  # anchor to first play of the session
        keep_play_ids.add(combined_id)
        consolidated_plays.append({
            "play_id": combined_id,
            "play_date": first["play_date"],
            "game_id": game_id,
            "duration_min": group["duration_min"].sum(),
            "duration_estimated": group["duration_estimated"].any(),
            "location_id": first["location_id"],
            "cooperative": True,
            "rating": first["rating"],
        })

    consolidated_df = pd.DataFrame(consolidated_plays)

    # For scores: keep only rows whose play_id matches the anchor of each group
    mm_scores = scores_df[scores_df["game_id"] == MAGIC_MAZE_ID]
    other_scores = scores_df[scores_df["game_id"] != MAGIC_MAZE_ID]
    mm_scores_kept = mm_scores[mm_scores["play_id"].isin(keep_play_ids)]

    new_plays = pd.concat([other, consolidated_df], ignore_index=True).sort_values("play_date").reset_index(drop=True)
    new_scores = pd.concat([other_scores, mm_scores_kept], ignore_index=True)

    return new_plays, new_scores


def apply_annie_mode(
    plays_df: pd.DataFrame, scores_df: pd.DataFrame, enabled: bool
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Filter to plays where Annie won (competitive games only)."""
    if not enabled:
        return plays_df, scores_df

    annie_wins = scores_df[
        (scores_df["player_id"] == ANNIE_ID)
        & (scores_df["winner"] == True)
        & (scores_df["cooperative"] == False)
    ]["play_id"]

    coop_play_ids = plays_df[plays_df["cooperative"] == True]["play_id"]

    keep_ids = set(annie_wins) | set(coop_play_ids)
    filtered_plays = plays_df[plays_df["play_id"].isin(keep_ids)]
    filtered_scores = scores_df[scores_df["play_id"].isin(keep_ids)]
    return filtered_plays, filtered_scores


@st.cache_data
def load_rankings(games_df: pd.DataFrame) -> pd.DataFrame:
    """
    Load MB rankings CSV and match rows to game_ids from games_df.

    Returns a DataFrame indexed by game_id with columns:
        rank  (int)  — group rank (1 = best)
        score (float) — Pub Meeple score 0-100

    Games that can't be matched are absent from the result.
    """
    _cache_version = 2  # increment to bust stale cache
    if not RANKINGS_PATH.exists():
        return pd.DataFrame(columns=["rank", "score"])

    csv = pd.read_csv(RANKINGS_PATH)
    csv.columns = ["rank", "game", "score", "times_ranked"]

    def _norm(s: str) -> str:
        s = str(s).lower().strip()
        s = re.sub(r"[^\w\s]", " ", s)   # strip punctuation
        s = re.sub(r"\s+", " ", s).strip()
        return s

    csv_lookup: dict[str, tuple[int, float]] = {
        _norm(row["game"]): (int(row["rank"]), float(row["score"]))
        for _, row in csv.iterrows()
    }

    result: dict[int, dict] = {}
    for game_id, row in games_df.iterrows():
        bgg_norm = _norm(row["name"])
        # 1. direct match
        if bgg_norm in csv_lookup:
            result[game_id] = {"rank": csv_lookup[bgg_norm][0], "score": csv_lookup[bgg_norm][1]}
            continue
        # 2. alias lookup
        alias = _norm(_RANK_ALIASES.get(bgg_norm, ""))
        if alias and alias in csv_lookup:
            result[game_id] = {"rank": csv_lookup[alias][0], "score": csv_lookup[alias][1]}
            continue
        # 3. substring match (csv name inside bgg name or vice versa)
        for csv_norm, (rrank, rscore) in csv_lookup.items():
            if csv_norm and (csv_norm in bgg_norm or bgg_norm in csv_norm):
                result[game_id] = {"rank": rrank, "score": rscore}
                break

    if not result:
        return pd.DataFrame(columns=["rank", "score"])
    return pd.DataFrame.from_dict(result, orient="index").rename_axis("game_id")
