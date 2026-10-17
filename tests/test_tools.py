import pytest

from chainbreaker import config, db
from chainbreaker.agent import validator
from chainbreaker.agent.tools import TOOLS, anthropic_schemas, run_tool

try:
    HAVE_DEMO = db.graph_exists("demo")
except Exception:  # noqa: BLE001
    HAVE_DEMO = False
needs_demo = pytest.mark.skipif(not HAVE_DEMO, reason="cb:demo not loaded")


def test_catalogue_shape():
    schemas = anthropic_schemas()
    assert len(schemas) == 10 and len(anthropic_schemas({"request_fix_approval"})) == 9
    assert all(s["input_schema"]["type"] == "object" for s in schemas)


def test_validator_flags_invented_names():
    known = ["chainbreaker-lab-divy/cb-changed-files@v3", "lab/web-frontend:.github/workflows/pr-check.yml"]
    g = validator.check("Exposed via `chainbreaker-lab-divy/cb-changed-files@v3` and foo/bar; see "
                        "lab/web-frontend:.github/workflows/pr-check.yml (PIN/REPIN, 9/11).", known)
    assert g["unverified"] == ["foo/bar"] and g["total"] == 3 and g["verified"] == 2
    assert validator.scrub("use foo/bar now", ["foo/bar"]) == "use [unverified] now"
    assert validator.extract("repo-1a2b3c:ci.yml is hidden; see https://x.com/a/b") == ["repo-1a2b3c:ci.yml"]


@needs_demo
def test_unknown_action_gives_suggestions():
    r = run_tool("demo", "find_action", {"query": "evil-corp/backdoor-action"})
    assert r["outcome"] == "unknown_entity" and r["suggestions"]
    assert run_tool("demo", "find_action", {"query": "cb-changed-files"})["outcome"] == "found"


@needs_demo
def test_blast_radius_shape():
    adv = run_tool("demo", "simulate_compromise", {"action_id": f"{config.DEMO_ORG}/cb-changed-files"})
    r = run_tool("demo", "blast_radius", {"advisory_id": adv["advisory_id"]})
    assert r["outcome"] == "answered_with_path"
    assert (r["exposed_total"], r["grep_depth1_total"], r["hidden"]) == (11, 2, 9)
    assert r["example_path"]["depth"] == 4 and all(h["lines"] for h in r["example_path"]["hops"])
    assert "graph_ms" in r and set(TOOLS) >= {"find_action", "blast_radius"}
