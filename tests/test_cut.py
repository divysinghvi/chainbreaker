"""Residual-cut extraction (from given flows) and the networkx fallback agree on synthetic graphs."""
import networkx as nx
import pytest

from chainbreaker.analysis.fix import disconnects, nx_cut, residual_cut


def _edges(spec):
    return [{"eid": i, "sid": s, "did": d, "cap": c} for i, (s, d, c) in enumerate(spec)]


def _flows(edges, sources, sinks):
    """Max flow via networkx, mapped back to per-edge flows (no parallel edges in these specs)."""
    g = nx.DiGraph()
    for e in edges:
        g.add_edge(e["sid"], e["did"], capacity=e["cap"])
    for s in sources:
        g.add_edge("S", s, capacity=10 ** 6)
    for t in sinks:
        g.add_edge(t, "T", capacity=10 ** 6)
    value, fd = nx.maximum_flow(g, "S", "T")
    return {e["eid"]: fd[e["sid"]][e["did"]] for e in edges}, value


CASES = {
    # the demo topology: web/docs direct, a shared composite, a pinned-but-exposed SHA chain
    "demo": ([("web", "bad", 1), ("docs", "bad", 1), ("analytics", "lint", 3), ("mobile", "lintL1", 1),
              ("lintL1", "bad", 10000), ("lint", "bad", 1), ("ci", "lint", 3), ("app1", "ci", 3), ("app2", "ci", 3),
              ("infra", "shared", 3), ("shared", "ci", 3)],
             {"web", "docs", "analytics", "mobile", "app1", "app2", "infra"}, {"bad"}, 4),
    # parallel chokepoint: two cheap parallel edges beat one expensive bottleneck upstream
    "parallel": ([("s1", "x", 3), ("s2", "x", 3), ("x", "m1", 1), ("x", "m2", 1), ("m1", "t", 3), ("m2", "t", 3)],
                 {"s1", "s2"}, {"t"}, 2),
    "two_sinks": ([("a", "t1", 1), ("a", "b", 3), ("b", "t2", 1), ("c", "b", 1)], {"a", "c"}, {"t1", "t2"}, 2),
}


@pytest.mark.parametrize("name", CASES)
def test_residual_cut_matches_networkx(name):
    spec, sources, sinks, expected = CASES[name]
    edges = _edges(spec)
    flows, value = _flows(edges, sources, sinks)
    cut = residual_cut(edges, flows, sources)
    nxc, nx_value = nx_cut(edges, sources, sinks)
    assert sum(e["cap"] for e in cut) == value == nx_value == expected
    assert disconnects(edges, cut, sources, sinks)
    assert disconnects(edges, nxc, sources, sinks)


def test_demo_cut_edges():
    spec, sources, sinks, _ = CASES["demo"]
    edges = _edges(spec)
    cut, _ = nx_cut(edges, sources, sinks)
    assert {(e["sid"], e["did"]) for e in cut} == {("web", "bad"), ("docs", "bad"), ("lint", "bad"),
                                                   ("mobile", "lintL1")}
