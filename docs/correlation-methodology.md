# Correlation graph methodology

`CORRELATES_WITH` edges in the knowledge graph are built by
`src/eurodata/graph/correlate.py`. An edge is a stronger claim than the
exploratory `EuroData.correlate()` helper ("these two indicators are related
across Europe"), so every pair has to clear the steps below before it is
stored. The edges are exposed through `EuroData.correlation_graph()` and
`GET /api/correlation-graph`.

> Correlation is not causation. Even a Granger-confirmed direction means
> "past values of A help predict B", not that A causes B.

## Pipeline

1. **Growth rates, not levels.** Each indicator is annualised per country
   (mean of the best-available statistics for the year) and converted to
   year-over-year percentage change. Correlating levels of two trending series
   produces spurious relationships; growth rates remove most of that. Infinite
   changes (division by zero) are dropped.
2. **Per-country Pearson r.** For each country with at least `MIN_YEARS` (8)
   overlapping growth-rate years, and non-constant series on both sides,
   compute the Pearson correlation.
3. **Pool across countries.** Per-country correlations are combined with a
   fixed-effect Fisher-z average, weighted by `n - 3`. A pair needs at least
   `MIN_COUNTRIES` (3) contributing countries for a pooled statistic to exist.
   The pooled r (the edge `weight`) and a two-sided p-value come from the
   normal approximation.
4. **Three lag tests per pair.** Contemporaneous (`A(t)` vs `B(t)`),
   `a_leads_b` (`A(t)` vs `B(t+1)`) and `b_leads_a` (`B(t)` vs `A(t+1)`).
   The test with the smallest pooled p-value becomes the pair's
   `relationship`.
5. **Bonferroni across the lag tests.** The winning p-value is multiplied by
   the number of lag tests that were actually computable for the pair (at most
   3, capped at 1.0).
6. **Benjamini-Hochberg FDR across pairs.** The adjusted p-values of all
   candidate pairs are corrected jointly at `FDR_ALPHA = 0.05`. Pairs that do
   not survive get no edge; survivors store their `q_value`.
7. **Granger confirmation of direction.** Only when a *lagged* test won, a
   per-country lag-1 Granger test (`ssr_ftest`) is run in both directions and
   the per-country p-values are combined with Fisher's method. The edge gets
   `direction = a_leads_b` (or `b_leads_a`) only if the winning direction has
   a combined p below `GRANGER_ALPHA = 0.05` **and** the opposite direction
   does not. Otherwise the direction is `undetermined`. Contemporaneous
   winners always have `direction = undetermined`. When the direction is
   `b_leads_a` the stored edge is flipped so it always points from leader to
   follower; otherwise the edge runs from `indicator_a` to `indicator_b` in an
   arbitrary order.

## Stored edge properties

| Property | Meaning |
| --- | --- |
| `weight` | signed pooled Pearson r of the winning test |
| `relationship` | `contemporaneous`, `a_leads_b` or `b_leads_a` (strongest test) |
| `direction` | Granger-confirmed lead/lag, or `undetermined` |
| `q_value` | Benjamini-Hochberg adjusted p-value |
| `p_value` | Bonferroni-adjusted pooled p-value of the winning test |
| `n_countries` | countries contributing to the pooled statistic |
| `granger_p_a_to_b`, `granger_p_b_to_a` | combined Granger p-values (set only when a lagged test won) |
| `per_country` | per-country r, years used and Granger p-values, for drill-down |

## Known limitations

- Annual series are short, so power is low for individual countries; the pooled
  statistic is what carries the signal.
- Pooling assumes a common effect across countries (fixed-effect). A pair that
  is strongly positive in some countries and negative in others will be
  weakened or dropped.
- Indicators that are components of one another (for example GDP and GDP per
  capita) correlate trivially and are not filtered out yet.
- Only a one-year lag is tested.
