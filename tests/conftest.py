"""
Shared fixtures and raw-data builder helpers for BGStats loader tests.

The helpers produce the same dict shapes that BGStatsExport.json contains,
so tests exercise the real parsing code without touching the file on disk.
"""

import pytest
import pandas as pd

from src.loader import (
    MAGIC_MAZE_ID,
    _build_games_df,
    _compute_global_avg_durations,
)

# ---------------------------------------------------------------------------
# Player ID constants (same as production)
# ---------------------------------------------------------------------------
BRIAN   = 54
ANNIE   = 582
BEN     = 583
KEVIN   = 77
GARRETT = 101
OUTSIDER = 999

CORE_IDS = {BRIAN, ANNIE, BEN, KEVIN, GARRETT}


# ---------------------------------------------------------------------------
# Raw-dict builder helpers
# ---------------------------------------------------------------------------

def make_game(game_id: int, name: str, cooperative: bool = False) -> dict:
    return {
        "id": game_id,
        "name": name,
        "bggName": name,
        "bggId": None,
        "bggYear": 2020,
        "cooperative": cooperative,
        "highestWins": True,
        "noPoints": False,
        "usesTeams": False,
        "urlThumb": "",
        "urlImage": "",
        "designers": "Test Designer",
        "minPlayerCount": 2,
        "maxPlayerCount": 5,
        "minPlayTime": 30,
        "maxPlayTime": 60,
        "minAge": 10,
        "isBaseGame": 1,
        "isExpansion": 0,
        "rating": 0,
        "previouslyPlayedAmount": 0,
        "copies": [],
        "metaData": "",
        "modificationDate": "2025-01-01 00:00:00",
        "preferredImage": 0,
    }


def make_player_score(
    player_id: int,
    score=None,
    winner: bool = False,
    rank: int = 0,
) -> dict:
    return {
        "playerRefId": player_id,
        "score": score,
        "winner": winner,
        "rank": rank,
        "newPlayer": False,
        "startPlayer": False,
        "seatOrder": 0,
    }


def make_play(
    uuid: str,
    game_ref_id: int,
    player_scores: list[dict],
    duration: int = 60,
    play_date: str = "2025-06-01 12:00:00",
    ignored: bool = False,
) -> dict:
    return {
        "uuid": uuid,
        "playDate": play_date,
        "entryDate": play_date,
        "modificationDate": play_date,
        "durationMin": duration,
        "gameRefId": game_ref_id,
        "locationRefId": 1,
        "ignored": ignored,
        "usesTeams": False,
        "manualWinner": False,
        "rounds": 0,
        "rating": 0,
        "bggId": None,
        "bggLastSync": None,
        "nemestatsId": 0,
        "importPlayId": 0,
        "scoringSetting": 0,
        "expansionPlays": [],
        "playerScores": player_scores,
    }


def all_five(scores=None, winner_idx: int | None = None) -> list[dict]:
    """Return playerScores for all 5 core members, optionally with a winner."""
    ids = [BRIAN, ANNIE, BEN, KEVIN, GARRETT]
    if scores is None:
        scores = [None] * 5
    return [
        make_player_score(
            pid,
            score=scores[i],
            winner=(i == winner_idx),
        )
        for i, pid in enumerate(ids)
    ]


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def standard_games_raw():
    """A minimal set of games: one competitive, one co-op, Magic Maze."""
    return [
        make_game(1,              "Alpha Game",  cooperative=False),
        make_game(2,              "Beta Coop",   cooperative=True),
        make_game(MAGIC_MAZE_ID,  "Magic Maze",  cooperative=True),
    ]


@pytest.fixture
def standard_games_df(standard_games_raw):
    return _build_games_df(standard_games_raw)


@pytest.fixture
def global_avg_no_zeros():
    """A global_avg_dur dict where game 1 has a known average, fallback set."""
    return {1: 45, MAGIC_MAZE_ID: 18, "_fallback": 40}
