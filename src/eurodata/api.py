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

from difflib import get_close_matches

import duckdb
import pandas as pd

from eurodata.config import get_settings
from eurodata.db import connect as _connect


class EuroDataLookupError(LookupError):
    """Unknown country / indicator / bloc, with did-you-mean suggestions."""


def _suggest(value: str, candidates: list[str], kind: str) -> str:
    close = get_close_matches(value, candidates, n=3, cutoff=0.4)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    return f"Unknown {kind}: {value!r}.{hint}"


_SERIES_SQL = """
SELECT g.iso3, g.name AS country, d.name AS domain, i.name AS indicator,
       s.year, s.value, COALESCE(s.unit, i.unit) AS unit,
       src.name AS source, i.is_proxy, i.proxy_note
FROM statistic_best s
JOIN geography g ON g.id = s.geography_id
JOIN indicator i ON i.id = s.indicator_id
JOIN domain d ON d.id = i.domain_id
JOIN source src ON src.id = s.source_id
"""


class EuroData:
    """A handle on one eurodata DuckDB database."""

    def __init__(self, path: str | None = None, *, read_only: bool = True) -> None:
        db_path = path or get_settings().duckdb_path
        try:
            self._con = _connect(db_path, read_only=read_only)
        except duckdb.Error as exc:
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
            "SELECT name, organization, url, license, redistributable, update_frequency "
            "FROM source ORDER BY id")

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
                "SELECT iso3 FROM geography UNION ALL SELECT name FROM geography").fetchall()]
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
               end: int | None = None) -> pd.DataFrame:
        """Time series filtered by any combination of country / indicator /
        domain / source / bloc (current members) / year range."""
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
        return self.query(sql + " ORDER BY indicator, iso3, year", params)

    def latest(self, indicator: str, *, bloc: str | None = None) -> pd.DataFrame:
        """Most recent value of an indicator for every country."""
        df = self.series(indicator=indicator, bloc=bloc)
        if df.empty:
            return df
        idx = df.groupby("iso3")["year"].idxmax()
        return (df.loc[idx].sort_values("value", ascending=False)
                  .reset_index(drop=True))

    def compare(self, countries: list[str], indicator: str, *,
                start: int | None = None, end: int | None = None) -> pd.DataFrame:
        """Wide year x country table for one indicator."""
        frames = [self.series(country=c, indicator=indicator, start=start, end=end)
                  for c in countries]
        long = pd.concat(frames, ignore_index=True)
        if long.empty:
            return long
        return long.pivot_table(index="year", columns="iso3", values="value")

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
                   MIN(s.year) AS first_year, MAX(s.year) AS last_year
            FROM indicator i
            JOIN domain d ON d.id = i.domain_id
            LEFT JOIN statistic_best s ON s.indicator_id = i.id
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

        For each matching event and affected country, compares the indicator
        mean over [year-window, year-1] with [year, year+window]. Returns one
        row per (event, country) with before/after means and deltas.
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
        out = []
        for _, ev in evs.iterrows():
            year = int(str(ev["start_date"])[:4])
            for iso3 in self._event_countries(ev):
                cdata = data[data["iso3"] == iso3]
                before = cdata[(cdata["year"] >= year - window_years) & (cdata["year"] < year)]["value"]
                after = cdata[(cdata["year"] >= year) & (cdata["year"] <= year + window_years)]["value"]
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
    def _indicator_frame(self, indicator: str) -> pd.DataFrame:
        ind_id = self._resolve_indicator(indicator)
        return self.query(
            "SELECT g.iso3, s.year, s.value FROM statistic_best s "
            "JOIN geography g ON g.id = s.geography_id WHERE s.indicator_id = ?",
            [ind_id])

    def lagged_correlation(self, indicator_a: str, indicator_b: str, *,
                           lag: int = 0, min_years: int = 5) -> pd.DataFrame:
        """Per-country Pearson correlation of a(t) with b(t + lag).

        lag > 0 tests whether indicator_a leads indicator_b by `lag` years.
        Countries with fewer than min_years overlapping observations are dropped.
        """
        a = self._indicator_frame(indicator_a).rename(columns={"value": "a"})
        b = self._indicator_frame(indicator_b).rename(columns={"value": "b"})
        b = b.assign(year=b["year"] - lag)  # b(t+lag) aligned onto year t
        merged = a.merge(b, on=["iso3", "year"])
        rows = []
        for iso3, grp in merged.groupby("iso3"):
            if len(grp) < min_years or grp["a"].std() == 0 or grp["b"].std() == 0:
                continue
            rows.append({"iso3": iso3, "n_years": len(grp),
                         "correlation": grp["a"].corr(grp["b"]), "lag": lag})
        return (pd.DataFrame(rows).sort_values("correlation", ascending=False)
                  .reset_index(drop=True) if rows else pd.DataFrame(
                      columns=["iso3", "n_years", "correlation", "lag"]))

    def correlate(self, indicator_a: str, indicator_b: str, *,
                  min_years: int = 5) -> pd.DataFrame:
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
years = _delegate("years")
search_indicators = _delegate("search_indicators")
series = _delegate("series")
latest = _delegate("latest")
compare = _delegate("compare")
coverage = _delegate("coverage")
ingestion_summary = _delegate("ingestion_summary")
events = _delegate("events")
event_types = _delegate("event_types")
event_study = _delegate("event_study")
correlate = _delegate("correlate")
lagged_correlation = _delegate("lagged_correlation")
query = _delegate("query")
relation = _delegate("relation")

__all__ = [
    "EuroData", "EuroDataLookupError", "open",
    "countries", "blocs", "bloc_members", "domains", "indicators", "sources",
    "years", "search_indicators", "series", "latest", "compare", "coverage",
    "ingestion_summary", "events", "event_types", "event_study",
    "correlate", "lagged_correlation", "query", "relation",
]
