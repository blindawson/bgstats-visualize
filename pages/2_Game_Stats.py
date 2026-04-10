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

st.title("Game Stats" + (" 🌸" if annie_mode else ""))

if plays.empty:
    st.info("No plays match the current filter.")
    st.stop()

# ---------------------------------------------------------------------------
# All-games summary table
# ---------------------------------------------------------------------------
st.subheader("All games")

game_summary = (
    plays.groupby("game_id")
    .agg(
        plays=("play_id", "count"),
        total_min=("duration_min", "sum"),
        first_play=("play_date", "min"),
        last_play=("play_date", "max"),
    )
    .reset_index()
)
game_summary["name"] = game_summary["game_id"].map(games["name"])
game_summary["total_hr"] = (game_summary["total_min"] / 60).round(1)

if not rankings_df.empty:
    game_summary = game_summary.merge(
        rankings_df[["rank", "score"]], left_on="game_id", right_index=True, how="left"
    )
    display_cols = ["name", "rank", "score", "plays", "total_hr", "first_play", "last_play"]
    rename_map = {
        "name": "Game", "rank": "Rank", "score": "Score",
        "plays": "Plays", "total_hr": "Total (hr)",
        "first_play": "First played", "last_play": "Last played",
    }
    col_cfg = {
        "Rank": st.column_config.NumberColumn("Rank", format="%d"),
        "Score": st.column_config.NumberColumn("Score", format="%.1f"),
        "Total (hr)": st.column_config.NumberColumn("Total (hr)", format="%.1f"),
        "Plays": st.column_config.NumberColumn("Plays"),
        "First played": st.column_config.DateColumn("First played", format="MMM DD, YYYY"),
        "Last played": st.column_config.DateColumn("Last played", format="MMM DD, YYYY"),
    }
else:
    display_cols = ["name", "plays", "total_hr", "first_play", "last_play"]
    rename_map = {
        "name": "Game", "plays": "Plays", "total_hr": "Total (hr)",
        "first_play": "First played", "last_play": "Last played",
    }
    col_cfg = {
        "Total (hr)": st.column_config.NumberColumn("Total (hr)", format="%.1f"),
        "Plays": st.column_config.NumberColumn("Plays"),
        "First played": st.column_config.DateColumn("First played", format="MMM DD, YYYY"),
        "Last played": st.column_config.DateColumn("Last played", format="MMM DD, YYYY"),
    }

st.dataframe(
    game_summary[display_cols]
    .rename(columns=rename_map)
    .sort_values("Total (hr)", ascending=False),
    column_config=col_cfg,
    width="stretch",
    hide_index=True,
)

st.divider()

# ---------------------------------------------------------------------------
# Game selector (alphabetical)
# ---------------------------------------------------------------------------
played_game_ids = plays["game_id"].unique()
game_names_sorted = (
    games.loc[games.index.isin(played_game_ids), "name"]
    .sort_values()
    .reset_index()
)
game_options = list(zip(game_names_sorted["game_id"], game_names_sorted["name"]))
name_list = [name for _, name in game_options]

last_played_id = plays.sort_values("play_date").iloc[-1]["game_id"]
last_played_name = games.loc[last_played_id, "name"] if last_played_id in games.index else name_list[0]
default_idx = name_list.index(last_played_name) if last_played_name in name_list else 0

selected_name = st.selectbox("Select a game", options=name_list, index=default_idx)
selected_id = game_options[name_list.index(selected_name)][0]

game_info = games.loc[selected_id]
game_plays = plays[plays["game_id"] == selected_id].sort_values("play_date")
game_scores = scores[scores["game_id"] == selected_id]
is_coop = bool(game_info["cooperative"])

# ---------------------------------------------------------------------------
# Game header
# ---------------------------------------------------------------------------
header_col, thumb_col = st.columns([4, 1])
with header_col:
    st.subheader(game_info["name"])
    tags = []
    if is_coop:
        tags.append("🤝 Co-op")
    if game_info.get("designers"):
        tags.append(f"✏️ {game_info['designers']}")
    if game_info.get("bgg_year"):
        tags.append(f"📅 {int(game_info['bgg_year'])}")
    if not rankings_df.empty and selected_id in rankings_df.index:
        r = rankings_df.loc[selected_id]
        tags.append(f"🏆 Group rank #{int(r['rank'])} · {r['score']:.1f}/100")
    st.caption("  ·  ".join(tags))

with thumb_col:
    if game_info.get("url_thumb"):
        st.image(game_info["url_thumb"], width=120)

st.divider()

# ---------------------------------------------------------------------------
# Key metrics
# ---------------------------------------------------------------------------
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("Total plays", len(game_plays))
with m2:
    total_min = game_plays["duration_min"].sum()
    st.metric("Total time", f"{total_min // 60}h {total_min % 60}m")
with m3:
    avg_min = int(game_plays["duration_min"].mean()) if len(game_plays) else 0
    st.metric("Avg duration", f"{avg_min} min")
with m4:
    first_play = game_plays["play_date"].min().strftime("%b %d, %Y") if len(game_plays) else "—"
    st.metric("First played", first_play)
with m5:
    last_play = game_plays["play_date"].max().strftime("%b %d, %Y") if len(game_plays) else "—"
    st.metric("Last played", last_play)

st.divider()

# ---------------------------------------------------------------------------
# Win rates (competitive only)
# ---------------------------------------------------------------------------
if is_coop:
    st.caption("Win statistics are not tracked for co-op games.")
else:
    st.subheader("Win rates")

    plays_with_winner = game_scores[game_scores.groupby("play_id")["winner"].transform("any")]
    total_decided = plays_with_winner["play_id"].nunique()

    win_counts = (
        game_scores[game_scores["winner"] == True]
        .groupby("player_name")
        .size()
        .reset_index(name="wins")
    )
    win_counts["total"] = total_decided
    win_counts["win_pct"] = (win_counts["wins"] / win_counts["total"] * 100).round(1)

    all_players = pd.DataFrame({"player_name": PLAYERS_ALPHA})
    win_counts = all_players.merge(win_counts, on="player_name", how="left").fillna(
        {"wins": 0, "total": total_decided, "win_pct": 0}
    )
    win_counts = win_counts.sort_values("win_pct", ascending=False)

    fig = px.bar(
        win_counts,
        x="player_name", y="win_pct",
        text=win_counts.apply(lambda r: f"{int(r.wins)}/{int(r.total)}", axis=1),
        labels={"player_name": "", "win_pct": "Win %"},
        color="player_name",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False, margin=dict(t=20, b=0), yaxis=dict(range=[0, 105]), dragmode=False)
    st.plotly_chart(fig, width="stretch", config={"scrollZoom": False})
    st.divider()

# ---------------------------------------------------------------------------
# Score history (competitive + scored games only)
# ---------------------------------------------------------------------------
has_scores = game_scores["score"].notna().any()
if has_scores and not is_coop:
    st.subheader("Score history")
    score_history = game_scores[game_scores["score"].notna()].copy()

    sh = score_history.sort_values("play_date").copy()
    fig = px.scatter(
        sh,
        x="play_date", y="score",
        color="player_name",
        symbol="player_name",
        labels={"play_date": "Date", "score": "Score", "player_name": "Player"},
        color_discrete_sequence=px.colors.qualitative.Set2,
        category_orders={"player_name": PLAYERS_ALPHA},
    )
    fig.update_traces(marker=dict(size=10))
    fig.update_layout(margin=dict(t=20, b=0), dragmode=False)
    st.plotly_chart(fig, width="stretch", config={"scrollZoom": False})
    st.divider()

# ---------------------------------------------------------------------------
# Session log — one row per play, score columns per player (alphabetical)
# ---------------------------------------------------------------------------
st.subheader("Session log")

def fmt_duration(row):
    m = row["duration_min"]
    s = f"{m // 60}h {m % 60}m" if m >= 60 else f"{m}m"
    return s + " *" if row["duration_estimated"] else s

log_rows = []
winner_sets = []  # parallel list: set of winning player names per row

for _, play in game_plays.sort_values("play_date", ascending=False).iterrows():
    pid = play["play_id"]
    play_scores = game_scores[game_scores["play_id"] == pid]
    winners = set(play_scores[play_scores["winner"] == True]["player_name"].tolist())
    winner_sets.append(winners)

    row: dict = {
        "Date": play["play_date"].strftime("%b %d, %Y"),
        "Duration": int(play["duration_min"]),
        "_dur_label": fmt_duration(play),
    }

    if not is_coop:
        row["Winner"] = ", ".join(sorted(winners)) if winners else "—"

    for player in PLAYERS_ALPHA:
        ps = play_scores[play_scores["player_name"] == player]
        row[player] = None if ps.empty else ps.iloc[0]["score"]

    log_rows.append(row)

log_df = pd.DataFrame(log_rows)

# Only show player score columns if any scores exist for this game
score_cols_exist = any(log_df[p].notna().any() for p in PLAYERS_ALPHA if p in log_df.columns)

def _fmt_dur_min(m: float) -> str:
    m = int(round(m))
    return f"{m // 60}h {m % 60}m" if m >= 60 else f"{m}m"

if score_cols_exist and not is_coop:
    # Build min/median/max summary rows
    raw_dur = game_plays.sort_values("play_date", ascending=False)["duration_min"].values
    summary_rows = []
    for label, fn in [("Min", "min"), ("Median", "median"), ("Max", "max")]:
        sr: dict = {"Date": label, "Winner": "", "Duration": None, "_dur_label": ""}
        dur_vals = pd.Series(raw_dur, dtype=float)
        sr["Duration"] = int(round(getattr(dur_vals, fn)()))
        sr["_dur_label"] = _fmt_dur_min(getattr(dur_vals, fn)())
        for player in PLAYERS_ALPHA:
            col = pd.to_numeric(log_df[player], errors="coerce").dropna()
            sr[player] = round(getattr(col, fn)(), 1) if len(col) else None
        summary_rows.append(sr)
    summary_df = pd.DataFrame(summary_rows)

    # Highlight winner cells in player columns using pandas Styler
    def highlight_winners(df: pd.DataFrame) -> pd.DataFrame:
        style_df = pd.DataFrame("", index=df.index, columns=df.columns)
        for i, w_set in enumerate(winner_sets):
            for player in PLAYERS_ALPHA:
                if player in df.columns and player in w_set:
                    val = df.iloc[i][player]
                    if pd.notna(val):
                        style_df.iloc[i, df.columns.get_loc(player)] = (
                            "background-color: #c6efce; color: #276221; font-weight: bold"
                        )
        return style_df

    display_cols = ["Date", "Winner"] + PLAYERS_ALPHA + ["Duration", "_dur_label"]
    display_df = log_df[[c for c in display_cols if c in log_df.columns]]

    # Append summary rows (no highlighting)
    full_df = pd.concat([display_df, summary_df[display_df.columns]], ignore_index=True)
    n_data = len(display_df)

    def highlight_all(df: pd.DataFrame) -> pd.DataFrame:
        style_df = pd.DataFrame("", index=df.index, columns=df.columns)
        for i, w_set in enumerate(winner_sets):
            for player in PLAYERS_ALPHA:
                if player in df.columns and player in w_set:
                    val = df.iloc[i][player]
                    if pd.notna(val):
                        style_df.iloc[i, df.columns.get_loc(player)] = (
                            "background-color: #c6efce; color: #276221; font-weight: bold"
                        )
        for i in range(n_data, len(df)):
            for col in df.columns:
                style_df.iloc[i, df.columns.get_loc(col)] = "font-style: italic; color: #888"
        return style_df

    score_col_config = {p: st.column_config.NumberColumn(p, format="%g") for p in PLAYERS_ALPHA}
    score_col_config["Duration"] = st.column_config.NumberColumn("Duration (min)", format="%d min")
    score_col_config["_dur_label"] = None  # hidden — used only for display reference
    st.dataframe(
        full_df.style.apply(highlight_all, axis=None),
        column_config=score_col_config,
        width="stretch",
        hide_index=True,
    )
elif is_coop:
    st.dataframe(
        log_df[["Date", "Duration"]].rename(columns={"Duration": "Duration (min)"}),
        column_config={"Duration (min)": st.column_config.NumberColumn("Duration (min)")},
        width="stretch",
        hide_index=True,
    )
else:
    cols = [c for c in ["Date", "Winner", "Duration"] if c in log_df.columns]
    st.dataframe(
        log_df[cols].rename(columns={"Duration": "Duration (min)"}),
        column_config={"Duration (min)": st.column_config.NumberColumn("Duration (min)")},
        width="stretch",
        hide_index=True,
    )

if game_plays["duration_estimated"].any():
    st.caption("\\* Duration estimated from global average for that game")
if score_cols_exist and not is_coop:
    st.caption("Highlighted scores indicate the winner(s)")
