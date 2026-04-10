import streamlit as st
import streamlit.components.v1 as components
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

st.title("Dashboard" + (" 🌸" if annie_mode else ""))

if plays.empty:
    st.info("No plays match the current filter.")
    st.stop()

# ---------------------------------------------------------------------------
# Top metrics
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Plays", len(plays))
with col2:
    total_min = plays["duration_min"].sum()
    st.metric("Hours Played", f"{total_min // 60}h {total_min % 60}m")
with col3:
    st.metric("Unique Games", plays["game_id"].nunique())
with col4:
    sessions = plays["play_date"].dt.date.nunique()
    st.metric("Sessions", sessions)

st.divider()

# ---------------------------------------------------------------------------
# Plays per year — bars show play count, labeled with plays + hours
# ---------------------------------------------------------------------------
st.subheader("Plays per year")
by_year = (
    plays.assign(year=plays["play_date"].dt.year)
    .groupby("year")
    .agg(plays=("play_id", "count"), total_min=("duration_min", "sum"))
    .reset_index()
)
by_year["label"] = by_year.apply(
    lambda r: f"{r.plays} plays · {r.total_min // 60}h", axis=1
)
fig = px.bar(
    by_year, x="year", y="plays",
    text="label",
    labels={"year": "Year", "plays": "Plays"},
    color_discrete_sequence=["#4C78A8"],
)
fig.update_traces(textposition="outside")
fig.update_layout(margin=dict(t=20, b=0), xaxis=dict(tickmode="linear"), dragmode=False)
st.plotly_chart(fig, width="stretch", config={"scrollZoom": False})

# ---------------------------------------------------------------------------
# Top 10 by plays and top 10 by duration — side by side
# ---------------------------------------------------------------------------
top_games_base = (
    plays.groupby("game_id")
    .agg(plays=("play_id", "count"), total_min=("duration_min", "sum"))
    .reset_index()
)
top_games_base["name"] = top_games_base["game_id"].map(games["name"])

col_plays, col_dur = st.columns(2)

with col_plays:
    st.subheader("Top 10 by plays")
    top_by_plays = top_games_base.sort_values("plays", ascending=False).head(10)
    top_by_plays["label"] = top_by_plays.apply(
        lambda r: f"{r.plays} · {r.total_min // 60}h", axis=1
    )
    fig2 = px.bar(
        top_by_plays.sort_values("plays"),
        x="plays", y="name", orientation="h", text="label",
        labels={"plays": "Plays", "name": ""},
        color_discrete_sequence=["#72B7B2"],
    )
    fig2.update_traces(textposition="outside")
    fig2.update_layout(margin=dict(t=20, b=0), dragmode=False)
    st.plotly_chart(fig2, width="stretch", config={"scrollZoom": False})

with col_dur:
    st.subheader("Top 10 by time")
    top_by_dur = top_games_base.sort_values("total_min", ascending=False).head(10)
    top_by_dur["total_hr"] = (top_by_dur["total_min"] / 60).round(1)
    top_by_dur["label"] = top_by_dur.apply(
        lambda r: f"{r.total_hr:.1f}h · {int(r.plays)} plays", axis=1
    )
    fig3 = px.bar(
        top_by_dur.sort_values("total_min"),
        x="total_hr", y="name", orientation="h", text="label",
        labels={"total_hr": "Hours", "name": ""},
        color_discrete_sequence=["#F58518"],
    )
    fig3.update_traces(textposition="outside")
    fig3.update_layout(margin=dict(t=20, b=0), dragmode=False)
    st.plotly_chart(fig3, width="stretch", config={"scrollZoom": False})

st.divider()

# ---------------------------------------------------------------------------
# Time played treemap — one box per game, sized by total duration, with box art
# ---------------------------------------------------------------------------
st.subheader("All games")

game_time = (
    plays.groupby("game_id")
    .agg(total_min=("duration_min", "sum"))
    .reset_index()
)
game_time["name"] = game_time["game_id"].map(games["name"])
game_time["url_thumb"] = game_time["game_id"].map(games["url_thumb"]).fillna("")
game_time["total_time"] = game_time["total_min"].apply(
    lambda m: f"{m // 60}h {m % 60}m" if m >= 60 else f"{m}m"
)

# --- Squarified treemap layout (pure Python) ---
TM_W = 1000.0
TM_H = max(360.0, len(game_time) * 16.0)

def _worst_ratio(row, w, h):
    area = sum(row)
    if area == 0 or w == 0 or h == 0:
        return float("inf")
    if w >= h:
        sh = area / w
        return max(max(s / sh, sh) / min(s / sh, sh) for s in row if s > 0)
    else:
        sw = area / h
        return max(max(sw, s / sw) / min(sw, s / sw) for s in row if s > 0)

def _sq(sizes, x, y, w, h):
    if not sizes or w <= 0 or h <= 0:
        return []
    if len(sizes) == 1:
        return [(x, y, w, h)]
    row = [sizes[0]]
    for s in sizes[1:]:
        if _worst_ratio(row + [s], w, h) <= _worst_ratio(row, w, h):
            row.append(s)
        else:
            break
    n, area = len(row), sum(row)
    rects = []
    if w >= h:
        sh = area / w
        x0 = x
        for s in row:
            rects.append((x0, y, s / sh, sh))
            x0 += s / sh
        rects += _sq(sizes[n:], x, y + sh, w, max(0.0, h - sh))
    else:
        sw = area / h
        y0 = y
        for s in row:
            rects.append((x, y0, sw, s / sw))
            y0 += s / sw
        rects += _sq(sizes[n:], x + sw, y, max(0.0, w - sw), h)
    return rects

items = game_time.sort_values("total_min", ascending=False).to_dict("records")
total_area = TM_W * TM_H
total_val = sum(i["total_min"] for i in items)
sizes = [i["total_min"] / total_val * total_area for i in items]
cell_rects = _sq(sizes, 0, 0, TM_W, TM_H)

# --- Build SVG with hover tooltips ---
import html as _html
PAD = 2

html_parts = [
    "<style>",
    "  body { margin:0; background:#111; }",
    "  .tip { position:fixed; background:rgba(0,0,0,0.88); color:#fff;",
    "         padding:6px 10px; border-radius:5px; font:13px sans-serif;",
    "         pointer-events:none; display:none; z-index:99; }",
    "  .cell { cursor:default; }",
    "  .cell:hover .hover-overlay { opacity:1; }",
    "  .hover-overlay { opacity:0; transition:opacity 0.15s; }",
    "</style>",
    '<div id="tip" class="tip"></div>',
    f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
    f'viewBox="0 0 {TM_W:.0f} {TM_H:.0f}" width="100%" '
    f'style="display:block;border-radius:6px;max-width:{TM_W:.0f}px">',
]

for i, (item, rect) in enumerate(zip(items, cell_rects)):
    rx, ry, rw, rh = rect[0] + PAD, rect[1] + PAD, rect[2] - 2 * PAD, rect[3] - 2 * PAD
    if rw <= 0 or rh <= 0:
        continue
    cid = f"c{i}"
    name = _html.escape(item["name"])
    duration = item["total_time"]
    url = item["url_thumb"]

    html_parts.append(
        f'<clipPath id="{cid}"><rect x="{rx:.1f}" y="{ry:.1f}" '
        f'width="{rw:.1f}" height="{rh:.1f}" rx="4"/></clipPath>'
    )
    html_parts.append(
        f'<g class="cell" clip-path="url(#{cid})" '
        f'data-name="{name}" data-time="{duration}">'
    )
    if url:
        html_parts.append(
            f'<image href="{url}" x="{rx:.1f}" y="{ry:.1f}" '
            f'width="{rw:.1f}" height="{rh:.1f}" preserveAspectRatio="xMidYMid slice"/>'
        )
    else:
        html_parts.append(
            f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" fill="#2c5f8a"/>'
        )
    # Subtle dark overlay that appears on hover
    html_parts.append(
        f'<rect class="hover-overlay" x="{rx:.1f}" y="{ry:.1f}" '
        f'width="{rw:.1f}" height="{rh:.1f}" fill="black" fill-opacity="0.25"/>'
    )
    html_parts.append("</g>")

html_parts.append("</svg>")
html_parts += [
    "<script>",
    "  const tip = document.getElementById('tip');",
    "  document.querySelectorAll('.cell').forEach(g => {",
    "    g.addEventListener('mousemove', e => {",
    "      tip.style.display = 'block';",
    "      tip.style.left = (e.clientX + 14) + 'px';",
    "      tip.style.top  = (e.clientY + 14) + 'px';",
    "      tip.innerHTML  = '<b>' + g.dataset.name + '</b><br>' + g.dataset.time;",
    "    });",
    "    g.addEventListener('mouseleave', () => { tip.style.display = 'none'; });",
    "  });",
    "</script>",
]

components.html("\n".join(html_parts), height=int(TM_H) + 20)

# ---------------------------------------------------------------------------
# "Do you play what you love?" — group score vs hours played
# ---------------------------------------------------------------------------
if not rankings_df.empty:
    st.divider()
    st.subheader("Do you play what you love?")

    scatter_data = game_time.merge(
        rankings_df[["rank", "score"]], left_on="game_id", right_index=True, how="inner"
    )
    scatter_data["total_hr"] = (scatter_data["total_min"] / 60).round(2)
    scatter_data["rank_label"] = scatter_data["rank"].astype(int).apply(lambda r: f"#{r}")

    max_hr = float(scatter_data["total_hr"].max())
    sizex = 7.0          # score units wide
    sizey = max_hr * 0.14  # ~square at typical chart aspect ratio

    fig_sc = px.scatter(
        scatter_data,
        x="score", y="total_hr",
        custom_data=["name", "rank_label", "total_time"],
        labels={"score": "Group score", "total_hr": "Hours played"},
        color_discrete_sequence=["rgba(0,0,0,0)"],
    )
    fig_sc.update_traces(
        marker=dict(size=24, opacity=0),
        hovertemplate=(
            "<b>%{customdata[1]} %{customdata[0]}</b><br>"
            "Score: %{x:.1f}<br>"
            "%{customdata[2]}<extra></extra>"
        ),
    )
    for _, row in scatter_data.iterrows():
        if row["url_thumb"]:
            fig_sc.add_layout_image(
                source=row["url_thumb"],
                x=float(row["score"]), y=float(row["total_hr"]),
                xref="x", yref="y",
                xanchor="center", yanchor="middle",
                sizex=sizex, sizey=sizey,
                layer="above",
            )
    fig_sc.update_layout(
        margin=dict(t=10, b=40, l=60, r=20),
        xaxis=dict(range=[0, 105], title="Group score (Pub Meeple)"),
        yaxis=dict(range=[-sizey * 0.8, max_hr + sizey * 1.2], title="Hours played"),
        dragmode=False,
    )
    st.plotly_chart(fig_sc, width="stretch", config={"scrollZoom": False})

st.divider()

# ---------------------------------------------------------------------------
# All plays table with optional filters
# ---------------------------------------------------------------------------
st.subheader("All plays")

with st.expander("Filters", expanded=False):
    f1, f2 = st.columns(2)
    with f1:
        all_years = sorted(plays["play_date"].dt.year.unique(), reverse=True)
        sel_years = st.multiselect("Year", options=all_years)
    with f2:
        all_game_names = sorted(plays["game_id"].map(games["name"]).unique())
        sel_games = st.multiselect("Game", options=all_game_names)

all_plays = plays.sort_values("play_date", ascending=False).copy()
if sel_years:
    all_plays = all_plays[all_plays["play_date"].dt.year.isin(sel_years)]
if sel_games:
    all_plays = all_plays[all_plays["game_id"].map(games["name"]).isin(sel_games)]

all_plays["game"] = all_plays["game_id"].map(games["name"])

def get_winners(play_id):
    w = scores[(scores["play_id"] == play_id) & (scores["winner"] == True)]["player_name"].tolist()
    return ", ".join(w) if w else "—"

def fmt_duration(row):
    m = row["duration_min"]
    s = f"{m // 60}h {m % 60}m" if m >= 60 else f"{m}m"
    return s + " *" if row["duration_estimated"] else s

all_plays["winner"] = all_plays["play_id"].apply(get_winners)
all_plays["duration_label"] = all_plays.apply(fmt_duration, axis=1)
all_plays["date"] = all_plays["play_date"].dt.strftime("%b %d, %Y")

st.dataframe(
    all_plays[["date", "game", "winner", "duration_min", "duration_label"]],
    column_config={
        "date": st.column_config.TextColumn("Date"),
        "game": st.column_config.TextColumn("Game"),
        "winner": st.column_config.TextColumn("Winner"),
        "duration_min": st.column_config.NumberColumn("Duration (min)", format="%d min"),
        "duration_label": None,
    },
    width="stretch",
    hide_index=True,
)
if all_plays["duration_estimated"].any():
    st.caption("\\* Duration estimated from global average for that game")
