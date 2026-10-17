"""FalkorDB connection, graph names and timed query helpers."""
import contextvars
import time
from typing import Any

from falkordb import FalkorDB

from . import config

_db: FalkorDB | None = None
_stats: contextvars.ContextVar[dict | None] = contextvars.ContextVar("cb_stats", default=None)


def get_db() -> FalkorDB:
    global _db
    if _db is None:
        _db = FalkorDB(host=config.FALKORDB_HOST, port=config.FALKORDB_PORT, username=config.FALKORDB_USERNAME,
                       password=config.FALKORDB_PASSWORD or None, ssl=config.FALKORDB_SSL)
    return _db


def gname(ds: str) -> str:
    """Dataset name -> graph key. Already-qualified names (cb:...) pass through."""
    return ds if ds.startswith("cb:") else f"cb:{ds}"


def graph(ds: str):
    return get_db().select_graph(gname(ds))


def graph_exists(ds: str) -> bool:
    return gname(ds) in get_db().list_graphs()


def reset_stats() -> dict:
    s = {"graph_ms": 0.0, "queries": 0}
    _stats.set(s)
    return s


def get_stats() -> dict:
    s = _stats.get()
    return {"graph_ms": round(s["graph_ms"], 2), "queries": s["queries"]} if s else {"graph_ms": 0.0, "queries": 0}


def _record(ms: float) -> None:
    s = _stats.get()
    if s is None:
        s = reset_stats()
    s["graph_ms"] += ms
    s["queries"] += 1


def run(ds: str, cypher: str, params: dict | None = None, ro: bool = False):
    """Run a query, return the raw QueryResult (keeps Node/Edge/Path objects)."""
    g = graph(ds)
    t = time.perf_counter()
    res = (g.ro_query if ro else g.query)(cypher, params or {})
    _record((time.perf_counter() - t) * 1000)
    return res


def q(ds: str, cypher: str, params: dict | None = None, ro: bool = False) -> list[dict[str, Any]]:
    """Run a query, return rows as dicts keyed by column alias."""
    res = run(ds, cypher, params, ro)
    cols = [h[1] for h in res.header]
    return [dict(zip(cols, row)) for row in res.result_set]


def q1(ds: str, cypher: str, params: dict | None = None, ro: bool = False) -> dict[str, Any] | None:
    rows = q(ds, cypher, params, ro)
    return rows[0] if rows else None
