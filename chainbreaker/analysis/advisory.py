"""Simulated compromises (Advisory nodes) and relinking after rebuilds (PLAN 8.4)."""
import datetime as dt
import json

from .. import config, db, queries as Q


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def known_good_sha(ds: str, action_id: str) -> str:
    if ds != "demo" or not config.GROUND_TRUTH.exists():
        return ""
    gt = json.loads(config.GROUND_TRUTH.read_text())
    return gt.get("known_good_sha", "") if action_id == gt.get("advisory_action", "").lower() else ""


def _next_id(ds: str) -> str:
    nums = [int(r["id"].rsplit("-", 1)[1]) for r in db.q(ds, Q.ADV_IDS) if r["id"].rsplit("-", 1)[1].isdigit()]
    return f"CB-ADV-{max(nums, default=0) + 1}"


def simulate_compromise(ds: str, action_id: str, refs: list[str] | None = None, new: bool = False) -> dict | None:
    """-> advisory dict, or None when the action is not in the graph."""
    aid = action_id.strip().lower()
    if not db.q1(ds, Q.ACTION_EXISTS, {"aid": aid}, ro=True):
        return None
    refs = sorted(refs or [])
    adv_id = None
    if not new:
        for r in db.q(ds, Q.ADV_FIND, {"aid": aid}, ro=True):
            if sorted(r["refs"] or []) == refs:
                adv_id = r["id"]
                break
    if adv_id is None:
        adv_id = _next_id(ds)
        summary = f"Simulated compromise of {aid} ({', '.join(refs) if refs else 'all mutable refs'})"
        db.q(ds, Q.ADV_CREATE, {"id": adv_id, "aid": aid, "refs": refs, "sha": known_good_sha(ds, aid),
                                "now": _now(), "summary": summary})
        db.q(ds, Q.ADV_LINK, {"adv": adv_id})
    return get(ds, adv_id)


def get(ds: str, adv_id: str) -> dict | None:
    a = db.q1(ds, Q.ADV_GET, {"adv": adv_id}, ro=True)
    if a:
        a["compromised_refs"] = [r["id"] for r in db.q(ds, Q.ADV_COMPROMISED, {"adv": adv_id}, ro=True)]
    return a


def relink(ds: str) -> int:
    """Re-point every advisory at its action's *current* mutable refs. Returns #advisories."""
    db.run(ds, Q.ADV_UNLINK_ALL)
    ids = [r["id"] for r in db.q(ds, Q.ADV_IDS)]
    for adv in ids:
        db.q(ds, Q.ADV_LINK, {"adv": adv})
    return len(ids)
