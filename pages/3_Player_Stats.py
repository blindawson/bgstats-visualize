import streamlit as st
import pandas as pd
import plotly.express as px

if "plays_df" not in st.session_state:
    st.warning("Please start the app from the home page.")
    st.stop()

plays: pd.DataFrame = st.session_state["plays_df"]
scores: pd.DataFrame = st.session_state["scores_df"]
games: pd.DataFrame = st.session_state["games_df"]
rankings_df: pd.DataFrame = st.session_state.get("rankings_df", pd.DataFrame())
annie_mode: bool = st.session_state.get("annie_mode", False)

PLAYERS_ALPHA = ["Annie", "Ben", "Brian", "Garrett", "Kevin"]

st.title("Player stats" + (" 🌸" if annie_mode else ""))

if plays.empty:
    st.info("No plays match the current filter.")
    st.stop()

# ---------------------------------------------------------------------------
# Player selector
# ---------------------------------------------------------------------------
selected_player = st.selectbox("Select a player", options=PLAYERS_ALPHA)
player_scores = scores[scores["player_name"] == selected_player]
comp_scores = player_scores[player_scores["cooperative"] == False]

# Decided competitive plays (at least one winner recorded)
decided_play_ids = (
    scores[(scores["cooperative"] == False)]
    .groupby("play_id")["winner"]
    .any()[lambda x: x]
    .index
)
comp_decided = comp_scores[comp_scores["play_id"].isin(decided_play_ids)]
wins = comp_decided[comp_decided["winner"] == True]["play_id"].nunique()
total_decided = comp_decided["play_id"].nunique()

# Time-based win %: minutes in winning plays / minutes in all competitive plays
comp_play_ids = comp_scores["play_id"].unique()
comp_plays_df = plays[plays["play_id"].isin(comp_play_ids)]
win_play_ids = comp_decided[comp_decided["winner"] == True]["play_id"].unique()
time_all_comp = comp_plays_df["duration_min"].sum()
time_wins = plays[plays["play_id"].isin(win_play_ids)]["duration_min"].sum()

st.divider()

# ---------------------------------------------------------------------------
# Overall win % metrics
# ---------------------------------------------------------------------------
c1, c2 = st.columns(2)
with c1:
    pct = f"{wins / total_decided * 100:.0f}%" if total_decided else "—"
    st.metric("Win rate (by plays)", f"{pct}  ({wins} / {total_decided})")
with c2:
    tpct = f"{time_wins / time_all_comp * 100:.0f}%" if time_all_comp else "—"
    st.metric("Win rate (by time)", tpct,
              help="Time spent in winning games ÷ total time in competitive games")

st.divider()

# ---------------------------------------------------------------------------
# Win rate by game — top 10 by win %
# ---------------------------------------------------------------------------
st.subheader("Win rate by game (top 10)")
game_stats = (
    comp_decided.groupby("game_id")
    .agg(plays=("play_id", "nunique"), wins=("winner", "sum"))
    .reset_index()
)
game_stats["win_pct"] = (game_stats["wins"] / game_stats["plays"] * 100).round(1)
game_stats["name"] = game_stats["game_id"].map(games["name"])
top = game_stats.sort_values("win_pct", ascending=False).head(10).sort_values("win_pct")

fig = px.bar(
    top, x="win_pct", y="name",
    orientation="h",
    text=top.apply(lambda r: f"{int(r.wins)}/{int(r.plays)}", axis=1),
    labels={"win_pct": "Win %", "name": ""},
    color_discrete_sequence=["#72B7B2"],
)
fig.update_traces(textposition="outside")
fig.update_layout(margin=dict(t=20, b=0), xaxis=dict(range=[0, 110]), dragmode=False)
st.plotly_chart(fig, width="stretch", config={"scrollZoom": False})

st.divider()

# ---------------------------------------------------------------------------
# All games breakdown
# ---------------------------------------------------------------------------
st.subheader("All games breakdown")

all_game_stats = (
    player_scores.groupby("game_id")
    .agg(plays=("play_id", "nunique"), wins=("winner", "sum"))
    .reset_index()
)
all_game_stats["name"] = all_game_stats["game_id"].map(games["name"])
all_game_stats["cooperative"] = all_game_stats["game_id"].map(games["cooperative"])
all_game_stats["total_min"] = all_game_stats["game_id"].map(
    plays.groupby("game_id")["duration_min"].sum()
)
all_game_stats["total_hr"] = (all_game_stats["total_min"] / 60).round(1)
all_game_stats["win_pct_num"] = all_game_stats.apply(
    lambda r: round(r.wins / r.plays * 100) if not r.cooperative and r.plays > 0 else None,
    axis=1,
)
all_game_stats["wins_num"] = all_game_stats.apply(
    lambda r: int(r.wins) if not r.cooperative else None, axis=1
)
all_game_stats["type"] = all_game_stats["cooperative"].map({True: "Co-op", False: "Competitive"})

if not rankings_df.empty:
    all_game_stats = all_game_stats.merge(
        rankings_df[["rank", "score"]], left_on="game_id", right_index=True, how="left"
    )
    display_cols_ags = ["name", "rank", "score", "total_hr", "plays", "wins_num", "win_pct_num", "type"]
    rename_ags = {
        "name": "Game", "rank": "Rank", "score": "Score",
        "total_hr": "Total time (hr)", "plays": "Plays",
        "wins_num": "Wins", "win_pct_num": "Win %", "type": "Type",
    }
    col_cfg_ags = {
        "Rank": st.column_config.NumberColumn("Rank", format="%d"),
        "Score": st.column_config.NumberColumn("Score", format="%.1f"),
        "Total time (hr)": st.column_config.NumberColumn("Total time (hr)", format="%.1f"),
        "Plays": st.column_config.NumberColumn("Plays"),
        "Wins": st.column_config.NumberColumn("Wins"),
        "Win %": st.column_config.NumberColumn("Win %", format="%d%%"),
    }
else:
    display_cols_ags = ["name", "total_hr", "plays", "wins_num", "win_pct_num", "type"]
    rename_ags = {
        "name": "Game", "total_hr": "Total time (hr)", "plays": "Plays",
        "wins_num": "Wins", "win_pct_num": "Win %", "type": "Type",
    }
    col_cfg_ags = {
        "Total time (hr)": st.column_config.NumberColumn("Total time (hr)", format="%.1f"),
        "Plays": st.column_config.NumberColumn("Plays"),
        "Wins": st.column_config.NumberColumn("Wins"),
        "Win %": st.column_config.NumberColumn("Win %", format="%d%%"),
    }

st.dataframe(
    all_game_stats[display_cols_ags]
    .rename(columns=rename_ags)
    .sort_values("Total time (hr)", ascending=False),
    column_config=col_cfg_ags,
    width="stretch",
    hide_index=True,
)

st.divider()

# ---------------------------------------------------------------------------
# Streaks
# ---------------------------------------------------------------------------
st.subheader("Streaks")

# Build ordered list of decided competitive plays for this player
comp_play_seq = (
    comp_decided
    .drop_duplicates("play_id")
    .sort_values("play_date")[["play_id", "play_date", "game_id", "winner"]]
    .to_dict("records")
)

def _streak(seq, won_key="won"):
    """Return (max_streak_len, list_of_entries_in_best_streak) for consecutive True values."""
    best, best_run = 0, []
    cur, cur_run = 0, []
    for entry in seq:
        if entry[won_key]:
            cur += 1
            cur_run.append(entry)
            if cur > best:
                best, best_run = cur, cur_run.copy()
        else:
            cur, cur_run = 0, []
    return best, best_run

def _loss_streak(seq):
    """Return (streak_len, loss_run_with_sandwich_wins)."""
    best, best_run = 0, []
    cur, cur_run = 0, []
    prev_win = None
    for idx, entry in enumerate(seq):
        if not entry["won"]:
            cur += 1
            cur_run.append(entry)
            if cur >= best:
                best = cur
                # include the win immediately before (if any) and peek at next win
                sandwich = (([prev_win] if prev_win else []) + cur_run.copy())
                best_run = (sandwich, idx)  # store idx to resolve next win later
        else:
            cur, cur_run = 0, []
            prev_win = entry
    if best == 0:
        return 0, []
    sandwich_partial, last_loss_idx = best_run
    # append the win immediately after the streak (if any)
    next_idx = last_loss_idx + 1
    if next_idx < len(seq) and seq[next_idx]["won"]:
        full_run = sandwich_partial + [seq[next_idx]]
    else:
        full_run = sandwich_partial
    return best, full_run

entries = [
    {"play_id": r["play_id"], "play_date": r["play_date"],
     "game_id": r["game_id"], "won": bool(r["winner"])}
    for r in comp_play_seq
]

win_n, win_run = _streak(entries)
loss_n, loss_run = _loss_streak(entries)

def _game_name(gid):
    return games.loc[gid, "name"] if gid in games.index else "?"

def _win_streak_label(run):
    if not run:
        return "—"
    date_range = (
        f"{run[0]['play_date'].strftime('%b %d, %Y')} – {run[-1]['play_date'].strftime('%b %d, %Y')}"
        if len(run) > 1 else run[0]["play_date"].strftime("%b %d, %Y")
    )
    return f"{date_range}  ·  " + ", ".join(_game_name(e["game_id"]) for e in run)

def _loss_streak_md(run):
    """Return markdown string with sandwich wins on separate lines.

    run is always structured as [win_before?, loss..., win_after?] — use
    positional checks rather than date comparisons so same-day wins are captured.
    """
    if not run:
        return "—"
    lines = []
    losses = [e for e in run if not e["won"]]
    # Use position: first element is sandwich-before if it's a win;
    # last element is sandwich-after if it's a win (and different from first).
    sandwich_before = run[0] if run[0]["won"] else None
    sandwich_after = run[-1] if (run[-1]["won"] and run[-1] is not run[0]) else None

    if sandwich_before:
        e = sandwich_before
        lines.append(f"{e['play_date'].strftime('%b %d, %Y')} — {_game_name(e['game_id'])} *(win)*")

    if losses:
        loss_names = ", ".join(_game_name(e["game_id"]) for e in losses)
        if len(losses) == 1:
            date_part = losses[0]["play_date"].strftime("%b %d, %Y")
        else:
            date_part = f"{losses[0]['play_date'].strftime('%b %d, %Y')} – {losses[-1]['play_date'].strftime('%b %d, %Y')}"
        lines.append(f"{date_part} — losses: {loss_names}")

    if sandwich_after:
        e = sandwich_after
        lines.append(f"{e['play_date'].strftime('%b %d, %Y')} — {_game_name(e['game_id'])} *(win)*")

    return "\n\n".join(lines)

sc1, sc2 = st.columns(2)
with sc1:
    st.metric("Longest win streak", f"{win_n} games" if win_n else "—")
    if win_run:
        st.caption(_win_streak_label(win_run))
with sc2:
    st.metric("Longest losing streak", f"{loss_n} games" if loss_n else "—")
    if loss_run:
        st.markdown(_loss_streak_md(loss_run))

# Per-game win streaks
per_game = []
for gid in comp_decided["game_id"].unique():
    game_seq = [e for e in entries if e["game_id"] == gid]
    gn, grun = _streak(game_seq)
    if gn >= 2:
        per_game.append({
            "Game": games.loc[gid, "name"] if gid in games.index else "?",
            "Streak": gn,
            "_start": grun[0]["play_date"],
            "_end": grun[-1]["play_date"],
        })

if per_game:
    st.markdown("**Win streaks by game** (2+ in a row)")
    streak_df = (
        pd.DataFrame(per_game)
        .sort_values("Streak", ascending=False)
    )
    streak_df["Date range"] = streak_df.apply(
        lambda r: (
            f"{r['_start'].strftime('%b %d, %Y')} – {r['_end'].strftime('%b %d, %Y')}"
            if r["_start"] != r["_end"] else r["_start"].strftime("%b %d, %Y")
        ),
        axis=1,
    )
    st.dataframe(
        streak_df[["Game", "Streak", "Date range"]],
        column_config={"Streak": st.column_config.NumberColumn("Streak")},
        width="stretch",
        hide_index=True,
    )
