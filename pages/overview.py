import streamlit as st
import pandas as pd

if "plays_df" not in st.session_state:
    st.warning("Please start the app from the home page.")
    st.stop()

plays: pd.DataFrame = st.session_state["plays_df"]
annie_mode: bool = st.session_state.get("annie_mode", False)

st.title("🎲 Game Night Stats" + (" 🌸" if annie_mode else ""))
st.markdown("**Brian · Annie · Ben · Kevin · Garrett**  |  Use the sidebar to navigate.")

st.divider()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Plays", len(plays))
with col2:
    hours = plays["duration_min"].sum() // 60
    mins = plays["duration_min"].sum() % 60
    st.metric("Hours Played", f"{hours}h {mins}m")
with col3:
    st.metric("Unique Games", plays["game_id"].nunique())
with col4:
    sessions = plays["play_date"].dt.date.nunique()
    st.metric("Sessions", sessions)
