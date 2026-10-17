# ChainBreaker build notes

## Decisions

- **Python via uv.** The host has no `python3.12`; the venv is `uv venv --python 3.12 .venv` + `uv pip install -e ".[dev]"` (CPython 3.12.13).
- **GitHub token = the gh CLI OAuth token** (scopes `repo, workflow, read:org, gist`) instead of a new classic PAT. Same scopes the plan asks for; Divy chose it. It lives only in the git-ignored `.env`.
- **`mcp[cli]<2`.** pip resolved mcp 2.x, where `mcp.server.fastmcp.FastMCP` was renamed `MCPServer`. Pinned to 1.x (1.30.0) so the plan's FastMCP code path holds.
- **Commits carry no AI co-author trailer** (Divy's standing preference); AI assistance is disclosed in the README instead (Rule 11).

## Surprises

- **FalkorDB image defaults are tiny:** `FALKORDB_ARGS=MAX_QUEUED_QUERIES 25 TIMEOUT 1000 RESULTSET_SIZE 10000` — a 1 s query timeout and a 10k-row cap. The CNCF graph needs more (edge export for the min-cut is >10k rows), so compose overrides it with `TIMEOUT_DEFAULT 60000 TIMEOUT_MAX 300000 RESULTSET_SIZE -1`.
- **Module version:** `MODULE LIST` reports `graph ver 42201` (FalkorDB 4.22.1) on `falkordb/falkordb:latest` with Redis 8.10.2 — not "v6.0.x" as the plan says. All six algorithms the plan wants are present (see the capability check below).

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

## Measured numbers
