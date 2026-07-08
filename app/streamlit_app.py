from __future__ import annotations

import pathlib
import sys

# Make the app runnable via `streamlit run app/streamlit_app.py` from anywhere:
# Streamlit puts only the script's own dir on sys.path, so add the repo root
# (for the `app` package) and `src` (for the `eurodata` package) explicitly.
_ROOT = pathlib.Path(__file__).resolve().parent.parent
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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
# Open on a populated view when possible (defaults that have ingested data).
_country_default = countries.index("DEU") if "DEU" in countries else 0
_indicator_default = indicators.index("GDP") if "GDP" in indicators else 0
iso3 = col1.selectbox("Country (ISO3)", countries, index=_country_default)
indicator = col2.selectbox("Indicator", indicators, index=_indicator_default)

df = indicator_timeseries(con, iso3, indicator)
if df.empty:
    st.info("No data yet — run `python scripts/run_ingestion.py` first.")
else:
    st.line_chart(df, x="year", y="value")
    st.dataframe(df, use_container_width=True)
