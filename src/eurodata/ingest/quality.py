"""Data-quality gates for the ingestion pipeline — the dataset's data contracts.

Each check is a small pure function over a DuckDB connection that returns a
:class:`Check`. :func:`run_quality_checks` runs the whole battery and returns a
:class:`QualityReport`; the orchestrated pipeline calls
``report.raise_for_status()`` after loading so a bad run fails loudly instead of
silently publishing corrupt data.

Checks carry a *severity*: ``ERROR`` checks block the pipeline (a broken
contract), ``WARN`` checks only surface (e.g. data that is merely getting old).
Everything here is deterministic and DB-only, so the contracts are unit-tested
without any network or orchestrator.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any

import duckdb

ERROR = "error"
WARN = "warn"

# Indicators whose values are additive across geography — a country total equals
# the sum of its regions — so cross-level reconciliation by summation is valid.
# Ratios, rates and per-capita series are deliberately excluded. Keyed by
# indicator.api_code.
ADDITIVE_INDICATORS = frozenset({"demo_pjan", "nama_10_gdp"})


class DataQualityError(RuntimeError):
    """Raised by ``QualityReport.raise_for_status`` when a blocking check fails."""


@dataclasses.dataclass(frozen=True)
class Check:
    """The outcome of one data-quality contract."""

    name: str
    passed: bool
    severity: str  # ERROR | WARN
    detail: str
    metrics: dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        """A failed ERROR-severity check stops the pipeline."""
        return not self.passed and self.severity == ERROR

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "severity": self.severity,
                "blocking": self.blocking, "detail": self.detail, "metrics": self.metrics}


@dataclasses.dataclass(frozen=True)
class QualityReport:
    checks: list[Check]
    ran_at: dt.datetime

    @property
    def ok(self) -> bool:
        """True when no blocking (ERROR) check failed. WARN failures are allowed."""
        return not any(c.blocking for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def raise_for_status(self) -> None:
        blocking = [c for c in self.checks if c.blocking]
        if blocking:
            lines = "\n".join(f"  - [{c.name}] {c.detail}" for c in blocking)
            raise DataQualityError(
                f"{len(blocking)} blocking data-quality check(s) failed:\n{lines}")

    def summary(self) -> str:
        def mark(c: Check) -> str:
            return "PASS" if c.passed else ("FAIL" if c.blocking else "WARN")
        lines = [f"  {mark(c):>4}  {c.name}: {c.detail}" for c in self.checks]
        verdict = "OK" if self.ok else "BLOCKED"
        return f"Data-quality report [{verdict}]\n" + "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "ran_at": self.ran_at.isoformat(),
                "checks": [c.as_dict() for c in self.checks]}


# --- individual contracts --------------------------------------------------
def check_row_count(con: duckdb.DuckDBPyConnection, *, minimum: int = 1000) -> Check:
    """The fact table must hold at least ``minimum`` rows — guards against an
    ingestion that ran green but loaded almost nothing."""
    n = con.execute("SELECT COUNT(*) FROM statistic_record").fetchone()[0]
    return Check("row_count", n >= minimum, ERROR,
                 f"{n:,} statistic_record rows (floor {minimum:,})",
                 {"rows": int(n), "minimum": minimum})


def check_referential_integrity(con: duckdb.DuckDBPyConnection) -> Check:
    """Every fact must point at a real geography, indicator and source."""
    geo, ind, src = con.execute("""
        SELECT
            COUNT(*) FILTER (WHERE g.id IS NULL) AS geo,
            COUNT(*) FILTER (WHERE i.id IS NULL) AS ind,
            COUNT(*) FILTER (WHERE s.id IS NULL) AS src
        FROM statistic_record r
        LEFT JOIN geography g ON g.id = r.geography_id
        LEFT JOIN indicator i ON i.id = r.indicator_id
        LEFT JOIN source    s ON s.id = r.source_id
    """).fetchone()
    total = int(geo) + int(ind) + int(src)
    return Check("referential_integrity", total == 0, ERROR,
                 (f"{geo} orphan geography, {ind} indicator, {src} source references"
                  if total else "all foreign keys resolve"),
                 {"orphan_geography": int(geo), "orphan_indicator": int(ind),
                  "orphan_source": int(src)})


def check_value_finiteness(con: duckdb.DuckDBPyConnection) -> Check:
    """No NaN/±Inf values should reach the fact table (defense in depth behind
    validate_records)."""
    bad = con.execute(
        "SELECT COUNT(*) FROM statistic_record "
        "WHERE value IS NOT NULL AND NOT isfinite(value)").fetchone()[0]
    return Check("value_finiteness", bad == 0, ERROR,
                 "all values finite" if not bad else f"{bad} non-finite values",
                 {"non_finite": int(bad)})


def check_freshness(con: duckdb.DuckDBPyConnection, *, warn_years: int = 3,
                    error_years: int = 8, as_of: dt.date | None = None) -> Check:
    """No indicator should lag reality by too long. Staleness beyond
    ``error_years`` blocks; beyond ``warn_years`` only warns (official series
    publish with a natural lag, so mild staleness is normal)."""
    as_of = as_of or dt.date.today()
    rows = con.execute("""
        SELECT i.name, MAX(r.year) AS last_year
        FROM indicator i JOIN statistic_record r ON r.indicator_id = i.id
        WHERE r.value IS NOT NULL
        GROUP BY i.name
    """).fetchall()
    warn, error = [], []
    for name, last_year in rows:
        age = as_of.year - int(last_year)
        if age >= error_years:
            error.append((name, age))
        elif age >= warn_years:
            warn.append((name, age))
    metrics = {"warn_years": warn_years, "error_years": error_years,
               "n_indicators": len(rows), "n_warn": len(warn), "n_error": len(error),
               "stale_error": error[:10], "stale_warn": warn[:10]}
    if error:
        worst = ", ".join(f"{n} ({a}y)" for n, a in sorted(error, key=lambda x: -x[1])[:5])
        return Check("freshness", False, ERROR,
                     f"{len(error)} indicator(s) staler than {error_years}y: {worst}", metrics)
    if warn:
        worst = ", ".join(f"{n} ({a}y)" for n, a in sorted(warn, key=lambda x: -x[1])[:5])
        return Check("freshness", False, WARN,
                     f"{len(warn)} indicator(s) staler than {warn_years}y: {worst}", metrics)
    return Check("freshness", True, WARN, f"all {len(rows)} indicators within {warn_years}y", metrics)


def check_no_failed_ingestion(con: duckdb.DuckDBPyConnection) -> Check:
    """The most recent ingestion_run of every source must not be 'failed'."""
    rows = con.execute("""
        SELECT source, arg_max(status, started_at) AS latest_status
        FROM ingestion_run GROUP BY source
    """).fetchall()
    failed = [s for s, st in rows if st == "failed"]
    return Check("ingestion_runs", not failed, ERROR,
                 "no source's latest run failed" if not failed
                 else f"latest run failed for: {', '.join(failed)}",
                 {"failed_sources": failed, "n_sources": len(rows)})


def check_nuts_rollup(con: duckdb.DuckDBPyConnection, *, tolerance: float = 0.02) -> Check:
    """For additive indicators present at both country and NUTS-2 level, a
    country's regions must sum to its national total within ``tolerance``.
    Skipped (non-blocking) when no such indicator has both levels."""
    codes = list(ADDITIVE_INDICATORS)
    placeholders = ",".join("?" * len(codes))
    rows = con.execute(f"""
        WITH additive AS (
            SELECT id FROM indicator WHERE api_code IN ({placeholders})
        ),
        country AS (
            SELECT b.indicator_id, b.geography_id AS country_id, b.year,
                   b.value AS country_value
            FROM statistic_best b JOIN geography g ON g.id = b.geography_id
            WHERE g.level = 'country' AND b.value IS NOT NULL
              AND b.indicator_id IN (SELECT id FROM additive)
        ),
        regions AS (
            SELECT b.indicator_id, g.parent_id AS country_id, b.year,
                   SUM(b.value) AS region_sum, COUNT(*) AS n_regions
            FROM statistic_best b JOIN geography g ON g.id = b.geography_id
            WHERE g.level = 'NUTS2' AND b.value IS NOT NULL AND g.parent_id IS NOT NULL
              AND b.indicator_id IN (SELECT id FROM additive)
            GROUP BY b.indicator_id, g.parent_id, b.year
        )
        SELECT c.indicator_id, c.country_id, c.year, c.country_value, r.region_sum,
               abs(r.region_sum - c.country_value)
                 / nullif(abs(c.country_value), 0) AS rel_diff
        FROM country c JOIN regions r
          ON r.indicator_id = c.indicator_id
         AND r.country_id = c.country_id AND r.year = c.year
    """, codes).fetchall()
    if not rows:
        return Check("nuts_rollup", True, WARN,
                     "no additive indicator has both country and NUTS-2 data (skipped)",
                     {"n_comparisons": 0})
    mismatched = [row for row in rows if row[5] is None or row[5] > tolerance]
    n = len(rows)
    return Check("nuts_rollup", not mismatched, ERROR,
                 (f"{n} country/region totals reconcile within {tolerance:.0%}"
                  if not mismatched
                  else f"{len(mismatched)}/{n} totals diverge beyond {tolerance:.0%}"),
                 {"n_comparisons": n, "n_mismatched": len(mismatched),
                  "tolerance": tolerance})


# --- battery ---------------------------------------------------------------
def run_quality_checks(con: duckdb.DuckDBPyConnection, *, min_rows: int = 1000,
                       warn_years: int = 3, error_years: int = 8,
                       rollup_tolerance: float = 0.02,
                       as_of: dt.date | None = None) -> QualityReport:
    """Run every data-quality contract and return a :class:`QualityReport`."""
    checks = [
        check_row_count(con, minimum=min_rows),
        check_referential_integrity(con),
        check_value_finiteness(con),
        check_freshness(con, warn_years=warn_years, error_years=error_years, as_of=as_of),
        check_no_failed_ingestion(con),
        check_nuts_rollup(con, tolerance=rollup_tolerance),
    ]
    return QualityReport(checks=checks, ran_at=dt.datetime.now())
