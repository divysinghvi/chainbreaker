"""Create / reset the synthetic demo org (PLAN CP4, 8.7) and write the ground truth."""
import json
import time

from .. import config, db, queries as Q
from ..github import rest
from . import scenario as S


def _ensure_file(org: str, repo: str, path: str, text: str, log) -> str:
    """Write `text` if it differs; return the sha of the last commit that touched `path`."""
    for attempt in range(10):  # contents API lags a few seconds behind repo creation
        try:
            cur, sha = rest.get_file(org, repo, path)
            break
        except rest.GitHubError:
            time.sleep(1 + attempt)
    if cur != text:
        rest.put_file(org, repo, path, text, f"chainbreaker lab: write {path}", sha=sha)
        log(f"    wrote {repo}/{path}")
    return rest.last_commit_for(org, repo, path)


def ground_truth(org: str, g: str, l1: str) -> dict:
    wf = {r: f"{org}/{r}:{S.WORKFLOWS[r][0]}" for r in S.APP_REPOS}
    depth = {"web-frontend": 1, "docs-site": 1, "analytics": 2, "mobile-app": 2, "payments-api": 3,
             "auth-service": 3, "orders-api": 3, "billing-worker": 3, "search-api": 3, "notifications": 3,
             "infra-terraform": 4}
    exposed = {}
    for r, d in depth.items():
        exposed[wf[r]] = {"depth": d, "severity": S.EXPECTED_SEVERITY[r]}
        if r == "mobile-app":
            exposed[wf[r]]["pinned_but_exposed"] = True
    return {"org": org, "advisory_action": f"{org}/cb-changed-files".lower(), "known_good_sha": g,
            "lint_reporter_v1_sha": l1, "exposed": exposed, "not_exposed": [wf["data-pipeline"]],
            "exposed_count": 11, "depth1_count": 2, "hidden_count": 9, "high_exposed_count": 9,
            "pinned_but_exposed_count": 1, "min_cut_high": 3, "min_cut_all": 4,
            "cut_high": [{"type": "PIN", "file": wf["web-frontend"]},
                         {"type": "PIN", "file": f"{org}/cb-lint-reporter:action.yml"},
                         {"type": "REPIN", "file": wf["mobile-app"]}],
            "after_fix_exposed_count": 0}


def seed(log=print) -> dict:
    org = config.DEMO_ORG
    for name in S.REPOS:
        repo = rest.create_repo(org, name, "Synthetic repo for the ChainBreaker lab. No real secrets.")
        rest.disable_actions(org, name)
        log(f"  {repo['html_url']}")
    for name in S.REPOS:
        _ensure_file(org, name, "README.md", S.README.format(repo=name), log)

    sha = {}
    for name in ["cb-changed-files", "cb-setup-reviewer", "cb-lint-reporter", "cb-ci-toolkit", "cb-release-kit"]:
        text = S.render(S.ACTIONS[name], org, sha.get("cb-changed-files", ""))
        sha[name] = _ensure_file(org, name, "action.yml", text, log)
        rest.set_tag(org, name, S.TAGS[name], sha[name])
        log(f"  {name}@{S.TAGS[name]} -> {sha[name]}")
    _ensure_file(org, "cb-shared-workflows", ".github/workflows/ci.yml", S.render(S.SHARED_CI, org), log)
    g, l1 = sha["cb-changed-files"], sha["cb-lint-reporter"]
    for name in S.APP_REPOS:
        path, text = S.WORKFLOWS[name]
        _ensure_file(org, name, path, S.render(text, org, g, l1), log)

    gt = ground_truth(org, g, l1)
    config.GROUND_TRUTH.write_text(json.dumps(gt, indent=2) + "\n")
    log(f"G  (cb-changed-files@v3 known-good) = {g}")
    log(f"L1 (cb-lint-reporter@v1)           = {l1}")
    return gt


def reset(log=print) -> dict:
    org = config.DEMO_ORG
    for name in S.REPOS:
        for pr in rest.list_prs(org, name, "all"):
            head = pr["head"]["ref"]
            if not head.startswith("chainbreaker/"):
                continue
            if pr["state"] == "open":
                rest.close_pr(org, name, pr["number"])
                log(f"  closed {name}#{pr['number']}")
            rest.delete_branch(org, name, head)
    if db.graph_exists("demo"):  # a fresh scenario starts with fresh agent memory
        db.run("demo", Q.FINDINGS_CLEAR)
    return seed(log)
