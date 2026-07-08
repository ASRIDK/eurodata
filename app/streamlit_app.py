from __future__ import annotations

import streamlit as st

from eurodata.db import connect
from app.components import indicator_timeseries

st.set_page_config(page_title="eurodata", layout="wide")
st.title("eurodata — European Data Intelligence")

con = connect()
countries = [r[0] for r in con.execute(
    "SELECT iso3 FROM geography WHERE level='country' ORDER BY name").fetchall()]
indicators = [r[0] for r in con.execute(
    "SELECT name FROM indicator ORDER BY name").fetchall()]

col1, col2 = st.columns(2)
iso3 = col1.selectbox("Country (ISO3)", countries)
indicator = col2.selectbox("Indicator", indicators)

df = indicator_timeseries(con, iso3, indicator)
if df.empty:
    st.info("No data yet — run `python scripts/run_ingestion.py` first.")
else:
    st.line_chart(df, x="year", y="value")
    st.dataframe(df, use_container_width=True)
