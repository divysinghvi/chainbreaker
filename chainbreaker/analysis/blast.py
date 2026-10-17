"""Blast radius, hidden depth, pinned-but-exposed, path evidence, viz subgraph (PLAN 8.4, CP5)."""
from collections import Counter, defaultdict, deque

from .. import config, db, queries as Q
from . import advisory

SEV_ORDER = {"HIGH": 0, "MED": 1, "LOW": 2}
VIZ_CAP = 600


def _ms_since(t0: float) -> float:
    return round(db.get_stats()["graph_ms"] - t0, 2)


def blast(ds: str, adv_id: str, max_depth: int | None = None) -> dict:
    t0 = db.get_stats()["graph_ms"]
    d = config.clamp_depth(max_depth)
    rows = db.q(ds, Q.depth(Q.BLAST, d), {"adv": adv_id}, ro=True)
    pinned = {r["workflow"] for r in db.q(ds, Q.depth(Q.PINNED, d), {"adv": adv_id}, ro=True)}
    exposed = sorted(({"workflow": r["workflow"], "repo": r["repo"], "severity": r["severity"], "depth": r["depth"],
                       "reasons": r["reasons"] or [], "pinned_but_exposed": r["workflow"] in pinned} for r in rows),
                     key=lambda x: (SEV_ORDER.get(x["severity"], 3), -x["depth"], x["workflow"]))
    by_depth = Counter(x["depth"] for x in exposed)
    by_sev = Counter(x["severity"] for x in exposed)
    return {"advisory_id": adv_id, "max_depth": d, "exposed": exposed, "exposed_total": len(exposed),
            "by_depth": {str(k): by_depth[k] for k in sorted(by_depth)},
            "by_severity": {s: by_sev.get(s, 0) for s in ("HIGH", "MED", "LOW")},
            "depth1": by_depth.get(1, 0), "hidden": sum(v for k, v in by_depth.items() if k >= 2),
            "high_total": by_sev.get("HIGH", 0), "pinned_but_exposed": sorted(pinned),
            "graph_ms": _ms_since(t0)}


def _hops(nodes: list, edges: list) -> list[dict]:
    hops = []
    for i, e in enumerate(edges):
        p = e.properties
        dst = nodes[i + 1].properties
        hops.append({"from": nodes[i].properties["id"], "to": dst["id"], "uses": p.get("uses"),
                     "kind": p.get("kind"), "file_repo": p.get("file_repo"), "file_path": p.get("file_path"),
                     "lines": p.get("lines") or [], "pinned": bool(dst.get("pinned")),
                     "src_immutable": bool(p.get("src_immutable"))})
    return hops


def explain(ds: str, adv_id: str, workflow_id: str, max_depth: int | None = None) -> dict | None:
    """Shortest exposing path, hop by hop. None when the workflow is not exposed."""
    t0 = db.get_stats()["graph_ms"]
    params = {"adv": adv_id, "wid": workflow_id}
    engine = "algo.SPpaths"
    try:
        res = db.run(ds, Q.depth(Q.PATH, max_depth), params, ro=True)
    except Exception:  # noqa: BLE001 - procedure missing / signature drift: plain var-length shortest
        engine = "var-length fallback"
        res = db.run(ds, Q.depth(Q.PATH_FALLBACK, max_depth), params, ro=True)
    if not res.result_set:
        return None
    path = res.result_set[0][0]
    hops = _hops(path.nodes(), path.edges())
    return {"workflow": workflow_id, "depth": len(hops), "hops": hops, "engine": engine, "graph_ms": _ms_since(t0)}


def _short(n: dict, label: str) -> str:
    nid = n["id"]
    if label == "Workflow":
        repo, _, path = nid.partition(":")
        base = path.rsplit("/", 1)[-1]
        name = repo.rsplit("/", 1)[-1]
        return f"{name}/{base}" if n.get("at_ref") else name
    if label == "ActionRef":
        aid, _, ref = nid.rpartition("@")
        ref = ref[:7] if len(ref) == 40 else ref
        return f"{aid.split('/', 1)[-1]}@{ref}"
    return nid.replace("docker://", "")


def viz_subgraph(ds: str, adv_id: str, max_depth: int | None = None) -> dict:
    t0 = db.get_stats()["graph_ms"]
    adv = advisory.get(ds, adv_id)
    if adv is None:
        return {"nodes": [], "links": [], "total_nodes": 0, "graph_ms": 0}
    d = config.clamp_depth(max_depth)
    links = db.q(ds, Q.depth(Q.VIZ_EDGES, d), {"aid": adv["action_id"]}, ro=True)
    ids = {x for e in links for x in (e["src"], e["dst"])}
    nodes: dict[str, dict] = {}
    for label in sorted(Q.USES_LABELS):
        for row in db.q(ds, Q.NODES_BY_ID.format(label=label), {"ids": sorted(ids)}, ro=True):
            p = row["n"].properties
            nodes[p["id"]] = {"id": p["id"], "label": label, "short": _short(p, label), "kind": p.get("kind"),
                              "pinned": bool(p.get("pinned")), "entry": bool(p.get("entry")),
                              "at_ref": p.get("at_ref"), "severity": p.get("severity"), "repo": p.get("repo_id")}
    bad = set(adv["compromised_refs"])
    b = blast(ds, adv_id, d)
    exp = {x["workflow"]: x for x in b["exposed"]}
    # nodes with a path to a compromised ref (within these links) are "on an exposed path"
    rev = defaultdict(list)
    for e in links:
        rev[e["dst"]].append(e["src"])
    reach, dq = set(bad), deque(bad)
    while dq:
        for s in rev[dq.popleft()]:
            if s not in reach:
                reach.add(s)
                dq.append(s)
    for nid, n in nodes.items():
        n["compromised"] = nid in bad
        n["exposed"] = nid in exp if (n["label"] == "Workflow" and not n["at_ref"]) else (nid in reach and nid not in bad)
        n["depth"] = exp[nid]["depth"] if nid in exp else None
        n["pinned_but_exposed"] = bool(exp.get(nid, {}).get("pinned_but_exposed"))
    total = len(nodes)
    if total > VIZ_CAP:  # keep the exposure story first
        keep = sorted(nodes, key=lambda i: (not nodes[i]["compromised"], i not in reach, i))[:VIZ_CAP]
        nodes = {i: nodes[i] for i in keep}
    out_links = [{"source": e["src"], "target": e["dst"], "kind": e["kind"], "uses": e["uses"],
                  "file_path": e["file_path"], "lines": e["lines"] or []}
                 for e in links if e["src"] in nodes and e["dst"] in nodes]
    return {"advisory_id": adv_id, "action_id": adv["action_id"], "max_depth": d, "nodes": list(nodes.values()),
            "links": out_links, "total_nodes": total, "compromised": sorted(bad),
            "summary": {k: b[k] for k in ("exposed_total", "depth1", "hidden", "high_total", "by_severity")},
            "graph_ms": _ms_since(t0)}
