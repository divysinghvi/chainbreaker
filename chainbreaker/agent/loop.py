"""Anthropic tool-use loop -> event stream (PLAN CP10). Append-only history; grounding check before the answer."""
import json
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator

import anthropic

from .. import config
from . import memory, prompts, validator
from .tools import anthropic_schemas, run_tool

MAX_ROUNDS = 8
# max_tokens covers adaptive thinking too, so the plan's 1500 would truncate multi-tool turns
MAX_TOKENS = 8000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
PATH_TOOLS = {"explain_exposure", "blast_radius"}
MAX_CHATS = 200

# Each chat keeps the *full* message list (tool calls, tool results, thinking blocks), so a follow-up question
# sees the evidence behind earlier answers instead of bare text it would then disown.
# ponytail: in-memory chats, lost on restart; persist them in FalkorDB if chats must survive deploys
_chats: OrderedDict[str, dict] = OrderedDict()
_lock = threading.Lock()


def _load_chat(ds: str, chat_id: str | None) -> tuple[str, dict]:
    with _lock:
        c = _chats.get(chat_id) if chat_id else None
        if c is None or c["ds"] != ds:
            return secrets.token_hex(8), {"ds": ds, "messages": [], "known": []}
        return chat_id, {"ds": ds, "messages": list(c["messages"]), "known": list(c["known"])}


def _save_chat(chat_id: str, chat: dict) -> None:
    with _lock:
        _chats[chat_id] = chat
        _chats.move_to_end(chat_id)
        while len(_chats) > MAX_CHATS:
            _chats.popitem(last=False)


def _summary(name: str, r: dict) -> tuple[str, int]:
    o = r.get("outcome", "")
    if name == "find_action":
        return (f"{len(r['matches'])} match(es)", len(r["matches"])) if o == "found" else \
            (f"not in graph · {len(r.get('suggestions', []))} suggestions", 0)
    if name == "simulate_compromise" and o == "simulated":
        return f"{r['advisory_id']} · {len(r['compromised_refs'])} compromised refs", len(r["compromised_refs"])
    if name == "blast_radius" and "exposed_total" in r:
        return (f"{r['exposed_total']} exposed · depth-1 {r['grep_depth1_total']} · hidden {r['hidden']}",
                r["exposed_total"])
    if name == "explain_exposure" and "hops" in r:
        return f"{r['depth']} hops", r["depth"]
    if name == "plan_fix" and "cut_size" in r:
        return f"{r['cut_size']} changes protect {r['protected']} (naive {r['naive']}) · {r['engine']}", r["cut_size"]
    if name == "simulate_fix" and "after" in r:
        return f"{r['before']} → {r['after']} · copy {r['copy_ms']} ms", 1
    if name == "load_bearing_actions" and "rows" in r:
        return f"{len(r['rows'])} actions", len(r["rows"])
    if name == "recall_findings":
        return f"{len(r.get('findings', []))} finding(s)", len(r.get("findings", []))
    return o, 0


def _outcome(results: list[tuple[str, dict]]) -> str:
    outs = [(n, r.get("outcome")) for n, r in results]
    if any(o == "answered_with_path" for _, o in outs):
        return "answered_with_path"
    if any(o == "answered_from_memory" for _, o in outs):
        return "answered_from_memory"
    if any(o == "unknown_entity" for _, o in outs):
        return "unknown_entity"
    if any(o == "not_in_graph" for _, o in outs):
        return "not_in_graph"
    return "answered"


def _paths(results: list[tuple[str, dict]]) -> list[dict]:
    out = []
    for name, r in results:
        if name == "explain_exposure" and r.get("hops"):
            out.append({"workflow": r["workflow"], "hops": r["hops"]})
        elif name == "blast_radius" and r.get("example_path"):
            out.append(r["example_path"])
    seen, uniq = set(), []
    for p in out:
        if p["workflow"] not in seen:
            seen.add(p["workflow"])
            uniq.append(p)
    return uniq


def _action_of(results: list[tuple[str, dict]]) -> str:
    for name, r in reversed(results):
        if name == "simulate_compromise" and r.get("action_id"):
            return r["action_id"]
        if name == "find_action" and r.get("matches"):
            return r["matches"][0]["id"]
    return ""


def run_agent(ds: str, message: str, chat_id: str | None = None) -> Iterator[dict]:
    try:
        headers = {"anthropic-workspace-id": config.ANTHROPIC_WORKSPACE_ID} if config.ANTHROPIC_WORKSPACE_ID else None
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY or None, default_headers=headers)
        tools = anthropic_schemas()
        chat_id, chat = _load_chat(ds, chat_id)
        yield {"type": "chat", "chat_id": chat_id, "turn": sum(1 for m in chat["messages"]
                                                                if m["role"] == "user" and isinstance(m["content"], str))}
        msgs: list = chat["messages"] + [{"role": "user", "content": message}]
        results: list[tuple[str, dict]] = []
        retried = False
        for _ in range(MAX_ROUNDS):
            resp = client.beta.messages.create(
                model=config.ANTHROPIC_MODEL, max_tokens=MAX_TOKENS, system=prompts.system(ds), tools=tools,
                messages=msgs, output_config={"effort": "medium"}, betas=[FALLBACK_BETA], fallbacks="default")
            if resp.stop_reason == "refusal":
                yield {"type": "error", "message": "The model declined this request."}
                return
            msgs.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "tool_use":
                blocks = []
                for b in resp.content:
                    if b.type != "tool_use":
                        continue
                    yield {"type": "tool_call", "name": b.name, "args": b.input}
                    t = time.perf_counter()
                    r = run_tool(ds, b.name, b.input)
                    ms = round((time.perf_counter() - t) * 1000, 1)
                    results.append((b.name, r))
                    summary, rows = _summary(b.name, r)
                    yield {"type": "tool_result", "name": b.name, "summary": summary, "ms": ms, "rows": rows,
                           "graph_ms": r.get("graph_ms"), "outcome": r.get("outcome")}
                    if b.name == "request_fix_approval" and r.get("outcome") == "awaiting_human_approval":
                        yield {"type": "approval", "plan_id": r["plan_id"], "summary": r["summary"],
                               "can_apply": r["can_apply"]}
                    blocks.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(r, default=str)})
                msgs.append({"role": "user", "content": blocks})
                continue
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            # names verified in earlier turns of this chat stay verified
            known = chat["known"] + [s for _, r in results for s in validator.strings(r)] + [message]
            g = validator.check(text, known)
            if g["unverified"] and not retried:
                retried = True
                yield {"type": "grounding_retry", "unverified": g["unverified"]}
                msgs.append({"role": "user", "content": f"These names were not returned by any tool: "
                             f"{g['unverified']}. Rewrite using only tool results."})
                continue
            text = validator.scrub(text, g["unverified"])
            outcome = _outcome(results)
            _save_chat(chat_id, {"ds": ds, "messages": msgs, "known": known})
            yield {"type": "final", "text": text, "outcome": outcome, "grounding": g, "paths": _paths(results),
                   "chat_id": chat_id}
            if outcome != "answered_from_memory" and results:
                memory.save_finding(ds, message, text, _action_of(results))
            return
        yield {"type": "error", "message": f"stopped after {MAX_ROUNDS} rounds"}
    except Exception as e:  # noqa: BLE001 - the stream must end with an event, not a broken connection
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
