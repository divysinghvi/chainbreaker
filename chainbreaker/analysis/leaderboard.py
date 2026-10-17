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
