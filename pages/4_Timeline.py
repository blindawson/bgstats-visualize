import streamlit as st
import pandas as pd
import plotly.express as px

if "plays_df" not in st.session_state:
    st.warning("Please start the app from the home page.")
    st.stop()

plays: pd.DataFrame = st.session_state["plays_df"]
scores: pd.DataFrame = st.session_state["scores_df"]
games: pd.DataFrame = st.session_state["games_df"]
annie_mode: bool = st.session_state.get("annie_mode", False)

st.title("Timeline" + (" 🌸" if annie_mode else ""))

if plays.empty:
    st.info("No plays match the current filter.")
    st.stop()

sorted_plays = plays.sort_values("play_date").copy()

# ---------------------------------------------------------------------------
# Plays per session — stacked by game, height = total duration, with box art
# ---------------------------------------------------------------------------
st.subheader("Plays per session")

play_rows_tl = []
for _, play in sorted_plays.iterrows():
    gid = play["game_id"]
    g = games.loc[gid] if gid in games.index else None
    play_winners = scores[
        (scores["play_id"] == play["play_id"]) & (scores["winner"] == True)
    ]["player_name"].tolist()
    if play["cooperative"]:
        winner_str = "Co-op"
    elif play_winners:
        winner_str = ", ".join(sorted(play_winners))
    else:
        winner_str = "—"
    play_rows_tl.append({
        "date": play["play_date"].date(),
        "game_name": g["name"] if g is not None else "Unknown",
        "duration_min": play["duration_min"],
        "url_thumb": (g["url_thumb"] or "") if g is not None else "",
        "winner": winner_str,
    })
play_tl = pd.DataFrame(play_rows_tl).sort_values(["date", "game_name"])

fig2 = px.bar(
    play_tl,
    x="date",
    y="duration_min",
    color="game_name",
    barmode="stack",
    custom_data=["winner"],
    labels={"date": "", "duration_min": "Duration (min)", "game_name": "Game"},
    color_discrete_sequence=px.colors.qualitative.Set3,
    category_orders={"game_name": sorted(play_tl["game_name"].unique())},
)
fig2.update_traces(
    hovertemplate="<b>%{fullData.name}</b><br>%{y} min<br>Winner: %{customdata[0]}<extra></extra>"
)
fig2.update_layout(
    bargap=0.1,
    height=520,
    margin=dict(t=20, b=100),
    dragmode=False,
    legend=dict(
        orientation="h", y=-0.25, x=0, title_text="",
        itemclick="toggleothers",
        itemdoubleclick="toggle",
    ),
)

# Add box art images centred on each bar segment
session_dates = sorted(play_tl["date"].unique())
if len(session_dates) >= 2:
    import numpy as np
    gaps_days = [(session_dates[i + 1] - session_dates[i]).days for i in range(len(session_dates) - 1)]
    img_width_ms = float(np.median(gaps_days)) * 86400000 * 0.65
else:
    img_width_ms = 7 * 86400000.0

for date, grp in play_tl.groupby("date"):
    cumulative = 0.0
    for _, row in grp.iterrows():
        seg = float(row["duration_min"])
        url = row["url_thumb"]
        if url and seg >= 15:
            fig2.add_layout_image(
                source=url,
                x=str(date),
                y=cumulative + seg / 2,
                xref="x",
                yref="y",
                xanchor="center",
                yanchor="middle",
                sizex=img_width_ms,
                sizey=seg,
                sizing="contain",
                layer="above",
                opacity=0.9,
            )
        cumulative += seg

st.plotly_chart(fig2, width="stretch", config={"scrollZoom": False})

st.divider()

# ---------------------------------------------------------------------------
# New games introduced over time
# ---------------------------------------------------------------------------
st.subheader("New games introduced over time")
seen: set = set()
new_game_rows = []
for _, row in sorted_plays.iterrows():
    if row["game_id"] not in seen:
        seen.add(row["game_id"])
        new_game_rows.append({
            "play_date": row["play_date"],
            "game_name": games.loc[row["game_id"], "name"] if row["game_id"] in games.index else "Unknown",
            "total_unique": len(seen),
        })
new_games_df = pd.DataFrame(new_game_rows)

fig3 = px.line(
    new_games_df,
    x="play_date", y="total_unique",
    hover_data=["game_name"],
    labels={"play_date": "Date", "total_unique": "Unique games", "game_name": "New game"},
    color_discrete_sequence=["#F58518"],
)
fig3.update_layout(margin=dict(t=20, b=0), dragmode=False)
st.plotly_chart(fig3, width="stretch", config={"scrollZoom": False})
