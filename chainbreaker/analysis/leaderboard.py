"""Dataset stats and the load-bearing-actions leaderboard."""
from .. import db, queries as Q


def stats(ds: str) -> dict:
    counts = {lbl: db.q1(ds, Q.COUNT_LABEL.format(label=lbl), ro=True)["c"]
              for lbl in ["Repo", "Workflow", "Action", "ActionRef", "DockerImage", "Advisory", "FixPlan", "Finding"]}
    wc = db.q1(ds, Q.WORKFLOW_COUNTS, ro=True) or {}
    share = db.q1(ds, Q.REF_PIN_SHARE, ro=True) or {}
    refs, pinned = int(share.get("refs") or 0), int(share.get("pinned") or 0)
    meta = db.q1(ds, Q.META, ro=True) or {}
    return {"dataset": ds, "counts": counts, "uses_edges": db.q1(ds, Q.COUNT_USES, ro=True)["c"],
            "workflows_head": int(wc.get("head") or 0), "workflows_entry": int(wc.get("entry") or 0),
            "workflows_at_ref": int(wc.get("at_ref") or 0),
            "external_refs": refs, "external_refs_pinned": pinned,
            "mutable_ref_pct": round(100 * (refs - pinned) / refs, 1) if refs else 0.0,
            "crawled_at": meta.get("crawled_at"), "orgs": meta.get("orgs") or []}


_cache: dict[tuple[str, str], dict] = {}


def _reach(ds: str, aid: str) -> dict:
    r = db.q1(ds, Q.depth(Q.REACH, None), {"aid": aid}, ro=True) or {}
    return {"reach": int(r.get("reach") or 0), "mutable_reach": int(r.get("mutable_reach") or 0)}


def leaderboard(ds: str, top_k: int = 15) -> dict:
    """PageRank over USES (aggregated per Action) + direct users, transitive reach and mutable reach."""
    t0 = db.get_stats()["graph_ms"]
    key = (ds, (db.q1(ds, Q.META, ro=True) or {}).get("crawled_at") or "")
    if key not in _cache:
        rows = []
        for r in db.q(ds, Q.PAGERANK, ro=True):
            aid = r["action"]
            direct = int((db.q1(ds, Q.DIRECT, {"aid": aid}, ro=True) or {}).get("direct") or 0)
            rr = _reach(ds, aid)
            rows.append({"action": aid, "pagerank": round(r["pagerank"], 5), "direct": direct, **rr,
                         "hidden_reach": max(0, rr["reach"] - direct),
                         "mutable_pct": round(100 * rr["mutable_reach"] / rr["reach"], 1) if rr["reach"] else 0.0})
        try:
            bridges = [{"id": r["id"], "score": r["score"]} for r in db.q(ds, Q.BETWEENNESS, ro=True)]
        except Exception:  # noqa: BLE001 - optional
            bridges = []
        _cache[key] = {"rows": rows, "bridges": bridges}
    c = _cache[key]
    return {"dataset": ds, "rows": c["rows"][:top_k], "bridges": c["bridges"],
            "graph_ms": round(db.get_stats()["graph_ms"] - t0, 2)}


def top_by_reach(ds: str, n: int = 20) -> list[dict]:
    """Candidates from PageRank, direct users and composite fan-in; ranked by transitive reach in FalkorDB."""
    cands = {r["action"] for r in db.q(ds, Q.PAGERANK, ro=True)}
    cands |= {r["action"] for r in db.q(ds, Q.DIRECT_ALL, ro=True)}
    cands |= {r["action"] for r in db.q(ds, Q.COMPOSITE_REACH, ro=True)}
    rows = [{"action": a, **_reach(ds, a)} for a in sorted(cands)]
    return sorted(rows, key=lambda r: (-r["reach"], r["action"]))[:n]
