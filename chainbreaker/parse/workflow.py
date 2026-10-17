"""Workflow YAML -> facts + severity (PLAN 8.2)."""
import io
import logging
import re
from dataclasses import dataclass, field

from ruamel.yaml import YAML

from .uses import UsesRef, parse_uses

log = logging.getLogger(__name__)

SECRET_RE = re.compile(r"\$\{\{\s*secrets\.([A-Za-z0-9_]+)\s*\}\}")
USES_LINE_RE = re.compile(r"""^\s*(?:-\s*)?uses:\s*['"]?([^'"#\s]+)""")


def load_yaml(text: str):
    y = YAML(typ="safe")  # YAML 1.2: `on` stays a string key
    y.allow_duplicate_keys = True
    return y.load(io.StringIO(text))


@dataclass
class UsesSite:
    ref: UsesRef
    kind: str  # step | call | image
    lines: list[int]
    job: str = ""
    step: int | None = None


@dataclass
class WorkflowFacts:
    name: str
    triggers: list[str]
    secrets: list[str]
    perms: str
    id_token_write: bool
    prt: bool
    entry: bool
    severity: str
    severity_reasons: list[str]
    uses: list[UsesSite] = field(default_factory=list)
    dynamic: int = 0
    invalid: int = 0


class LineFinder:
    """Map each uses value to the next unused raw line that carries it."""

    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.used: set[int] = set()

    def find(self, value: str) -> list[int]:
        value = value.strip()
        for exact in (True, False):
            for i, ln in enumerate(self.lines):
                if i in self.used or "uses:" not in ln and "image:" not in ln:
                    continue
                m = USES_LINE_RE.match(ln)
                hit = (m and m.group(1) == value) if exact else value in ln
                if hit:
                    self.used.add(i)
                    return [i + 1]
        return []


def _triggers(doc: dict) -> list[str]:
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return [on]
    if isinstance(on, list):
        return [str(x) for x in on]
    if isinstance(on, dict):
        return [str(k) for k in on]
    return []


def _write_scopes(p) -> list[str]:
    if isinstance(p, str):
        return ["write-all"] if p == "write-all" else []
    if isinstance(p, dict):
        return [f"{k}: write" for k, v in p.items() if v == "write"]
    return []


def summarize_perms(doc: dict) -> tuple[str, bool, list[str]]:
    """-> (perms, id_token_write, write scopes)."""
    top = doc.get("permissions")
    jobs = doc.get("jobs") if isinstance(doc.get("jobs"), dict) else {}
    blocks = [top] + [j.get("permissions") for j in jobs.values() if isinstance(j, dict)]
    writes = sorted({w for b in blocks for w in _write_scopes(b)})
    id_tok = any(isinstance(b, dict) and b.get("id-token") == "write" for b in blocks)
    if writes:
        return "write", id_tok, writes
    if top is None and any(isinstance(j, dict) and "permissions" not in j for j in jobs.values()):
        return "default", id_tok, []
    return "read", id_tok, []


def severity(prt: bool, secrets: list[str], perms: str, id_tok: bool, writes: list[str]) -> tuple[str, list[str]]:
    real = [s for s in secrets if s != "GITHUB_TOKEN"]
    has_secrets = bool(real)
    reasons = []
    if prt:
        reasons.append("pull_request_target trigger")
    if has_secrets:
        reasons.append("secrets: " + ", ".join(real))
    reasons += writes
    if perms == "default":
        reasons.append("no permissions block (repo default)")
    if id_tok:
        reasons.append("id-token: write")
    if prt or (has_secrets and perms in ("write", "default")) or (has_secrets and id_tok):
        return "HIGH", reasons
    if has_secrets or perms in ("write", "default"):
        return "MED", reasons
    return "LOW", reasons


def parse_workflow(text: str, owner: str, repo: str, at_ref: str | None = None) -> WorkflowFacts | None:
    try:
        doc = load_yaml(text)
    except Exception as e:  # noqa: BLE001 - any YAML error means "skip this file"
        log.info("bad workflow yaml %s/%s: %s", owner, repo, e)
        return None
    if not isinstance(doc, dict):
        return None
    triggers = _triggers(doc)
    secrets = sorted(set(SECRET_RE.findall(text)))
    perms, id_tok, writes = summarize_perms(doc)
    prt = "pull_request_target" in triggers
    sev, reasons = severity(prt, secrets, perms, id_tok, writes)
    facts = WorkflowFacts(name=str(doc.get("name") or ""), triggers=triggers, secrets=secrets, perms=perms,
                          id_token_write=id_tok, prt=prt, entry=triggers != ["workflow_call"],
                          severity=sev, severity_reasons=reasons)
    lf = LineFinder(text)
    jobs = doc.get("jobs") if isinstance(doc.get("jobs"), dict) else {}
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        sites: list[tuple[object, str, int | None]] = []
        if "uses" in job:
            sites.append((job["uses"], "call", None))
        for i, step in enumerate(job.get("steps") or []):
            if isinstance(step, dict) and "uses" in step:
                sites.append((step["uses"], "step", i))
        for val, kind, idx in sites:
            u = parse_uses(val, owner, repo, at_ref, in_action=False)
            lines = lf.find(str(val))
            if u is None:
                facts.invalid += 1
            elif u.kind == "dynamic":
                facts.dynamic += 1
            else:
                facts.uses.append(UsesSite(u, "image" if u.kind == "docker" else kind, lines, str(job_id), idx))
    return facts
