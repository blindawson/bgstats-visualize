import streamlit as st

st.set_page_config(
    page_title="MoneyBoyz Stats",
    page_icon="🎲",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.loader import load_data, apply_annie_mode, load_rankings  # noqa: E402
from src.bgg_loader import BGG_CONFIG_PATH, load_data_bgg, clear_cache  # noqa: E402

# ---------------------------------------------------------------------------
# Data loading — BGG when configured, static JSON as fallback
# ---------------------------------------------------------------------------

_using_bgg = BGG_CONFIG_PATH.exists()

if _using_bgg:
    try:
        with st.spinner("Loading data from BGG…"):
            plays_df, scores_df, games_df = load_data_bgg()
    except Exception as _err:
        st.error(
            f"BGG fetch failed: {_err}\n\nFalling back to static export."
        )
        _using_bgg = False

if not _using_bgg:
    plays_df, scores_df, games_df = load_data()

rankings_df = load_rankings(games_df)

# ---------------------------------------------------------------------------
# Sidebar — Annie Mode toggle + optional BGG refresh
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🎲 MoneyBoyz Stats")
    st.markdown("**Annie · Ben · Brian · Garrett · Kevin**")
    st.divider()

    annie_mode = st.toggle(
        "Annie Mode 🌸",
        value=st.session_state.get("annie_mode", False),
        help="Show only games where Annie won (co-op games always shown)",
    )
    st.session_state["annie_mode"] = annie_mode

    if annie_mode:
        st.info("Showing only Annie's victories 🏆")

    st.divider()
    st.caption(
        f"{len(plays_df)} plays · "
        f"{plays_df['play_date'].min().strftime('%b %Y')} – "
        f"{plays_df['play_date'].max().strftime('%b %Y')}"
    )

    if _using_bgg:
        st.divider()
        st.caption("📡 Live data from BGG")
        if st.button("🔄 Refresh BGG data", help="Re-fetch from BoardGameGeek"):
            clear_cache()
            st.rerun()

filtered_plays, filtered_scores = apply_annie_mode(plays_df, scores_df, annie_mode)
st.session_state["plays_df"] = filtered_plays
st.session_state["scores_df"] = filtered_scores
st.session_state["games_df"] = games_df
st.session_state["rankings_df"] = rankings_df

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
pg = st.navigation([
    st.Page("pages/1_Dashboard.py",    title="Dashboard",     icon="📊"),
    st.Page("pages/2_Game_Stats.py",   title="Game Stats",    icon="🎮"),
    st.Page("pages/3_Player_Stats.py", title="Player Stats",  icon="👤"),
    st.Page("pages/4_Timeline.py",     title="Timeline",      icon="📅"),
])
pg.run()
