"""`cb eval`: demo PASS/FAIL vs ground truth + measured CNCF numbers (aggregates and action names only)."""
import datetime as dt
import json
import time

from .. import config, db, queries as Q
from . import advisory, leaderboard
from .blast import blast
from .fix import plan_fix, simulate_fix


def eval_demo() -> list[dict]:
    gt = json.loads(config.GROUND_TRUTH.read_text())
    adv = advisory.simulate_compromise("demo", gt["advisory_action"])["id"]
    b = blast("demo", adv, 6)
    got = {x["workflow"]: x for x in b["exposed"]}
    hi, al = plan_fix("demo", adv, "high"), plan_fix("demo", adv, "all")
    s_hi, s_al = simulate_fix("demo", hi["id"]), simulate_fix("demo", al["id"])
    cut_hi = sorted((f["type"], f"{f['file_repo']}:{f['file_path']}") for f in hi["fixes"])
    rows = [
        ("exposure set (11 workflows)", sorted(got) == sorted(gt["exposed"]), f"{len(got)} exposed"),
        ("data-pipeline not exposed (chain ends at a pinned ref)", not set(gt["not_exposed"]) & set(got), "safe"),
        ("depth per workflow", all(got.get(w, {}).get("depth") == e["depth"] for w, e in gt["exposed"].items()),
         str(b["by_depth"])),
        ("severity per workflow", all(got.get(w, {}).get("severity") == e["severity"] for w, e in gt["exposed"].items()),
         str(b["by_severity"])),
        ("depth-1 (grep) count = 2", blast("demo", adv, 1)["exposed_total"] == gt["depth1_count"], str(b["depth1"])),
        ("hidden (depth >= 2) = 9", b["hidden"] == gt["hidden_count"], str(b["hidden"])),
        ("pinned-but-exposed = {mobile-app}",
         b["pinned_but_exposed"] == [w for w, e in gt["exposed"].items() if e.get("pinned_but_exposed")],
         ", ".join(w.split("/", 1)[1].split(":")[0] for w in b["pinned_but_exposed"])),
        ("min cut, high-value targets = 3", hi["cut_size"] == gt["min_cut_high"], f"{hi['cut_size']} (naive {hi['naive']})"),
        ("cut edges = PIN web-frontend, PIN cb-lint-reporter, REPIN mobile-app",
         cut_hi == sorted((c["type"], c["file"]) for c in gt["cut_high"]), " · ".join(t for t, _ in cut_hi)),
        ("min cut, all targets = 4", al["cut_size"] == gt["min_cut_all"], f"{al['cut_size']} (naive {al['naive']})"),
        ("cut computed by FalkorDB algo.maxFlow", hi["engine"] == al["engine"] == "falkordb.algo.maxFlow", al["engine"]),
        ("simulate fix (high) on GRAPH.COPY -> 0", s_hi["after"] == 0, f"{s_hi['before']} -> {s_hi['after']}"),
        ("simulate fix (all) on GRAPH.COPY -> 0", s_al["after"] == 0 and s_al["after_total"] == 0,
         f"{s_al['before']} -> {s_al['after']} ({s_al['copy_ms']} ms copy)"),
    ]
    return [{"check": c, "pass": bool(p), "value": v} for c, p, v in rows]


def _int(x) -> int:
    return int(x or 0)


def eval_cncf(n: int = 20) -> dict:
    st = leaderboard.stats("cncf")
    any_mut = db.q1("cncf", Q.depth(Q.TRANSITIVE_MUTABLE.replace("{MIN}", "1"), None), ro=True)
    hid_mut = db.q1("cncf", Q.depth(Q.TRANSITIVE_MUTABLE.replace("{MIN}", "2"), None), ro=True)
    eco = {"repos": st["counts"]["Repo"], "orgs": len(st["orgs"]), "entry_workflows": st["workflows_entry"],
           "action_refs": st["counts"]["ActionRef"], "uses_edges": st["uses_edges"],
           "external_refs": st["external_refs"], "mutable_external_ref_pct": st["mutable_ref_pct"],
           "workflows_with_mutable_ref": _int(any_mut["with_mutable"]),
           "workflows_with_hidden_mutable_ref": _int(hid_mut["with_mutable"]),
           "max_depth_seen": _int(db.q1("cncf", Q.depth(Q.MAX_DEPTH_SEEN, None), ro=True)["d"]),
           "crawled_at": st["crawled_at"]}
    eco["pct_with_mutable_ref"] = round(100 * eco["workflows_with_mutable_ref"] / eco["entry_workflows"], 1)
    eco["pct_with_hidden_mutable_ref"] = round(100 * eco["workflows_with_hidden_mutable_ref"] / eco["entry_workflows"], 1)
    rows = []
    for r in leaderboard.top_by_reach("cncf", n):
        t = time.perf_counter()
        adv = advisory.simulate_compromise("cncf", r["action"])
        b = blast("cncf", adv["id"], None)
        blast_ms = round((time.perf_counter() - t) * 1000, 1)
        row = {"action": r["action"], "reach": r["reach"], "mutable_reach": r["mutable_reach"],
               "compromised_refs": len(adv["compromised_refs"]), "exposed": b["exposed_total"], "depth1": b["depth1"],
               "hidden": b["hidden"], "hidden_pct": round(100 * b["hidden"] / b["exposed_total"], 1) if b["exposed_total"] else 0.0,
               "high": b["high_total"], "pinned_but_exposed": len(b["pinned_but_exposed"]), "blast_ms": blast_ms}
        if b["high_total"]:
            t = time.perf_counter()
            p = plan_fix("cncf", adv["id"], "high")
            row |= {"naive_high": p["naive"], "cut_high": p["cut_size"], "engine": p["engine"],
                    "copy_ms": p["copy_ms"], "plan_ms": round((time.perf_counter() - t) * 1000, 1)}
        else:
            row |= {"naive_high": 0, "cut_high": 0, "engine": "-", "copy_ms": 0, "plan_ms": 0}
        rows.append(row)
    tot = lambda k: sum(r[k] for r in rows)  # noqa: E731
    head = {"exposed": tot("exposed"), "hidden": tot("hidden"),
            "hidden_pct": round(100 * tot("hidden") / tot("exposed"), 1) if tot("exposed") else 0.0,
            "pinned_but_exposed": tot("pinned_but_exposed"), "naive_high": tot("naive_high"), "cut_high": tot("cut_high"),
            "actions_with_hidden": sum(1 for r in rows if r["hidden"]),
            "engines": sorted({r["engine"] for r in rows if r["engine"] != "-"})}
    return {"ecosystem": eco, "rows": rows, "headline": head}


def write(results: dict) -> None:
    out = config.ROOT / "eval"
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    md = [f"# ChainBreaker eval results\n\nGenerated {results['generated_at']} by `cb eval`. "
          "CNCF numbers are aggregates over public repos; only public action names are listed.\n",
          "## Demo org vs ground truth\n", "| Check | Result | Value |", "|---|---|---|"]
    md += [f"| {r['check']} | {'PASS' if r['pass'] else '**FAIL**'} | {r['value']} |" for r in results["demo"]]
    if "cncf" in results:
        e, h = results["cncf"]["ecosystem"], results["cncf"]["headline"]
        md += ["\n## CNCF ecosystem\n", f"Crawled {e['crawled_at']} · {e['orgs']} orgs.\n", "| Metric | Value |", "|---|---|",
               f"| Repos | {e['repos']:,} |", f"| Entry workflows | {e['entry_workflows']:,} |",
               f"| Action refs / USES edges | {e['action_refs']:,} / {e['uses_edges']:,} |",
               f"| External `uses:` refs from workflows that are mutable (tag/branch) | {e['mutable_external_ref_pct']}% of {e['external_refs']:,} |",
               f"| Entry workflows with ≥1 mutable ref anywhere in their chain | {e['workflows_with_mutable_ref']:,} ({e['pct_with_mutable_ref']}%) |",
               f"| …of which reachable only through an intermediate action (hidden) | {e['workflows_with_hidden_mutable_ref']:,} ({e['pct_with_hidden_mutable_ref']}%) |",
               f"| Deepest `uses:` chain seen | {e['max_depth_seen']} hops |",
               f"\n## Simulated compromise of the {len(results['cncf']['rows'])} actions with the highest transitive reach\n",
               f"Totals: **{h['exposed']:,}** exposed workflows, **{h['hidden']:,} hidden ({h['hidden_pct']}%)**, "
               f"**{h['pinned_but_exposed']}** pinned-but-exposed; fixing every HIGH pipeline takes **{h['cut_high']:,}** "
               f"line changes (min-cut) vs **{h['naive_high']:,}** naive. Engine: {', '.join(h['engines'])}.\n",
               "| Action | Reach | Exposed | Depth-1 | Hidden | Hidden % | HIGH | Pinned-but-exposed | Naive (HIGH) | Cut (HIGH) | Blast ms | Plan ms |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        md += [f"| `{r['action']}` | {r['reach']} | {r['exposed']} | {r['depth1']} | {r['hidden']} | {r['hidden_pct']}% | "
               f"{r['high']} | {r['pinned_but_exposed']} | {r['naive_high']} | {r['cut_high']} | {r['blast_ms']} | {r['plan_ms']} |"
               for r in results["cncf"]["rows"]]
    (out / "RESULTS.md").write_text("\n".join(md) + "\n")


def run(include_cncf: bool = True) -> dict:
    res = {"generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "demo": eval_demo()}
    if include_cncf and db.graph_exists("cncf"):
        res["cncf"] = eval_cncf()
    write(res)
    return res
