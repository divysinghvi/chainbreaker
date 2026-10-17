"""`cb` command line."""
import datetime as dt
import json

import httpx
import typer

from . import config, db

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def _root() -> None:
    """ChainBreaker: blast radius and min-cut fixes for GitHub Actions supply-chain attacks."""

ALGOS = ["algo.maxFlow", "algo.HarmonicCentrality", "algo.SPpaths", "algo.pageRank", "algo.betweenness", "algo.WCC"]


def _out(obj) -> None:
    typer.echo(json.dumps(obj, indent=2, default=str))


@app.command()
def check() -> None:
    """FalkorDB version + procedures, GitHub token scopes + demo org, Anthropic key."""
    lines: list[str] = []
    fdb = db.get_db()
    mods = fdb.connection.execute_command("MODULE", "LIST")
    ver = {}
    for m in mods:
        d = {m[i].decode() if isinstance(m[i], bytes) else m[i]: m[i + 1] for i in range(0, len(m), 2)}
        ver[d["name"].decode() if isinstance(d["name"], bytes) else d["name"]] = d["ver"]
    lines.append(f"FalkorDB modules: {ver}")
    tmp = "cb:check-tmp"
    g = fdb.select_graph(tmp)
    g.query("RETURN 1")
    procs = sorted(r[0] for r in g.query("CALL dbms.procedures() YIELD name RETURN name").result_set)
    g.delete()
    lines.append(f"procedures ({len(procs)}): {', '.join(procs)}")
    for a in ALGOS:
        lines.append(f"  {a}: {'yes' if a in procs else 'NO'}")

    stop = []
    if not config.GITHUB_TOKEN:
        stop.append("GITHUB_TOKEN missing in .env")
    else:
        h = {"Authorization": f"Bearer {config.GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
        r = httpx.get("https://api.github.com/user", headers=h, timeout=20)
        scopes = [s.strip() for s in r.headers.get("X-OAuth-Scopes", "").split(",") if s.strip()]
        lines.append(f"github user: {r.json().get('login')} · scopes: {', '.join(scopes)}")
        for need in ("repo", "workflow"):
            if need not in scopes:
                stop.append(f"token lacks the '{need}' scope")
        if not config.DEMO_ORG:
            stop.append("DEMO_ORG missing in .env")
        else:
            o = httpx.get(f"https://api.github.com/orgs/{config.DEMO_ORG}", headers=h, timeout=20)
            lines.append(f"org {config.DEMO_ORG}: {'OK' if o.status_code == 200 else f'FAIL {o.status_code}'}")
            if o.status_code != 200:
                stop.append(f"GET /orgs/{config.DEMO_ORG} -> {o.status_code}")
    lines.append(f"ANTHROPIC_API_KEY: {'present' if config.ANTHROPIC_API_KEY else 'MISSING'}")
    if not config.ANTHROPIC_API_KEY:
        stop.append("ANTHROPIC_API_KEY missing in .env")

    for ln in lines:
        typer.echo(ln)
    block = (f"\n### `cb check` · {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}\n\n```\n"
             + "\n".join(lines) + "\n```\n")
    notes = config.NOTES.read_text() if config.NOTES.exists() else "## FalkorDB capabilities\n"
    head = "## FalkorDB capabilities\n"
    notes = notes.replace(head, head + block, 1) if head in notes else notes + block
    config.NOTES.write_text(notes)
    if stop:
        typer.echo("STOP: " + "; ".join(stop), err=True)
        raise typer.Exit(1)



def _orgs_for(dataset: str, orgs: str | None) -> list[str]:
    if orgs:
        return [o.strip() for o in orgs.split(",") if o.strip()]
    if dataset == "demo":
        return [config.DEMO_ORG]
    if dataset == "cncf":
        return config.CNCF_ORGS
    raise typer.BadParameter("--orgs is required for this dataset")


@app.command()
def crawl(dataset: str = typer.Option(..., "--dataset"), orgs: str = typer.Option(None, "--orgs"),
          max_repos: int = typer.Option(None, "--max-repos"), no_cache: bool = typer.Option(False, "--no-cache")) -> None:
    """Crawl GitHub into data/cache/<dataset>/crawl.json."""
    import logging

    from .ingest import crawl as crawl_mod
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if dataset == "demo":
        no_cache = True
    if max_repos is None:
        max_repos = config.CNCF_MAX_REPOS_PER_ORG if dataset == "cncf" else 100
    out = crawl_mod.crawl(dataset, _orgs_for(dataset, orgs), max_repos, no_cache)
    typer.echo(crawl_mod.summary(out))


@app.command()
def load(dataset: str = typer.Option(..., "--dataset")) -> None:
    """Load data/cache/<dataset>/crawl.json into graph cb:<dataset>."""
    from .ingest.load import load_file
    typer.echo(load_file(dataset))


@app.command()
def stats(dataset: str = typer.Option(..., "--dataset")) -> None:
    """Counts per label, USES edges, mutable-ref share, crawl date."""
    from .analysis.leaderboard import stats as stats_fn
    _out(stats_fn(dataset))


@app.command("seed-demo")
def seed_demo() -> None:
    """Create the synthetic demo org repos, tags and ground truth (idempotent)."""
    from .demo.seed import seed
    seed(typer.echo)


@app.command("reset-demo")
def reset_demo() -> None:
    """Close ChainBreaker PRs, restore every scenario file and tag, rewrite the ground truth."""
    from .demo.seed import reset
    reset(typer.echo)


@app.command()
def advisory(dataset: str = typer.Option(..., "--dataset"), action: str = typer.Option(..., "--action"),
             refs: str = typer.Option("", "--refs"), new: bool = typer.Option(False, "--new")) -> None:
    """Simulate a compromise of an action (creates an Advisory)."""
    from .analysis.advisory import simulate_compromise
    a = simulate_compromise(dataset, action, [r for r in refs.split(",") if r], new)
    if a is None:
        typer.echo(f"{action} is not in the graph", err=True)
        raise typer.Exit(1)
    _out(a)


@app.command()
def blast(dataset: str = typer.Option(..., "--dataset"), advisory: str = typer.Option(..., "--advisory"),
          depth: int = typer.Option(config.MAX_DEPTH, "--depth")) -> None:
    """Blast radius of an advisory: exposed, depth-1 (grep) vs hidden, pinned-but-exposed."""
    from .analysis.blast import blast as blast_fn
    b = blast_fn(dataset, advisory, depth)
    typer.echo(f"depth<={b['max_depth']}: exposed {b['exposed_total']} · depth-1 {b['depth1']} · hidden {b['hidden']}"
               f" · HIGH {b['high_total']} · pinned-but-exposed {len(b['pinned_but_exposed'])}"
               f" · by depth {b['by_depth']} · {b['graph_ms']} ms")
    for x in b["exposed"]:
        flag = "  [pinned-but-exposed]" if x["pinned_but_exposed"] else ""
        typer.echo(f"  d{x['depth']} {x['severity']:<4} {x['workflow']}{flag}")


@app.command()
def path(dataset: str = typer.Option(..., "--dataset"), advisory: str = typer.Option(..., "--advisory"),
         workflow: str = typer.Option(..., "--workflow"), depth: int = typer.Option(config.MAX_DEPTH, "--depth")) -> None:
    """Shortest exposing path for one workflow, hop by hop with file:line."""
    from .analysis.blast import explain
    p = explain(dataset, advisory, workflow, depth)
    if p is None:
        typer.echo(f"{workflow} is not exposed by {advisory}")
        raise typer.Exit(1)
    typer.echo(f"{p['depth']} hops ({p['engine']}):")
    for i, h in enumerate(p["hops"], 1):
        lines = ",".join(map(str, h["lines"]))
        typer.echo(f"  {i}. {h['from']}\n     --[{h['kind']}] {h['file_repo']}:{h['file_path']}:{lines}  uses: {h['uses']}"
                   f"\n     -> {h['to']}{'  (pinned)' if h['pinned'] else ''}")


def _print_plan(p: dict) -> None:
    typer.echo(f"{p['id']} ({p['targets']}): {p['cut_size']} changes protect {p['protected']} pipelines"
               f" (naive: {p['naive']}) · engine {p['engine']} · maxFlow {p['max_flow']} · copy {p.get('copy_ms')} ms")
    if p.get("engine_note"):
        typer.echo(f"  note: {p['engine_note']}")
    for f in p["fixes"]:
        typer.echo(f"  {f['type']:<6} {f['file_repo']}:{f['file_path']}:{','.join(map(str, f['lines']))}"
                   f"  {f['old_uses']} -> {f['new_uses'] or '(at apply time)' if f['type'] == 'REPIN' else f['new_uses'] or '(manual)'}"
                   f"  protects {f['protects']} · phase {f['phase']}")


@app.command()
def plan(dataset: str = typer.Option(..., "--dataset"), advisory: str = typer.Option(..., "--advisory"),
         targets: str = typer.Option("all", "--targets")) -> None:
    """Minimum set of uses: line changes that cut every attack path (min-cut)."""
    from .analysis.fix import plan_fix
    p = plan_fix(dataset, advisory, targets)
    if p is None:
        raise typer.Exit(1)
    _print_plan(p)


@app.command()
def simulate(dataset: str = typer.Option(..., "--dataset"), plan: str = typer.Option(..., "--plan")) -> None:
    """What-if: apply the plan's cut on a GRAPH.COPY scratch graph and re-run blast."""
    from .analysis.fix import simulate_fix
    _out(simulate_fix(dataset, plan))


@app.command("leaderboard")
def leaderboard_cmd(dataset: str = typer.Option(..., "--dataset"), top: int = typer.Option(15, "--top")) -> None:
    """Most load-bearing actions: PageRank, direct users, transitive reach, mutable reach."""
    from .analysis.leaderboard import leaderboard as lb
    res = lb(dataset, top)
    typer.echo(f"{'action':<52} {'pagerank':>9} {'direct':>7} {'reach':>6} {'hidden':>6} {'mutable':>8}")
    for r in res["rows"]:
        typer.echo(f"{r['action']:<52} {r['pagerank']:>9} {r['direct']:>7} {r['reach']:>6} {r['hidden_reach']:>6}"
                   f" {r['mutable_pct']:>7}%")


@app.command("eval")
def eval_cmd(no_cncf: bool = typer.Option(False, "--no-cncf")) -> None:
    """Write eval/results.json + eval/RESULTS.md."""
    from .analysis.evaluate import run
    res = run(not no_cncf)
    for r in res["demo"]:
        typer.echo(f"  {'PASS' if r['pass'] else 'FAIL'}  {r['check']}  ({r['value']})")
    if "cncf" in res:
        _out(res["cncf"]["headline"] | {"ecosystem": res["cncf"]["ecosystem"]})


@app.command("snapshot-export")
def snapshot_export(dataset: str = typer.Option(..., "--dataset"), redact: bool = typer.Option(False, "--redact")) -> None:
    """data/cache/<ds>/crawl.json -> data/snapshots/<ds>.crawl.json.gz (pseudonymized with --redact)."""
    from .ingest.snapshot import export
    typer.echo(export(dataset, redact))


@app.command("snapshot-import")
def snapshot_import(dataset: str = typer.Option(..., "--dataset")) -> None:
    """Load data/snapshots/<ds>.crawl.json.gz into cb:<ds>."""
    from .ingest.snapshot import import_
    typer.echo(import_(dataset))


@app.command("apply-demo")
def apply_demo(plan: str = typer.Option(..., "--plan"), open_: bool = typer.Option(False, "--open"),
               merge: bool = typer.Option(False, "--merge")) -> None:
    """Open the phase-1 PRs (--open) or merge them, move tags, REPIN and rescan (--merge). Demo org only."""
    from .demo import apply
    if open_:
        apply.open_phase1(plan, typer.echo)
    if merge:
        _out(apply.merge_and_continue(plan, typer.echo))


@app.command("rescan-demo")
def rescan_demo() -> None:
    """Re-crawl the demo org (no cache), rebuild cb:demo, relink advisories, print exposure."""
    from .demo import apply
    _out(apply.rescan(typer.echo))


@app.command("mcp-selftest")
def mcp_selftest() -> None:
    """Start the MCP server over stdio, list its tools and call blast_radius on the demo."""
    import asyncio
    import os
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def main() -> None:
        params = StdioServerParameters(command=sys.executable, args=["-m", "chainbreaker.mcp_server"],
                                       env=dict(os.environ), cwd=str(config.ROOT))
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            typer.echo(f"{len(tools)} tools: {', '.join(t.name for t in tools)}")
            adv = await s.call_tool("simulate_compromise", {"action_id": f"{config.DEMO_ORG}/cb-changed-files"})
            adv_id = json.loads(adv.content[0].text)["advisory_id"]
            res = json.loads((await s.call_tool("blast_radius", {"advisory_id": adv_id})).content[0].text)
            typer.echo(f"blast_radius({adv_id}): outcome {res['outcome']} · exposed {res['exposed_total']} · "
                       f"grep depth-1 {res['grep_depth1_total']} · hidden {res['hidden']}")

    asyncio.run(main())


@app.command()
def ask(question: str = typer.Argument(...), dataset: str = typer.Option("demo", "--dataset")) -> None:
    """Ask the agent; prints tool calls, results and the grounded final answer as they stream."""
    from .agent.loop import run_agent
    for ev in run_agent(dataset, question):
        t = ev["type"]
        if t == "chat":
            continue
        if t == "tool_call":
            typer.echo(f"→ {ev['name']}({json.dumps(ev['args'])})")
        elif t == "tool_result":
            typer.echo(f"  ← {ev['summary']}  [{ev['ms']} ms, outcome {ev['outcome']}]")
        elif t == "approval":
            typer.echo(f"  ⏸ awaiting human approval for {ev['plan_id']}: {ev['summary']}")
        elif t == "grounding_retry":
            typer.echo(f"  ↻ grounding retry, unverified: {ev['unverified']}")
        elif t == "final":
            g = ev["grounding"]
            typer.echo(f"\n{ev['text']}\n\n[outcome {ev['outcome']} · grounded {g['verified']}/{g['total']}"
                       f"{' · unverified ' + str(g['unverified']) if g['unverified'] else ''}]")
        else:
            typer.echo(f"ERROR: {ev['message']}", err=True)


@app.command("load-replay")
def load_replay_cmd() -> None:
    """Load data/replay_tj_2025.json into graph cb:replay-tj-2025."""
    from .ingest.replay import load_replay
    typer.echo(load_replay())


if __name__ == "__main__":
    app()
