"""GitHub REST helpers (PLAN C.6). Every write asserts the owner is DEMO_ORG."""
import base64
import time

import httpx

from .. import config

_client = httpx.Client(base_url="https://api.github.com", timeout=30)


class GitHubError(Exception):
    pass


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.GITHUB_TOKEN}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _guard(owner: str) -> None:
    if not config.DEMO_ORG or owner.lower() != config.DEMO_ORG.lower():
        raise PermissionError(f"refusing to write to {owner!r}: writes are allowed only in DEMO_ORG={config.DEMO_ORG!r}")


def _req(method: str, path: str, ok=(200, 201, 204), **kw) -> httpx.Response:
    for attempt in range(6):
        r = _client.request(method, path, headers=_headers(), **kw)
        retry = r.status_code >= 500 or r.status_code == 429 or (
            r.status_code == 403 and "secondary rate limit" in r.text.lower())
        if not retry:
            break
        time.sleep(float(r.headers.get("Retry-After") or 2 ** attempt))
    if r.status_code not in ok:
        raise GitHubError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
    return r


# ---------- reads ----------
def get_repo(o: str, r: str) -> dict | None:
    resp = _req("GET", f"/repos/{o}/{r}", ok=(200, 404))
    return resp.json() if resp.status_code == 200 else None


def get_file(o: str, r: str, path: str, ref: str | None = None) -> tuple[str | None, str | None]:
    resp = _req("GET", f"/repos/{o}/{r}/contents/{path}", ok=(200, 404), params={"ref": ref} if ref else None)
    if resp.status_code == 404:
        return None, None
    j = resp.json()
    return base64.b64decode(j["content"]).decode(), j["sha"]


def last_commit_for(o: str, r: str, path: str) -> str:
    resp = _req("GET", f"/repos/{o}/{r}/commits", params={"path": path, "per_page": 1})
    return resp.json()[0]["sha"]


def get_ref(o: str, r: str, kind: str, name: str) -> str | None:
    resp = _req("GET", f"/repos/{o}/{r}/git/ref/{kind}/{name}", ok=(200, 404))
    if resp.status_code == 404:
        return None
    j = resp.json()
    return j["object"]["sha"] if isinstance(j, dict) else None


def list_prs(o: str, r: str, state: str = "open") -> list[dict]:
    return _req("GET", f"/repos/{o}/{r}/pulls", params={"state": state, "per_page": 100}).json()


# ---------- writes (DEMO_ORG only) ----------
def create_repo(org: str, name: str, description: str) -> dict:
    _guard(org)
    resp = _req("POST", f"/orgs/{org}/repos", ok=(201, 422),
                json={"name": name, "description": description, "auto_init": True, "private": False,
                      "has_issues": False, "has_wiki": False, "has_projects": False})
    return resp.json() if resp.status_code == 201 else get_repo(org, name)


def disable_actions(o: str, r: str) -> None:
    """Belt and braces: the lab never needs its workflows to actually run."""
    _guard(o)
    _req("PUT", f"/repos/{o}/{r}/actions/permissions", json={"enabled": False})


def put_file(o: str, r: str, path: str, text: str, message: str, branch: str | None = None,
             sha: str | None = None) -> str:
    _guard(o)
    body = {"message": message, "content": base64.b64encode(text.encode()).decode()}
    if branch:
        body["branch"] = branch
    if sha:
        body["sha"] = sha
    return _req("PUT", f"/repos/{o}/{r}/contents/{path}", json=body).json()["commit"]["sha"]


def create_ref(o: str, r: str, ref: str, sha: str) -> None:
    _guard(o)
    _req("POST", f"/repos/{o}/{r}/git/refs", json={"ref": ref, "sha": sha})


def move_tag(o: str, r: str, tag: str, sha: str) -> None:
    _guard(o)
    _req("PATCH", f"/repos/{o}/{r}/git/refs/tags/{tag}", json={"sha": sha, "force": True})


def set_tag(o: str, r: str, tag: str, sha: str) -> None:
    if get_ref(o, r, "tags", tag) is None:
        create_ref(o, r, f"refs/tags/{tag}", sha)
    else:
        move_tag(o, r, tag, sha)


def delete_branch(o: str, r: str, b: str) -> None:
    _guard(o)
    _req("DELETE", f"/repos/{o}/{r}/git/refs/heads/{b}", ok=(204, 422, 404))


def open_pr(o: str, r: str, title: str, head: str, base: str, body: str) -> dict:
    _guard(o)
    j = _req("POST", f"/repos/{o}/{r}/pulls", json={"title": title, "head": head, "base": base, "body": body}).json()
    return {"url": j["html_url"], "number": j["number"]}


def merge_pr(o: str, r: str, n: int) -> str:
    _guard(o)
    for _ in range(10):  # GitHub computes mergeability asynchronously right after a PR opens
        resp = _req("PUT", f"/repos/{o}/{r}/pulls/{n}/merge", ok=(200, 405, 409), json={"merge_method": "squash"})
        if resp.status_code == 200:
            return resp.json()["sha"]
        time.sleep(2)
    raise GitHubError(f"could not merge {o}/{r}#{n}: {resp.text[:200]}")


def close_pr(o: str, r: str, n: int) -> None:
    _guard(o)
    _req("PATCH", f"/repos/{o}/{r}/pulls/{n}", json={"state": "closed"})
