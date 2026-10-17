"""Min-cut fix planner (FalkorDB algo.maxFlow + networkx fallback) and GRAPH.COPY what-if (PLAN 8.5, 8.6)."""
import atexit
import datetime as dt
import secrets
import time
from collections import defaultdict, deque

import networkx as nx

from .. import config, db, queries as Q
from . import advisory
from .blast import blast

ENGINE_FDB = "falkordb.algo.maxFlow"
ENGINE_NX = "networkx (fallback)"
SUPER = 10 ** 6
_mine: set[str] = set()


# ---------- scratch graphs ----------
def copy_graph(ds: str) -> tuple[str, float]:
    name = f"{db.gname(ds)}:scratch:{secrets.token_hex(4)}"
    t = time.perf_counter()
    for attempt in range(12):  # GRAPH.COPY forks; Redis allows one fork at a time (a background save may hold it)
        try:
            db.graph(ds).copy(name)
            break
        except Exception as e:  # noqa: BLE001
            if "could not fork" not in str(e) or attempt == 11:
                raise
            time.sleep(0.25 * (attempt + 1))
    _mine.add(name)
    return name, round((time.perf_counter() - t) * 1000, 2)


def drop_graph(name: str) -> None:
    if ":scratch:" not in name:
        raise ValueError(f"refusing to delete non-scratch graph {name}")
    try:
        db.get_db().select_graph(name).delete()
    finally:
        _mine.discard(name)


@atexit.register
def _sweep() -> None:  # only this process's leftovers: another process may be mid-plan
    for name in list(_mine):
        try:
            drop_graph(name)
        except Exception:  # noqa: BLE001
            pass


# ---------- pure min-cut helpers (unit-tested in tests/test_cut.py) ----------
def parse_maxflow(row: dict) -> tuple[dict[int, float], float]:
    """algo.maxFlow on FalkorDB 4.22 yields one row: nodes, edges (Edge objects with flow),
    edgeFlows (floats aligned with edges) and maxFlow (float). Map flow by edge id."""
    return {e.id: float(f) for e, f in zip(row["edges"] or [], row["edgeFlows"] or [])}, float(row["maxFlow"] or 0)


def residual_cut(edges: list[dict], flows: dict[int, float], sources: set[int]) -> list[dict]:
    fwd, bwd = defaultdict(list), defaultdict(list)
    for e in edges:
        fwd[e["sid"]].append(e)
        bwd[e["did"]].append(e)
    seen, dq = set(sources), deque(sources)
    while dq:
        n = dq.popleft()
        for e in fwd[n]:
            if flows.get(e["eid"], 0) < e["cap"] - 1e-9 and e["did"] not in seen:
                seen.add(e["did"])
                dq.append(e["did"])
        for e in bwd[n]:
            if flows.get(e["eid"], 0) > 1e-9 and e["sid"] not in seen:
                seen.add(e["sid"])
                dq.append(e["sid"])
    return [e for e in edges if e["sid"] in seen and e["did"] not in seen]


def nx_cut(edges: list[dict], sources: set[int], sinks: set[int]) -> tuple[list[dict], float]:
    g = nx.DiGraph()
    for e in edges:
        u, v = e["sid"], e["did"]
        if g.has_edge(u, v):
            g[u][v]["capacity"] += e["cap"]
        else:
            g.add_edge(u, v, capacity=e["cap"])
    for s in sources:
        g.add_edge("S", s, capacity=SUPER)
    for t in sinks:
        g.add_edge(t, "T", capacity=SUPER)
    value, (reach, _) = nx.minimum_cut(g, "S", "T")
    return [e for e in edges if e["sid"] in reach and e["did"] not in reach], float(value)


def disconnects(edges: list[dict], cut: list[dict], sources: set[int], sinks: set[int]) -> bool:
    removed = {e["eid"] for e in cut}
    fwd = defaultdict(list)
    for e in edges:
        if e["eid"] not in removed:
            fwd[e["sid"]].append(e["did"])
    seen, dq = set(sources), deque(sources)
    while dq:
        for d in fwd[dq.popleft()]:
            if d not in seen:
                seen.add(d)
                dq.append(d)
    return not (seen & sinks)


def reach_counts(edges: list[dict], cut: list[dict], sources: set[int], sinks: set[int]) -> dict[int, int]:
    """protects: #sources with at least one source->sink path through each cut edge."""
    fwd, rev = defaultdict(list), defaultdict(list)
    for e in edges:
        fwd[e["sid"]].append(e["did"])
        rev[e["did"]].append(e["sid"])

    def bfs(start: set[int], adj) -> set[int]:
        seen, dq = set(start), deque(start)
        while dq:
            for x in adj[dq.popleft()]:
                if x not in seen:
                    seen.add(x)
                    dq.append(x)
        return seen

    to_sink = bfs(sinks, rev)
    reach = {s: bfs({s}, fwd) for s in sources}
    return {e["eid"]: sum(1 for s in sources if e["sid"] in reach[s] and e["did"] in to_sink) for e in cut}


# ---------- planner ----------
def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _next_plan_id(ds: str) -> str:
    nums = [int(r["id"].rsplit("-", 1)[1]) for r in db.q(ds, Q.PLAN_IDS) if r["id"].rsplit("-", 1)[1].isdigit()]
    return f"CB-PLAN-{max(nums, default=0) + 1}"


def _fix_type(e: dict, bad: set[int]) -> str:
    if e["cap"] >= 10000:
        return "IMMUTABLE"
    if e["cap"] == 1:
        return "PIN" if e["did"] in bad else "REPIN"
    return "VENDOR"


def plan_fix(ds: str, adv_id: str, targets: str = "all") -> dict | None:
    t0 = db.get_stats()["graph_ms"]
    adv = advisory.get(ds, adv_id)
    if adv is None:
        return None
    b = blast(ds, adv_id, config.MAX_DEPTH)
    sources = sorted(x["workflow"] for x in b["exposed"] if targets == "all" or x["severity"] == "HIGH")
    scratch, copy_ms = copy_graph(ds)
    try:
        db.run(scratch, Q.CAP_1)
        db.run(scratch, Q.CAP_2, {"adv": adv_id})
        edges, page = [], 5000
        while True:
            rows = db.q(scratch, Q.EDGES_EXPORT.replace("{SKIP}", str(len(edges))).replace("{LIMIT}", str(page)), ro=True)
            edges += rows
            if len(rows) < page:
                break
        key_of = {}
        for e in edges:
            key_of[e["sid"]], key_of[e["did"]] = e["s_key"], e["d_key"]
        src_ids = {r["nid"] for r in db.q(scratch, Q.SOURCE_NIDS, {"ids": sources}, ro=True)}
        bad = {r["nid"] for r in db.q(scratch, Q.SINK_NIDS, {"adv": adv_id}, ro=True)}
        cut, engine, max_flow, note = [], ENGINE_FDB, 0.0, ""
        if src_ids and bad:
            if config.FIX_ENGINE in ("auto", "falkordb"):
                try:
                    row = db.q1(scratch, Q.MAXFLOW, {"sources": sources, "adv": adv_id}, ro=True)
                    flows, max_flow = parse_maxflow(row)
                    cut = residual_cut(edges, flows, src_ids)
                    ok = abs(sum(e["cap"] for e in cut) - max_flow) < 1e-6 and disconnects(edges, cut, src_ids, bad)
                    if not ok:
                        note = f"algo.maxFlow cut failed validation (maxFlow={max_flow}, cut={sum(e['cap'] for e in cut)})"
                except Exception as ex:  # noqa: BLE001 - procedure missing / output drift
                    ok, note = False, f"algo.maxFlow unavailable: {ex}"
            else:
                ok, note = False, "FIX_ENGINE=networkx"
            if not ok:
                engine = ENGINE_NX
                cut, max_flow = nx_cut(edges, src_ids, bad)
        protects = reach_counts(edges, cut, src_ids, bad)
    finally:
        drop_graph(scratch)

    plan_id = _next_plan_id(ds)
    sha = adv.get("known_good_sha") or ""
    fixes = []
    for i, e in enumerate(sorted(cut, key=lambda e: (-protects[e["eid"]], e["s_key"])), 1):
        typ = _fix_type(e, bad)
        old = e["uses"] or ""
        if typ == "PIN":
            new, phase = (old.rsplit("@", 1)[0] + "@" + sha, 1) if sha else (old.rsplit("@", 1)[0] + "@<VERIFIED-SHA>", 0)
        elif typ == "REPIN":
            new, phase = "", 2
        else:
            new, phase = "", 0
        fixes.append({"id": f"{plan_id}-F{i}", "plan_id": plan_id, "type": typ, "src_id": e["s_key"],
                      "src_label": e["s_label"], "dst_id": e["d_key"], "dst_label": e["d_label"],
                      "file_repo": e["file_repo"] or "", "file_path": e["file_path"] or "", "lines": e["lines"] or [],
                      "old_uses": old, "new_uses": new, "protects": protects[e["eid"]], "phase": phase,
                      "cap": int(e["cap"])})
    rec = {"id": plan_id, "advisory_id": adv_id, "action_id": adv["action_id"], "targets": targets,
           "cut_size": len(fixes), "cut_cost": int(sum(f["cap"] for f in fixes)), "protected": len(sources),
           "naive": len(sources), "engine": engine, "engine_note": note, "max_flow": max_flow, "sources": sources,
           "copy_ms": copy_ms, "created_at": _now()}
    db.q(ds, Q.PLAN_CREATE, {"adv": adv_id, "id": plan_id, "targets": targets, "cut_size": rec["cut_size"],
                             "protected": rec["protected"], "naive": rec["naive"], "engine": engine,
                             "now": rec["created_at"], "sources": sources, "max_flow": max_flow, "fixes": fixes})
    return rec | {"fixes": fixes, "graph_ms": round(db.get_stats()["graph_ms"] - t0, 2)}


def get_plan(ds: str, plan_id: str) -> dict | None:
    row = db.q1(ds, Q.PLAN_GET, {"pid": plan_id}, ro=True)
    if row is None:
        return None
    p = row["p"].properties
    p["fixes"] = [r["f"].properties for r in db.q(ds, Q.PLAN_FIXES, {"pid": plan_id}, ro=True)]
    p["prs"] = [r["pr"].properties | {"fix_id": r["fix_id"]} for r in db.q(ds, Q.PLAN_PRS, {"pid": plan_id}, ro=True)]
    return p


def simulate_fix(ds: str, plan_id: str) -> dict | None:
    t0 = db.get_stats()["graph_ms"]
    plan = get_plan(ds, plan_id)
    if plan is None:
        return None
    adv_id, sources = plan["advisory_id"], set(plan.get("sources") or [])
    before = blast(ds, adv_id, config.MAX_DEPTH)
    scratch, copy_ms = copy_graph(ds)
    try:
        for f in plan["fixes"]:
            assert f["src_label"] in Q.USES_LABELS and f["dst_label"] in Q.USES_LABELS
            db.run(scratch, Q.DELETE_EDGE.format(sl=f["src_label"], dl=f["dst_label"]),
                   {"s": f["src_id"], "d": f["dst_id"]})
        after = blast(scratch, adv_id, config.MAX_DEPTH)
    finally:
        drop_graph(scratch)
    hit = lambda b: sum(1 for x in b["exposed"] if x["workflow"] in sources)  # noqa: E731
    return {"plan_id": plan_id, "before": hit(before), "after": hit(after), "before_total": before["exposed_total"],
            "after_total": after["exposed_total"], "removed_edges": len(plan["fixes"]), "copy_ms": copy_ms,
            "graph_ms": round(db.get_stats()["graph_ms"] - t0, 2)}
