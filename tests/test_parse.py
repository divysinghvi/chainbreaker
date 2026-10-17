from pathlib import Path

import pytest

from chainbreaker.demo import scenario
from chainbreaker.parse.action import parse_action
from chainbreaker.parse.uses import parse_uses
from chainbreaker.parse.workflow import parse_workflow

FIX = Path(__file__).parent / "fixtures"
SHA = "a" * 40


@pytest.mark.parametrize("s,kind,node_id,pinned,local", [
    ("actions/checkout@v4", "action", "actions/checkout@v4", False, False),
    ("github/codeql-action/init@v3", "action", "github/codeql-action/init@v3", False, False),
    (f"actions/checkout@{SHA}", "action", f"actions/checkout@{SHA}", True, False),
    ("./.github/actions/setup", "action", "o/r/.github/actions/setup@HEAD", False, True),
    ("./.github/workflows/reusable.yml", "workflow", "o/r:.github/workflows/reusable.yml", False, True),
    ("org/repo/.github/workflows/ci.yml@main", "workflow", "org/repo:.github/workflows/ci.yml@main", False, False),
    ("docker://alpine:3.19", "docker", "docker://alpine:3.19", False, False),
    ("docker://alpine@sha256:" + "b" * 64, "docker", "docker://alpine@sha256:" + "b" * 64, True, False),
    ("  Owner/Repo@v1  ", "action", "owner/repo@v1", False, False),
])
def test_uses_forms(s, kind, node_id, pinned, local):
    u = parse_uses(s, "O", "R", None, in_action=False)
    assert (u.kind, u.node_id, u.pinned, u.local) == (kind, node_id, pinned, local)


def test_uses_dynamic_invalid_and_local_in_action():
    assert parse_uses("${{ matrix.x }}", "o", "r", None, False).kind == "dynamic"
    assert parse_uses("not-a-uses", "o", "r", None, False) is None
    assert parse_uses("./sub", "o", "r", "v1", in_action=True).kind == "unresolved"
    # a tag is mutable, a 40-hex SHA is not
    assert not parse_uses("a/b@v1.2.3", "o", "r", None, False).pinned
    assert parse_uses(f"a/b@{SHA}", "o", "r", None, False).pinned


@pytest.mark.parametrize("on,expected", [
    ("on: push\n", ["push"]),
    ("on: [push, pull_request]\n", ["push", "pull_request"]),
    ("on:\n  push:\n  workflow_dispatch:\n", ["push", "workflow_dispatch"]),
])
def test_triggers(on, expected):
    f = parse_workflow(on + "jobs:\n  a:\n    runs-on: x\n    steps: []\n", "o", "r")
    assert f.triggers == expected


@pytest.mark.parametrize("perm_block,job_perm,expected", [
    ("permissions: write-all\n", "", "write"),
    ("permissions:\n  contents: write\n", "", "write"),
    ("permissions:\n  contents: read\n", "", "read"),
    ("", "", "default"),
    ("", "    permissions:\n      contents: read\n", "read"),
    ("", "    permissions:\n      packages: write\n", "write"),
])
def test_permissions(perm_block, job_perm, expected):
    text = f"on: push\n{perm_block}jobs:\n  a:\n    runs-on: x\n{job_perm}    steps: []\n"
    assert parse_workflow(text, "o", "r").perms == expected


def test_secrets_and_lines():
    f = parse_workflow((FIX / "lines.yml").read_text(), "o", "r")
    assert f.secrets == ["GITHUB_TOKEN", "NPM_TOKEN"]
    by = {(s.ref.node_id, tuple(s.lines)) for s in f.uses}
    assert ("actions/checkout@v4", (8,)) in by
    assert ("actions/checkout@v4", (14,)) in by
    assert ("actions/setup-node@v4.1", (9,)) in by
    assert ("o/r:.github/workflows/reusable.yml", (17,)) in by
    assert f.dynamic == 1
    # only GITHUB_TOKEN + read perms would be LOW; NPM_TOKEN with default perms is HIGH
    assert f.severity == "HIGH"


@pytest.mark.parametrize("repo", scenario.APP_REPOS)
def test_demo_severity(repo):
    path, text = scenario.WORKFLOWS[repo]
    f = parse_workflow(scenario.render(text, "lab", SHA, SHA), "lab", repo)
    assert f.severity == scenario.EXPECTED_SEVERITY[repo], f.severity_reasons
    assert f.entry


def test_demo_shared_ci_not_entry():
    f = parse_workflow(scenario.render(scenario.SHARED_CI, "lab"), "lab", "cb-shared-workflows")
    assert not f.entry and [s.ref.node_id for s in f.uses] == ["lab/cb-ci-toolkit@v2"]


def test_demo_lint_reporter_action():
    a = parse_action(scenario.render(scenario.ACTIONS["cb-lint-reporter"], "lab"), "lab", "cb-lint-reporter", "v1")
    assert a.kind == "composite"
    assert [(s.ref.node_id, s.lines) for s in a.uses] == [("lab/cb-setup-reviewer@v1", [6]),
                                                           ("lab/cb-changed-files@v3", [7])]
    assert parse_action(None, "o", "r", "v1").kind == "unresolved"
    assert parse_action("runs:\n  using: node20\n  main: x.js\n", "o", "r", "v1").kind == "node"
    d = parse_action("runs:\n  using: docker\n  image: docker://alpine:3\n", "o", "r", "v1")
    assert d.kind == "docker" and d.uses[0].ref.node_id == "docker://alpine:3"
