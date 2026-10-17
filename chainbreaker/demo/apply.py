"""Act on a fix plan in the demo org: open PRs, merge, move tags, REPIN, rescan (PLAN 8.7). Admin only."""
from .. import config, db, queries as Q
from ..analysis import advisory
from ..analysis.blast import blast, explain
from ..analysis.fix import get_plan
from ..github import rest
from ..ingest.crawl import crawl
from ..ingest.load import load

DS = "demo"


def edit_lines(text: str, lines: list[int], old: str, new: str) -> str:
    """Replace `old` with `new` on the recorded lines only; add `# <old ref>` when the line has no comment."""
    rows = text.splitlines(keepends=True)
    targets = [n - 1 for n in lines if 0 < n <= len(rows) and old in rows[n - 1]]
    if not targets:  # the file moved since the crawl: fall back to every line that carries the exact value
        targets = [i for i, r in enumerate(rows) if old in r and "uses:" in r]
    if not targets:
        raise ValueError(f"`{old}` not found")
    old_ref = old.rsplit("@", 1)[1]
    for i in targets:
        body = rows[i].rstrip("\r\n")
        eol = rows[i][len(body):]
        body = body.replace(old, new)
        if "#" not in body:
            body += f" # {old_ref}"
        rows[i] = body + eol
    return "".join(rows)


def _example_path(plan: dict, f: dict) -> str:
    for wid in plan.get("sources") or []:
        p = explain(DS, plan["advisory_id"], wid)
        if p and any(h["from"] == f["src_id"] and h["to"] == f["dst_id"] for h in p["hops"]):
            return "\n".join(f"{i}. `{h['from']}` → `{h['to']}` ({h['file_repo']}:{h['file_path']}:"
                             f"{','.join(map(str, h['lines']))})" for i, h in enumerate(p["hops"], 1))
    return "(path not found)"


def _body(plan: dict, f: dict, action_id: str) -> str:
    return (f"**ChainBreaker fix · {plan['advisory_id']}**\n\n"
            f"`{f['old_uses']}` → `{f['new_uses']}` in `{f['file_path']}` (line {', '.join(map(str, f['lines']))})\n\n"
            f"Why: this line is one of the {plan['cut_size']} changes in the minimum cut computed by {plan['engine']}. "
            f"Together they disconnect {plan['protected']} pipelines from the compromised `{action_id}` refs "
            f"(a naive fix would touch {plan['naive']} pipelines).\n\n"
            f"This line protects {f['protects']} pipeline(s), e.g.\n{_example_path(plan, f)}\n\n"
            f"Type: {f['type']} · Opened by ChainBreaker (demo lab, synthetic repos).\n")


def _open(plan: dict, f: dict, n: int, action_id: str, log) -> dict:
    owner, repo = f["file_repo"].split("/", 1)
    rest._guard(owner)
    base = rest.get_repo(owner, repo)["default_branch"]
    text, sha = rest.get_file(owner, repo, f["file_path"], ref=base)
    new_text = edit_lines(text, f["lines"], f["old_uses"], f["new_uses"])
    branch = f"chainbreaker/{plan['id']}-{n}"
    if rest.get_ref(owner, repo, "heads", branch) is None:
        rest.create_ref(owner, repo, f"refs/heads/{branch}", rest.get_ref(owner, repo, "heads", base))
    rest.put_file(owner, repo, f["file_path"], new_text, f"chainbreaker: {f['type']} {f['old_uses']} -> {f['new_uses']}",
                  branch=branch, sha=sha)
    pr = rest.open_pr(owner, repo, f"ChainBreaker {f['type']}: {f['old_uses'].split('/', 1)[1]} → "
                      f"{f['new_uses'].rsplit('@', 1)[1][:12]}", branch, base, _body(plan, f, action_id))
    rec = {"id": f"{plan['id']}-PR{n}", "url": pr["url"], "number": pr["number"], "repo": f["file_repo"],
           "phase": f["phase"], "status": "open", "fix_id": f["id"], "branch": branch}
    db.q(DS, Q.FIXPR_CREATE, {k: rec[k] for k in ("id", "url", "number", "repo", "phase", "status")} | {"fix": f["id"]})
    log(f"  opened {pr['url']}  ({f['type']} {f['file_repo']}:{f['file_path']})")
    return rec


def _merge(pr: dict, log) -> str:
    owner, repo = pr["repo"].split("/", 1)
    sha = rest.merge_pr(owner, repo, pr["number"])
    db.q(DS, Q.FIXPR_STATUS, {"id": pr["id"], "status": "merged", "sha": sha})
    rest.delete_branch(owner, repo, f"chainbreaker/{pr['id'].rsplit('-PR', 1)[0]}-{pr['id'].rsplit('-PR', 1)[1]}")
    log(f"  merged {pr['url']} -> {sha[:12]}")
    return sha


def open_phase1(plan_id: str, log=print) -> list[dict]:
    plan = get_plan(DS, plan_id)
    if plan is None:
        raise ValueError(f"unknown plan {plan_id}")
    action_id = advisory.get(DS, plan["advisory_id"])["action_id"]
    done = {p["fix_id"] for p in plan["prs"]}
    out = []
    for n, f in enumerate(plan["fixes"], 1):
        if f["phase"] == 1 and f["id"] not in done:
            out.append(_open(plan, f, n, action_id, log))
    return out


def merge_and_continue(plan_id: str, log=print) -> dict:
    plan = get_plan(DS, plan_id)
    if plan is None:
        raise ValueError(f"unknown plan {plan_id}")
    fixes = {f["id"]: f for f in plan["fixes"]}
    phase1 = [p for p in plan["prs"] if p["phase"] == 1]
    if not phase1:
        raise ValueError("open the phase-1 PRs first")
    fixed_sha: dict[str, str] = {}
    log("phase 1: merge PINs, move tags")
    for pr in phase1:
        f = fixes[pr["fix_id"]]
        sha = pr.get("merge_sha") if pr["status"] == "merged" else _merge(pr, log)
        if f["src_label"] == "ActionRef":
            aid, ref = f["src_id"].rsplit("@", 1)
            owner, repo = f["file_repo"].split("/", 1)
            if rest.get_ref(owner, repo, "tags", ref):
                rest.move_tag(owner, repo, ref, sha)
                log(f"  moved tag {repo}@{ref} -> {sha[:12]}")
            fixed_sha[aid] = sha
    log("phase 2: REPIN pins to the fixed commits")
    action_id = advisory.get(DS, plan["advisory_id"])["action_id"]
    done = {p["fix_id"] for p in plan["prs"]}
    for n, f in enumerate(plan["fixes"], 1):
        if f["phase"] != 2 or f["id"] in done:
            continue
        dst_aid = f["dst_id"].rsplit("@", 1)[0]
        owner, repo = dst_aid.split("/")[:2]
        new_sha = fixed_sha.get(dst_aid) or rest.get_ref(owner, repo, "heads", rest.get_repo(owner, repo)["default_branch"])
        f["new_uses"] = f["old_uses"].rsplit("@", 1)[0] + "@" + new_sha
        db.q(DS, Q.FIX_SET_NEW, {"fix": f["id"], "new_uses": f["new_uses"]})
        _merge(_open(plan, f, n, action_id, log), log)
    log("rescan")
    return rescan(log)


def rescan(log=print) -> dict:
    out = crawl(DS, [config.DEMO_ORG], 100, no_cache=True)
    load(DS, out)
    res = {}
    for r in db.q(DS, Q.ADV_IDS, ro=True):
        b = blast(DS, r["id"])
        res[r["id"]] = {k: b[k] for k in ("exposed_total", "depth1", "hidden", "high_total")}
        log(f"  {r['id']}: exposed {b['exposed_total']} (hidden {b['hidden']})")
    return res
