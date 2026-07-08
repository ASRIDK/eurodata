from __future__ import annotations

from pathlib import Path

import duckdb

_FACTS_QUERY = """
SELECT g.iso3, g.name AS country, d.name AS domain, i.name AS indicator,
       src.name AS source_name, s.year, s.value, s.unit, s.currency,
       s.price_basis, s.vintage_date
FROM statistic_current s
JOIN geography g ON g.id = s.geography_id
JOIN indicator i ON i.id = s.indicator_id
JOIN domain d ON d.id = i.domain_id
JOIN source src ON src.id = s.source_id
WHERE src.redistributable = TRUE
"""


def export_facts(con: duckdb.DuckDBPyConnection, out_dir) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "facts.parquet"
    con.execute(f"COPY ({_FACTS_QUERY}) TO '{out}' (FORMAT PARQUET)")
    return out
