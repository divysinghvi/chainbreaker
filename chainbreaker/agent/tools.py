"""The fixed tool catalogue (PLAN Appendix E.2). The LLM picks tools; it never writes Cypher."""
import difflib
import re
from dataclasses import dataclass
from typing import Callable, Literal

from pydantic import BaseModel, Field

from .. import db, queries as Q
from ..analysis import advisory, fix, leaderboard
from ..analysis.blast import blast, explain
from . import memory

TOP = 12
MAX_FIXES = 15


def _ms(t0: float) -> float:
    return round(db.get_stats()["graph_ms"] - t0, 2)


# ---------- name resolution ----------
def _suggest(ds: str, q: str) -> list[str]:
    out: list[str] = []
    words = re.findall(r"[a-z0-9]+", q.lower())
    if words:
        try:
            out += [r["id"] for r in db.q(ds, Q.FT_SEARCH, {"q": "|".join(words)}, ro=True)]
        except Exception:  # noqa: BLE001 - full-text index still building: CONTAINS only
            pass
    out += [r["id"] for r in db.q(ds, Q.CONTAINS_SEARCH, {"q": q}, ro=True)]
    ids = [r["id"] for r in db.q(ds, Q.ALL_ACTION_IDS, ro=True)]
    out += difflib.get_close_matches(q.lower(), ids, n=5, cutoff=0.5)
    return list(dict.fromkeys(out))[:5]


def _unknown(ds: str, q: str, t0: float) -> dict:
    sugg, basis = _suggest(ds, q), "similar names in the graph"
    if not sugg:  # nothing similar: say so, and offer what *is* in the graph
        sugg, basis = [r["action"] for r in db.q(ds, Q.DIRECT_ALL, ro=True)][:5], "most-used actions in this graph"
    return {"outcome": "unknown_entity", "query": q, "suggestions": sugg, "suggestion_basis": basis, "graph_ms": _ms(t0)}


def _exact(ds: str, q: str) -> list[str]:
    q = q.strip().lower().split("@", 1)[0]
    if db.q1(ds, Q.ACTION_EXISTS, {"aid": q}, ro=True):
        return [q]
    hits = [r["id"] for r in db.q(ds, Q.CONTAINS_SEARCH, {"q": q}, ro=True)]
    return [h for h in hits if h == q or h.endswith("/" + q)]


def _resolve_workflow(ds: str, wid: str) -> list[str]:
    if db.q1(ds, Q.WORKFLOW_GET, {"wid": wid}, ro=True):
        return [wid]
    return [r["id"] for r in db.q(ds, Q.WORKFLOW_SEARCH, {"q": wid}, ro=True)]


# ---------- tool functions: (ds, **args) -> dict with `outcome` + `graph_ms` ----------
def find_action(ds: str, query: str) -> dict:
    t0 = db.get_stats()["graph_ms"]
    ids = _exact(ds, query)
    if not ids:
        return _unknown(ds, query, t0)
    matches = []
    for aid in ids:
        refs = db.q(ds, Q.ACTION_REFS, {"aid": aid}, ro=True)
        direct = db.q1(ds, Q.DIRECT, {"aid": aid}, ro=True) or {}
        matches.append({"id": aid, "refs": [r["ref"] for r in refs], "mutable_refs": [r["ref"] for r in refs if not r["pinned"]],
                        "direct_users": int(direct.get("direct") or 0)})
    return {"outcome": "found", "matches": matches, "graph_ms": _ms(t0)}


def simulate_compromise(ds: str, action_id: str, refs: list[str]) -> dict:
    t0 = db.get_stats()["graph_ms"]
    ids = _exact(ds, action_id)
    if len(ids) != 1:
        return _unknown(ds, action_id, t0) if not ids else {
            "outcome": "unknown_entity", "query": action_id, "suggestions": ids, "suggestion_basis": "ambiguous",
            "graph_ms": _ms(t0)}
    a = advisory.simulate_compromise(ds, ids[0], refs or None)
    return {"outcome": "simulated", "advisory_id": a["id"], "action_id": a["action_id"],
            "compromised_refs": a["compromised_refs"], "known_good_sha": a.get("known_good_sha") or None,
            "graph_ms": _ms(t0)}


def _hops(p: dict) -> list[dict]:
    return [{"from": h["from"], "to": h["to"], "uses": h["uses"], "file": f"{h['file_repo']}:{h['file_path']}",
             "lines": h["lines"], "pinned": h["pinned"]} for h in p["hops"]]


def blast_radius(ds: str, advisory_id: str, max_depth: int) -> dict:
    t0 = db.get_stats()["graph_ms"]
    if advisory.get(ds, advisory_id) is None:
        return {"outcome": "not_in_graph", "advisory_id": advisory_id, "graph_ms": _ms(t0)}
    b = blast(ds, advisory_id, max_depth)
    d1 = blast(ds, advisory_id, 1)["exposed_total"] if b["max_depth"] > 1 else b["exposed_total"]
    out = {k: b[k] for k in ("advisory_id", "max_depth", "exposed_total", "depth1", "hidden", "high_total", "by_depth",
                             "by_severity", "pinned_but_exposed")}
    out["grep_depth1_total"] = d1
    out["top"] = [{"workflow": x["workflow"], "severity": x["severity"], "depth": x["depth"]} for x in b["exposed"][:TOP]]
    deepest = max(b["exposed"], key=lambda x: x["depth"], default=None)
    if deepest:
        p = explain(ds, advisory_id, deepest["workflow"], max_depth)
        out["example_path"] = {"workflow": deepest["workflow"], "depth": p["depth"], "hops": _hops(p)} if p else None
    out |= {"outcome": "answered_with_path" if b["exposed_total"] else "answered", "graph_ms": _ms(t0)}
    return out


def explain_exposure(ds: str, advisory_id: str, workflow_id: str) -> dict:
    t0 = db.get_stats()["graph_ms"]
    ids = _resolve_workflow(ds, workflow_id)
    if len(ids) != 1:
        return {"outcome": "unknown_entity", "query": workflow_id, "suggestions": ids[:5], "graph_ms": _ms(t0)}
    p = explain(ds, advisory_id, ids[0])
    if p is None:
        return {"outcome": "not_exposed", "workflow": ids[0], "graph_ms": _ms(t0)}
    return {"outcome": "answered_with_path", "workflow": ids[0], "depth": p["depth"], "engine": p["engine"],
            "hops": _hops(p), "graph_ms": _ms(t0)}


def workflow_risk(ds: str, workflow_id: str) -> dict:
    t0 = db.get_stats()["graph_ms"]
    ids = _resolve_workflow(ds, workflow_id)
    if len(ids) != 1:
        return {"outcome": "unknown_entity", "query": workflow_id, "suggestions": ids[:5], "graph_ms": _ms(t0)}
    w = db.q1(ds, Q.WORKFLOW_GET, {"wid": ids[0]}, ro=True)["w"].properties
    return {"outcome": "found", "workflow": w["id"], "triggers": w.get("triggers", []), "perms": w.get("perms"),
            "id_token_write": w.get("id_token_write"), "secrets": w.get("secrets", []), "severity": w.get("severity"),
            "reasons": w.get("severity_reasons", []), "graph_ms": _ms(t0)}


def plan_fix(ds: str, advisory_id: str, targets: str) -> dict:
    t0 = db.get_stats()["graph_ms"]
    p = fix.plan_fix(ds, advisory_id, targets)
    if p is None:
        return {"outcome": "not_in_graph", "advisory_id": advisory_id, "graph_ms": _ms(t0)}
    fixes = [{"type": f["type"], "file": f"{f['file_repo']}:{f['file_path']}", "lines": f["lines"],
              "old_uses": f["old_uses"], "new_uses": f["new_uses"] or None, "protects": f["protects"], "phase": f["phase"]}
             for f in p["fixes"]]
    return {"outcome": "planned", "plan_id": p["id"], "targets": targets, "cut_size": p["cut_size"],
            "protected": p["protected"], "naive": p["naive"], "engine": p["engine"], "fixes": fixes[:MAX_FIXES],
            "fixes_total": len(fixes), "graph_ms": _ms(t0)}


def simulate_fix(ds: str, plan_id: str) -> dict:
    t0 = db.get_stats()["graph_ms"]
    s = fix.simulate_fix(ds, plan_id)
    if s is None:
        return {"outcome": "not_in_graph", "plan_id": plan_id, "graph_ms": _ms(t0)}
    return s | {"outcome": "simulated", "graph_ms": _ms(t0)}


def request_fix_approval(ds: str, plan_id: str) -> dict:
    t0 = db.get_stats()["graph_ms"]
    p = fix.get_plan(ds, plan_id)
    if p is None:
        return {"outcome": "not_in_graph", "plan_id": plan_id, "graph_ms": _ms(t0)}
    return {"outcome": "awaiting_human_approval", "plan_id": plan_id, "dataset": ds,
            "summary": f"{p['cut_size']} changes protect {p['protected']} pipelines (naive {p['naive']}); "
                       f"engine {p['engine']}. A human must approve in the UI before any PR is opened.",
            "can_apply": ds == "demo", "graph_ms": _ms(t0)}


def load_bearing_actions(ds: str, top_k: int) -> dict:
    t0 = db.get_stats()["graph_ms"]
    lb = leaderboard.leaderboard(ds, max(1, min(25, top_k)))
    return {"outcome": "answered", "rows": lb["rows"], "graph_ms": _ms(t0)}


def recall_findings(ds: str, action_id: str) -> dict:
    t0 = db.get_stats()["graph_ms"]
    f = memory.recall_findings(ds, action_id)
    return {"outcome": "answered_from_memory" if f else "none", "findings": f, "graph_ms": _ms(t0)}


# ---------- argument models ----------
class FindActionArgs(BaseModel):
    query: str = Field(description="Action name or id, e.g. 'actions/checkout' or 'changed-files'.")


class SimulateCompromiseArgs(BaseModel):
    action_id: str = Field(description="Action id from find_action, e.g. 'owner/repo' or 'owner/repo/path'.")
    refs: list[str] = Field(default_factory=list, description="Only these refs; empty = every mutable ref.")


class BlastRadiusArgs(BaseModel):
    advisory_id: str = Field(description="Advisory id from simulate_compromise, e.g. 'CB-ADV-1'.")
    max_depth: int = Field(default=6, ge=1, le=8, description="Max uses: hops; 1 = what a grep finds.")


class ExplainExposureArgs(BaseModel):
    advisory_id: str
    workflow_id: str = Field(description="Workflow id from blast_radius (a unique substring also works).")


class WorkflowRiskArgs(BaseModel):
    workflow_id: str


class PlanFixArgs(BaseModel):
    advisory_id: str
    targets: Literal["high", "all"] = Field(default="all", description="'high' = only HIGH-severity pipelines.")


class PlanIdArgs(BaseModel):
    plan_id: str = Field(description="Plan id from plan_fix, e.g. 'CB-PLAN-1'.")


class LoadBearingArgs(BaseModel):
    top_k: int = Field(default=10, ge=1, le=25)


class RecallArgs(BaseModel):
    action_id: str = Field(default="", description="Filter by action id (substring); empty = most recent findings.")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[..., dict]


TOOLS = {t.name: t for t in [
    Tool("find_action", "Resolve an action name to ids in the graph, with its refs and direct users. Returns "
         "unknown_entity + suggestions when the name is not in the graph.", FindActionArgs, find_action),
    Tool("simulate_compromise", "Mark an action's mutable refs (tags/branches) as compromised by creating an Advisory. "
         "Idempotent per action.", SimulateCompromiseArgs, simulate_compromise),
    Tool("blast_radius", "Exposed entry workflows for an advisory, contrasting depth 1 (grep) with full depth: counts by "
         "depth/severity, hidden count, pinned-but-exposed, top workflows and the deepest example path.",
         BlastRadiusArgs, blast_radius),
    Tool("explain_exposure", "The shortest exposing path for one workflow, hop by hop with file and line "
         "(FalkorDB algo.SPpaths).", ExplainExposureArgs, explain_exposure),
    Tool("workflow_risk", "Triggers, token permissions, secret names and severity reasons of a workflow.",
         WorkflowRiskArgs, workflow_risk),
    Tool("plan_fix", "Minimum set of uses: line changes that cut every attack path (min-cut via FalkorDB "
         "algo.maxFlow on a GRAPH.COPY scratch graph). PIN/REPIN/VENDOR fixes with file:line.", PlanFixArgs, plan_fix),
    Tool("simulate_fix", "What-if: remove the plan's cut edges on a GRAPH.COPY scratch graph and re-run blast radius. "
         "Proves the plan reaches 0.", PlanIdArgs, simulate_fix),
    Tool("request_fix_approval", "Ask a human to approve opening the plan's PRs. You can never open or merge PRs "
         "yourself.", PlanIdArgs, request_fix_approval),
    Tool("load_bearing_actions", "Most load-bearing actions: PageRank over uses: edges plus direct users, transitive "
         "reach and share of mutable refs.", LoadBearingArgs, load_bearing_actions),
    Tool("recall_findings", "Earlier investigations (question, answer, date) stored as Finding nodes.", RecallArgs,
         recall_findings),
]}
MCP_EXCLUDE = {"request_fix_approval"}


def anthropic_schemas(exclude: set[str] = frozenset()) -> list[dict]:
    out = []
    for t in TOOLS.values():
        if t.name in exclude:
            continue
        schema = t.args.model_json_schema()
        schema.pop("title", None)
        out.append({"name": t.name, "description": t.description, "input_schema": schema})
    return out


def run_tool(ds: str, name: str, args: dict) -> dict:
    t = TOOLS.get(name)
    if t is None:
        return {"outcome": "error", "error": f"unknown tool {name}", "graph_ms": 0}
    try:
        parsed = t.args.model_validate(args or {})
    except Exception as e:  # noqa: BLE001 - bad arguments go back to the model as data
        return {"outcome": "error", "error": f"invalid arguments: {e}", "graph_ms": 0}
    if ":" in ds or not db.graph_exists(ds):
        return {"outcome": "not_in_graph", "error": f"dataset {ds!r} is not loaded", "graph_ms": 0}
    return t.fn(ds, **parsed.model_dump())
