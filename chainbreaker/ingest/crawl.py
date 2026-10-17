"""Crawl repos -> workflows -> action files at refs (BFS) into a normalized crawl.json (PLAN C.4)."""
import datetime as dt
import json
import logging
import time
from collections import Counter

from .. import config
from ..github import discover, gql
from ..parse.action import parse_action
from ..parse.uses import UsesRef, is_sha
from ..parse.workflow import UsesSite, parse_workflow

log = logging.getLogger(__name__)
BATCH = 25


def workflows_query(repos: list[dict]) -> str:
    parts = []
    for i, r in enumerate(repos):
        parts.append(f'''r{i}: repository(owner: {json.dumps(r["owner"])}, name: {json.dumps(r["name"])}) {{
          nameWithOwner stargazerCount isArchived defaultBranchRef {{ name }}
          object(expression: "HEAD:.github/workflows") {{
            ... on Tree {{ entries {{ name type object {{ ... on Blob {{ text isTruncated }} }} }} }}
          }}
        }}''')
    return "query { rateLimit { remaining resetAt } " + "\n".join(parts) + " }"


def blobs_query(items: list[tuple[str, str, list[str]]]) -> str:
    parts = []
    for i, (o, n, exprs) in enumerate(items):
        objs = " ".join(f'y{j}: object(expression: {json.dumps(e)}) {{ ... on Blob {{ text }} }}'
                        for j, e in enumerate(exprs))
        parts.append(f'a{i}: repository(owner: {json.dumps(o)}, name: {json.dumps(n)}) {{ {objs} }}')
    return "query { rateLimit { remaining resetAt } " + "\n".join(parts) + " }"


def _exprs(u: UsesRef) -> list[str]:
    if u.kind == "workflow":
        return [f"{u.ref}:{u.raw_path}"]
    p = u.raw_path + "/" if u.raw_path else ""
    return [f"{u.ref}:{p}action.yml", f"{u.ref}:{p}action.yaml"]


class Crawl:
    def __init__(self, dataset: str, orgs: list[str]):
        self.out = {"dataset": dataset, "crawled_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                    "orgs": orgs, "repos": [], "workflows": {}, "actions": {}, "action_refs": {},
                    "docker_images": {}, "edges": {}}
        self.stats = Counter()
        self.targets: dict[str, UsesRef] = {}  # node id -> ref, for every uses target seen
        self.done: set[str] = set()

    def _target(self, u: UsesRef) -> None:
        nid = u.node_id
        if nid in self.targets:
            return
        self.targets[nid] = u
        if u.kind == "docker":
            self.out["docker_images"][nid] = {"id": nid, "pinned": u.pinned}
            self.done.add(nid)
        elif u.kind in ("action", "unresolved"):
            self.out["action_refs"][nid] = {"id": nid, "action_id": u.action_id, "ref": u.ref, "pinned": u.pinned,
                                            "local": u.local, "kind": "unresolved" if u.kind == "unresolved" else "unknown"}
            if u.kind == "action":
                aid = u.action_id
                self.out["actions"].setdefault(aid, {
                    "id": aid, "owner": u.owner, "repo": u.repo, "path": u.path,
                    "search": " ".join([aid] + aid.replace("/", " ").replace("-", " ").replace("_", " ").split())})
            else:
                self.stats["unresolved"] += 1
                self.done.add(nid)
        elif u.kind == "workflow" and not u.ref:
            self.done.add(nid)  # a HEAD workflow in the same repo: already crawled from the tree

    def add_edges(self, src: str, src_label: str, immutable: bool, file_repo: str, file_path: str,
                  sites: list[UsesSite]) -> None:
        for s in sites:
            self._target(s.ref)
            key = f"{src}\u0000{s.ref.node_id}"
            e = self.out["edges"].get(key)
            if e:
                e["lines"] = sorted(set(e["lines"]) | set(s.lines))
                continue
            self.out["edges"][key] = {"src": src, "src_label": src_label, "dst": s.ref.node_id,
                                      "dst_label": s.ref.label, "kind": s.kind, "file_repo": file_repo,
                                      "file_path": file_path, "lines": s.lines, "uses": s.ref.raw,
                                      "src_immutable": immutable}

    def add_workflow(self, rid: str, owner: str, name: str, path: str, text: str, at_ref: str | None) -> bool:
        f = parse_workflow(text, owner, name, at_ref=at_ref)
        if f is None:
            self.stats["bad_yaml"] += 1
            return False
        self.stats["dynamic_uses"] += f.dynamic
        self.stats["invalid"] += f.invalid
        wid = f"{rid}:{path}" + (f"@{at_ref}" if at_ref else "")
        rec = {"id": wid, "repo_id": rid, "path": path, "name": f.name, "triggers": f.triggers, "secrets": f.secrets,
               "perms": f.perms, "id_token_write": f.id_token_write, "prt": f.prt, "entry": f.entry if not at_ref else False,
               "at_ref": at_ref, "pinned": is_sha(at_ref) if at_ref else False}
        if not at_ref:
            rec |= {"severity": f.severity, "severity_reasons": f.severity_reasons}
        self.out["workflows"][wid] = rec
        self.add_edges(wid, "Workflow", is_sha(at_ref), rid, path, f.uses)
        return True

    def crawl_repos(self, repos: list[dict], use_cache: bool) -> None:
        self.out["repos"] = [{"id": r["id"], "stars": r["stars"], "default_branch": r["default_branch"]} for r in repos]
        for chunk, data in gql.batched(repos, BATCH, workflows_query, use_cache):
            for i, r in enumerate(chunk):
                node = data.get(f"r{i}") if data else None
                tree = (node or {}).get("object") or {}
                for e in tree.get("entries") or []:
                    if e["type"] != "blob" or not e["name"].endswith((".yml", ".yaml")):
                        continue
                    blob = e.get("object") or {}
                    if blob.get("isTruncated") or blob.get("text") is None:
                        self.stats["truncated"] += 1
                        continue
                    self.add_workflow(r["id"], r["owner"], r["name"], f".github/workflows/{e['name']}",
                                      blob["text"], None)

    def resolve(self, use_cache: bool) -> int:
        """BFS over pending targets; returns the deepest level reached."""
        level = 0
        while level < config.MAX_DEPTH:
            pending = sorted(n for n in self.targets if n not in self.done)
            if not pending:
                break
            level += 1
            items = [self.targets[n] for n in pending]
            build = lambda ch: blobs_query([(u.raw_owner, u.raw_repo, _exprs(u)) for u in ch])  # noqa: E731
            for chunk, data in gql.batched(items, BATCH, build, use_cache):
                for i, u in enumerate(chunk):
                    self.done.add(u.node_id)
                    node = data.get(f"a{i}") if data else None
                    blobs = [((node or {}).get(f"y{j}") or {}).get("text") for j in range(len(_exprs(u)))]
                    found = next(((j, t) for j, t in enumerate(blobs) if t is not None), None)
                    if u.kind == "workflow":
                        rid = f"{u.owner}/{u.repo}"
                        if found is None or not self.add_workflow(rid, u.raw_owner, u.raw_repo, u.path,
                                                                   found[1], u.ref):
                            self.stats["unresolved"] += 1
                            self.out["workflows"][u.node_id] = {
                                "id": u.node_id, "repo_id": rid, "path": u.path, "name": "", "triggers": [],
                                "secrets": [], "perms": "read", "id_token_write": False, "prt": False,
                                "entry": False, "at_ref": u.ref, "pinned": u.pinned}
                        continue
                    rec = self.out["action_refs"][u.node_id]
                    if found is None:
                        rec["kind"] = "unresolved"
                        self.stats["unresolved"] += 1
                        continue
                    j, text = found
                    facts = parse_action(text, u.raw_owner, u.raw_repo, u.ref)
                    rec["kind"] = facts.kind
                    self.stats["dynamic_uses"] += facts.dynamic
                    self.stats["invalid"] += facts.invalid
                    fpath = _exprs(u)[j].split(":", 1)[1]
                    self.add_edges(u.node_id, "ActionRef", u.pinned, f"{u.owner}/{u.repo}", fpath, facts.uses)
        self.stats["depth_capped"] = sum(1 for n in self.targets if n not in self.done)
        return level

    def result(self) -> dict:
        o = self.out
        wf_ids = set(o["workflows"])
        edges = [e for e in o["edges"].values() if e["dst_label"] != "Workflow" or e["dst"] in wf_ids]
        self.stats["dangling_edges"] = len(o["edges"]) - len(edges)
        return {**{k: o[k] for k in ("dataset", "crawled_at", "orgs", "repos")},
                "workflows": list(o["workflows"].values()), "actions": list(o["actions"].values()),
                "action_refs": list(o["action_refs"].values()), "docker_images": list(o["docker_images"].values()),
                "edges": edges, "stats": dict(self.stats)}


def crawl(dataset: str, orgs: list[str], max_repos: int, no_cache: bool = False) -> dict:
    t0 = time.perf_counter()
    gql.STATS.update(hits=0, misses=0, retries=0)
    use_cache = not no_cache
    repos: list[dict] = []
    for org in orgs:
        found = discover.org_repos(org, max_repos, use_cache)
        log.info("org %s: %d repos", org, len(found))
        print(f"  {org}: {len(found)} repos", flush=True)
        repos += found
    c = Crawl(dataset, orgs)
    c.crawl_repos(repos, use_cache)
    print(f"  workflows parsed: {len(c.out['workflows'])}; resolving actions…", flush=True)
    levels = c.resolve(use_cache)
    out = c.result()
    out["stats"]["levels"] = levels
    out["stats"]["elapsed_s"] = round(time.perf_counter() - t0, 1)
    out["stats"]["cache"] = dict(gql.STATS)
    path = config.CACHE / dataset / "crawl.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def summary(c: dict) -> str:
    wf = c["workflows"]
    head = [w for w in wf if not w.get("at_ref")]
    kinds = Counter(r["kind"] for r in c["action_refs"])
    s = c["stats"]
    return "\n".join([
        f"dataset {c['dataset']} · crawled {c['crawled_at']}",
        f"repos {len(c['repos'])}",
        f"workflows {len(wf)} (HEAD {len(head)}, entry {sum(1 for w in head if w['entry'])}, at-ref {len(wf) - len(head)})",
        f"actions {len(c['actions'])} · action refs {len(c['action_refs'])} by kind {dict(kinds)}",
        f"docker images {len(c['docker_images'])} · USES edges {len(c['edges'])}",
        f"unresolved {s.get('unresolved', 0)} · dynamic uses {s.get('dynamic_uses', 0)} · invalid {s.get('invalid', 0)}"
        f" · bad yaml {s.get('bad_yaml', 0)} · depth-capped {s.get('depth_capped', 0)} · BFS levels {s.get('levels')}",
        f"cache hits {s['cache']['hits']} · misses {s['cache']['misses']} · retries {s['cache']['retries']}"
        f" · elapsed {s['elapsed_s']}s",
    ])
