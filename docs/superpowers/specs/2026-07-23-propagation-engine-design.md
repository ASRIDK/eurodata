# Propagation engine — spreading activation over the correlation graph

_Design spec — 2026-07-23_

## Purpose

Trace how a shock to one indicator (optionally within one country) ripples through
the rest of the dataset, by propagating signed activation along the
`CORRELATES_WITH` edges the graph builder already computes.

The value is not prediction. It is **structured exploration**: given that
unemployment moved, which other indicators historically moved with it, in which
direction, by how much, and through what chain. Everything this produces is
associative. Only 37 of 247 correlation edges carry a Granger-confirmed
direction; the rest are symmetric co-movement. The engine, the API docstrings and
the UI must all say so.

## What the graph actually looks like

Measured against the built graph (`scripts/build_graph.py` output):

- **105 nodes** — 50 country, 37 indicator, 7 domain, 6 bloc, 5 source
- **609 edges** — `CORRELATES_WITH` 247, `BORDERS` 172, `MEMBER_OF` 115,
  `PROVIDES` 38, `BELONGS_TO` 37
- Correlation weights span **−0.509 … 0.999**; 94 are negative
- 36 indicators carry at least one edge; **median degree 14, max 26**

That density is the central design constraint, and it produced two findings that
shaped the algorithm.

### Finding 1: naive spreading activation saturates

Summing arrivals across a median-degree-14 graph lights up nearly everything
within two hops. Measured node counts reached from a shock to Unemployment Rate,
by decay and threshold:

| decay | threshold | Unemployment | GDP | Renewables | Inflation |
| --- | --- | --- | --- | --- | --- |
| 0.5 | 0.02 | 29 | 24 | 24 | 9 |
| 0.6 | 0.02 | 30 | 25 | 29 | 11 |
| 0.6 | 0.05 | 24 | 23 | 15 | 7 |
| 0.6 | 0.10 | 15 | 15 | 6 | 1 |
| 0.7 | 0.05 | 28 | 24 | 19 | 7 |

Of 36 reachable indicators, the originally proposed defaults (decay 0.6,
threshold 0.02) reach 30 — i.e. "everything". Hence **strongest-path** rather
than accumulation: a node's activation is the single strongest signed path
reaching it, which is naturally bounded and explains itself.

### Finding 2: without an edge floor there is no cascade

Even with strongest-path, a dense graph means almost every node is a *direct*
neighbour, and a one-hop edge (`w × decay`) beats any two-hop product
(`w₁ × w₂ × decay²`). Hop distribution from Unemployment Rate (decay 0.6,
threshold 0.05):

| min \|weight\| | directed arcs | hop distribution |
| --- | --- | --- |
| 0.00 | 449 | **h1:22, h2:2** |
| 0.25 | 135 | h1:4, h2:10 |
| 0.35 | 38 | h1:2, h2:7 |
| 0.45 | 22 | h1:1, h2:1 |
| 0.55 | 8 | nothing reached |

At no floor the result is one fat column and the engine degenerates into
"sort correlations by weight" — which `/correlations` already does. **An
`edge_floor` of ~0.25–0.35 is what makes multi-hop structure exist.** Default
**0.30**, exposed as a parameter.

## Architecture

### Core — `src/eurodata/graph/propagate.py` (new, pure, no DB)

```python
propagate(edges, source, *, shock=1.0, max_hops=3, decay=0.6,
          threshold=0.05, edge_floor=0.30, collapse_variants=True)
    -> list[Activation]        # node, hop, activation, path, via, directed
```

`edges` is an iterable of `(a, b, weight, direction)` supplied by the caller.
That is what lets one engine serve both the pooled and the per-country edge sets
without knowing which it has.

Algorithm — frontier expansion by hop:

1. Seed `source` with `shock` at hop 0.
2. For each node on the frontier, for each outgoing edge above `edge_floor`:
   `candidate = activation × weight × decay`.
3. Discard if `|candidate| < threshold`.
4. Record if the node is unseen, or if `|candidate|` beats its current arrival.
   Only-improve is what terminates cycles — no visited set or special casing.
5. Stop at `max_hops` or when the frontier empties.

Signed throughout: a negative edge flips sign, so two negatives correctly yield a
positive. Each node keeps the path it arrived by, so the UI can show
*via Gov Debt → R&D*.

**Direction.** `a_leads_b` traverses a→b only; `b_leads_a` traverses b→a only;
`undetermined` and `contemporaneous` traverse both ways. Each result carries
`directed: bool` so the UI can style the 37 confirmed edges differently from the
210 symmetric ones.

**Variant collapsing.** The strongest correlations in this graph are tautologies:
`GDP ↔ GDP per capita` 0.999, `Inflation (HICP) ↔ Inflation (HICP, monthly)`
0.997, `New Business Density ↔ New Businesses Registered` 0.999. Unfiltered, hop
1 is entirely "GDP affects GDP per capita". Reuse the stem heuristic already used
on the country page (strip parentheticals; treat a pair as variants when one stem
prefixes the other).

Variants are excluded from **results**, not merely from edges: at `edge_floor`
0.45 a shock to Unemployment Rate reached "Unemployment Rate (monthly)" at hop 2
via Government Debt. A ripple that reports the source affecting itself is noise.

`propagate` being a pure function of its arguments is deliberate — every
algorithmic property below is testable without a database.

### API — `EuroData.propagate(node, *, country=None, ...)`

Resolves `node`, selects the edge set (`correlation_graph()` pooled, or
`country_correlations(country)` per-country), calls the core, and returns a
DataFrame: `node, hop, activation, path, via, directed`.

Optional `spill_to_neighbours` uses the 172 `BORDERS` edges to attribute a damped
copy of the ripple to adjacent countries. Off by default.

Exposed module-level via the existing `_delegate` mechanism and `__all__`.

### Endpoint — `GET /api/propagate`

`node`, `shock`, `max_hops`, `country`, `edge_floor`, `spill`. Mirrors the
existing `@app.get` patterns and `df_records` shape. Unknown node → the existing
`EuroDataLookupError` path → 404.

### Page — `/propagate`

Source picker (indicator, optional country), shock magnitude, hop slider, edge
floor control. Renders the cascade: one column per hop, each node a signed bar
with its value, its `via` path on hover, and distinct styling for directed vs
symmetric arrivals.

A permanent, non-dismissible caveat states that this is historical co-movement,
not a causal forecast. Proxy and staleness badges are reused from Explore.

## Data flow

```
/propagate page → GET /api/propagate → EuroData.propagate
                                     → correlation_graph() | country_correlations()
                                     → graph.propagate.propagate()
```

## Error handling

- Unknown indicator or country → `EuroDataLookupError` → 404, matching the rest
  of the API.
- Graph not built (`graph_edge` empty) → empty result plus an explicit message
  pointing at `scripts/build_graph.py`, the way `correlation_graph()` already
  behaves rather than raising.
- Nothing above threshold → an empty cascade with copy explaining that no edge
  cleared the floor, and a hint to lower it. This is a normal outcome for a
  weakly-connected indicator, not an error.

## Testing

**Core (hand-built micro-graphs, no DB):** sign propagates through negative edges
and double negatives yield positive; decay reduces activation per hop; threshold
prunes; a strong direct edge beats a weaker two-hop route and vice versa; cycles
terminate; `a_leads_b` is not traversed backwards; variants are excluded from
results even when reachable indirectly; `edge_floor` removes weak edges.

The two most substantive tests — strongest-path selection and cycle termination —
get mutation-checked, as `indicator_trends` and `ingestion_summary` were: the
test must fail when the behaviour it describes is broken.

**API:** against the in-memory fixture in `tests/test_api.py`.
**Endpoint:** TestClient, including the 404 and graph-not-built paths.
**Frontend:** `next build`, `eslint`, and a Playwright drive asserting the
cascade renders, hop columns are populated, and there is no horizontal overflow
at 390px.

## Defaults

| parameter | default | basis |
| --- | --- | --- |
| `decay` | 0.6 | mid of the measured range; 0.7 saturates, 0.5 truncates |
| `threshold` | 0.05 | 0.02 reaches 30 of 36 nodes |
| `edge_floor` | 0.30 | between the 0.25 and 0.35 rows above, where cascade structure appears |
| `max_hops` | 3 | h3 was empty at every floor tested; 3 leaves headroom |

Note the two tables above vary one parameter at a time — Finding 1 holds
`edge_floor` at 0, Finding 2 holds `threshold` at 0.05. **Combined, the defaults
land between the 0.25 and 0.35 rows of Finding 2: roughly 9–14 nodes spread over
two hops**, which is the target. Any tuning should be judged on that combined
number, not on either table in isolation.

These are measured against the current graph and should be re-checked whenever
`scripts/build_graph.py` is re-run over materially different data.

## Out of scope

- A chat tool wrapping this (deliberate; revisit once ranking behaviour settles)
- Force-directed graph rendering — a median-degree-14 graph renders as a hairball
- Any claim of causal inference or counterfactual simulation
