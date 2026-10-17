"""FastAPI app: JSON API + SSE agent stream + the static web console (PLAN CP11)."""
import functools
import json
import logging
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, queries as Q
from .agent import tools as agent_tools
from .agent.loop import run_agent
from .analysis import advisory, blast as blast_mod, fix, leaderboard

log = logging.getLogger("chainbreaker.api")
DATASETS = ("demo", "cncf")
REPLAY_DS = "replay-tj-2025"


def autoload() -> None:
    """Import snapshots into an empty FalkorDB (fresh volume / deploy). Public mode only ever serves the
    redacted CNCF snapshot."""
    from .ingest import snapshot
    for attempt in range(30):  # FalkorDB may still be starting under compose
        try:
            db.get_db().list_graphs()
            break
        except Exception:  # noqa: BLE001
            time.sleep(1)
    for ds in DATASETS:
        if not snapshot.path_for(ds).exists():
            continue
        meta = db.q1(ds, Q.META, ro=True) if db.graph_exists(ds) else None
        stale = ds == "cncf" and config.PUBLIC_MODE and not (meta or {}).get("redacted")
        if meta is None or stale:
            log.warning("importing snapshot %s%s", ds, " (redacted, public mode)" if stale else "")
            snapshot.import_(ds)
    if not db.graph_exists(REPLAY_DS) and config.REPLAY.exists():
        from .ingest.replay import load_replay
        load_replay()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    autoload()
    yield


app = FastAPI(title="ChainBreaker", lifespan=lifespan)


def timed(fn):
    """Every JSON response carries the request's total FalkorDB time and query count."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        db.reset_stats()
        out = fn(*a, **kw)
        return out | db.get_stats() if isinstance(out, dict) else out
    return wrapper


def _ds(ds: str) -> str:
    if ds not in DATASETS or not db.graph_exists(ds):
        raise HTTPException(404, f"dataset {ds!r} is not loaded")
    return ds


def _admin(token: str | None) -> None:
    ok = bool(token) and secrets.compare_digest(token, config.ADMIN_TOKEN)
    if not ok or (config.PUBLIC_MODE and config.ADMIN_TOKEN == "change-me"):
        raise HTTPException(401, "admin token required (X-Admin-Token)")


_hits: dict[str, deque] = defaultdict(deque)


def _rate_limit(ip: str) -> None:
    if not config.PUBLIC_MODE:
        return
    now, q = time.time(), _hits[ip]
    while q and q[0] < now - 600:
        q.popleft()
    if len(q) >= config.AGENT_RATE_LIMIT:
        raise HTTPException(429, f"agent limit is {config.AGENT_RATE_LIMIT} requests / 10 min")
    q.append(now)


# ---------- read endpoints ----------
@app.get("/healthz")
def healthz() -> dict:
    try:
        db.get_db().connection.ping()
        return {"ok": True, "falkordb": True}
    except Exception:  # noqa: BLE001
        return {"ok": False, "falkordb": False}


@app.get("/api/datasets")
@timed
def datasets() -> dict:
    known = {f"cb:{d}" for d in (*DATASETS, REPLAY_DS)}  # dev-only graphs (cb:sample) stay hidden
    graphs = [g for g in db.get_db().list_graphs() if g in known]
    out = []
    for g in sorted(graphs):
        ds = g[3:]
        out.append({"id": ds, "graph": g, "stats": leaderboard.stats(ds) if ds in DATASETS else None})
    return {"datasets": out, "public_mode": config.PUBLIC_MODE, "demo_org": config.DEMO_ORG}


@app.get("/api/replay/tj-2025")
def replay() -> dict:
    data = json.loads(config.REPLAY.read_text())
    return data | {"graph": f"cb:{REPLAY_DS}", "loaded": db.graph_exists(REPLAY_DS)}


@app.get("/api/{ds}/stats")
@timed
def stats(ds: str) -> dict:
    return leaderboard.stats(_ds(ds))


@app.get("/api/{ds}/actions/search")
@timed
def search(ds: str, q: str = "") -> dict:
    _ds(ds)
    if not q.strip():
        rows = db.q(ds, Q.DIRECT_ALL, ro=True)[:10]
        return {"q": q, "results": [{"id": r["action"], "direct": r["direct"]} for r in rows]}
    ids = agent_tools._exact(ds, q) + agent_tools._suggest(ds, q)
    return {"q": q, "results": [{"id": i} for i in list(dict.fromkeys(ids))[:10]]}


class AdvisoryBody(BaseModel):
    action_id: str
    refs: list[str] = []


@app.post("/api/{ds}/advisories")
@timed
def create_advisory(ds: str, body: AdvisoryBody) -> dict:
    a = advisory.simulate_compromise(_ds(ds), body.action_id, body.refs or None)
    if a is None:
        raise HTTPException(404, {"error": f"{body.action_id} is not in the graph",
                                  "suggestions": agent_tools._suggest(ds, body.action_id)})
    return a


def _adv(ds: str, adv: str) -> None:
    if advisory.get(ds, adv) is None:
        raise HTTPException(404, f"advisory {adv} not found")


@app.get("/api/{ds}/advisories/{adv}/blast")
@timed
def get_blast(ds: str, adv: str, depth: int = config.MAX_DEPTH) -> dict:
    _adv(_ds(ds), adv)
    return blast_mod.blast(ds, adv, depth)


@app.get("/api/{ds}/advisories/{adv}/graph")
@timed
def get_graph(ds: str, adv: str, depth: int = config.MAX_DEPTH) -> dict:
    _adv(_ds(ds), adv)
    return blast_mod.viz_subgraph(ds, adv, depth)


@app.get("/api/{ds}/advisories/{adv}/path")
@timed
def get_path(ds: str, adv: str, workflow: str, depth: int = config.MAX_DEPTH) -> dict:
    _adv(_ds(ds), adv)
    p = blast_mod.explain(ds, adv, workflow, depth)
    w = db.q1(ds, Q.WORKFLOW_GET, {"wid": workflow}, ro=True)
    risk = {k: w["w"].properties.get(k) for k in ("triggers", "perms", "secrets", "severity", "severity_reasons",
                                                  "id_token_write")} if w else {}
    return {"workflow": workflow, "exposed": p is not None, "path": p, "risk": risk}


class PlanBody(BaseModel):
    targets: Literal["high", "all"] = "all"


@app.post("/api/{ds}/advisories/{adv}/plan")
@timed
def create_plan(ds: str, adv: str, body: PlanBody) -> dict:
    _adv(_ds(ds), adv)
    return fix.plan_fix(ds, adv, body.targets)


@app.post("/api/{ds}/plans/{pid}/simulate")
@timed
def simulate(ds: str, pid: str) -> dict:
    s = fix.simulate_fix(_ds(ds), pid)
    if s is None:
        raise HTTPException(404, f"plan {pid} not found")
    return s


@app.get("/api/{ds}/plans/{pid}")
@timed
def get_plan(ds: str, pid: str) -> dict:
    p = fix.get_plan(_ds(ds), pid)
    if p is None:
        raise HTTPException(404, f"plan {pid} not found")
    return p


@app.get("/api/{ds}/leaderboard")
@timed
def get_leaderboard(ds: str, top: int = 15) -> dict:
    return leaderboard.leaderboard(_ds(ds), top)


# ---------- admin: real GitHub writes, demo org only ----------
def _run_logged(fn, *args) -> dict:
    lines: list[str] = []
    result = fn(*args, lines.append)
    return {"result": result, "log": lines}


@app.post("/api/demo/plans/{pid}/open")
@timed
def open_prs(pid: str, x_admin_token: str | None = Header(None)) -> dict:
    _admin(x_admin_token)
    from .demo import apply
    out = _run_logged(apply.open_phase1, pid)
    return out | {"plan": fix.get_plan("demo", pid)}


@app.post("/api/demo/plans/{pid}/merge")
@timed
def merge_prs(pid: str, x_admin_token: str | None = Header(None)) -> dict:
    _admin(x_admin_token)
    from .demo import apply
    out = _run_logged(apply.merge_and_continue, pid)
    return out | {"plan": fix.get_plan("demo", pid)}


@app.post("/api/demo/rescan")
@timed
def rescan(x_admin_token: str | None = Header(None)) -> dict:
    _admin(x_admin_token)
    from .demo import apply
    return _run_logged(apply.rescan)


@app.post("/api/demo/reset")
@timed
def reset(x_admin_token: str | None = Header(None)) -> dict:
    _admin(x_admin_token)
    from .demo import apply, seed
    out = _run_logged(seed.reset)
    after = _run_logged(apply.rescan)
    return {"log": out["log"] + after["log"], "result": after["result"]}


# ---------- agent (SSE) ----------
class AgentBody(BaseModel):
    dataset: str = "demo"
    message: str
    chat_id: str | None = None  # server-side chat history; omit to start a new chat


@app.post("/api/agent")
def agent(body: AgentBody, request: Request) -> StreamingResponse:
    _rate_limit(request.client.host if request.client else "?")
    ds = _ds(body.dataset)
    if not body.message.strip() or len(body.message) > 2000:
        raise HTTPException(400, "message must be 1-2000 characters")

    def events():
        db.reset_stats()
        for ev in run_agent(ds, body.message, body.chat_id):
            yield f"data: {json.dumps(ev | db.get_stats(), default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.mount("/", StaticFiles(directory=config.WEB, html=True), name="web")
