# Propagation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trace how a shock to one indicator ripples through the rest of the dataset, by propagating signed activation along the `CORRELATES_WITH` graph, exposed as a Python API, an HTTP endpoint, and a `/propagate` page.

**Architecture:** A pure, DB-free core (`src/eurodata/graph/propagate.py`) takes an edge list and returns ranked activations by hop. `EuroData.propagate()` adapts either the pooled `correlation_graph()` or per-country `country_correlations()` into that edge list. A FastAPI endpoint wraps it; a Next.js page renders the result as a cascade of columns, one per hop.

**Tech Stack:** Python 3.11+, pandas, DuckDB, FastAPI, Next.js 16 (App Router, client components), Tailwind v4, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-23-propagation-engine-design.md`. Read it before Task 1.
- There is no `python` on PATH. Use `/Users/toto/eurodata/.venv/bin/python`.
- Run tests as: `cd /Users/toto/eurodata && PYTHONPATH=src .venv/bin/python -m pytest -q`
- **Test baseline is 130 passing.** It must never drop.
- Frontend: `cd web/frontend && npm run build`; lint `npx eslint src`. **Lint baseline is 0 errors — do not add any.**
- Calibrated defaults, from measurements in the spec: `decay=0.6`, `threshold=0.05`, `edge_floor=0.30`, `max_hops=3`. Do not change these without re-running the calibration.
- Output is **associative, not causal**. Only 37 of 247 edges are Granger-directed. Docstrings and UI copy must not imply causation or forecasting.
- Backend runs without `--reload`; restart it to pick up Python changes.

---

### Task 1: Pure propagation core

**Files:**
- Create: `src/eurodata/graph/propagate.py`
- Test: `tests/test_graph_propagate.py`

**Interfaces:**
- Consumes: nothing (pure module, no project imports).
- Produces:
  - `Activation` frozen dataclass with fields `node: str`, `hop: int`, `activation: float`, `path: tuple[str, ...]`, `directed: bool`, and property `via: str`.
  - `propagate(edges, source, *, shock=1.0, max_hops=3, decay=0.6, threshold=0.05, edge_floor=0.30, collapse_variants=True) -> list[Activation]`
  - `is_variant(a: str, b: str) -> bool`
  - `Edge = tuple[str, str, float, str]` — `(node_a, node_b, weight, direction)` where direction is one of `"a_leads_b"`, `"b_leads_a"`, `"undetermined"`, `"contemporaneous"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_graph_propagate.py`:

```python
"""The propagation core, exercised on hand-built micro-graphs.

No database: propagate() is a pure function of its edge list, which is what
makes every algorithmic property below directly assertable.
"""
import pytest

from eurodata.graph.propagate import Activation, is_variant, propagate

# A -> B -> C, all strong and positive.
CHAIN = [
    ("A", "B", 0.8, "undetermined"),
    ("B", "C", 0.8, "undetermined"),
]


def acts(result):
    """{node: activation} for terse assertions."""
    return {a.node: round(a.activation, 6) for a in result}


def test_activation_decays_with_each_hop():
    out = propagate(CHAIN, "A", shock=1.0, decay=0.5, threshold=0.0, edge_floor=0.0)
    # hop 1: 1.0 * 0.8 * 0.5 ; hop 2: 0.4 * 0.8 * 0.5
    assert acts(out) == {"B": 0.4, "C": 0.16}
    assert {a.node: a.hop for a in out} == {"B": 1, "C": 2}


def test_source_is_never_in_the_result():
    out = propagate(CHAIN, "A", edge_floor=0.0, threshold=0.0)
    assert "A" not in {a.node for a in out}


def test_negative_edge_flips_the_sign_and_two_negatives_restore_it():
    edges = [
        ("A", "B", -0.8, "undetermined"),
        ("B", "C", -0.8, "undetermined"),
    ]
    out = acts(propagate(edges, "A", decay=0.5, threshold=0.0, edge_floor=0.0))
    assert out["B"] < 0          # a positive shock depresses B
    assert out["C"] > 0          # ...which in turn lifts C


def test_threshold_prunes_weak_arrivals():
    out = propagate(CHAIN, "A", decay=0.5, threshold=0.3, edge_floor=0.0)
    # B arrives at 0.4 (kept); C would arrive at 0.16 (pruned)
    assert {a.node for a in out} == {"B"}


def test_edge_floor_removes_weak_edges_entirely():
    edges = [("A", "B", 0.9, "undetermined"), ("A", "C", 0.1, "undetermined")]
    out = propagate(edges, "A", threshold=0.0, edge_floor=0.3)
    assert {a.node for a in out} == {"B"}


def test_max_hops_bounds_the_walk():
    edges = CHAIN + [("C", "D", 0.8, "undetermined")]
    out = propagate(edges, "A", max_hops=2, decay=0.5, threshold=0.0, edge_floor=0.0)
    assert {a.node for a in out} == {"B", "C"}


def test_strongest_path_wins_over_a_weaker_shorter_one():
    # A->C directly is weak; A->B->C is strong enough to beat it.
    edges = [
        ("A", "C", 0.10, "undetermined"),
        ("A", "B", 0.90, "undetermined"),
        ("B", "C", 0.90, "undetermined"),
    ]
    out = {a.node: a for a in propagate(edges, "A", decay=1.0, threshold=0.0,
                                        edge_floor=0.0)}
    assert out["C"].activation == pytest.approx(0.81)
    assert out["C"].hop == 2
    assert out["C"].path == ("A", "B", "C")


def test_weaker_indirect_route_does_not_overwrite_a_strong_direct_one():
    edges = [
        ("A", "C", 0.90, "undetermined"),
        ("A", "B", 0.50, "undetermined"),
        ("B", "C", 0.50, "undetermined"),
    ]
    out = {a.node: a for a in propagate(edges, "A", decay=1.0, threshold=0.0,
                                        edge_floor=0.0)}
    assert out["C"].activation == pytest.approx(0.90)
    assert out["C"].hop == 1


def test_cycles_terminate():
    edges = [
        ("A", "B", 0.9, "undetermined"),
        ("B", "C", 0.9, "undetermined"),
        ("C", "A", 0.9, "undetermined"),
    ]
    out = propagate(edges, "A", max_hops=5, decay=0.9, threshold=0.01,
                    edge_floor=0.0)
    assert {a.node for a in out} == {"B", "C"}      # returns, does not hang


def test_a_leads_b_is_not_traversed_backwards():
    edges = [("A", "B", 0.9, "a_leads_b")]
    assert {a.node for a in propagate(edges, "A", threshold=0.0, edge_floor=0.0)} == {"B"}
    assert propagate(edges, "B", threshold=0.0, edge_floor=0.0) == []


def test_b_leads_a_traverses_only_b_to_a():
    edges = [("A", "B", 0.9, "b_leads_a")]
    assert {a.node for a in propagate(edges, "B", threshold=0.0, edge_floor=0.0)} == {"A"}
    assert propagate(edges, "A", threshold=0.0, edge_floor=0.0) == []


def test_directed_is_true_only_when_every_edge_on_the_path_is_directed():
    edges = [("A", "B", 0.9, "a_leads_b"), ("B", "C", 0.9, "undetermined")]
    out = {a.node: a for a in propagate(edges, "A", decay=1.0, threshold=0.0,
                                        edge_floor=0.0)}
    assert out["B"].directed is True
    assert out["C"].directed is False


def test_via_names_the_intermediate_nodes():
    out = {a.node: a for a in propagate(CHAIN, "A", decay=1.0, threshold=0.0,
                                        edge_floor=0.0)}
    assert out["B"].via == ""
    assert out["C"].via == "B"


def test_is_variant_matches_same_series_at_different_precision():
    assert is_variant("GDP", "GDP per capita")
    assert is_variant("Inflation (HICP)", "Inflation (HICP, monthly)")
    assert not is_variant("GDP", "Unemployment Rate")


def test_variants_are_dropped_from_edges_and_from_results():
    # The direct GDP -> GDP per capita edge is a tautology, and GDP per capita
    # must not sneak back in via a longer route either.
    edges = [
        ("GDP", "GDP per capita", 0.99, "undetermined"),
        ("GDP", "Unemployment Rate", 0.60, "undetermined"),
        ("Unemployment Rate", "GDP per capita", 0.60, "undetermined"),
    ]
    out = {a.node for a in propagate(edges, "GDP", decay=1.0, threshold=0.0,
                                     edge_floor=0.0)}
    assert out == {"Unemployment Rate"}


def test_results_are_sorted_by_hop_then_descending_magnitude():
    edges = [
        ("A", "B", 0.5, "undetermined"),
        ("A", "C", 0.9, "undetermined"),
        ("C", "D", 0.9, "undetermined"),
    ]
    out = propagate(edges, "A", decay=1.0, threshold=0.0, edge_floor=0.0)
    assert [a.node for a in out] == ["C", "B", "D"]


def test_empty_edges_yield_no_activations():
    assert propagate([], "A") == []


def test_unknown_source_yields_no_activations():
    assert propagate(CHAIN, "Z") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/toto/eurodata && PYTHONPATH=src .venv/bin/python -m pytest tests/test_graph_propagate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'eurodata.graph.propagate'`

- [ ] **Step 3: Write the implementation**

Create `src/eurodata/graph/propagate.py`:

```python
"""Spreading activation over an indicator correlation graph.

Given a shock to one node, walk the signed edges outward and report which other
nodes historically moved with it, in which direction, and through what chain.

This is association, not causation. Most edges in this graph carry no confirmed
direction (see `eurodata.graph.correlate`), so an activation says "these moved
together historically", never "this causes that". `Activation.directed` marks
the minority of results whose entire path is Granger-confirmed.

Two properties of the real graph drive the design (measurements in
docs/superpowers/specs/2026-07-23-propagation-engine-design.md):

1. It is dense -- median degree 14 across 36 connected indicators. Summing
   arrivals saturates: a shock reaches 30 of 36 nodes and the ranking becomes
   meaningless. So a node's activation is the single *strongest* signed path
   reaching it, which is bounded and explains itself via `path`.
2. Because it is dense, a direct edge almost always beats a two-hop product, so
   without `edge_floor` nearly every result lands on hop 1 and there is no
   cascade to speak of. The floor is what creates multi-hop structure.

This module is deliberately free of database and pandas imports: it is a pure
function of its edge list, so every property above is testable directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# (node_a, node_b, weight, direction)
Edge = tuple[str, str, float, str]

_PARENTHETICAL = re.compile(r"\s*\(.*?\)")


@dataclass(frozen=True)
class Activation:
    """One node reached by a shock, and the route it arrived by."""

    node: str
    hop: int
    activation: float
    path: tuple[str, ...]
    directed: bool

    @property
    def via(self) -> str:
        """The intermediate nodes, for display: 'Gov Debt → R&D'. Empty for a
        direct arrival."""
        return " → ".join(self.path[1:-1])


def _stem(name: str) -> str:
    return _PARENTHETICAL.sub("", name).strip().lower()


def is_variant(a: str, b: str) -> bool:
    """True when two indicator names denote the same underlying series at a
    different frequency or normalization -- "GDP" / "GDP per capita",
    "Inflation (HICP)" / "Inflation (HICP, monthly)".

    Their ~1.0 correlation is a tautology rather than a finding, and left in
    place it consumes the whole first hop of every ripple.
    """
    x, y = _stem(a), _stem(b)
    return x == y or x.startswith(y) or y.startswith(x)


def _adjacency(edges: list[Edge], *, edge_floor: float
               ) -> dict[str, list[tuple[str, float, bool]]]:
    """Directed arcs keyed by source node: {src: [(dst, weight, directed)]}.

    A Granger-confirmed edge yields one arc; an undetermined one yields both,
    because co-movement without a confirmed lead/lag is symmetric.
    """
    adj: dict[str, list[tuple[str, float, bool]]] = {}
    for a, b, weight, direction in edges:
        if abs(weight) < edge_floor:
            continue
        if direction == "a_leads_b":
            arcs = [(a, b, True)]
        elif direction == "b_leads_a":
            arcs = [(b, a, True)]
        else:
            arcs = [(a, b, False), (b, a, False)]
        for src, dst, is_directed in arcs:
            adj.setdefault(src, []).append((dst, weight, is_directed))
    return adj


def propagate(edges: list[Edge], source: str, *, shock: float = 1.0,
              max_hops: int = 3, decay: float = 0.6, threshold: float = 0.05,
              edge_floor: float = 0.30, collapse_variants: bool = True
              ) -> list[Activation]:
    """Propagate `shock` outward from `source` and return what it reaches.

    Each hop multiplies by the edge weight and by `decay`. An arrival is kept
    only if it beats the node's current best magnitude, which is also what makes
    cycles terminate -- no visited set is needed. A node's `hop` is the hop at
    which its strongest arrival was found, so a node can move to a later hop if a
    stronger route turns up (its downstream is not re-expanded; with `max_hops`
    in single digits the difference is immaterial and the reported path always
    matches the reported activation).

    Returns activations sorted by hop, then by descending magnitude. The source
    itself is never included.
    """
    pairs = list(edges)
    if collapse_variants:
        pairs = [e for e in pairs if not is_variant(e[0], e[1])]
    adj = _adjacency(pairs, edge_floor=edge_floor)

    best: dict[str, Activation] = {
        source: Activation(source, 0, float(shock), (source,), True)
    }
    frontier = [source]
    for hop in range(1, max_hops + 1):
        nxt: list[str] = []
        for node in frontier:
            current = best[node]
            for dst, weight, is_directed in adj.get(node, ()):
                candidate = current.activation * weight * decay
                if abs(candidate) < threshold:
                    continue
                previous = best.get(dst)
                if previous is not None and abs(previous.activation) >= abs(candidate):
                    continue
                best[dst] = Activation(
                    node=dst,
                    hop=hop,
                    activation=candidate,
                    path=current.path + (dst,),
                    directed=current.directed and is_directed,
                )
                nxt.append(dst)
        frontier = nxt
        if not frontier:
            break

    out = [a for name, a in best.items() if name != source]
    if collapse_variants:
        # A variant can be reached indirectly even once its direct edge is gone;
        # a ripple reporting the source affecting itself is noise.
        out = [a for a in out if not is_variant(a.node, source)]
    return sorted(out, key=lambda a: (a.hop, -abs(a.activation)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/toto/eurodata && PYTHONPATH=src .venv/bin/python -m pytest tests/test_graph_propagate.py -q`
Expected: PASS, 18 passed

- [ ] **Step 5: Mutation-check the two load-bearing tests**

The strongest-path rule and cycle termination are the properties everything else rests on. Confirm their tests actually fail when the behaviour breaks.

```bash
cd /Users/toto/eurodata
cp src/eurodata/graph/propagate.py /tmp/prop_backup.py

# Mutation A: keep the FIRST arrival instead of the strongest
.venv/bin/python - <<'PY'
import pathlib
p = pathlib.Path("src/eurodata/graph/propagate.py"); s = p.read_text()
s = s.replace("if previous is not None and abs(previous.activation) >= abs(candidate):",
              "if previous is not None:")
p.write_text(s)
PY
PYTHONPATH=src .venv/bin/python -m pytest tests/test_graph_propagate.py -q -k "strongest_path_wins"
cp /tmp/prop_backup.py src/eurodata/graph/propagate.py

# Mutation B: remove the magnitude guard entirely (cycles no longer settle)
.venv/bin/python - <<'PY'
import pathlib
p = pathlib.Path("src/eurodata/graph/propagate.py"); s = p.read_text()
s = s.replace("                if previous is not None and abs(previous.activation) >= abs(candidate):\n                    continue\n", "")
p.write_text(s)
PY
PYTHONPATH=src .venv/bin/python -m pytest tests/test_graph_propagate.py -q -k "cycles_terminate or weaker_indirect"
cp /tmp/prop_backup.py src/eurodata/graph/propagate.py
rm /tmp/prop_backup.py
PYTHONPATH=src .venv/bin/python -m pytest tests/test_graph_propagate.py -q
```

Expected: mutation A fails `test_strongest_path_wins_over_a_weaker_shorter_one`; mutation B fails at least one of the two named tests; the final restored run is 18 passed. If a mutation does **not** fail its test, the test is vacuous — strengthen it before continuing.

- [ ] **Step 6: Commit**

```bash
cd /Users/toto/eurodata
git add src/eurodata/graph/propagate.py tests/test_graph_propagate.py
git commit -m "feat(graph): spreading-activation propagation core

Strongest-path rather than summed arrivals: the correlation graph has
median degree 14, so accumulation saturates at 30 of 36 nodes. Keeping
only the strongest signed path bounds the result and gives each node an
explaining path. The only-improve rule is also what terminates cycles.

edge_floor exists because density means a direct edge almost always beats
a two-hop product; without it nearly every result lands on hop 1 and
there is no cascade.

Pure module, no DB or pandas import, so the algorithm is testable
directly."
```

---

### Task 2: `EuroData.propagate()` — adapt the graph to the core

**Files:**
- Modify: `src/eurodata/api.py` (add method near `country_correlations`, ~line 835; add `_delegate` line and `__all__` entry at the end of the file)
- Modify: `src/eurodata/__init__.py` (re-export)
- Test: `tests/test_api.py` (append)

**Interfaces:**
- Consumes: `propagate`, `Activation` from Task 1; existing `self.correlation_graph()` → columns `indicator_a, indicator_b, domain_a, domain_b, weight, relationship, direction, q_value, n_countries`; existing `self.country_correlations(country, limit=None)` → columns `indicator_a, indicator_b, domain_a, domain_b, correlation, n_years, p_value, relationship, q_value` (**note: `correlation`, not `weight`, and no `direction` column**).
- Produces: `EuroData.propagate(node, *, country=None, shock=1.0, max_hops=3, decay=0.6, threshold=0.05, edge_floor=0.30) -> pd.DataFrame` with columns `node, hop, activation, via, path, directed`; module-level `eurodata.propagate`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api.py`:

```python
# --- propagation ------------------------------------------------------------

def _seed_edges(db, rows):
    """Insert CORRELATES_WITH edges directly, so propagation can be tested
    without running the full graph builder.

    graph_node.id is an INTEGER PRIMARY KEY with no sequence default, so ids
    must be assigned explicitly — the same thing scripts/build_graph.py does
    with its counter. correlation_graph() parses props as JSON and reads
    relationship/direction/q_value/n_countries, so all four must be present.
    """
    def node_id(name):
        ind_id = db.con.execute(
            "SELECT id FROM indicator WHERE name = ?", [name]).fetchone()[0]
        existing = db.con.execute(
            "SELECT id FROM graph_node WHERE node_type='indicator' AND ref_id = ?",
            [ind_id]).fetchone()
        if existing:
            return existing[0]
        nid = db.con.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM graph_node").fetchone()[0]
        db.con.execute(
            "INSERT INTO graph_node (id, node_type, ref_id, label) "
            "VALUES (?, 'indicator', ?, ?)", [nid, ind_id, name])
        return nid

    for a, b, weight, direction in rows:
        props = ('{"direction": "%s", "q_value": 0.01, '
                 '"relationship": "contemporaneous", "n_countries": 5}' % direction)
        db.con.execute(
            "INSERT INTO graph_edge (src_node_id, dst_node_id, edge_type, weight, props) "
            "VALUES (?, ?, 'CORRELATES_WITH', ?, ?)",
            [node_id(a), node_id(b), weight, props])


def test_propagate_ripples_across_indicators(db):
    _seed_edges(db, [
        ("Unemployment Rate", "Government Debt (% GDP)", 0.6, "undetermined"),
        ("Government Debt (% GDP)", "R&D Expenditure (% GDP)", -0.6, "undetermined"),
    ])
    out = db.propagate("Unemployment Rate", edge_floor=0.3, threshold=0.05)
    rows = {r["node"]: r for _, r in out.iterrows()}
    assert set(rows) == {"Government Debt (% GDP)", "R&D Expenditure (% GDP)"}
    assert rows["Government Debt (% GDP)"]["hop"] == 1
    assert rows["Government Debt (% GDP)"]["activation"] > 0
    # positive shock -> debt up -> R&D down, two hops out
    assert rows["R&D Expenditure (% GDP)"]["hop"] == 2
    assert rows["R&D Expenditure (% GDP)"]["activation"] < 0
    assert rows["R&D Expenditure (% GDP)"]["via"] == "Government Debt (% GDP)"
    assert list(out.columns) == ["node", "hop", "activation", "via", "path", "directed"]


def test_propagate_rejects_an_unknown_node(db):
    with pytest.raises(EuroDataLookupError):
        db.propagate("Unemploymnet Rate")


def test_propagate_returns_empty_frame_when_the_graph_is_unbuilt(db):
    out = db.propagate("GDP")
    assert out.empty
    assert list(out.columns) == ["node", "hop", "activation", "via", "path", "directed"]


def test_propagate_accepts_an_indicator_api_code(db):
    _seed_edges(db, [("Unemployment Rate", "Government Debt (% GDP)", 0.6,
                      "undetermined")])
    # une_rt_a is Unemployment Rate's api_code; _resolve_indicator accepts either
    out = db.propagate("une_rt_a", edge_floor=0.3)
    assert "Government Debt (% GDP)" in set(out["node"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/toto/eurodata && PYTHONPATH=src .venv/bin/python -m pytest tests/test_api.py -q -k propagate`
Expected: FAIL — `AttributeError: 'EuroData' object has no attribute 'propagate'`

- [ ] **Step 3: Write the implementation**

In `src/eurodata/api.py`, add this import near the other `eurodata.graph` imports at the top of the file:

```python
from eurodata.graph.propagate import propagate as _propagate_core
```

Add the method immediately after `country_correlations`:

```python
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
```

At the end of `api.py`, next to the other delegates, add:

```python
propagate = _delegate("propagate")
```

and add `"propagate"` to the `__all__` list.

In `src/eurodata/__init__.py`, add `propagate` to the names imported from `eurodata.api`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/toto/eurodata && PYTHONPATH=src .venv/bin/python -m pytest tests/test_api.py -q`
Expected: PASS — previously 39, now 43 passed

- [ ] **Step 5: Sanity-check against the real graph**

```bash
cd /Users/toto/eurodata && PYTHONPATH=src .venv/bin/python -c "
import eurodata as ed
d = ed.open()
out = d.propagate('Unemployment Rate')
print(out.to_string(index=False))
print()
print('nodes reached:', len(out), '| hops:', sorted(out[\"hop\"].unique()))
"
```

Expected: roughly 9–14 rows spread over hops 1 and 2 (the spec's calibration target). If it returns 25+ rows or everything sits on hop 1, `edge_floor` is not being applied — stop and fix before continuing.

- [ ] **Step 6: Commit**

```bash
cd /Users/toto/eurodata
git add src/eurodata/api.py src/eurodata/__init__.py tests/test_api.py
git commit -m "feat(api): EuroData.propagate over the correlation graph

Adapts either the pooled correlation_graph() or per-country
country_correlations() into the core's edge list. The two differ:
country_correlations names its weight column 'correlation' and has no
direction column at all, since a per-country correlation is plain
co-movement -- those edges are fed in as undetermined."
```

---

### Task 3: `GET /api/propagate`

**Files:**
- Modify: `web/backend/main.py` (add endpoint after the `country_correlations` endpoint, ~line 253)
- Test: `tests/test_web_endpoints.py` (append)

**Interfaces:**
- Consumes: `EuroData.propagate(...)` from Task 2; existing `_query(method, **kwargs)` helper and `df_records(df)` in `main.py`.
- Produces: `GET /api/propagate?node=&country=&shock=&max_hops=&decay=&threshold=&edge_floor=` → `{"rows": [{node, hop, activation, via, path, directed}]}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_endpoints.py`:

```python
def test_propagate_endpoint_returns_rows(client):
    r = client.get("/api/propagate", params={"node": "GDP"})
    assert r.status_code == 200
    assert "rows" in r.json()


def test_propagate_endpoint_404s_on_an_unknown_node(client):
    r = client.get("/api/propagate", params={"node": "Not An Indicator"})
    assert r.status_code == 404


def test_propagate_endpoint_passes_through_tuning_parameters(client):
    r = client.get("/api/propagate", params={
        "node": "GDP", "shock": 2.0, "max_hops": 1, "edge_floor": 0.9})
    assert r.status_code == 200
    for row in r.json()["rows"]:
        assert row["hop"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/toto/eurodata && PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_web_endpoints.py -q -k propagate`
Expected: FAIL — 404 from FastAPI because the route does not exist (the first test asserts 200)

- [ ] **Step 3: Write the implementation**

In `web/backend/main.py`, after the `country_correlations` endpoint:

```python
@app.get("/api/propagate")
def propagate(node: str, country: str | None = None, shock: float = 1.0,
              max_hops: int = 3, decay: float = 0.6, threshold: float = 0.05,
              edge_floor: float = 0.30) -> dict:
    """Ripple of a shock to `node` across the correlation graph.

    Associative, not causal: `directed` is True only where every edge on the
    path carries a Granger-confirmed direction.
    """
    df = _query("propagate", node=node, country=country, shock=shock,
                max_hops=max_hops, decay=decay, threshold=threshold,
                edge_floor=edge_floor)
    return {"rows": df_records(df)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/toto/eurodata && PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_web_endpoints.py -q`
Expected: PASS (3 new tests added to the file's existing count)

- [ ] **Step 5: Verify against the live backend**

```bash
cd /Users/toto/eurodata
pkill -f "uvicorn web.backend.main:app"; sleep 2
source .venv/bin/activate && PYTHONPATH=src:. nohup uvicorn web.backend.main:app --port 8000 >/tmp/uv.log 2>&1 &
sleep 8
curl -s "localhost:8000/api/propagate?node=Unemployment%20Rate" | .venv/bin/python -m json.tool | head -30
curl -s -o /dev/null -w "unknown node -> %{http_code}\n" "localhost:8000/api/propagate?node=Nope"
```

Expected: a rows array with `node`/`hop`/`activation`/`via`; unknown node → 404.

- [ ] **Step 6: Commit**

```bash
cd /Users/toto/eurodata
git add web/backend/main.py tests/test_web_endpoints.py
git commit -m "feat(web): GET /api/propagate"
```

---

### Task 4: `/propagate` page with the hop cascade

**Files:**
- Create: `web/frontend/src/app/propagate/page.tsx`
- Create: `web/frontend/src/app/propagate/layout.tsx`
- Create: `web/frontend/src/components/propagation-cascade.tsx`
- Modify: `web/frontend/src/components/navbar.tsx` (add to `LINKS`)
- Modify: `web/frontend/src/lib/api.ts` (add `PropagationRow` type)

**Interfaces:**
- Consumes: `GET /api/propagate` from Task 3; `GET /api/indicators` and `GET /api/countries` (existing); `api<T>(path)` from `@/lib/api`.
- Produces: a `/propagate` route; `PropagationRow` type exported from `@/lib/api`.

- [ ] **Step 1: Add the row type**

In `web/frontend/src/lib/api.ts`, next to the other row types:

```ts
export type PropagationRow = {
  node: string;
  hop: number;
  activation: number;
  via: string;
  path: string;
  directed: boolean;
};
```

- [ ] **Step 2: Write the cascade component**

Create `web/frontend/src/components/propagation-cascade.tsx`:

```tsx
"use client";

import type { PropagationRow } from "@/lib/api";

// One column per hop, so the ripple reads left to right as a chain of
// consequences. A force-directed view of this graph (median degree 14) would
// render as a hairball; columns stay legible and work on a phone.
export function PropagationCascade({
  rows,
  source,
}: {
  rows: PropagationRow[];
  source: string;
}) {
  if (!rows.length) return null;
  const hops = [...new Set(rows.map((r) => r.hop))].sort((a, b) => a - b);
  const peak = Math.max(...rows.map((r) => Math.abs(r.activation)));

  return (
    <div className="mt-6 overflow-x-auto">
      <div className="flex min-w-max gap-4">
        <div className="w-48 shrink-0">
          <div className="text-xs font-medium text-black/40 dark:text-white/40">
            SHOCK
          </div>
          <div className="mt-2 rounded-lg border border-black/15 px-3 py-2 text-sm font-medium dark:border-white/15">
            {source}
          </div>
        </div>
        {hops.map((hop) => (
          <div key={hop} className="w-56 shrink-0">
            <div className="text-xs font-medium text-black/40 dark:text-white/40">
              HOP {hop}
            </div>
            <ul className="mt-2 space-y-1.5">
              {rows
                .filter((r) => r.hop === hop)
                .map((r) => (
                  <li
                    key={r.node}
                    title={r.via ? `via ${r.via}` : "direct"}
                    className="rounded-lg border border-black/10 px-2.5 py-1.5 dark:border-white/10"
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-xs">{r.node}</span>
                      <span
                        className={`shrink-0 text-xs tabular-nums ${
                          r.activation >= 0
                            ? "text-emerald-700 dark:text-emerald-400"
                            : "text-orange-700 dark:text-orange-400"
                        }`}
                      >
                        {r.activation >= 0 ? "+" : ""}
                        {r.activation.toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-1 h-1 rounded-full bg-black/5 dark:bg-white/10">
                      <div
                        className={`h-1 rounded-full ${
                          r.activation >= 0 ? "bg-emerald-600" : "bg-orange-600"
                        }`}
                        style={{
                          width: `${(Math.abs(r.activation) / peak) * 100}%`,
                        }}
                      />
                    </div>
                    {/* Granger-confirmed paths are the minority; mark them
                        rather than letting every arrival look equally causal. */}
                    {r.directed ? (
                      <div className="mt-1 text-[10px] text-black/40 dark:text-white/40">
                        directed
                      </div>
                    ) : null}
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write the page and its metadata**

Create `web/frontend/src/app/propagate/layout.tsx`:

```tsx
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Propagate",
  description:
    "Trace how a shock to one European indicator ripples through the others, along the correlation graph.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
```

Create `web/frontend/src/app/propagate/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";

import { PropagationCascade } from "@/components/propagation-cascade";
import { api, type PropagationRow, type Row } from "@/lib/api";

export default function Propagate() {
  const [indicators, setIndicators] = useState<Row[]>([]);
  const [node, setNode] = useState("Unemployment Rate");
  const [hops, setHops] = useState(3);
  const [floor, setFloor] = useState(0.3);
  const [rows, setRows] = useState<PropagationRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ rows: Row[] }>("/api/indicators")
      .then((r) => setIndicators(r.rows))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!node) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-change: loading/error reset before the async load below
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      node,
      max_hops: String(hops),
      edge_floor: String(floor),
    });
    api<{ rows: PropagationRow[] }>(`/api/propagate?${params}`)
      .then((r) => {
        if (!cancelled) setRows(r.rows);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [node, hops, floor]);

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Propagate</h1>
      <p className="mt-1 max-w-prose text-sm text-black/60 dark:text-white/60">
        Shock one indicator and follow where it leads. Each hop multiplies by the
        correlation between two indicators, so a negative edge flips the sign.
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-3 text-sm">
        <select
          value={node}
          onChange={(e) => setNode(e.target.value)}
          className="rounded-lg border border-black/15 px-3 py-1.5 dark:border-white/15 dark:bg-black"
        >
          {indicators.map((i) => (
            <option key={String(i.name)} value={String(i.name)}>
              {String(i.name)}
            </option>
          ))}
        </select>
        <label className="inline-flex items-center gap-2">
          Hops
          <input
            type="range"
            min={1}
            max={4}
            value={hops}
            onChange={(e) => setHops(Number(e.target.value))}
          />
          <span className="tabular-nums">{hops}</span>
        </label>
        <label className="inline-flex items-center gap-2">
          Min edge
          <input
            type="range"
            min={0}
            max={0.6}
            step={0.05}
            value={floor}
            onChange={(e) => setFloor(Number(e.target.value))}
          />
          <span className="tabular-nums">{floor.toFixed(2)}</span>
        </label>
      </div>

      <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-800 dark:text-amber-200">
        These are indicators that moved together historically, not a forecast and
        not a causal claim. Most edges in the graph carry no confirmed direction;
        the few whose whole path is direction-confirmed are marked
        &ldquo;directed&rdquo;.
      </div>

      {error ? (
        <div className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          {error}
        </div>
      ) : loading ? (
        <p className="mt-6 text-sm text-black/50 dark:text-white/50">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="mt-6 max-w-prose text-sm text-black/50 dark:text-white/50">
          Nothing cleared the threshold. Lower the minimum edge weight, or pick an
          indicator with more correlations — a weakly connected one has no ripple
          to show.
        </p>
      ) : (
        <PropagationCascade rows={rows} source={node} />
      )}
    </main>
  );
}
```

- [ ] **Step 4: Add the nav link**

In `web/frontend/src/components/navbar.tsx`, add to the `LINKS` array after the `/correlations` entry:

```tsx
  { href: "/propagate", label: "Propagate" },
```

- [ ] **Step 5: Build and lint**

```bash
cd /Users/toto/eurodata/web/frontend
npx eslint src
npm run build
```

Expected: eslint reports **0 errors**; build succeeds and lists `/propagate` among the routes.

- [ ] **Step 6: Drive it in a browser**

With the backend on :8000 and `npm run dev` on :3000:

```bash
cd /private/tmp/claude-501/-Users-toto/08e077a0-8d7d-4d09-9fd0-20f8f396946f/scratchpad
cat > propagate-check.mjs <<'EOF'
import { chromium } from "playwright";
const b = await chromium.launch();
const errs = [];
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
p.on("pageerror", (e) => errs.push(e.message));
p.on("console", (c) => { if (c.type() === "error") errs.push(c.text()); });
await p.goto("http://localhost:3000/propagate", { waitUntil: "networkidle" });
await p.waitForTimeout(2500);
console.log("hop columns:", await p.locator("text=/^HOP \\d+$/").count());
console.log("nodes shown:", await p.locator("main li").count());
await p.screenshot({ path: "propagate-desktop.png", fullPage: true });
const m = await b.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
await m.goto("http://localhost:3000/propagate", { waitUntil: "networkidle" });
await m.waitForTimeout(2500);
const o = await m.evaluate(() => ({ s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth }));
console.log("mobile:", o.s > o.c + 1 ? `OVERFLOW ${o.s}>${o.c}` : "no overflow");
await m.screenshot({ path: "propagate-mobile.png" });
console.log("errors:", errs.length ? errs.join(" | ") : "none");
await b.close();
EOF
node propagate-check.mjs
```

Expected: at least 2 hop columns, 5–15 nodes, **no mobile overflow**, no console errors. The cascade itself scrolls horizontally inside its own container — that is intended and must not make the page body scroll.

- [ ] **Step 7: Commit**

```bash
cd /Users/toto/eurodata
git add web/frontend/src/app/propagate web/frontend/src/components/propagation-cascade.tsx \
        web/frontend/src/components/navbar.tsx web/frontend/src/lib/api.ts
git commit -m "feat(web): /propagate page with the hop cascade

Columns per hop rather than a node-link diagram: at median degree 14 a
force-directed view is a hairball. The cascade scrolls inside its own
container so the page body never scrolls sideways on a phone.

Carries a permanent caveat that this is historical co-movement, and marks
the minority of results whose whole path is direction-confirmed."
```

---

### Task 5: Documentation and final verification

**Files:**
- Modify: `HANDOFF.md` (prepend an update block)
- Modify: `PITCH.md` (add the feature to the page table, ~line 151)

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: no code.

- [ ] **Step 1: Record the feature in PITCH.md**

Add a row to the pages table:

```markdown
| `/propagate` | Shock an indicator and trace the ripple across the correlation graph, hop by hop, with the path each result arrived by |
```

- [ ] **Step 2: Prepend the HANDOFF update**

```markdown
> **Update (2026-07-23, propagation engine).** `/propagate` ships: shock one
> indicator, follow signed activation along the `CORRELATES_WITH` edges, read
> the result as a cascade of hops. Core is `src/eurodata/graph/propagate.py`
> (pure, no DB), surfaced via `ed.propagate()`, `GET /api/propagate`, and the
> page. Spec and its calibration measurements:
> `docs/superpowers/specs/2026-07-23-propagation-engine-design.md`.
>
> Two graph properties shaped it and are worth remembering before tuning:
> summing arrivals saturates (a shock reaches 30 of 36 indicators), hence
> strongest-path; and without `edge_floor` almost everything lands on hop 1,
> because at median degree 14 a direct edge beats a two-hop product. Defaults
> `decay=0.6 threshold=0.05 edge_floor=0.30 max_hops=3` yield ~9-14 nodes over
> two hops and should be re-calibrated if the graph is rebuilt over materially
> different data.
```

- [ ] **Step 3: Run the full suite and frontend checks**

```bash
cd /Users/toto/eurodata
PYTHONPATH=src .venv/bin/python -m pytest -q
cd web/frontend && npx eslint src && npm run build
```

Expected: **≥ 155 passing** (130 baseline + 18 core + 4 api + 3 endpoint), eslint 0 errors, build clean with `/propagate` listed.

- [ ] **Step 4: Commit and open the PR**

```bash
cd /Users/toto/eurodata
git add HANDOFF.md PITCH.md
git commit -m "docs: record the propagation engine"
git push -u origin feat/propagation-engine
gh pr create --base main --head feat/propagation-engine \
  --title "Propagation engine: trace a shock across the correlation graph" \
  --body "Implements docs/superpowers/specs/2026-07-23-propagation-engine-design.md. See the spec for the two measurements that shaped the algorithm: accumulation saturates at 30 of 36 nodes, and without an edge floor 22 of 24 results land on hop 1."
```

---

## Self-Review

**Spec coverage.** Core algorithm → Task 1. Variant collapsing and direction handling → Task 1 (they are properties of the core's edge preparation, not separable deliverables). Pooled/per-country adapter → Task 2. Endpoint and its 404 path → Task 3. Cascade page, caveat copy, empty state → Task 4. Docs → Task 5.

**Deliberately deferred, and why.** `spill_to_neighbours` over `BORDERS` edges is specced but not planned: it needs a country-level activation model that the indicator-level core does not yet imply, and the cascade has no place to show a second entity type. It should be its own spec once the ranking behaviour has been judged in use. The spec's "out of scope" list (chat tool, force-directed rendering) is respected.

**Type consistency.** `Activation(node, hop, activation, path, directed)` and its `via` property are defined in Task 1 and consumed unchanged in Task 2. The DataFrame columns `node, hop, activation, via, path, directed` are fixed in Task 2 and matched exactly by `PropagationRow` in Task 4. `Edge` is `(str, str, float, str)` throughout. The `weight` / `correlation` column difference between the two edge sources is handled explicitly in Task 2 and called out in its Interfaces block.

**Placeholders.** None: every code step carries complete code, every command its expected output.
