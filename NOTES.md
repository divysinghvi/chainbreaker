# ChainBreaker build notes

## Decisions

- **Python via uv.** The host has no `python3.12`; the venv is `uv venv --python 3.12 .venv` + `uv pip install -e ".[dev]"` (CPython 3.12.13).
- **GitHub token = the gh CLI OAuth token** (scopes `repo, workflow, read:org, gist`) instead of a new classic PAT. Same scopes the plan asks for; Divy chose it. It lives only in the git-ignored `.env`.
- **`mcp[cli]<2`.** pip resolved mcp 2.x, where `mcp.server.fastmcp.FastMCP` was renamed `MCPServer`. Pinned to 1.x (1.30.0) so the plan's FastMCP code path holds.
- **Commits carry no AI co-author trailer** (Divy's standing preference); AI assistance is disclosed in the README instead (Rule 11).

## Surprises

- **FalkorDB image defaults are tiny:** `FALKORDB_ARGS=MAX_QUEUED_QUERIES 25 TIMEOUT 1000 RESULTSET_SIZE 10000` — a 1 s query timeout and a 10k-row cap. The CNCF graph needs more (edge export for the min-cut is >10k rows), so compose overrides it with `TIMEOUT_DEFAULT 60000 TIMEOUT_MAX 300000 RESULTSET_SIZE -1`.
- **Module version:** `MODULE LIST` reports `graph ver 42201` (FalkorDB 4.22.1) on `falkordb/falkordb:latest` with Redis 8.10.2 — not "v6.0.x" as the plan says. All six algorithms the plan wants are present (see the capability check below).

- **Invalid `uses:` values are real:** the CP2 sample crawl's 68 "invalid" sites are literal `uses: $/.github/actions/...` strings in upstream workflow files (not a parser bug). They are counted and skipped.
- **Crawl ids:** action ids are lowercase (owner/repo/path) but the original case is kept for fetching (`raw_path`), because git tree paths are case-sensitive. Workflow file paths keep their case in ids (they are file names). A local reusable call (`./.github/workflows/x.yml`) from a HEAD workflow points at that HEAD Workflow node itself rather than a duplicate `@HEAD` node.
- **Pinned-but-exposed uses `coalesce(nodes(p)[1].pinned, false)`.** A first hop into a HEAD workflow (local reusable call) has no `pinned` property, and `null <> true` is null, so the plan's literal Q-PINNED would count such workflows as pinned.
- **Fix `new_uses` keeps the original casing**: PIN builds `old_uses` up to the last `@` + the known-good SHA, instead of the lowercased action id (paths are case-sensitive).
- **Scratch sweep is per process**: the `atexit` sweep deletes only scratch graphs this process created, so a CLI run can't delete an API server's in-flight what-if.
- **Redaction scope (8.8):** besides Repo ids, HEAD workflow ids and local actions, *at-ref reusable workflows that live in a crawled repo* are pseudonymized too (they are the projects' own files), and workflow `name` becomes the file basename (names like "Kubernetes E2E" identify a repo). Non-local Action/ActionRef ids stay visible as the plan requires — so 33 of 1,129 crawled repos still appear, because they *are* published actions (`helm/kind-action`, `cilium/cilium-cli`, `envoyproxy/toolshed`, or `cilium/cilium/.github/actions/disk-cleanup@<sha>` used from another repo). `kubernetes/kubernetes`, `prometheus/prometheus`, `istio/istio`, `envoyproxy/envoy`, `argoproj/argo-cd` do not appear in the snapshot.
- **Public mode reads only the redacted graph**: instead of rewriting strings at the output layer, the API re-imports the redacted snapshot when `PUBLIC_MODE=1` and the loaded `cb:cncf` graph's `Meta.redacted` is false. The redacted snapshot reproduces the same eval numbers (topology is unchanged).
- **CNCF eval candidates**: "top 20 by transitive reach" is computed in FalkorDB (Q-REACH) over the union of the PageRank top 25, the top 60 by direct users and the top 40 by composite fan-in.
- **Demo repos have GitHub Actions disabled** (`PUT /actions/permissions {enabled:false}` at seed time). The lab only needs the workflow *files*; nothing in it should ever run, `pull_request_target` on our fix PRs included.
- **Seeder SHAs come from "last commit that touched the file"** (`GET /commits?path=`), so re-running `cb seed-demo` writes nothing and keeps G/L1 stable; `reset-demo` closes `chainbreaker/*` PRs, deletes their branches and re-seeds (only L1 changes, since only cb-lint-reporter's action.yml was edited).
- **CP8 run (2026-10-17):** plan CB-PLAN-5 opened PRs #1 in cb-lint-reporter, docs-site and web-frontend; merge moved `cb-lint-reporter@v1` to the squash commit L2 and the REPIN PR (mobile-app#1) pinned L2; rescan → exposed 0; `reset-demo` → 11 again with a new L1.
- **Agent request shape (Sonnet 5.5):** `max_tokens=8000`, not the plan's 1500, because adaptive thinking counts against it; `output_config.effort="medium"`; no forced `tool_choice` (it 400s on this model); full `response.content` is appended back each round (append-only history, thinking blocks preserved); server-side refusal fallback on (`fallbacks="default"`, beta `server-side-fallback-2026-07-01`). `ANTHROPIC_WORKSPACE_ID` is sent as `anthropic-workspace-id` when set — the first key was not workspace-scoped and every call 400'd until it was swapped.
- **Grounding validator earns its keep:** on the first CP10 question the model shortened names (`infra-terraform/.github/workflows/plan.yml`); the validator flagged 4 names, the one retry rewrote with exact ids → Grounded 11/11. Names from the user's own question count as known (so "X is not in the graph" is not flagged).
- **find_action falls back to the most-used actions** as suggestions when nothing in the graph resembles the query (the demo has no name near `evil-corp/backdoor-action`), and says which basis it used.
- **API (CP11):** sync endpoints + a `timed` decorator add the request's total FalkorDB `graph_ms`/`queries` to every JSON body; the agent SSE stream is a sync generator in `StreamingResponse` (`data: <json>\n\n`), each event also carrying the running FalkorDB counters. `/api/datasets` lists only `cb:demo`, `cb:cncf`, `cb:replay-tj-2025` (dev graphs like `cb:sample` stay hidden). Admin endpoints compare `X-Admin-Token` with `secrets.compare_digest`, and in public mode the default `change-me` token never authorizes.
- **Replay graph (CP13):** `cb:replay-tj-2025` holds only the five facts from the Unit 42 write-up (nodes labelled Token / ActionRef / Action / Repo, `LEADS_TO {step, caption, source}` edges). It is loaded by `cb load-replay` or automatically at API startup, and `MATCH p=()-[*]->() RETURN p` returns the full chain spotbugs-token → reviewdog/action-setup@v1 → tj-actions/eslint-changed-files → tj-actions/changed-files → coinbase/agentkit.
- **Deploy (CP14):** `docker compose down -v && docker compose up -d --build falkordb app` on an empty volume imports the demo + CNCF snapshots and the replay graph at startup, then serves the full flow (2 → 11, plan 4, what-if 0, CNCF leaderboard, agent SSE). The Dockerfile sets `CB_ROOT=/app` because the package is pip-installed into site-packages, away from `web/` and `data/`.
- **Left for Divy:** record the demo video (DEMO.md), deploy to a personal VPS with `--profile prod` (`PUBLIC_MODE=1`, strong `ADMIN_TOKEN`), add both links to the README, try the MCP server from Claude Desktop, and edit the AI-disclosure paragraph so it is accurate.
- **Multi-turn history fix (2026-10-17):** the UI used to send earlier turns as plain text. On a follow-up the model saw its own numbers with none of the tool results behind them, and rule 1 ("every fact must come from a tool result in this conversation") made it append "I need to correct my previous answer… disregard those figures". Chats now live server-side (`chat_id`, in-memory, 200 most recent) with the full message list (tool calls, tool results, thinking blocks, append-only), names verified in earlier turns stay verified, and the Agent tab has a **New chat** button. Re-checked: Q1 "What happens if cb-changed-files is compromised?" then Q2 "Is evil-corp/backdoor-action in our CI?" in one chat → Q2 says not in the graph, no correction, grounded 5/5.
- **BFS batches are sorted by node id** so the per-query disk cache hits on re-runs (Python string hashing is randomized per process, so set order would change every run).

## FalkorDB capabilities

### `cb check` · 2026-10-17T11:40:27+00:00

```
FalkorDB modules: {'graph': 42201, 'vectorset': 1}
procedures (26): algo.AStar, algo.BFS, algo.HarmonicCentrality, algo.MSF, algo.SPpaths, algo.SSpaths, algo.WCC, algo.betweenness, algo.labelPropagation, algo.maxFlow, algo.pageRank, db.constraints, db.idx.cch.query, db.idx.fulltext.createNodeIndex, db.idx.fulltext.drop, db.idx.fulltext.queryNodes, db.idx.fulltext.queryRelationships, db.idx.vector.queryNodes, db.idx.vector.queryRelationships, db.indexes, db.labels, db.meta.stats, db.propertyKeys, db.relationshipTypes, dbms.functions, dbms.procedures
  algo.maxFlow: yes
  algo.HarmonicCentrality: yes
  algo.SPpaths: yes
  algo.pageRank: yes
  algo.betweenness: yes
  algo.WCC: yes
github user: divysinghvi · scopes: gist, read:org, repo, workflow
org chainbreaker-lab-divy: OK
ANTHROPIC_API_KEY: present
```

### `algo.maxFlow` output shape (CP6 probe, FalkorDB 4.22.1)

Q-PROBE (s→a, s→b cap 1; a→t, b→t cap 5) returns **one row** with columns `nodes, edges, edgeFlows, maxFlow`:
`nodes` = list of Node objects on flow paths, `edges` = list of Edge objects carrying flow (their `.id` equals
`id(e)` in Cypher), `edgeFlows` = list of floats aligned 1:1 with `edges`, `maxFlow` = float (`2.0`).
`parse_maxflow()` maps flows by edge id; edges missing from the list have flow 0. Multi-source / multi-target
lists work as documented. The residual-graph cut passes both validations on the demo, so the **engine that ran is
`falkordb.algo.maxFlow`** (networkx is only the fallback).

`algo.SPpaths` also works with the plan's signature (`relDirection: 'outgoing'`, `maxLen`, `pathCount: 1`) and
yields a `Path` whose nodes/edges are in hop order.

## Measured numbers

From `cb eval` (2026-10-17, CNCF crawl of 47 orgs at 11:47 UTC):

- **Demo:** 13/13 ground-truth checks PASS — 11 exposed, 2 at depth 1 (grep), 9 hidden, 1 pinned-but-exposed; min cut 3 (high) / 4 (all), computed by `falkordb.algo.maxFlow`; GRAPH.COPY what-if → 0 (copy ≈ 70–90 ms).
- **CNCF scale:** 1,129 repos, 4,556 entry workflows, 16,541 USES edges, 2,247 action refs (766 composite); crawl took 423 s cold.
- **28.9%** of 13,485 external `uses:` refs in CNCF workflows are mutable (tag/branch); **34.8%** of entry workflows have ≥1 mutable ref somewhere in their chain, **8.5%** have one reachable only through an intermediate action (hidden).
- Simulating a compromise of each of the 20 highest-reach actions: **3,017** exposed workflows, **532 hidden (17.6%)**, **34 pinned to a SHA and still exposed**; 18 of the 20 actions have hidden victims.
- Min-cut for the HIGH pipelines: **864 line changes vs 927 naive** across the 20 (cut < naive wherever composites are shared); the deepest chain seen is 6 hops. Blast radius is ~10–60 ms per action and a full plan (GRAPH.COPY + maxFlow) is ~0.5 s on the CNCF graph.

