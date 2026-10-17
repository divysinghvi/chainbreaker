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


if __name__ == "__main__":
    app()
