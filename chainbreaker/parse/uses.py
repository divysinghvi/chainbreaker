"""Parse a `uses:` string (PLAN 8.1)."""
import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

SHA_RE = re.compile(r"[0-9a-f]{40}")
REMOTE_RE = re.compile(r"^([^/@\s]+)/([^/@\s]+)((?:/[^@\s]+)?)@(\S+)$")
WORKFLOW_PATH_RE = re.compile(r"\.github/workflows/[^/]+\.ya?ml")


def is_sha(ref: str | None) -> bool:
    return bool(ref) and SHA_RE.fullmatch(ref) is not None


@dataclass(frozen=True)
class UsesRef:
    kind: str  # action | workflow | docker | dynamic | unresolved
    raw: str
    owner: str = ""  # lowercase
    repo: str = ""  # lowercase
    path: str = ""  # lowercase for actions; workflow paths keep their case (they are file names)
    ref: str = ""  # as written; "" for HEAD workflows
    raw_owner: str = ""  # original case, for fetching
    raw_repo: str = ""
    raw_path: str = ""
    local: bool = False

    @property
    def pinned(self) -> bool:
        if self.kind == "docker":
            return "@sha256:" in self.raw
        return is_sha(self.ref)

    @property
    def action_id(self) -> str:
        return "/".join(x for x in (self.owner, self.repo, self.path) if x)

    @property
    def node_id(self) -> str:
        """Id of the node this uses-site points at."""
        if self.kind == "docker":
            return self.raw
        if self.kind == "workflow":
            base = f"{self.owner}/{self.repo}:{self.path}"
            return f"{base}@{self.ref}" if self.ref else base
        return f"{self.action_id}@{self.ref}"

    @property
    def label(self) -> str:
        return {"docker": "DockerImage", "workflow": "Workflow"}.get(self.kind, "ActionRef")


def parse_uses(s, ctx_owner: str, ctx_repo: str, ctx_ref: str | None, in_action: bool) -> UsesRef | None:
    """ctx_ref is None for a HEAD workflow (a local reusable call then points at the HEAD file itself)."""
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    if "${{" in s:
        return UsesRef(kind="dynamic", raw=s)
    if s.startswith("docker://"):
        return UsesRef(kind="docker", raw=s)
    if s.startswith("./"):
        path = s[2:].strip("/")
        if in_action:
            # resolved against the caller's workspace, which we cannot know: an unresolved leaf
            return UsesRef(kind="unresolved", raw=s, owner=ctx_owner.lower(), repo=ctx_repo.lower(),
                           path=f"./{path}".lower(), ref=ctx_ref or "HEAD", local=True)
        if WORKFLOW_PATH_RE.fullmatch(path):
            return UsesRef(kind="workflow", raw=s, owner=ctx_owner.lower(), repo=ctx_repo.lower(), path=path,
                           ref=ctx_ref or "", raw_owner=ctx_owner, raw_repo=ctx_repo, raw_path=path, local=True)
        return UsesRef(kind="action", raw=s, owner=ctx_owner.lower(), repo=ctx_repo.lower(), path=path.lower(),
                       ref=ctx_ref or "HEAD", raw_owner=ctx_owner, raw_repo=ctx_repo, raw_path=path, local=True)
    m = REMOTE_RE.match(s)
    if not m:
        log.info("invalid uses: %r", s)
        return None
    owner, repo, path, ref = m.group(1), m.group(2), m.group(3).strip("/"), m.group(4)
    if WORKFLOW_PATH_RE.fullmatch(path):
        return UsesRef(kind="workflow", raw=s, owner=owner.lower(), repo=repo.lower(), path=path, ref=ref,
                       raw_owner=owner, raw_repo=repo, raw_path=path)
    return UsesRef(kind="action", raw=s, owner=owner.lower(), repo=repo.lower(), path=path.lower(), ref=ref,
                   raw_owner=owner, raw_repo=repo, raw_path=path)
