"""Public Python API for the eurodata dataset.

Usage:
    import eurodata as ed

    ed.countries()
    ed.series(country="FRA", indicator="GDP")
    ed.compare(["FRA", "DEU", "ITA"], "Unemployment Rate")
    ed.events(country="UKR", since="2020-01-01")
    ed.event_study(event_type="pandemic", indicator="Unemployment Rate")

All functions return pandas DataFrames. Module-level functions operate on a
default database handle (the bundled DuckDB file, opened read-only on first
use); ``ed.open(path)`` swaps in a different database.
"""
from __future__ import annotations

import json
import math
from difflib import get_close_matches
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from eurodata.config import get_settings
from eurodata.db import connect as _connect
from eurodata._forecast import forecast_values
from eurodata.graph.propagate import propagate as _propagate_core


class EuroDataLookupError(LookupError):
    """Unknown country / indicator / bloc, with did-you-mean suggestions."""


def _suggest(value: str, candidates: list[str], kind: str) -> str:
    close = get_close_matches(value, candidates, n=3, cutoff=0.4)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    return f"Unknown {kind}: {value!r}.{hint}"


# period: '2020' / '2020-Q3' / '2020-07'; t: decimal year (period start) for
# plotting and ordering sub-annual series.
_SERIES_SQL = """
SELECT COALESCE(g.iso3, g.code) AS iso3, g.name AS country, d.name AS domain, i.name AS indicator,
       s.year, s.quarter, s.month,
       CASE WHEN s.month > 0 THEN printf('%d-%02d', s.year, s.month)
            WHEN s.quarter > 0 THEN printf('%d-Q%d', s.year, s.quarter)
            ELSE CAST(s.year AS VARCHAR) END AS period,
       s.year + CASE WHEN s.month > 0 THEN (s.month - 1) / 12.0
                     WHEN s.quarter > 0 THEN (s.quarter - 1) / 4.0
                     ELSE 0.0 END AS t,
       s.value, COALESCE(s.unit, i.unit) AS unit,
       src.name AS source, i.is_proxy, i.proxy_note
FROM statistic_best s
JOIN geography g ON g.id = s.geography_id
JOIN indicator i ON i.id = s.indicator_id
JOIN domain d ON d.id = i.domain_id
JOIN source src ON src.id = s.source_id
"""


def _yoy_transform(df: pd.DataFrame) -> pd.DataFrame:
    """Year-over-year % change: each value vs the same period one year earlier."""
    if df.empty:
        return df
    keys = ["iso3", "indicator", "year", "_q", "_m"]
    df = df.assign(_q=df["quarter"].fillna(-1), _m=df["month"].fillna(-1))
    prev = df[keys + ["value"]].copy()
    prev["year"] = prev["year"] + 1
    merged = df.merge(prev, on=keys, how="inner", suffixes=("", "_prev"))
    merged = merged[merged["value_prev"] != 0]
    merged["value"] = (merged["value"] / merged["value_prev"] - 1.0) * 100.0
    merged["unit"] = "% y/y"
    return (merged.drop(columns=["value_prev", "_q", "_m"])
                  .sort_values(["indicator", "iso3", "t"]).reset_index(drop=True))


def _rebase_transform(df: pd.DataFrame, base_year: int) -> pd.DataFrame:
    """Index each country's series to 100 at base_year (mean if sub-annual).

    Countries with no observation in base_year are dropped.
    """
    if df.empty:
        return df
    base = (df[df["year"] == base_year]
            .groupby(["iso3", "indicator"])["value"].mean().rename("_base"))
    merged = df.merge(base, on=["iso3", "indicator"], how="inner")
    merged = merged[merged["_base"] != 0]
    merged["value"] = merged["value"] / merged["_base"] * 100.0
    merged["unit"] = f"index ({base_year}=100)"
    return (merged.drop(columns=["_base"])
                  .sort_values(["indicator", "iso3", "t"]).reset_index(drop=True))


def _pearson_stats(r: float, n: int) -> tuple[float | None, float | None, float | None]:
    """Two-sided p-value and 95% CI for a Pearson r via the Fisher z-transform.

    Normal approximation (no scipy needed); requires n > 3.
    """
    if n <= 3 or pd.isna(r):
        return None, None, None
    r_c = max(-0.999999999, min(0.999999999, r))  # atanh(±1) is infinite
    z = math.atanh(r_c)
    se = 1.0 / math.sqrt(n - 3)
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z / se) / math.sqrt(2.0))))
    return p, math.tanh(z - 1.959964 * se), math.tanh(z + 1.959964 * se)


class EuroData:
    """A handle on one eurodata DuckDB database."""

    def __init__(self, path: str | None = None, *, read_only: bool = True) -> None:
        db_path = path or get_settings().duckdb_path
        try:
            self._con = _connect(db_path, read_only=read_only)
        except duckdb.Error as exc:
            if Path(db_path).exists():
                # The file is there: a lock conflict (Streamlit / ingestion
                # holding it) or corruption, NOT a missing database.
                raise RuntimeError(
                    f"Could not open eurodata database at {db_path!r} — the file "
                    f"exists, so another process may hold its lock (close the "
                    f"Streamlit app or ingestion run and retry): {exc}"
                ) from exc
            raise FileNotFoundError(
                f"Could not open eurodata database at {db_path!r} "
                f"(run `python scripts/init_db.py` and `python scripts/run_ingestion.py` "
                f"to build it): {exc}"
            ) from exc
        self.path = db_path

    @classmethod
    def from_connection(cls, con: duckdb.DuckDBPyConnection) -> "EuroData":
        """Wrap an already-open connection (used by the dashboard)."""
        obj = object.__new__(cls)
        obj._con = con
        obj.path = None
        return obj

    # -- plumbing ---------------------------------------------------------
    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        """The underlying DuckDB connection, for power users."""
        return self._con

    def close(self) -> None:
        self._con.close()

    def query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        """Run arbitrary SQL against the database and return a DataFrame."""
        return self._con.execute(sql, params or []).df()

    def relation(self, table_or_sql: str) -> duckdb.DuckDBPyRelation:
        """Return a DuckDB relation for lazy composition."""
        return self._con.sql(table_or_sql)

    # -- catalog ----------------------------------------------------------
    def countries(self) -> pd.DataFrame:
        return self.query(
            "SELECT iso3, iso2, name, is_transcontinental, is_disputed "
            "FROM geography WHERE level = 'country' ORDER BY name")

    def regions(self, country: str | None = None) -> pd.DataFrame:
        """NUTS 2 regions (code, name, parent country), optionally one country's."""
        where, params = "", []
        if country is not None:
            where = "AND p.id = ?"
            params = [self._resolve_country(country)]
        return self.query(f"""
            SELECT g.code, g.name, p.iso3 AS country_iso3, p.name AS country
            FROM geography g JOIN geography p ON p.id = g.parent_id
            WHERE g.level = 'NUTS2' {where}
            ORDER BY g.code""", params)

    def blocs(self) -> pd.DataFrame:
        return self.query(
            "SELECT b.code, b.name, COUNT(gb.geography_id) FILTER (WHERE gb.until_year IS NULL) AS current_members "
            "FROM bloc b LEFT JOIN geography_bloc gb ON gb.bloc_id = b.id "
            "GROUP BY b.code, b.name ORDER BY b.code")

    def bloc_members(self, code: str) -> pd.DataFrame:
        codes = [r[0] for r in self._con.execute("SELECT code FROM bloc").fetchall()]
        if code.upper() not in codes:
            raise EuroDataLookupError(_suggest(code, codes, "bloc"))
        return self.query(
            "SELECT g.iso3, g.name, gb.since_year, gb.until_year "
            "FROM geography_bloc gb JOIN bloc b ON b.id = gb.bloc_id "
            "JOIN geography g ON g.id = gb.geography_id "
            "WHERE b.code = ? ORDER BY gb.since_year, g.name", [code.upper()])

    def country_blocs(self, country: str) -> pd.DataFrame:
        """Every bloc a country currently belongs to or has historically
        belonged to. Columns: bloc_code, bloc_name, since_year, until_year
        (NULL = still a member)."""
        geo_id = self._resolve_country(country)
        return self.query(
            "SELECT b.code AS bloc_code, b.name AS bloc_name, "
            "gb.since_year, gb.until_year "
            "FROM geography_bloc gb JOIN bloc b ON b.id = gb.bloc_id "
            "WHERE gb.geography_id = ? ORDER BY gb.since_year", [geo_id])

    def domains(self) -> pd.DataFrame:
        return self.query("SELECT name, description FROM domain ORDER BY id")

    def indicators(self, domain: str | None = None) -> pd.DataFrame:
        sql = ("SELECT i.name, d.name AS domain, i.unit, i.api_code, i.definition, "
               "i.is_proxy, i.proxy_note FROM indicator i JOIN domain d ON d.id = i.domain_id")
        params: list = []
        if domain is not None:
            sql += " WHERE lower(d.name) = lower(?)"
            params.append(domain)
        return self.query(sql + " ORDER BY d.id, i.name", params)

    def sources(self) -> pd.DataFrame:
        return self.query(
            "SELECT name, organization, url, reliability_score, license, "
            "redistributable, update_frequency FROM source ORDER BY reliability_score DESC, id")

    def correlation_graph(self, indicator: str | None = None) -> pd.DataFrame:
        """`CORRELATES_WITH` structural graph edges: growth-rate correlation
        between indicator pairs, pooled across countries and FDR-corrected
        (see `eurodata.graph.correlate` for the full methodology). Pass
        `indicator` to only return edges touching that indicator; omit it
        for the whole graph.

        Columns: indicator_a, indicator_b, domain_a, domain_b, weight
        (signed pooled Pearson r on YoY growth rates), relationship
        ('contemporaneous' / 'a_leads_b' / 'b_leads_a' — whichever lag test
        was strongest for the pair), direction ('a_leads_b' / 'b_leads_a' /
        'undetermined' — only set when a per-country Granger causality test
        confirms it), q_value (Benjamini-Hochberg FDR-corrected across every
        pair tested), n_countries (how many contributed to the pooled stat).

        Empty if the graph hasn't been built yet (`scripts/build_graph.py`).
        """
        sql = (
            "SELECT ia.name AS indicator_a, ib.name AS indicator_b, "
            "da.name AS domain_a, db.name AS domain_b, e.weight, e.props "
            "FROM graph_edge e "
            "JOIN graph_node na ON na.id = e.src_node_id "
            "JOIN graph_node nb ON nb.id = e.dst_node_id "
            "JOIN indicator ia ON ia.id = na.ref_id "
            "JOIN indicator ib ON ib.id = nb.ref_id "
            "JOIN domain da ON da.id = ia.domain_id "
            "JOIN domain db ON db.id = ib.domain_id "
            "WHERE e.edge_type = 'CORRELATES_WITH'")
        params: list = []
        if indicator is not None:
            ind_id = self._resolve_indicator(indicator)
            sql += " AND (na.ref_id = ? OR nb.ref_id = ?)"
            params += [ind_id, ind_id]
        df = self.query(sql, params)
        if df.empty:
            return df.assign(relationship=None, direction=None, q_value=None, n_countries=None)
        meta = df.pop("props").apply(json.loads)
        df["relationship"] = meta.apply(lambda m: m["relationship"])
        df["direction"] = meta.apply(lambda m: m["direction"])
        df["q_value"] = meta.apply(lambda m: m["q_value"])
        df["n_countries"] = meta.apply(lambda m: m["n_countries"])
        return (df.reindex(df["weight"].abs().sort_values(ascending=False).index)
                  .reset_index(drop=True))

    def years(self) -> tuple[int, int]:
        lo, hi = self._con.execute(
            "SELECT MIN(year), MAX(year) FROM statistic_record").fetchone()
        return int(lo), int(hi)

    def search_indicators(self, text: str) -> pd.DataFrame:
        like = f"%{text.lower()}%"
        return self.query(
            "SELECT i.name, d.name AS domain, i.unit, i.api_code, i.definition, i.is_proxy "
            "FROM indicator i JOIN domain d ON d.id = i.domain_id "
            "WHERE lower(i.name) LIKE ? OR lower(coalesce(i.definition, '')) LIKE ? "
            "OR lower(coalesce(i.api_code, '')) LIKE ? OR lower(d.name) LIKE ? "
            "ORDER BY i.name", [like, like, like, like])

    # -- resolution -------------------------------------------------------
    def _resolve_country(self, country: str) -> int:
        # Resolves any geography: country iso3/iso2/name, or a region code
        # (geography.code == iso3 for countries, so the extra match only
        # adds NUTS codes like 'FR10').
        row = self._con.execute(
            "SELECT id FROM geography WHERE upper(iso3) = upper(?) "
            "OR upper(iso2) = upper(?) OR lower(name) = lower(?) "
            "OR upper(code) = upper(?)",
            [country, country, country, country]).fetchone()
        if row is None:
            names = [r[0] for r in self._con.execute(
                "SELECT code FROM geography "
                "UNION ALL SELECT name FROM geography").fetchall()]
            raise EuroDataLookupError(_suggest(country, names, "country or region"))
        return row[0]

    def _resolve_indicator(self, indicator: str) -> int:
        row = self._con.execute(
            "SELECT id FROM indicator WHERE lower(name) = lower(?) "
            "OR lower(coalesce(api_code, '')) = lower(?)",
            [indicator, indicator]).fetchone()
        if row is None:
            names = [r[0] for r in self._con.execute("SELECT name FROM indicator").fetchall()]
            raise EuroDataLookupError(_suggest(indicator, names, "indicator"))
        return row[0]

    # -- data access ------------------------------------------------------
    def series(self, country: str | None = None, indicator: str | None = None, *,
               domain: str | None = None, source: str | None = None,
               bloc: str | None = None, start: int | None = None,
               end: int | None = None, rebase: int | None = None,
               yoy: bool = False) -> pd.DataFrame:
        """Time series filtered by any combination of country / indicator /
        domain / source / bloc (current members) / year range.

        Sub-annual series carry ``quarter``/``month``, a ``period`` label
        ('2020-Q3', '2020-07') and a decimal-year ``t`` for plotting.

        Transforms (mutually exclusive):
        - ``rebase=2000`` indexes each country to 100 at that year;
        - ``yoy=True`` converts values to % change vs the same period one
          year earlier.
        """
        if rebase is not None and yoy:
            raise ValueError("rebase and yoy are mutually exclusive transforms")
        where, params = [], []
        if country is not None:
            where.append("s.geography_id = ?")
            params.append(self._resolve_country(country))
        if indicator is not None:
            where.append("s.indicator_id = ?")
            params.append(self._resolve_indicator(indicator))
        if domain is not None:
            where.append("lower(d.name) = lower(?)")
            params.append(domain)
        if source is not None:
            where.append("lower(src.name) = lower(?)")
            params.append(source)
        if bloc is not None:
            where.append(
                "s.geography_id IN (SELECT gb.geography_id FROM geography_bloc gb "
                "JOIN bloc b ON b.id = gb.bloc_id WHERE upper(b.code) = upper(?) "
                "AND gb.until_year IS NULL)")
            params.append(bloc)
        if start is not None:
            where.append("s.year >= ?"); params.append(start)
        if end is not None:
            where.append("s.year <= ?"); params.append(end)
        sql = _SERIES_SQL
        if where:
            sql += " WHERE " + " AND ".join(where)
        df = self.query(sql + " ORDER BY indicator, iso3, t", params)
        if yoy:
            df = _yoy_transform(df)
        if rebase is not None:
            df = _rebase_transform(df, rebase)
        return df

    def latest(self, indicator: str, *, bloc: str | None = None) -> pd.DataFrame:
        """Most recent value of an indicator for every country."""
        df = self.series(indicator=indicator, bloc=bloc)
        if df.empty:
            return df
        idx = df.groupby("iso3")["t"].idxmax()
        return (df.loc[idx].sort_values("value", ascending=False)
                  .reset_index(drop=True))

    def provenance(self, indicator: str, country: str) -> pd.DataFrame:
        """Per-source values for one indicator/country, latest vintage of
        each source (not deduplicated to a single "best" source the way
        `series()` is). Use this to see where sources disagree — e.g. a
        proxy indicator where Eurostat and World Bank report different
        numbers for the same country/year.

        Columns: period, year, t, source, value, unit, reliability_score,
        is_best (whether this row is the one `statistic_best`/`series()`
        would surface).
        """
        ind_id = self._resolve_indicator(indicator)
        geo_id = self._resolve_country(country)
        df = self.query(
            "SELECT CASE WHEN s.month > 0 THEN printf('%d-%02d', s.year, s.month) "
            "            WHEN s.quarter > 0 THEN printf('%d-Q%d', s.year, s.quarter) "
            "            ELSE CAST(s.year AS VARCHAR) END AS period, "
            "       s.year, "
            "       s.year + CASE WHEN s.month > 0 THEN (s.month - 1) / 12.0 "
            "                     WHEN s.quarter > 0 THEN (s.quarter - 1) / 4.0 "
            "                     ELSE 0.0 END AS t, "
            "       src.name AS source, s.value, COALESCE(s.unit, i.unit) AS unit, "
            "       src.reliability_score "
            "FROM statistic_current s "
            "JOIN source src ON src.id = s.source_id "
            "JOIN indicator i ON i.id = s.indicator_id "
            "WHERE s.indicator_id = ? AND s.geography_id = ? "
            # Re-ingestion can insert several identical rows for the same
            # source/period on one vintage date; collapse those before
            # showing "which sources disagree" — repeats aren't disagreement.
            "GROUP BY period, s.year, t, src.name, s.value, COALESCE(s.unit, i.unit), "
            "src.reliability_score "
            "ORDER BY t, src.reliability_score DESC", [ind_id, geo_id])
        if df.empty:
            return df.assign(is_best=pd.Series(dtype=bool))
        df["is_best"] = ~df.duplicated("period", keep="first")
        return df

    # -- revisions --------------------------------------------------------
    # A "revision" is the same source re-reporting a different value for the
    # same (indicator, country, period) at a later vintage_date. This is read
    # straight from statistic_record (the statistic_best/_current views collapse
    # vintages, so revisions are invisible through them).
    _REVISION_PERIOD = (
        "CASE WHEN s.month > 0 THEN printf('%d-%02d', s.year, s.month) "
        "     WHEN s.quarter > 0 THEN printf('%d-Q%d', s.year, s.quarter) "
        "     ELSE CAST(s.year AS VARCHAR) END")

    def revisions(self, indicator: str, country: str) -> pd.DataFrame:
        """Full vintage-by-vintage trail for one indicator/country: every
        (period, source, vintage_date) whose value was revised at least once.

        Columns: period, year, quarter, month, source, vintage_date, value,
        previous_value, delta (vs the prior vintage of the same period/source),
        pct_change, is_latest. Sorted by period then vintage_date.

        A per-period summary (n_vintages, first/latest value, total delta) is
        attached at ``df.attrs['summary']`` and ``df.attrs['n_revised']``.
        """
        ind_id = self._resolve_indicator(indicator)
        geo_id = self._resolve_country(country)
        trail = self.query(
            f"SELECT {self._REVISION_PERIOD} AS period, s.year, s.quarter, s.month, "
            "       src.name AS source, s.vintage_date, s.value "
            "FROM statistic_record s "
            "JOIN source src ON src.id = s.source_id "
            "WHERE s.indicator_id = ? AND s.geography_id = ? "
            "      AND s.vintage_date IS NOT NULL "
            "ORDER BY s.year, s.quarter, s.month, src.name, s.vintage_date",
            [ind_id, geo_id])
        empty_cols = ["period", "year", "quarter", "month", "source", "vintage_date",
                      "value", "previous_value", "delta", "pct_change", "is_latest"]
        if trail.empty:
            out = pd.DataFrame(columns=empty_cols)
            out.attrs["summary"] = pd.DataFrame(
                columns=["period", "n_vintages", "first_value", "latest_value", "delta"])
            out.attrs["n_revised"] = 0
            return out
        g = trail.groupby(["period", "source"], sort=False)
        trail["previous_value"] = g["value"].shift(1)
        trail["delta"] = trail["value"] - trail["previous_value"]
        trail["pct_change"] = trail["delta"] / trail["previous_value"].replace(0, pd.NA) * 100.0
        trail["is_latest"] = trail.index == g["value"].transform(lambda s: s.index[-1])
        # keep only series (period, source) that were actually revised at least once
        revised = g["value"].transform(lambda s: s.nunique(dropna=True) > 1)
        out = trail[revised].reset_index(drop=True)

        summary = (out.groupby("period", sort=False)
                      .agg(n_vintages=("vintage_date", "nunique"),
                           first_value=("value", "first"),
                           latest_value=("value", "last"))
                      .reset_index())
        summary["delta"] = summary["latest_value"] - summary["first_value"]
        out.attrs["summary"] = summary
        out.attrs["n_revised"] = int(summary["period"].nunique())
        return out

    def revisions_summary(self, country: str | None = None,
                          indicator: str | None = None) -> pd.DataFrame:
        """One row per revised (indicator, country, period, source) across the
        whole dataset: n_vintages, first/latest value and vintage, delta and
        pct_change. Feeds the /revisions browse view (most-revised indicators,
        largest revisions, revision timeline). Filterable by country/indicator.

        Sorted by absolute pct_change (largest revisions first)."""
        where, params = ["s.vintage_date IS NOT NULL"], []
        if indicator is not None:
            where.append("s.indicator_id = ?"); params.append(self._resolve_indicator(indicator))
        if country is not None:
            where.append("s.geography_id = ?"); params.append(self._resolve_country(country))
        df = self.query(
            f"SELECT i.name AS indicator, COALESCE(g.iso3, g.code) AS country, "
            f"       d.name AS domain, src.name AS source, "
            f"       {self._REVISION_PERIOD} AS period, s.year, "
            "        COUNT(DISTINCT s.vintage_date) AS n_vintages, "
            "        arg_min(s.value, s.vintage_date) AS first_value, "
            "        arg_max(s.value, s.vintage_date) AS latest_value, "
            "        min(s.vintage_date) AS first_vintage, "
            "        max(s.vintage_date) AS latest_vintage "
            "FROM statistic_record s "
            "JOIN geography g ON g.id = s.geography_id "
            "JOIN indicator i ON i.id = s.indicator_id "
            "JOIN domain d ON d.id = i.domain_id "
            "JOIN source src ON src.id = s.source_id "
            f"WHERE {' AND '.join(where)} "
            "GROUP BY i.name, country, d.name, src.name, period, s.year "
            "HAVING COUNT(DISTINCT s.vintage_date) > 1 "
            "   AND arg_min(s.value, s.vintage_date) IS DISTINCT FROM "
            "       arg_max(s.value, s.vintage_date)",
            params)
        if df.empty:
            return df.assign(delta=pd.Series(dtype=float), pct_change=pd.Series(dtype=float))
        df["delta"] = df["latest_value"] - df["first_value"]
        df["pct_change"] = df["delta"] / df["first_value"].replace(0, pd.NA) * 100.0
        return (df.reindex(df["pct_change"].abs().sort_values(ascending=False,
                                                              na_position="last").index)
                  .reset_index(drop=True))

    def compare(self, countries: list[str], indicator: str, *,
                start: int | None = None, end: int | None = None) -> pd.DataFrame:
        """Wide period x country table for one indicator (index: year for
        annual series, period label for sub-annual ones)."""
        frames = [self.series(country=c, indicator=indicator, start=start, end=end)
                  for c in countries]
        long = pd.concat(frames, ignore_index=True)
        if long.empty:
            return long
        index = "year" if long["period"].nunique() == long["year"].nunique() else "period"
        return long.pivot_table(index=index, columns="iso3", values="value")

    def forecast(self, indicator: str, country: str, *, horizon: int = 5,
                 level: float = 0.8) -> pd.DataFrame:
        """Project one indicator/country series ``horizon`` periods forward.

        Auto-selects a simple model (drift / linear / log-linear / Holt, plus
        seasonal models for sub-annual series) by one-step backtest error and
        returns history + forecast rows with an empirical ``lo``/``hi`` band.
        This is trend extrapolation, not prediction — see ``df.attrs['disclaimer']``.
        """
        hist = self.series(indicator=indicator, country=country)
        hist = hist[hist["value"].notna()].sort_values("t").reset_index(drop=True)
        if hist.empty:
            raise EuroDataLookupError(
                f"No data to forecast for {indicator!r} in {country!r}.")
        # single frequency: infer from the sub-annual columns (0 = not
        # applicable, the NOT NULL sentinel; annual rows carry month/quarter 0)
        if (hist["month"] > 0).any():
            freq, step = 12, 1.0 / 12.0
        elif (hist["quarter"] > 0).any():
            freq, step = 4, 0.25
        else:
            freq, step = 1, 1.0

        res = forecast_values(hist["value"].to_numpy(), horizon=horizon,
                              freq=freq, level=level)

        last_t = float(hist["t"].iloc[-1])
        unit = hist["unit"].iloc[0] if "unit" in hist else None
        fc_rows = []
        for i, p in enumerate(res.points, start=1):
            t = last_t + step * i
            year = int(np.floor(t + 1e-9))
            if freq == 12:
                period = f"{year}-{int(round((t - year) * 12)) + 1:02d}"
            elif freq == 4:
                period = f"{year}-Q{int(round((t - year) * 4)) + 1}"
            else:
                period = str(year)
            fc_rows.append({"t": t, "period": period, "value": p.yhat,
                            "kind": "forecast", "lo": p.lo, "hi": p.hi})

        hist_out = hist[["t", "period", "value"]].copy()
        hist_out["kind"] = "history"
        hist_out["lo"] = np.nan
        hist_out["hi"] = np.nan
        out = pd.concat([hist_out, pd.DataFrame(fc_rows)], ignore_index=True)
        out.attrs.update({
            "method": res.method, "freq": res.freq,
            "backtest_mae": res.backtest_mae, "fallback": res.fallback,
            "n_obs": res.n_obs, "disclaimer": res.disclaimer,
            "unit": unit, "indicator": indicator, "country": country,
        })
        return out

    def coverage(self, indicator: str | None = None) -> pd.DataFrame:
        """Rows / countries / year span per indicator; empty indicators included."""
        where, params = "", []
        if indicator is not None:
            where = "WHERE i.id = ?"
            params = [self._resolve_indicator(indicator)]
        return self.query(f"""
            SELECT i.name AS indicator, d.name AS domain, i.is_proxy,
                   COUNT(s.value) AS rows,
                   COUNT(DISTINCT s.geography_id) AS countries,
                   ANY_VALUE(g.level) AS geo_level,
                   MIN(s.year) AS first_year, MAX(s.year) AS last_year,
                   year(CURRENT_DATE) - MAX(s.year) AS years_stale
            FROM indicator i
            JOIN domain d ON d.id = i.domain_id
            LEFT JOIN statistic_best s ON s.indicator_id = i.id
            LEFT JOIN geography g ON g.id = s.geography_id
            {where}
            GROUP BY i.name, d.name, i.is_proxy, d.id, i.id
            ORDER BY d.id, i.id""", params)

    def country_indicators(self, country: str) -> pd.DataFrame:
        """Indicators with at least one data point for this country/region,
        with each indicator's most recent value. Used to scope which
        indicators/correlations are actually relevant to a given country."""
        geo_id = self._resolve_country(country)
        return self.query(
            "SELECT i.name AS indicator, d.name AS domain, "
            "MAX(s.year) AS last_year "
            "FROM statistic_best s "
            "JOIN indicator i ON i.id = s.indicator_id "
            "JOIN domain d ON d.id = i.domain_id "
            "WHERE s.geography_id = ? "
            "GROUP BY i.name, d.name, i.id, d.id ORDER BY d.id, i.name", [geo_id])

    def ingestion_summary(self) -> pd.DataFrame:
        """Recent ingestion runs with status and per-series error counts."""
        return self.query("""
            SELECT r.source, r.started_at, r.status, r.records_processed, r.error,
                   (SELECT COUNT(*) FROM ingestion_error e
                    WHERE e.source = r.source
                      AND e.occurred_at BETWEEN r.started_at AND r.ended_at) AS series_errors
            FROM ingestion_run r ORDER BY r.started_at DESC""")

    # -- events -----------------------------------------------------------
    def events(self, country: str | None = None, event_type: str | None = None, *,
               bloc: str | None = None, since: str | None = None,
               until: str | None = None, tag: str | None = None) -> pd.DataFrame:
        where, params = [], []
        if country is not None:
            iso3 = self.query("SELECT iso3 FROM geography WHERE id = ?",
                              [self._resolve_country(country)]).iloc[0, 0]
            where.append(
                "(e.iso3 = ? OR (e.iso3 IS NULL AND (e.bloc_code IS NULL OR "
                "e.bloc_code IN (SELECT b.code FROM geography_bloc gb "
                "JOIN bloc b ON b.id = gb.bloc_id JOIN geography g ON g.id = gb.geography_id "
                "WHERE g.iso3 = ? AND gb.until_year IS NULL))))")
            params += [iso3, iso3]
        if event_type is not None:
            where.append("lower(e.event_type) = lower(?)"); params.append(event_type)
        if bloc is not None:
            where.append("upper(e.bloc_code) = upper(?)"); params.append(bloc)
        if since is not None:
            where.append("e.start_date >= ?"); params.append(since)
        if until is not None:
            where.append("e.start_date <= ?"); params.append(until)
        if tag is not None:
            where.append("',' || e.tags || ',' LIKE ?"); params.append(f"%,{tag},%")
        sql = ("SELECT e.code, e.title, e.event_type, e.iso3, e.bloc_code, "
               "e.start_date, e.end_date, e.source, e.source_url, e.confidence, "
               "e.tags, e.affected_domains, e.description FROM event e")
        if where:
            sql += " WHERE " + " AND ".join(where)
        return self.query(sql + " ORDER BY e.start_date", params)

    def event_types(self) -> pd.DataFrame:
        return self.query(
            "SELECT event_type, COUNT(*) AS events FROM event GROUP BY 1 ORDER BY 2 DESC")

    def _event_countries(self, event: pd.Series) -> list[str]:
        """Countries an event applies to: its country, its bloc's members at
        the event year, or (global events) every country."""
        if event["iso3"] is not None and not pd.isna(event["iso3"]):
            return [event["iso3"]]
        year = int(str(event["start_date"])[:4])
        if event["bloc_code"] is not None and not pd.isna(event["bloc_code"]):
            df = self.query(
                "SELECT g.iso3 FROM geography_bloc gb JOIN bloc b ON b.id = gb.bloc_id "
                "JOIN geography g ON g.id = gb.geography_id WHERE b.code = ? "
                "AND gb.since_year <= ? AND (gb.until_year IS NULL OR gb.until_year > ?)",
                [event["bloc_code"], year, year])
            return df["iso3"].tolist()
        return self.countries()["iso3"].tolist()

    def event_study(self, indicator: str, *, event_type: str | None = None,
                    event_code: str | None = None,
                    window_years: int = 3) -> pd.DataFrame:
        """Before/after comparison of an indicator around events.

        Windows are measured from the event *date* (month precision), not the
        calendar year: each observation is placed at its period midpoint, and
        the before window is [event - window_years, event), the after window
        [event, event + window_years]. With monthly or quarterly series this
        gives up to 12x/4x more observations per window than annual data.
        Returns one row per (event, country) with before/after means and
        deltas. Descriptive, not causal.
        """
        ind_id = self._resolve_indicator(indicator)
        evs = self.events(event_type=event_type)
        if event_code is not None:
            evs = self.query("SELECT * FROM event WHERE code = ?", [event_code])
            if evs.empty:
                codes = [r[0] for r in self._con.execute("SELECT code FROM event").fetchall()]
                raise EuroDataLookupError(_suggest(event_code, codes, "event"))
        data = self.query(
            f"{_SERIES_SQL} WHERE s.indicator_id = ?", [ind_id])
        # Period midpoints: month -> (m-0.5)/12, quarter -> (q-0.5)/4, year -> +0.5.
        # month/quarter are 0 (the NOT NULL "not applicable" sentinel), never
        # NULL/NaN, so branch on > 0 explicitly rather than on NaN cascading
        # through fillna -- otherwise every annual row would be mis-dated.
        m = data["month"].to_numpy()
        q = data["quarter"].to_numpy()
        offset = np.where(m > 0, (m - 0.5) / 12.0,
                          np.where(q > 0, (q - 0.5) / 4.0, 0.5))
        data = data.assign(t_mid=data["year"] + offset)
        out = []
        for _, ev in evs.iterrows():
            start = str(ev["start_date"])
            year, ev_month = int(start[:4]), int(start[5:7])
            ev_t = year + (ev_month - 0.5) / 12.0
            for iso3 in self._event_countries(ev):
                cdata = data[data["iso3"] == iso3]
                before = cdata[(cdata["t_mid"] >= ev_t - window_years)
                               & (cdata["t_mid"] < ev_t)]["value"]
                after = cdata[(cdata["t_mid"] >= ev_t)
                              & (cdata["t_mid"] <= ev_t + window_years)]["value"]
                if before.empty or after.empty:
                    continue
                b, a = before.mean(), after.mean()
                out.append({"event_code": ev["code"], "event_title": ev["title"],
                            "event_year": year, "iso3": iso3,
                            "before_mean": b, "after_mean": a, "delta": a - b,
                            "pct_change": (a - b) / abs(b) * 100 if b else None,
                            "n_before": len(before), "n_after": len(after)})
        return pd.DataFrame(out)

    # -- correlations -----------------------------------------------------
    def indicator_trends(self, indicators: list[str], *,
                         start: int | None = None, end: int | None = None,
                         rebase: bool = True) -> pd.DataFrame:
        """Pan-European annual trend per indicator, for visual comparison
        (e.g. the two sides of a `CORRELATES_WITH` edge, on one chart).

        Each indicator is annualized per country (`_indicator_frame`) and
        reduced to the cross-country *median* per year — an equal-weight
        European trend, robust to individual outliers and consistent with the
        pooled correlation methodology. When ``rebase`` (default), every
        indicator is indexed to 100 at the first calendar year for which *all*
        requested indicators have data, so series carrying different units
        share a single axis.

        Columns: indicator, year, value (indexed to 100 when rebased, else the
        raw median), n_countries, base_year. Empty if the indicators never
        share a year, or any requested indicator has no data in range.
        """
        frames: dict[str, pd.DataFrame] = {}
        for name in indicators:
            f = self._indicator_frame(name)
            if start is not None:
                f = f[f["year"] >= start]
            if end is not None:
                f = f[f["year"] <= end]
            if f.empty:
                continue
            agg = (f.groupby("year")
                    .agg(value=("value", "median"), n_countries=("iso3", "nunique"))
                    .reset_index())
            agg["indicator"] = name
            frames[name] = agg
        cols = ["indicator", "year", "value", "n_countries", "base_year"]
        if len(frames) < len(indicators):
            return pd.DataFrame(columns=cols)
        common = set.intersection(*(set(f["year"]) for f in frames.values()))
        if not common:
            return pd.DataFrame(columns=cols)
        base_year = min(common)
        out = pd.concat(frames.values(), ignore_index=True)
        out["base_year"] = base_year
        if rebase:
            bases = out[out["year"] == base_year].set_index("indicator")["value"]
            out["value"] = out.apply(
                lambda r: r["value"] / bases[r["indicator"]] * 100.0
                if bases[r["indicator"]] else None, axis=1)
        return out.sort_values(["indicator", "year"]).reset_index(drop=True)[cols]

    def _indicator_frame(self, indicator: str) -> pd.DataFrame:
        """One value per (country, year); sub-annual series are annualized
        (mean) so correlations always align on calendar years."""
        ind_id = self._resolve_indicator(indicator)
        return self.query(
            "SELECT g.iso3, s.year, AVG(s.value) AS value FROM statistic_best s "
            "JOIN geography g ON g.id = s.geography_id WHERE s.indicator_id = ? "
            "GROUP BY g.iso3, s.year",
            [ind_id])

    _CORR_COLUMNS = ["iso3", "n_years", "correlation", "p_value",
                     "ci_low", "ci_high", "lag"]

    @staticmethod
    def _growth_frame(frame: pd.DataFrame, col: str) -> pd.DataFrame:
        """Per-country YoY % growth of `col` (levels -> growth rates), the same
        transform `graph.correlate` uses. Guards against the classic spurious
        correlation between two series that merely trend over time."""
        frame = frame.sort_values(["iso3", "year"]).copy()
        frame[col] = frame.groupby("iso3")[col].pct_change() * 100.0
        return (frame.replace([float("inf"), float("-inf")], pd.NA)
                     .dropna(subset=[col]))

    def lagged_correlation(self, indicator_a: str, indicator_b: str, *,
                           lag: int = 0, min_years: int = 10,
                           on: str = "growth") -> pd.DataFrame:
        """Per-country Pearson correlation of a(t) with b(t + lag).

        ``on='growth'`` (default) correlates year-over-year growth rates; two
        series that both merely trend upward do NOT correlate spuriously this
        way. ``on='levels'`` correlates raw levels (kept for continuity, but any
        two trending series will read ~0.99 — use with care). lag > 0 tests
        whether indicator_a leads indicator_b by `lag` years. Countries with
        fewer than min_years overlapping points are dropped. p_value and the 95%
        CI [ci_low, ci_high] come from the Fisher z-transform (normal
        approximation, unadjusted for multiple tests).
        """
        if on not in ("growth", "levels"):
            raise ValueError("on must be 'growth' or 'levels'")
        a = self._indicator_frame(indicator_a).rename(columns={"value": "a"})
        b = self._indicator_frame(indicator_b).rename(columns={"value": "b"})
        if on == "growth":
            a = self._growth_frame(a, "a")
            b = self._growth_frame(b, "b")
        b = b.assign(year=b["year"] - lag)  # b(t+lag) aligned onto year t
        merged = a.merge(b, on=["iso3", "year"])
        rows = []
        for iso3, grp in merged.groupby("iso3"):
            if len(grp) < min_years or grp["a"].std() == 0 or grp["b"].std() == 0:
                continue
            r = grp["a"].corr(grp["b"])
            p, lo, hi = _pearson_stats(r, len(grp))
            rows.append({"iso3": iso3, "n_years": len(grp), "correlation": r,
                         "p_value": p, "ci_low": lo, "ci_high": hi, "lag": lag})
        out = (pd.DataFrame(rows).sort_values("correlation", ascending=False)
                 .reset_index(drop=True) if rows
               else pd.DataFrame(columns=self._CORR_COLUMNS))
        out.attrs["basis"] = on
        return out

    def correlate(self, indicator_a: str, indicator_b: str, *,
                  min_years: int = 10, on: str = "growth") -> pd.DataFrame:
        """Per-country Pearson correlation between two indicators (lag 0).

        Defaults to year-over-year growth rates (``on='growth'``); pass
        ``on='levels'`` for raw levels. See ``lagged_correlation``.
        """
        return self.lagged_correlation(indicator_a, indicator_b, lag=0,
                                       min_years=min_years, on=on)

    # The headline figures a country profile leads with. Kept here rather than
    # in the frontend so rank and median are computed where the data is.
    PROFILE_INDICATORS = ("GDP", "GDP per capita", "Population",
                          "Unemployment Rate", "Inflation (HICP)")

    def country_profile(self, country: str, *, trend_years: int = 10) -> dict:
        """Everything a country profile summary needs, as structured facts.

        Returns the country's identity, its bloc memberships with join years,
        each headline indicator with its value *and* its rank and the European
        median for context, and the indicators that moved most over the last
        ``trend_years``.

        Facts, not prose: ranks and deltas are computed here where the data is
        and can be tested, and the page composes sentences from them, so the
        wording can never drift from the numbers rendered beside it.

        A rank is simply the position when every country's latest value is
        sorted high to low -- it carries no judgement about whether high is
        good, which varies by indicator.
        """
        geo_id = self._resolve_country(country)
        row = self.query(
            "SELECT COALESCE(iso3, code) AS iso3, iso2, name FROM geography "
            "WHERE id = ?", [geo_id])
        if row.empty:
            raise EuroDataLookupError(f"Unknown country: {country!r}")
        iso3 = str(row.iloc[0]["iso3"])

        headline = []
        for name in self.PROFILE_INDICATORS:
            try:
                across = self.latest(name)
            except EuroDataLookupError:
                continue
            if across.empty or iso3 not in set(across["iso3"]):
                continue
            mine = across[across["iso3"] == iso3].iloc[0]
            ordered = across.sort_values("value", ascending=False).reset_index(drop=True)
            rank = int(ordered.index[ordered["iso3"] == iso3][0]) + 1
            headline.append({
                "indicator": name,
                "value": float(mine["value"]),
                "unit": None if pd.isna(mine["unit"]) else str(mine["unit"]),
                "period": str(mine["period"]),
                "rank": rank,
                "of": int(len(ordered)),
                "median": float(across["value"].median()),
            })

        # "Fastest rising/falling" is deliberately measured relative to peers,
        # not in raw percent. A raw proportional change is dominated by
        # rate/percentage indicators with near-zero baselines (an interest rate
        # going 0.5 -> 3.7 reads as "+620%"), and it surfaces Europe-wide shifts
        # that say nothing about this country. Instead: this country's decade
        # change per indicator, ranked as a percentile against every country's
        # decade change for the same indicator, in the indicator's own units.
        # A high percentile means it rose more here than almost anywhere; that
        # is the distinctive story. The interest-rate rise -- which happened
        # everywhere -- lands mid-pack and does not win.
        changes = self.query("""
            WITH win AS (
                SELECT s.geography_id, s.indicator_id, s.year, s.value,
                       COALESCE(s.unit, i.unit) AS unit, i.name AS indicator
                FROM statistic_best s
                JOIN indicator i ON i.id = s.indicator_id
                JOIN geography g ON g.id = s.geography_id
                WHERE g.level = 'country' AND s.value IS NOT NULL
                  AND s.year >= (SELECT MAX(year) FROM statistic_best) - ?
            )
            SELECT geography_id, indicator, ANY_VALUE(unit) AS unit,
                   MIN(year) AS from_year, MAX(year) AS to_year,
                   arg_max(value, year) - arg_min(value, year) AS change
            FROM win GROUP BY geography_id, indicator
            HAVING MIN(year) < MAX(year)""", [trend_years])

        rising = falling = None
        if not changes.empty:
            # Percentile of each country's change within its indicator's
            # cross-country distribution. Needs a few peers to mean anything.
            counts = changes.groupby("indicator")["change"].transform("size")
            changes = changes[counts >= 5]
            changes = changes.assign(
                pct=changes.groupby("indicator")["change"].rank(pct=True))
            mine = changes[changes["geography_id"] == geo_id]
            if not mine.empty:
                def _fact(r):
                    return {"indicator": str(r["indicator"]),
                            "change": float(r["change"]),
                            "percentile": round(float(r["pct"]) * 100.0),
                            "unit": None if pd.isna(r["unit"]) else str(r["unit"]),
                            "from_year": int(r["from_year"]),
                            "to_year": int(r["to_year"])}
                top = mine.loc[mine["pct"].idxmax()]
                bottom = mine.loc[mine["pct"].idxmin()]
                # Only claim "rising" if it actually rose (and fell, for
                # falling) -- a top-percentile change can still be a decline if
                # every country declined.
                if top["change"] > 0:
                    rising = _fact(top)
                if bottom["change"] < 0:
                    falling = _fact(bottom)

        coverage = self.query(
            "SELECT COUNT(DISTINCT indicator_id) AS n, MAX(year) AS last_year "
            "FROM statistic_best WHERE geography_id = ?", [geo_id])
        blocs = self.country_blocs(iso3)
        return {
            "iso3": iso3,
            "iso2": None if pd.isna(row.iloc[0]["iso2"]) else str(row.iloc[0]["iso2"]),
            "name": str(row.iloc[0]["name"]),
            # pd.isna, not `is None`: a nullable-int column yields pd.NA for a
            # current member (no until_year), which `is None` does not catch.
            "blocs": [{"code": str(b["bloc_code"]), "name": str(b["bloc_name"]),
                       "since_year": None if pd.isna(b["since_year"]) else int(b["since_year"]),
                       "until_year": None if pd.isna(b["until_year"]) else int(b["until_year"])}
                      for _, b in blocs.iterrows()],
            "headline": headline,
            "fastest_rising": rising,
            "fastest_falling": falling,
            "n_indicators": int(coverage.iloc[0]["n"] or 0),
            "last_year": None if pd.isna(coverage.iloc[0]["last_year"])
                         else int(coverage.iloc[0]["last_year"]),
        }

    def country_correlations(self, country: str, *, min_years: int = 8,
                             limit: int | None = 20) -> pd.DataFrame:
        """This country's own growth-rate correlations for the indicator pairs
        the structural graph flagged as significant across Europe.

        Rather than presenting Europe-wide pooled edges as if they were local,
        this walks the FDR-surviving pairs from ``correlation_graph()`` and
        computes *this country's* Pearson r (on YoY growth) for each. Columns:
        indicator_a, indicator_b, domain_a, domain_b, correlation, n_years,
        p_value, relationship (the pair's strongest lag test in the pooled
        graph), q_value (the pair's Europe-wide FDR q). Sorted by |correlation|.
        """
        geo_id = self._resolve_country(country)  # validate / raise for unknown
        iso3 = self._con.execute(
            "SELECT COALESCE(iso3, code) FROM geography WHERE id = ?", [geo_id]).fetchone()[0]
        edges = self.correlation_graph()
        cols = ["indicator_a", "indicator_b", "domain_a", "domain_b",
                "correlation", "n_years", "p_value", "relationship", "q_value"]
        if edges.empty:
            return pd.DataFrame(columns=cols)
        # Growth frame per indicator (built once), restricted to this country.
        names = pd.unique(edges[["indicator_a", "indicator_b"]].values.ravel())
        gframes: dict[str, pd.DataFrame] = {}
        for name in names:
            f = self._indicator_frame(name).rename(columns={"value": "v"})
            f = self._growth_frame(f, "v")
            gframes[name] = f[f["iso3"] == iso3][["year", "v"]]
        rows = []
        for _, e in edges.iterrows():
            fa, fb = gframes[e["indicator_a"]], gframes[e["indicator_b"]]
            m = fa.merge(fb, on="year", suffixes=("_a", "_b"))
            if len(m) < min_years or m["v_a"].std() == 0 or m["v_b"].std() == 0:
                continue
            r = m["v_a"].corr(m["v_b"])
            if pd.isna(r):
                continue
            p, _, _ = _pearson_stats(r, len(m))
            rows.append({"indicator_a": e["indicator_a"], "indicator_b": e["indicator_b"],
                         "domain_a": e["domain_a"], "domain_b": e["domain_b"],
                         "correlation": r, "n_years": len(m), "p_value": p,
                         "relationship": e["relationship"], "q_value": e["q_value"]})
        if not rows:
            return pd.DataFrame(columns=cols)
        out = (pd.DataFrame(rows)
                 .reindex(pd.DataFrame(rows)["correlation"].abs()
                          .sort_values(ascending=False).index)
                 .reset_index(drop=True))
        return out.head(limit) if limit else out

    _PROPAGATE_COLUMNS = ["node", "hop", "activation", "via", "path", "directed"]

    def propagate(self, node: str, *, country: str | None = None,
                  shock: float = 1.0, max_hops: int = 3, decay: float = 0.6,
                  threshold: float = 0.05, edge_floor: float = 0.30
                  ) -> pd.DataFrame:
        """Trace how a shock to one indicator ripples through the others.

        Walks the signed `CORRELATES_WITH` edges outward from `node`, reporting
        each indicator reached, the hop it was reached at, the signed activation
        that arrived, and the route it took. Pass `country` to walk that
        country's own correlations (`country_correlations`) instead of the
        Europe-wide pooled ones (`correlation_graph`).

        This is historical co-movement, not causation or forecast: most edges
        carry no confirmed direction, so `directed` is True only when every edge
        on a result's path was Granger-confirmed.

        Defaults are calibrated against the built graph -- see
        docs/superpowers/specs/2026-07-23-propagation-engine-design.md. In
        particular `edge_floor` is what produces multi-hop structure; at 0 the
        graph is dense enough that almost everything lands on hop 1.

        Columns: node, hop, activation, via, path, directed. Empty (with those
        columns) when the graph has not been built.
        """
        name = self.query("SELECT name FROM indicator WHERE id = ?",
                          [self._resolve_indicator(node)]).iloc[0, 0]
        if country is None:
            edges_df = self.correlation_graph()
            weight_col = "weight"
        else:
            self._resolve_country(country)   # raises EuroDataLookupError if unknown
            edges_df = self.country_correlations(country, limit=None)
            weight_col = "correlation"
        if edges_df.empty:
            return pd.DataFrame(columns=self._PROPAGATE_COLUMNS)

        # country_correlations carries no `direction` column -- per-country
        # correlations are plain co-movement, so every edge is symmetric there.
        directions = (edges_df["direction"] if "direction" in edges_df.columns
                      else pd.Series(["undetermined"] * len(edges_df)))
        edges = [
            (str(a), str(b), float(w), str(d))
            for a, b, w, d in zip(edges_df["indicator_a"], edges_df["indicator_b"],
                                  edges_df[weight_col], directions, strict=True)
        ]
        activations = _propagate_core(
            edges, name, shock=shock, max_hops=max_hops, decay=decay,
            threshold=threshold, edge_floor=edge_floor)
        if not activations:
            return pd.DataFrame(columns=self._PROPAGATE_COLUMNS)
        return pd.DataFrame([
            {"node": a.node, "hop": a.hop, "activation": a.activation,
             "via": a.via, "path": " → ".join(a.path), "directed": a.directed}
            for a in activations
        ])


# --- module-level default handle -----------------------------------------
_default: EuroData | None = None


def open(path: str | None = None, *, read_only: bool = True) -> EuroData:  # noqa: A001
    """Open a database (default: the bundled one) and make it the default handle."""
    global _default
    if _default is not None:
        _default.close()
    _default = EuroData(path, read_only=read_only)
    return _default


def _get() -> EuroData:
    global _default
    if _default is None:
        _default = EuroData()
    return _default


def _delegate(name):
    def fn(*args, **kwargs):
        return getattr(_get(), name)(*args, **kwargs)
    fn.__name__ = name
    fn.__qualname__ = name
    fn.__doc__ = getattr(EuroData, name).__doc__
    return fn


countries = _delegate("countries")
blocs = _delegate("blocs")
bloc_members = _delegate("bloc_members")
domains = _delegate("domains")
indicators = _delegate("indicators")
sources = _delegate("sources")
correlation_graph = _delegate("correlation_graph")
years = _delegate("years")
search_indicators = _delegate("search_indicators")
series = _delegate("series")
latest = _delegate("latest")
provenance = _delegate("provenance")
revisions = _delegate("revisions")
revisions_summary = _delegate("revisions_summary")
country_blocs = _delegate("country_blocs")
country_indicators = _delegate("country_indicators")
country_correlations = _delegate("country_correlations")
country_profile = _delegate("country_profile")
compare = _delegate("compare")
forecast = _delegate("forecast")
coverage = _delegate("coverage")
ingestion_summary = _delegate("ingestion_summary")
events = _delegate("events")
event_types = _delegate("event_types")
event_study = _delegate("event_study")
correlate = _delegate("correlate")
lagged_correlation = _delegate("lagged_correlation")
indicator_trends = _delegate("indicator_trends")
query = _delegate("query")
relation = _delegate("relation")
propagate = _delegate("propagate")

__all__ = [
    "EuroData", "EuroDataLookupError", "open",
    "countries", "blocs", "bloc_members", "domains", "indicators", "sources",
    "years", "search_indicators", "series", "latest", "provenance",
    "revisions", "revisions_summary",
    "country_blocs", "country_indicators", "country_profile", "country_correlations",
    "compare", "forecast", "coverage",
    "ingestion_summary", "events", "event_types", "event_study",
    "correlate", "lagged_correlation", "indicator_trends", "correlation_graph",
    "query", "relation", "propagate",
]
