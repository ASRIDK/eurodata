from __future__ import annotations

import duckdb
import pandas as pd

_TS_QUERY = """
SELECT s.year, s.value
FROM statistic_best s
JOIN geography g ON g.id = s.geography_id
JOIN indicator i ON i.id = s.indicator_id
WHERE g.iso3 = ? AND i.name = ?
ORDER BY s.year
"""


def indicator_timeseries(con: duckdb.DuckDBPyConnection, iso3: str,
                         indicator_name: str) -> pd.DataFrame:
    return con.execute(_TS_QUERY, [iso3, indicator_name]).fetchdf()
