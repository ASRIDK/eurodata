"""Rigorous indicator-to-indicator correlation edges (`CORRELATES_WITH`).

`EuroData.correlate()` / `.lagged_correlation()` (in `eurodata.api`) are a
quick-look, per-country tool for the dashboard/chat: raw levels, one lag at a
time, unadjusted p-values — explicitly documented there as "correlation is
not causation" and fine for exploratory use.

Structural graph edges are a stronger claim ("this repo asserts these two
indicators are related"), so this module follows the methodology the v1
design spec requires before `CORRELATES_WITH` can ship:

1. **Growth rates, not levels** — year-over-year % change per country, to
   avoid the classic spurious correlation from two series that both merely
   trend over time.
2. **Pooled across countries** — each per-country Pearson r is combined into
   a single statistic via a Fisher-z-weighted average (a standard
   fixed-effect meta-analysis pool), so the edge represents a relationship
   general across Europe, not one country's coincidence.
3. **Lagged, not just contemporaneous** — for every pair, three pooled tests
   are run: contemporaneous (t vs t), "A leads B" (A(t) vs B(t+1)), and "B
   leads A" (B(t) vs A(t+1)). Whichever is strongest is the pair's
   relationship; the other two tried tests earn it a Bonferroni penalty
   (x3) before it's compared against other pairs — a naive contemporaneous-
   only test would miss genuinely lagged relationships entirely.
4. **FDR correction across pairs** — every indicator pair's (Bonferroni-
   adjusted) p-value is then corrected jointly with Benjamini-Hochberg
   (`statsmodels.stats.multitest.multipletests`), so only relationships
   that survive multiple-comparison correction get an edge at all.
5. **Granger-style directionality, as confirmation** — a lag-1 Granger
   causality test (per country, combined across countries via Fisher's
   method) is only consulted *after* a pair clears FDR and only when a lag
   (not the contemporaneous test) won: a direction is recorded on the edge
   solely when the Granger evidence is one-sided too. This keeps the
   primary significance ranking apples-to-apples (all Pearson-r-based)
   while still requiring genuine Granger causality before an edge claims
   "A leads B" rather than just "A and B move together".

Needs the `app` extra (`pip install -e ".[app]"`): statsmodels + scipy.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from itertools import combinations
from math import atanh, erf, sqrt, tanh

import duckdb
import pandas as pd
from scipy.stats import combine_pvalues
from statsmodels.stats.multitest import multipletests
from statsmodels.tsa.stattools import grangercausalitytests

# Minimum overlapping (country, year) growth-rate points for a country to
# count towards a pooled statistic at all.
MIN_YEARS = 8
# Minimum number of countries contributing a valid per-country correlation
# before a pair is even considered a "pooled" relationship.
MIN_COUNTRIES = 3
# Annual series are short; keep the Granger VAR tiny so it stays estimable.
MAX_GRANGER_LAG = 1
# Benjamini-Hochberg FDR threshold across all indicator pairs tested.
FDR_ALPHA = 0.05
# Threshold on the *combined* (cross-country) Granger p-value before a
# lead/lag direction is claimed at all.
GRANGER_ALPHA = 0.05


@dataclass
class PairResult:
    indicator_a: int
    indicator_b: int
    weight: float                      # signed pooled r of the winning test
    p_value: float                     # Bonferroni-adjusted (across the up to 3 lag tests tried)
    n_countries: int
    relationship: str                  # "contemporaneous" | "a_leads_b" | "b_leads_a" (strongest test)
    direction: str                     # "a_leads_b" | "b_leads_a" | "undetermined" (Granger-confirmed)
    granger_p_a_to_b: float | None
    granger_p_b_to_a: float | None
    per_country: list[dict] = field(default_factory=list)
    q_value: float | None = None


def _growth_rate_frame(con: duckdb.DuckDBPyConnection, indicator_id: int) -> pd.DataFrame:
    """One row per (country, year) growth rate: annualized level -> YoY % change."""
    df = con.execute(
        "SELECT g.iso3, s.year, AVG(s.value) AS value FROM statistic_best s "
        "JOIN geography g ON g.id = s.geography_id WHERE s.indicator_id = ? "
        "GROUP BY g.iso3, s.year", [indicator_id]).df()
    if df.empty:
        return df
    df = df.sort_values(["iso3", "year"])
    df["growth"] = df.groupby("iso3")["value"].pct_change()
    df = df.replace([float("inf"), float("-inf")], pd.NA)
    return df.dropna(subset=["growth"])[["iso3", "year", "growth"]]


def _fisher_pool(rs: list[float], ns: list[int]) -> tuple[float, float]:
    """Fixed-effect pool of per-country Pearson r via the Fisher z-transform.

    Weighted by (n - 3), the usual inverse-variance weight for Fisher z.
    Returns the pooled r and its two-sided p-value (normal approximation,
    same approach as `eurodata.api._pearson_stats`, no scipy needed here).
    """
    zs = [atanh(max(-0.999999999, min(0.999999999, r))) for r in rs]
    weights = [n - 3 for n in ns]
    total_w = sum(weights)
    z_bar = sum(z * w for z, w in zip(zs, weights)) / total_w
    se = 1.0 / sqrt(total_w)
    p = 2.0 * (1.0 - 0.5 * (1.0 + erf(abs(z_bar / se) / sqrt(2.0))))
    return tanh(z_bar), p


def _pooled_lag_correlation(frame_leader: pd.DataFrame, frame_follower: pd.DataFrame,
                             lag: int) -> dict | None:
    """Pool, across countries, the correlation of `leader(t)` with
    `follower(t + lag)`. lag=0 is the contemporaneous test; lag=1 tests
    whether `leader` leads `follower` by a year.
    """
    shifted = frame_follower.assign(year=frame_follower["year"] - lag) if lag else frame_follower
    merged = frame_leader.merge(shifted, on=["iso3", "year"], suffixes=("_x", "_y"))
    rows = []
    for iso3, grp in merged.groupby("iso3"):
        if len(grp) < MIN_YEARS or grp["growth_x"].std() == 0 or grp["growth_y"].std() == 0:
            continue
        r = grp["growth_x"].corr(grp["growth_y"])
        if pd.isna(r):
            continue
        rows.append((iso3, float(r), int(len(grp))))
    if len(rows) < MIN_COUNTRIES:
        return None
    pooled_r, pooled_p = _fisher_pool([r for _, r, _ in rows], [n for _, _, n in rows])
    return {
        "pooled_r": pooled_r, "pooled_p": pooled_p, "n_countries": len(rows),
        "per_country": {iso3: {"correlation": round(r, 4), "n_years": n} for iso3, r, n in rows},
    }


def _granger_p(y: pd.Series, x: pd.Series) -> float | None:
    """p-value that `x` Granger-causes `y` at MAX_GRANGER_LAG.

    `grangercausalitytests` takes a 2-column array [response, predictor].
    Returns None if the series is too short, the regression is singular, or
    the resulting F-test is numerically degenerate (NaN).
    """
    data = pd.DataFrame({"y": y.to_numpy(), "x": x.to_numpy()}).to_numpy()
    if len(data) < 2 * (MAX_GRANGER_LAG + 1) + 2:
        return None
    try:
        with warnings.catch_warnings():
            # Short annual series occasionally produce a rank-deficient or
            # near-singular regression; statsmodels warns loudly (and
            # returns NaN, handled below) rather than raising.
            warnings.simplefilter("ignore")
            result = grangercausalitytests(data, maxlag=MAX_GRANGER_LAG, verbose=False)
        p = float(result[MAX_GRANGER_LAG][0]["ssr_ftest"][1])
    except Exception:
        return None
    return None if p != p else p  # NaN != NaN


def _combine_p(pvals: list[float]) -> float | None:
    """Fisher's method: combine independent per-country p-values into one."""
    clean = [max(p, 1e-300) for p in pvals if p is not None]
    if not clean:
        return None
    return float(combine_pvalues(clean, method="fisher")[1])


def _pooled_granger(frame_a: pd.DataFrame, frame_b: pd.DataFrame) -> tuple[float | None, float | None, dict]:
    """Per-country lag-1 Granger causality in both directions, combined
    across countries. Returns (p_a_causes_b, p_b_causes_a, per-country detail).
    """
    merged = frame_a.merge(frame_b, on=["iso3", "year"], suffixes=("_a", "_b"))
    p_a_to_b, p_b_to_a, detail = [], [], {}
    for iso3, grp in merged.groupby("iso3"):
        grp = grp.sort_values("year")
        if len(grp) < MIN_YEARS:
            continue
        p_ab = _granger_p(grp["growth_b"], grp["growth_a"])  # does a lead b?
        p_ba = _granger_p(grp["growth_a"], grp["growth_b"])  # does b lead a?
        if p_ab is not None:
            p_a_to_b.append(p_ab)
        if p_ba is not None:
            p_b_to_a.append(p_ba)
        detail[iso3] = {"granger_p_a_to_b": p_ab, "granger_p_b_to_a": p_ba}
    return _combine_p(p_a_to_b), _combine_p(p_b_to_a), detail


def _pair_result(ind_a: int, ind_b: int, frame_a: pd.DataFrame, frame_b: pd.DataFrame) -> PairResult | None:
    tests = {
        "contemporaneous": _pooled_lag_correlation(frame_a, frame_b, 0),
        "a_leads_b": _pooled_lag_correlation(frame_a, frame_b, 1),
        "b_leads_a": _pooled_lag_correlation(frame_b, frame_a, 1),
    }
    available = {k: v for k, v in tests.items() if v is not None}
    if not available:
        return None

    best_key = min(available, key=lambda k: available[k]["pooled_p"])
    best = available[best_key]
    # Bonferroni across the (up to 3) lag tests actually tried for this pair.
    pair_p = min(1.0, best["pooled_p"] * len(available))

    direction = "undetermined"
    granger_p_a_to_b = granger_p_b_to_a = None
    granger_detail: dict = {}
    if best_key != "contemporaneous":
        granger_p_a_to_b, granger_p_b_to_a, granger_detail = _pooled_granger(frame_a, frame_b)
        if granger_p_a_to_b is not None and granger_p_b_to_a is not None:
            if (best_key == "a_leads_b" and granger_p_a_to_b < GRANGER_ALPHA
                    and granger_p_b_to_a >= GRANGER_ALPHA):
                direction = "a_leads_b"
            elif (best_key == "b_leads_a" and granger_p_b_to_a < GRANGER_ALPHA
                    and granger_p_a_to_b >= GRANGER_ALPHA):
                direction = "b_leads_a"

    per_country = []
    for iso3, stats in sorted(best["per_country"].items()):
        entry = {"iso3": iso3, "relationship": best_key, **stats}
        entry.update(granger_detail.get(iso3, {}))
        per_country.append(entry)

    return PairResult(
        indicator_a=ind_a, indicator_b=ind_b, weight=best["pooled_r"], p_value=pair_p,
        n_countries=best["n_countries"], relationship=best_key, direction=direction,
        granger_p_a_to_b=granger_p_a_to_b, granger_p_b_to_a=granger_p_b_to_a,
        per_country=per_country,
    )


def compute_correlation_edges(con: duckdb.DuckDBPyConnection) -> list[PairResult]:
    """All indicator pairs whose strongest growth-rate relationship (tested
    contemporaneously and at a 1-year lag in both directions) survives
    Benjamini-Hochberg FDR correction applied jointly across every pair,
    each carrying a Granger-confirmed lead/lag direction when there is one.
    """
    indicator_ids = [r[0] for r in con.execute("SELECT id FROM indicator ORDER BY id").fetchall()]
    frames = {iid: _growth_rate_frame(con, iid) for iid in indicator_ids}
    frames = {iid: f for iid, f in frames.items() if not f.empty}

    candidates = []
    for a, b in combinations(sorted(frames), 2):
        result = _pair_result(a, b, frames[a], frames[b])
        if result is not None:
            candidates.append(result)
    if not candidates:
        return []

    pvals = [c.p_value for c in candidates]
    reject, qvals, _, _ = multipletests(pvals, alpha=FDR_ALPHA, method="fdr_bh")
    significant = []
    for cand, rej, q in zip(candidates, reject, qvals):
        if rej:
            cand.q_value = float(q)
            significant.append(cand)
    return significant
