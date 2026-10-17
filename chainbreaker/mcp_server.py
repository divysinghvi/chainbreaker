"""MCP server (stdio) exposing the same fixed tool catalogue, minus request_fix_approval.

Claude Desktop: command = .venv/bin/python, args = ["-m", "chainbreaker.mcp_server"].
"""
from typing import Literal

from mcp.server.fastmcp import FastMCP

from .agent.tools import TOOLS, run_tool

mcp = FastMCP("chainbreaker")


def _d(name: str) -> str:
    return TOOLS[name].description + " `dataset`: demo (synthetic org) or cncf (1k public repos)."


@mcp.tool(description=_d("find_action"))
def find_action(query: str, dataset: str = "demo") -> dict:
    return run_tool(dataset, "find_action", {"query": query})


@mcp.tool(description=_d("simulate_compromise"))
def simulate_compromise(action_id: str, refs: list[str] | None = None, dataset: str = "demo") -> dict:
    return run_tool(dataset, "simulate_compromise", {"action_id": action_id, "refs": refs or []})


@mcp.tool(description=_d("blast_radius"))
def blast_radius(advisory_id: str, max_depth: int = 6, dataset: str = "demo") -> dict:
    return run_tool(dataset, "blast_radius", {"advisory_id": advisory_id, "max_depth": max_depth})


@mcp.tool(description=_d("explain_exposure"))
def explain_exposure(advisory_id: str, workflow_id: str, dataset: str = "demo") -> dict:
    return run_tool(dataset, "explain_exposure", {"advisory_id": advisory_id, "workflow_id": workflow_id})


@mcp.tool(description=_d("workflow_risk"))
def workflow_risk(workflow_id: str, dataset: str = "demo") -> dict:
    return run_tool(dataset, "workflow_risk", {"workflow_id": workflow_id})


@mcp.tool(description=_d("plan_fix"))
def plan_fix(advisory_id: str, targets: Literal["high", "all"] = "all", dataset: str = "demo") -> dict:
    return run_tool(dataset, "plan_fix", {"advisory_id": advisory_id, "targets": targets})


@mcp.tool(description=_d("simulate_fix"))
def simulate_fix(plan_id: str, dataset: str = "demo") -> dict:
    return run_tool(dataset, "simulate_fix", {"plan_id": plan_id})


@mcp.tool(description=_d("load_bearing_actions"))
def load_bearing_actions(top_k: int = 10, dataset: str = "cncf") -> dict:
    return run_tool(dataset, "load_bearing_actions", {"top_k": top_k})


@mcp.tool(description=_d("recall_findings"))
def recall_findings(action_id: str = "", dataset: str = "demo") -> dict:
    return run_tool(dataset, "recall_findings", {"action_id": action_id})


if __name__ == "__main__":
    mcp.run()
