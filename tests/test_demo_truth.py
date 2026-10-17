"""Demo graph vs data/demo_ground_truth.json. Skipped when cb:demo is not loaded."""
import json

import pytest

from chainbreaker import config, db

try:
    HAVE_DEMO = db.graph_exists("demo") and config.GROUND_TRUTH.exists()
except Exception:  # noqa: BLE001 - FalkorDB not running
    HAVE_DEMO = False

pytestmark = pytest.mark.skipif(not HAVE_DEMO, reason="cb:demo not loaded")


@pytest.fixture(scope="module")
def gt():
    return json.loads(config.GROUND_TRUTH.read_text())


@pytest.fixture(scope="module")
def adv(gt):
    from chainbreaker.analysis import advisory
    return advisory.simulate_compromise("demo", gt["advisory_action"])["id"]


def test_blast_matches_ground_truth(gt, adv):
    from chainbreaker.analysis.blast import blast
    b = blast("demo", adv, 6)
    got = {x["workflow"]: x for x in b["exposed"]}
    assert set(got) == set(gt["exposed"])
    for wid, exp in gt["exposed"].items():
        assert got[wid]["depth"] == exp["depth"], wid
        assert got[wid]["severity"] == exp["severity"], wid
        assert got[wid]["pinned_but_exposed"] == exp.get("pinned_but_exposed", False), wid
    assert not set(gt["not_exposed"]) & set(got)
    assert (b["exposed_total"], b["depth1"], b["hidden"], b["high_total"], len(b["pinned_but_exposed"])) == (
        gt["exposed_count"], gt["depth1_count"], gt["hidden_count"], gt["high_exposed_count"],
        gt["pinned_but_exposed_count"])
    assert blast("demo", adv, 1)["exposed_total"] == gt["depth1_count"]


def test_infra_path_has_four_hops(gt, adv):
    from chainbreaker.analysis.blast import explain
    wid = next(w for w in gt["exposed"] if "infra-terraform" in w)
    p = explain("demo", adv, wid, 6)
    assert p["depth"] == 4
    assert [h["to"].split("/", 1)[1] for h in p["hops"]] == [
        "cb-shared-workflows:.github/workflows/ci.yml@main", "cb-ci-toolkit@v2", "cb-lint-reporter@v1",
        "cb-changed-files@v3"]
    assert all(h["lines"] for h in p["hops"])
