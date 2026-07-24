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


def test_results_that_are_variants_of_each_other_are_collapsed():
    # Reaching both "GDP" and "GDP per capita" reports one finding as two. The
    # source-relative filter does not catch this: neither is a variant of the
    # shocked node.
    edges = [
        ("Unemployment Rate", "GDP", 0.9, "undetermined"),
        ("Unemployment Rate", "GDP per capita", 0.8, "undetermined"),
        ("Unemployment Rate", "Renewable Energy Share %", 0.7, "undetermined"),
    ]
    out = propagate(edges, "Unemployment Rate", decay=1.0, threshold=0.0,
                    edge_floor=0.0)
    nodes = [a.node for a in out]
    assert nodes == ["GDP", "Renewable Energy Share %"]   # strongest of the pair kept


def test_variant_collapsing_can_be_switched_off():
    edges = [
        ("Unemployment Rate", "GDP", 0.9, "undetermined"),
        ("Unemployment Rate", "GDP per capita", 0.8, "undetermined"),
    ]
    out = propagate(edges, "Unemployment Rate", decay=1.0, threshold=0.0,
                    edge_floor=0.0, collapse_variants=False)
    assert {a.node for a in out} == {"GDP", "GDP per capita"}
