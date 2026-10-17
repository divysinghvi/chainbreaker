"""crawl.json -> FalkorDB graph cb:<dataset>."""
import json
from collections import defaultdict

from .. import config, db, queries as Q
from ..analysis import advisory

BATCH = 1000


def ensure_indexes(ds: str) -> None:
    for stmt in Q.INDEXES + [Q.FT_INDEX]:
        try:
            db.run(ds, stmt)
        except Exception as e:  # noqa: BLE001 - "already indexed" is the expected repeat-run error
            if "already" not in str(e).lower():
                raise


def _clean(row: dict) -> dict:
    """FalkorDB props must be primitives or lists of primitives; drop nulls."""
    return {k: v for k, v in row.items() if v is not None}


def _batches(rows: list, n: int = BATCH):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def load(ds: str, crawl: dict) -> dict:
    ensure_indexes(ds)
    for label in Q.CRAWL_LABELS:  # never Advisory / FixPlan / Fix / FixPR / Finding
        db.run(ds, Q.DELETE_LABEL.format(label=label))
    nodes = {"Repo": crawl["repos"], "Workflow": crawl["workflows"], "Action": crawl["actions"],
             "ActionRef": crawl["action_refs"], "DockerImage": crawl["docker_images"]}
    for label, rows in nodes.items():
        for chunk in _batches([_clean(r) for r in rows]):
            db.run(ds, Q.LOAD_NODES.format(label=label), {"rows": chunk})
    db.run(ds, Q.META_CREATE,
           {"ds": crawl["dataset"], "at": crawl["crawled_at"], "orgs": crawl["orgs"],
            "stats": json.dumps(crawl.get("stats", {})), "redacted": bool(crawl.get("redacted"))})

    repo_ids = {r["id"] for r in crawl["repos"]}
    hw = [{"src": w["repo_id"], "dst": w["id"]} for w in crawl["workflows"]
          if not w.get("at_ref") and w["repo_id"] in repo_ids]
    for chunk in _batches(hw):
        db.run(ds, Q.LOAD_HAS_WORKFLOW, {"rows": chunk})
    action_ids = {a["id"] for a in crawl["actions"]}
    vo = [{"src": r["id"], "dst": r["action_id"]} for r in crawl["action_refs"] if r["action_id"] in action_ids]
    for chunk in _batches(vo):
        db.run(ds, Q.LOAD_VERSION_OF, {"rows": chunk})

    by_pair: dict[tuple[str, str], list] = defaultdict(list)
    for e in crawl["edges"]:
        props = {k: e[k] for k in ("kind", "file_repo", "file_path", "lines", "uses", "src_immutable")} | {"weight": 1}
        by_pair[(e["src_label"], e["dst_label"])].append({"src": e["src"], "dst": e["dst"], "props": props})
    for (sl, dl), rows in by_pair.items():
        assert sl in Q.USES_LABELS and dl in Q.USES_LABELS
        for chunk in _batches(rows):
            db.run(ds, Q.LOAD_USES.format(src=sl, dst=dl), {"rows": chunk})

    relinked = advisory.relink(ds)
    return {"advisories_relinked": relinked}


def load_file(ds: str, path=None) -> dict:
    path = path or config.CACHE / ds / "crawl.json"
    return load(ds, json.loads(open(path).read()))
