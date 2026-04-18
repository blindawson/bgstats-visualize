"""
Unit tests for src/loader.py.

Covers:
  - _build_games_df        : games dataframe shape and values
  - _compute_global_avg_durations : duration averaging with edge cases
  - _build_plays_dfs       : core-group filter, duration estimation, score parsing
  - _consolidate_magic_maze : session consolidation
  - apply_annie_mode       : Annie Mode filtering
"""

import pandas as pd
import pytest

from src.loader import (
    ANNIE_ID,
    MAGIC_MAZE_ID,
    _build_games_df,
    _build_plays_dfs,
    _compute_global_avg_durations,
    _consolidate_magic_maze,
    _evaluate_score,
    apply_annie_mode,
)
from tests.conftest import (
    ANNIE,
    BEN,
    BRIAN,
    GARRETT,
    KEVIN,
    OUTSIDER,
    all_five,
    make_game,
    make_play,
    make_player_score,
)


# ===========================================================================
# _evaluate_score
# ===========================================================================

class TestEvaluateScore:
    def test_none_returns_none(self):
        assert _evaluate_score(None) is None

    def test_empty_string_returns_none(self):
        assert _evaluate_score("") is None

    def test_plain_integer_string(self):
        assert _evaluate_score("42") == 42

    def test_plain_negative_integer(self):
        assert _evaluate_score("-110") == -110

    def test_plain_integer_value(self):
        assert _evaluate_score(42) == 42

    def test_subtraction_expression(self):
        # 6 nimmt style: start value minus penalty rounds
        assert _evaluate_score("66-5-0-11-17") == 33

    def test_addition_expression(self):
        # MLEM style: sum of earned points
        assert _evaluate_score("31+3+1+8+7") == 50

    def test_mixed_addition_and_subtraction(self):
        assert _evaluate_score("10+5-3") == 12

    def test_single_term_with_subtraction_chain(self):
        assert _evaluate_score("66-11-12") == 43

    def test_zero_terms_handled(self):
        assert _evaluate_score("66-0-9-8-0-24") == 25

    def test_result_is_integer_not_float(self):
        result = _evaluate_score("66-5-0-11-17")
        assert isinstance(result, int)

    def test_float_string_returns_int_when_whole(self):
        assert _evaluate_score("7.0") == 7

    def test_float_string_returns_float_when_fractional(self):
        assert _evaluate_score("7.5") == 7.5


# ===========================================================================
# _build_games_df
# ===========================================================================

class TestBuildGamesDf:
    def test_indexed_by_game_id(self, standard_games_raw):
        df = _build_games_df(standard_games_raw)
        assert df.index.name == "game_id"
        assert 1 in df.index
        assert 2 in df.index

    def test_cooperative_flag_true(self, standard_games_raw):
        df = _build_games_df(standard_games_raw)
        assert df.loc[2, "cooperative"]

    def test_cooperative_flag_false(self, standard_games_raw):
        df = _build_games_df(standard_games_raw)
        assert not df.loc[1, "cooperative"]

    def test_name_stored(self, standard_games_raw):
        df = _build_games_df(standard_games_raw)
        assert df.loc[1, "name"] == "Alpha Game"

    def test_all_games_present(self, standard_games_raw):
        df = _build_games_df(standard_games_raw)
        assert len(df) == len(standard_games_raw)


# ===========================================================================
# _compute_global_avg_durations
# ===========================================================================

class TestComputeGlobalAvgDurations:
    @pytest.fixture(autouse=True)
    def no_avg_dur_file(self, monkeypatch, tmp_path):
        """Point AVG_DUR_PATH at a nonexistent location so the function
        always computes from the supplied plays rather than loading from disk."""
        import src.loader as _loader
        monkeypatch.setattr(_loader, "AVG_DUR_PATH", tmp_path / "nonexistent.json")

    def _plays(self, game_id, durations):
        """Build minimal raw-play dicts for duration computation."""
        return [
            {"gameRefId": game_id, "durationMin": d}
            for d in durations
        ]

    def test_basic_average(self):
        plays = self._plays(1, [30, 60, 90])
        avgs = _compute_global_avg_durations(plays)
        assert avgs[1] == 60

    def test_zero_duration_excluded_from_average(self):
        plays = self._plays(1, [0, 60, 60])
        avgs = _compute_global_avg_durations(plays)
        assert avgs[1] == 60

    def test_all_zero_duration_game_absent_from_result(self):
        plays = self._plays(1, [0, 0])
        avgs = _compute_global_avg_durations(plays)
        assert 1 not in avgs

    def test_fallback_key_always_present(self):
        plays = self._plays(1, [45])
        avgs = _compute_global_avg_durations(plays)
        assert "_fallback" in avgs

    def test_fallback_is_global_mean(self):
        plays = self._plays(1, [40]) + self._plays(2, [60])
        avgs = _compute_global_avg_durations(plays)
        assert avgs["_fallback"] == 50

    def test_multiple_games_independent(self):
        plays = self._plays(1, [30]) + self._plays(2, [90])
        avgs = _compute_global_avg_durations(plays)
        assert avgs[1] == 30
        assert avgs[2] == 90

    def test_rounds_to_nearest_int(self):
        plays = self._plays(1, [10, 11])   # avg = 10.5 → rounds to 10 or 11
        avgs = _compute_global_avg_durations(plays)
        assert isinstance(avgs[1], int)


# ===========================================================================
# _build_plays_dfs  —  core-group filtering
# ===========================================================================

class TestBuildPlaysDfsFiltering:
    """Only plays with exactly the 5 core IDs should survive."""

    def _run(self, plays_raw, games_raw=None):
        if games_raw is None:
            games_raw = [make_game(1, "Test")]
        gdf = _build_games_df(games_raw)
        avg = {1: 45, "_fallback": 45}
        return _build_plays_dfs(plays_raw, gdf, avg)

    def test_exact_core_group_included(self):
        play = make_play("p1", 1, all_five())
        plays_df, _ = self._run([play])
        assert len(plays_df) == 1

    def test_four_core_players_excluded(self):
        scores = [make_player_score(p) for p in [BRIAN, ANNIE, BEN, KEVIN]]
        play = make_play("p1", 1, scores)
        plays_df, _ = self._run([play])
        assert len(plays_df) == 0

    def test_outsider_with_core_excluded(self):
        scores = all_five() + [make_player_score(OUTSIDER)]
        play = make_play("p1", 1, scores)
        plays_df, _ = self._run([play])
        assert len(plays_df) == 0

    def test_ignored_play_excluded(self):
        play = make_play("p1", 1, all_five(), ignored=True)
        plays_df, _ = self._run([play])
        assert len(plays_df) == 0

    def test_multiple_plays_filtered_correctly(self):
        good = make_play("p1", 1, all_five())
        bad_scores = [make_player_score(p) for p in [BRIAN, ANNIE, BEN, KEVIN, OUTSIDER]]
        bad  = make_play("p2", 1, bad_scores)
        plays_df, _ = self._run([good, bad])
        assert len(plays_df) == 1
        assert plays_df.iloc[0]["play_id"] == "p1"

    def test_scores_df_has_five_rows_per_play(self):
        play = make_play("p1", 1, all_five())
        _, scores_df = self._run([play])
        assert len(scores_df) == 5

    def test_scores_df_player_names_correct(self):
        play = make_play("p1", 1, all_five())
        _, scores_df = self._run([play])
        assert set(scores_df["player_name"]) == {"Brian", "Annie", "Ben", "Kevin", "Garrett"}

    def test_play_date_parsed(self):
        play = make_play("p1", 1, all_five(), play_date="2024-03-15 10:00:00")
        plays_df, _ = self._run([play])
        assert plays_df.iloc[0]["play_date"].year == 2024
        assert plays_df.iloc[0]["play_date"].month == 3

    def test_cooperative_flag_propagated(self):
        games = [make_game(1, "Coop", cooperative=True)]
        play = make_play("p1", 1, all_five())
        plays_df, scores_df = self._run([play], games_raw=games)
        assert plays_df.iloc[0]["cooperative"]
        assert scores_df.iloc[0]["cooperative"]

    def test_sorted_by_play_date(self):
        p1 = make_play("p1", 1, all_five(), play_date="2025-12-01 10:00:00")
        p2 = make_play("p2", 1, all_five(), play_date="2025-01-01 10:00:00")
        plays_df, _ = self._run([p1, p2])
        assert plays_df.iloc[0]["play_id"] == "p2"
        assert plays_df.iloc[1]["play_id"] == "p1"


# ===========================================================================
# _build_plays_dfs  —  zero-duration estimation
# ===========================================================================

class TestDurationEstimation:
    def _run(self, plays_raw, global_avg=None):
        games_raw = [make_game(1, "Test"), make_game(2, "Other")]
        gdf = _build_games_df(games_raw)
        if global_avg is None:
            global_avg = {1: 45, 2: 30, "_fallback": 40}
        return _build_plays_dfs(plays_raw, gdf, global_avg)

    def test_nonzero_duration_unchanged(self):
        play = make_play("p1", 1, all_five(), duration=75)
        plays_df, _ = self._run([play])
        assert plays_df.iloc[0]["duration_min"] == 75

    def test_nonzero_not_flagged_estimated(self):
        play = make_play("p1", 1, all_five(), duration=75)
        plays_df, _ = self._run([play])
        assert not plays_df.iloc[0]["duration_estimated"]

    def test_zero_duration_replaced_with_game_avg(self):
        play = make_play("p1", 1, all_five(), duration=0)
        plays_df, _ = self._run([play], global_avg={1: 45, "_fallback": 40})
        assert plays_df.iloc[0]["duration_min"] == 45

    def test_zero_duration_flagged_estimated(self):
        play = make_play("p1", 1, all_five(), duration=0)
        plays_df, _ = self._run([play])
        assert plays_df.iloc[0]["duration_estimated"]

    def test_zero_duration_unknown_game_uses_fallback(self):
        games_raw = [make_game(99, "Unknown")]
        gdf = _build_games_df(games_raw)
        global_avg = {"_fallback": 50}  # game 99 absent
        play = make_play("p1", 99, all_five(), duration=0)
        plays_df, _ = _build_plays_dfs([play], gdf, global_avg)
        assert plays_df.iloc[0]["duration_min"] == 50
        assert plays_df.iloc[0]["duration_estimated"]

    def test_none_duration_treated_as_zero(self):
        """durationMin=None in source data (uses `or 0` coercion)."""
        play = make_play("p1", 1, all_five(), duration=None)
        plays_df, _ = self._run([play], global_avg={1: 33, "_fallback": 40})
        assert plays_df.iloc[0]["duration_min"] == 33
        assert plays_df.iloc[0]["duration_estimated"]


# ===========================================================================
# _build_plays_dfs  —  score and winner parsing
# ===========================================================================

class TestScoreParsing:
    def _run(self, plays_raw):
        games_raw = [make_game(1, "Test")]
        gdf = _build_games_df(games_raw)
        return _build_plays_dfs(plays_raw, gdf, {1: 45, "_fallback": 40})

    def test_winner_flag_true(self):
        scores = [make_player_score(BRIAN, winner=True)] + [
            make_player_score(p) for p in [ANNIE, BEN, KEVIN, GARRETT]
        ]
        play = make_play("p1", 1, scores)
        _, scores_df = self._run([play])
        brian_row = scores_df[scores_df["player_id"] == BRIAN].iloc[0]
        assert brian_row["winner"]

    def test_winner_flag_false_for_others(self):
        scores = [make_player_score(BRIAN, winner=True)] + [
            make_player_score(p) for p in [ANNIE, BEN, KEVIN, GARRETT]
        ]
        play = make_play("p1", 1, scores)
        _, scores_df = self._run([play])
        non_winners = scores_df[scores_df["player_id"] != BRIAN]
        assert non_winners["winner"].sum() == 0

    def test_numeric_score_stored(self):
        scores = [make_player_score(BRIAN, score=42)] + [
            make_player_score(p) for p in [ANNIE, BEN, KEVIN, GARRETT]
        ]
        play = make_play("p1", 1, scores)
        _, scores_df = self._run([play])
        brian_row = scores_df[scores_df["player_id"] == BRIAN].iloc[0]
        assert brian_row["score"] == 42

    def test_null_score_stored_as_none(self):
        play = make_play("p1", 1, all_five(scores=None))
        _, scores_df = self._run([play])
        assert scores_df["score"].isna().all()


# ===========================================================================
# _consolidate_magic_maze
# ===========================================================================

class TestConsolidateMagicMaze:
    def _build_mm_inputs(self, plays_raw):
        """Build plays_df and scores_df containing Magic Maze plays."""
        games_raw = [
            make_game(1, "Other Game"),
            make_game(MAGIC_MAZE_ID, "Magic Maze", cooperative=True),
        ]
        gdf = _build_games_df(games_raw)
        global_avg = {MAGIC_MAZE_ID: 18, 1: 45, "_fallback": 40}
        return _build_plays_dfs(plays_raw, gdf, global_avg)

    def test_six_same_day_plays_become_one(self):
        plays_raw = [
            make_play(f"mm{i}", MAGIC_MAZE_ID, all_five(), duration=10, play_date=f"2025-04-19 1{i}:00:00")
            for i in range(6)
        ]
        plays_df, scores_df = self._build_mm_inputs(plays_raw)
        plays_df, scores_df = _consolidate_magic_maze(plays_df, scores_df)
        mm_plays = plays_df[plays_df["game_id"] == MAGIC_MAZE_ID]
        assert len(mm_plays) == 1

    def test_durations_summed(self):
        plays_raw = [
            make_play(f"mm{i}", MAGIC_MAZE_ID, all_five(), duration=10, play_date=f"2025-04-19 1{i}:00:00")
            for i in range(6)
        ]
        plays_df, scores_df = self._build_mm_inputs(plays_raw)
        plays_df, scores_df = _consolidate_magic_maze(plays_df, scores_df)
        mm_row = plays_df[plays_df["game_id"] == MAGIC_MAZE_ID].iloc[0]
        assert mm_row["duration_min"] == 60

    def test_estimated_true_if_any_constituent_was_zero(self):
        durations = [10, 10, 0, 10, 10, 10]  # one zero → estimated
        plays_raw = [
            make_play(f"mm{i}", MAGIC_MAZE_ID, all_five(), duration=durations[i], play_date=f"2025-04-19 1{i}:00:00")
            for i in range(6)
        ]
        plays_df, scores_df = self._build_mm_inputs(plays_raw)
        plays_df, scores_df = _consolidate_magic_maze(plays_df, scores_df)
        mm_row = plays_df[plays_df["game_id"] == MAGIC_MAZE_ID].iloc[0]
        assert mm_row["duration_estimated"]

    def test_estimated_false_if_no_zeros(self):
        plays_raw = [
            make_play(f"mm{i}", MAGIC_MAZE_ID, all_five(), duration=10, play_date=f"2025-04-19 1{i}:00:00")
            for i in range(6)
        ]
        plays_df, scores_df = self._build_mm_inputs(plays_raw)
        plays_df, scores_df = _consolidate_magic_maze(plays_df, scores_df)
        mm_row = plays_df[plays_df["game_id"] == MAGIC_MAZE_ID].iloc[0]
        assert not mm_row["duration_estimated"]

    def test_two_sessions_on_different_dates_stay_separate(self):
        session_a = [
            make_play(f"a{i}", MAGIC_MAZE_ID, all_five(), duration=10, play_date=f"2025-04-19 1{i}:00:00")
            for i in range(3)
        ]
        session_b = [
            make_play(f"b{i}", MAGIC_MAZE_ID, all_five(), duration=10, play_date=f"2025-05-01 1{i}:00:00")
            for i in range(3)
        ]
        plays_df, scores_df = self._build_mm_inputs(session_a + session_b)
        plays_df, scores_df = _consolidate_magic_maze(plays_df, scores_df)
        mm_plays = plays_df[plays_df["game_id"] == MAGIC_MAZE_ID]
        assert len(mm_plays) == 2

    def test_non_magic_maze_plays_unaffected(self):
        other = make_play("other1", 1, all_five(), duration=60)
        mm = make_play("mm1", MAGIC_MAZE_ID, all_five(), duration=10)
        plays_df, scores_df = self._build_mm_inputs([other, mm])
        plays_df, scores_df = _consolidate_magic_maze(plays_df, scores_df)
        assert len(plays_df[plays_df["game_id"] == 1]) == 1

    def test_no_magic_maze_plays_returns_unchanged(self):
        other = make_play("other1", 1, all_five(), duration=60)
        games_raw = [make_game(1, "Other")]
        gdf = _build_games_df(games_raw)
        plays_df, scores_df = _build_plays_dfs([other], gdf, {1: 45, "_fallback": 40})
        original_len = len(plays_df)
        plays_df, scores_df = _consolidate_magic_maze(plays_df, scores_df)
        assert len(plays_df) == original_len

    def test_scores_kept_for_anchor_play_only(self):
        plays_raw = [
            make_play(f"mm{i}", MAGIC_MAZE_ID, all_five(), duration=10, play_date=f"2025-04-19 1{i}:00:00")
            for i in range(3)
        ]
        plays_df, scores_df = self._build_mm_inputs(plays_raw)
        plays_df, scores_df = _consolidate_magic_maze(plays_df, scores_df)
        mm_scores = scores_df[scores_df["game_id"] == MAGIC_MAZE_ID]
        # One anchor play × 5 players
        assert len(mm_scores) == 5


# ===========================================================================
# apply_annie_mode
# ===========================================================================

class TestApplyAnnieMode:
    def _make_dfs(self, plays_raw, games_raw):
        gdf = _build_games_df(games_raw)
        global_avg = {g["id"]: 45 for g in games_raw}
        global_avg["_fallback"] = 45
        return _build_plays_dfs(plays_raw, gdf, global_avg)

    def test_disabled_returns_unchanged(self):
        games_raw = [make_game(1, "Test")]
        scores = [make_player_score(ANNIE, winner=True)] + [
            make_player_score(p) for p in [BRIAN, BEN, KEVIN, GARRETT]
        ]
        play = make_play("p1", 1, scores)
        plays_df, scores_df = self._make_dfs([play], games_raw)
        fp, fs = apply_annie_mode(plays_df, scores_df, enabled=False)
        assert len(fp) == len(plays_df)
        assert len(fs) == len(scores_df)

    def test_annie_win_competitive_included(self):
        games_raw = [make_game(1, "Competitive", cooperative=False)]
        scores = [make_player_score(ANNIE, winner=True)] + [
            make_player_score(p) for p in [BRIAN, BEN, KEVIN, GARRETT]
        ]
        play = make_play("p1", 1, scores)
        plays_df, scores_df = self._make_dfs([play], games_raw)
        fp, _ = apply_annie_mode(plays_df, scores_df, enabled=True)
        assert len(fp) == 1

    def test_annie_loss_competitive_excluded(self):
        games_raw = [make_game(1, "Competitive", cooperative=False)]
        scores = [make_player_score(BRIAN, winner=True)] + [
            make_player_score(p) for p in [ANNIE, BEN, KEVIN, GARRETT]
        ]
        play = make_play("p1", 1, scores)
        plays_df, scores_df = self._make_dfs([play], games_raw)
        fp, _ = apply_annie_mode(plays_df, scores_df, enabled=True)
        assert len(fp) == 0

    def test_coop_play_always_included(self):
        games_raw = [make_game(2, "Co-op Game", cooperative=True)]
        play = make_play("p1", 2, all_five())
        plays_df, scores_df = self._make_dfs([play], games_raw)
        fp, _ = apply_annie_mode(plays_df, scores_df, enabled=True)
        assert len(fp) == 1

    def test_mixed_competitive_and_coop(self):
        games_raw = [
            make_game(1, "Competitive", cooperative=False),
            make_game(2, "Co-op",       cooperative=True),
        ]
        annie_win_scores = [make_player_score(ANNIE, winner=True)] + [
            make_player_score(p) for p in [BRIAN, BEN, KEVIN, GARRETT]
        ]
        annie_loss_scores = [make_player_score(BRIAN, winner=True)] + [
            make_player_score(p) for p in [ANNIE, BEN, KEVIN, GARRETT]
        ]
        plays_raw = [
            make_play("win",  1, annie_win_scores,  play_date="2025-01-01 10:00:00"),
            make_play("loss", 1, annie_loss_scores, play_date="2025-02-01 10:00:00"),
            make_play("coop", 2, all_five(),         play_date="2025-03-01 10:00:00"),
        ]
        plays_df, scores_df = self._make_dfs(plays_raw, games_raw)
        fp, _ = apply_annie_mode(plays_df, scores_df, enabled=True)
        assert set(fp["play_id"]) == {"win", "coop"}

    def test_no_winner_recorded_excluded(self):
        games_raw = [make_game(1, "Competitive", cooperative=False)]
        play = make_play("p1", 1, all_five())  # all winner=False
        plays_df, scores_df = self._make_dfs([play], games_raw)
        fp, _ = apply_annie_mode(plays_df, scores_df, enabled=True)
        assert len(fp) == 0

    def test_scores_df_filtered_consistently(self):
        games_raw = [make_game(1, "Competitive", cooperative=False)]
        annie_win = [make_player_score(ANNIE, winner=True)] + [
            make_player_score(p) for p in [BRIAN, BEN, KEVIN, GARRETT]
        ]
        annie_loss = [make_player_score(BRIAN, winner=True)] + [
            make_player_score(p) for p in [ANNIE, BEN, KEVIN, GARRETT]
        ]
        plays_raw = [
            make_play("win",  1, annie_win,  play_date="2025-01-01 10:00:00"),
            make_play("loss", 1, annie_loss, play_date="2025-02-01 10:00:00"),
        ]
        plays_df, scores_df = self._make_dfs(plays_raw, games_raw)
        fp, fs = apply_annie_mode(plays_df, scores_df, enabled=True)
        assert set(fs["play_id"]) == {"win"}
        assert len(fs) == 5  # 5 player rows for the one kept play
