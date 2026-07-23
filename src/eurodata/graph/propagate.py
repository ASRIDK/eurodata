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
