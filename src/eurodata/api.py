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


class EuroDataLookupError(LookupError):
    """Unknown country / indicator / bloc, with did-you-mean suggestions."""


def _suggest(value: str, candidates: list[str], kind: str) -> str:
    close = get_close_matches(value, candidates, n=3, cutoff=0.4)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    return f"Unknown {kind}: {value!r}.{hint}"


# period: '2020' / '2020-Q3' / '2020-07'; t: decimal year (period start) for
# plotting and ordering sub-annual series.
_SERIES_SQL = """
SELECT g.iso3, g.name AS country, d.name AS domain, i.name AS indicator,
       s.year, s.quarter, s.month,
       CASE WHEN s.month IS NOT NULL THEN printf('%d-%02d', s.year, s.month)
            WHEN s.quarter IS NOT NULL THEN printf('%d-Q%d', s.year, s.quarter)
            ELSE CAST(s.year AS VARCHAR) END AS period,
       s.year + CASE WHEN s.month IS NOT NULL THEN (s.month - 1) / 12.0
                     WHEN s.quarter IS NOT NULL THEN (s.quarter - 1) / 4.0
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
        row = self._con.execute(
            "SELECT id FROM geography WHERE upper(iso3) = upper(?) "
            "OR upper(iso2) = upper(?) OR lower(name) = lower(?)",
            [country, country, country]).fetchone()
        if row is None:
            names = [r[0] for r in self._con.execute(
                "SELECT iso3 FROM geography WHERE iso3 IS NOT NULL "
                "UNION ALL SELECT name FROM geography").fetchall()]
            raise EuroDataLookupError(_suggest(country, names, "country"))
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
        # single frequency: infer from the sub-annual columns
        if hist["month"].notna().any():
            freq, step = 12, 1.0 / 12.0
        elif hist["quarter"].notna().any():
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
                   MIN(s.year) AS first_year, MAX(s.year) AS last_year
            FROM indicator i
            JOIN domain d ON d.id = i.domain_id
            LEFT JOIN statistic_best s ON s.indicator_id = i.id
            LEFT JOIN geography g ON g.id = s.geography_id
            {where}
            GROUP BY i.name, d.name, i.is_proxy, d.id, i.id
            ORDER BY d.id, i.id""", params)

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
        # Period midpoints: month -> (m-0.5)/12, quarter -> (q-0.5)/4, year -> +0.5
        data = data.assign(t_mid=data["year"]
                           + ((data["month"] - 0.5) / 12.0)
                             .fillna((data["quarter"] - 0.5) / 4.0)
                             .fillna(0.5))
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

    def lagged_correlation(self, indicator_a: str, indicator_b: str, *,
                           lag: int = 0, min_years: int = 10) -> pd.DataFrame:
        """Per-country Pearson correlation of a(t) with b(t + lag).

        lag > 0 tests whether indicator_a leads indicator_b by `lag` years.
        Countries with fewer than min_years overlapping years are dropped.
        p_value and the 95% CI [ci_low, ci_high] come from the Fisher
        z-transform (normal approximation, unadjusted for multiple tests).
        """
        a = self._indicator_frame(indicator_a).rename(columns={"value": "a"})
        b = self._indicator_frame(indicator_b).rename(columns={"value": "b"})
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
        return (pd.DataFrame(rows).sort_values("correlation", ascending=False)
                  .reset_index(drop=True) if rows
                else pd.DataFrame(columns=self._CORR_COLUMNS))

    def correlate(self, indicator_a: str, indicator_b: str, *,
                  min_years: int = 10) -> pd.DataFrame:
        """Per-country Pearson correlation between two indicators (lag 0)."""
        return self.lagged_correlation(indicator_a, indicator_b, lag=0,
                                       min_years=min_years)


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

__all__ = [
    "EuroData", "EuroDataLookupError", "open",
    "countries", "blocs", "bloc_members", "domains", "indicators", "sources",
    "years", "search_indicators", "series", "latest", "compare", "forecast", "coverage",
    "ingestion_summary", "events", "event_types", "event_study",
    "correlate", "lagged_correlation", "indicator_trends", "correlation_graph",
    "query", "relation",
]
