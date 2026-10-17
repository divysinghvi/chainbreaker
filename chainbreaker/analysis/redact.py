"""Pseudonymize CNCF repo + workflow names in a crawl snapshot (PLAN 8.8). Public action ids stay visible."""
import copy
import hashlib

from .. import config


def pseudo(name: str) -> str:
    return "repo-" + hashlib.sha1((config.REDACTION_SALT + name).encode()).hexdigest()[:6]


def redact_crawl(crawl: dict) -> dict:
    c = copy.deepcopy(crawl)
    repos = {r["id"] for r in c["repos"]}
    rmap = {rid: pseudo(rid) for rid in repos}
    idmap: dict[str, str] = {}

    for r in c["repos"]:
        r["id"], r["redacted"] = rmap[r["id"]], True
    for w in c["workflows"]:
        rid = w["repo_id"]
        if rid not in rmap:  # a public reusable workflow in a repo we did not crawl: like an action, stays visible
            continue
        base = w["path"].rsplit("/", 1)[-1]
        new = f"{rmap[rid]}:{base}" if not w.get("at_ref") else f"{rmap[rid]}:{w['path']}@{w['at_ref']}"
        idmap[w["id"]] = new
        w.update(id=new, repo_id=rmap[rid], name=base)
    local_actions = set()
    for ar in c["action_refs"]:
        if not ar["local"]:
            continue
        owner_repo = "/".join(ar["action_id"].split("/")[:2])
        if owner_repo in rmap:
            new_aid = rmap[owner_repo] + ar["action_id"][len(owner_repo):]
            local_actions.add(ar["action_id"])
            new = new_aid + ar["id"][len(ar["action_id"]):]
            idmap[ar["id"]] = new
            ar.update(id=new, action_id=new_aid)
    for a in c["actions"]:
        if a["id"] in local_actions:
            owner_repo = f"{a['owner']}/{a['repo']}"
            new = rmap[owner_repo] + a["id"][len(owner_repo):]
            a.update(id=new, owner=rmap[owner_repo], repo="", search=new.replace("/", " "))
    for e in c["edges"]:
        if e["dst"] in idmap and not e["uses"].startswith("./"):
            owner_repo = "/".join(e["uses"].split("/")[:2]).lower()
            if owner_repo in rmap:
                e["uses"] = rmap[owner_repo] + e["uses"][len(owner_repo):]
        e["src"], e["dst"] = idmap.get(e["src"], e["src"]), idmap.get(e["dst"], e["dst"])
        e["file_repo"] = rmap.get(e["file_repo"], e["file_repo"])
    c["redacted"] = True
    return c
