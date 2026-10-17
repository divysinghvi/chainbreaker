# ChainBreaker — Implementation Plan (hand this whole file to Claude Code)

**Hackathon:** WeMakeDevs × FalkorDB "Graph Hacks: Context for AI Agents" (https://www.wemakedevs.org/hackathons/falkordb)
**Track:** 01, Agents That Act on Connected Data (one track only)
**Deadline:** Sun 18 Oct 2026, 11:59 PM IST
**Builder:** Divy (solo), coding with Claude Code

---

## 0. FOR DIVY: do this before starting Claude Code (about 10 minutes)

1. **Create a free GitHub organization** for the demo, e.g. `chainbreaker-lab-divy` (github.com → Your organizations → New organization → Free). It holds synthetic demo repos. The agent opens real PRs there and nowhere else.
2. **Create a classic personal access token** (github.com/settings/tokens → Tokens (classic)) with the scopes `repo`, `workflow` and `read:org`. The `workflow` scope is required to edit `.github/workflows/*` files through the API.
3. **Have an Anthropic API key** ready.
4. **Make sure these are installed:** Docker, Python 3.12, git.
5. **Create the repo:** make an empty **public** GitHub repo `chainbreaker`, clone it, and put this file in its root as `PLAN.md`.
6. **Create `.env`** in the repo root (it is git-ignored in CP0):
   ```
   GITHUB_TOKEN=ghp_xxx
   DEMO_ORG=chainbreaker-lab-divy
   ANTHROPIC_API_KEY=sk-ant-xxx
   ```
7. **Remove the earlier test container** if you started one: `docker rm -f falkordb 2>/dev/null; true`
8. **Start Claude Code** in the repo and paste this kickoff prompt:

```
Read PLAN.md end to end before writing any code. Then build it checkpoint by checkpoint, in order, starting at CP0. After each checkpoint: run every "Done when" check, fix until they all pass, then commit with that checkpoint's exact commit message and push. Do not stop to ask me anything between checkpoints unless a step says STOP. Log every decision and every surprise (anything that behaves differently from this plan) in NOTES.md. Never commit secrets.
```

> **Rule 13 (projects made entirely by AI "may be rejected"):** you must be able to explain this system. After the build, read sections 1, 7 and 8 of this plan plus `NOTES.md`. These are the design decisions you'll defend.

---

## 1. What we are building, and why it wins (context for Claude Code)

**ChainBreaker** is an AI incident agent for GitHub Actions supply-chain attacks. When an action is compromised, it:

1. finds every workflow that runs it, including workflows that reach it only through 2–4 layers of composite actions and reusable workflows;
2. shows the exact path, with file and line for every hop;
3. computes the **fewest `uses:` line changes that cut every attack path**, using FalkorDB's `algo.maxFlow` (min-cut);
4. **acts**: opens real fix PRs (in the demo org only), merges them, moves tags and re-scans until exposure is **0**.

**The real incident behind it:** in March 2025 a leaked SpotBugs token led to a compromised `reviewdog/action-setup@v1`, then `tj-actions/eslint-changed-files`, then `tj-actions/changed-files` (used by 23,000+ repos), with `coinbase/agentkit` as the target. Source: https://unit42.paloaltonetworks.com/github-actions-supply-chain-attack/. Most victims never referenced the compromised action directly.

**What the judges reward**, from the organizers' official guide (https://www.wemakedevs.org/blogs/how-to-build-an-agent-that-reasons-over-a-graph) and past winners:

- The graph must do work the agent couldn't do without it. Rule 3 says that if the product works without FalkorDB, the graph is "decoration".
- "Same question twice": run at depth 1, then at depth 4, and a hidden multi-hop link appears with its path.
- The LLM never writes Cypher. It picks from fixed, parameterized tools.
- Every answer returns its path.
- Unknown entities get "not in graph", never a guess.
- An action, then a re-run that proves the effect (count drops to 0).
- Real public data at scale plus one measured result.
- Visible use of FalkorDB's newest features: `algo.maxFlow`, `GRAPH.COPY` and multi-graph.

**The five moments the demo must deliver** (build everything toward these):

1. **Hidden depth.** At depth 1, "grep" finds **2** exposed pipelines. At depth 4, ChainBreaker finds **11**, of which **9 are hidden**, and **1 is pinned to a SHA but still exposed**.
2. **Path behind every answer.** Each hop shows file and line.
3. **Min-cut.** "**4 line changes** make all 11 safe" (or 3 changes for the 9 high-value ones). Computed by FalkorDB `algo.maxFlow`, and the UI says which engine was used.
4. **Real action.** Real PRs in the demo org, then merge and tag moves, then rescan, and exposure is **0**.
5. **Honesty.** An unknown action gets "not in graph", and every name in an agent answer is verified against tool results ("Grounded: 7/7").

**Scale proof:** the same analysis runs on ~1,000 real public CNCF repos, with measured, aggregate-only numbers.

**Rules to respect** (from the event rules page):

- **Rule 2:** FalkorDB must be the primary database.
- **Rule 6:** only public, synthetic or own data.
- **Rule 10:** the README must contain setup steps, the graph data model, the Cypher queries and algorithms used, the demo video, a live deploy or local setup, and the track entered.
- **Rule 11:** AI assistance must be disclosed.

---

## 2. Ground rules for Claude Code

1. **Work in checkpoint order** (CP0 → CP14). A checkpoint is done only when all its "Done when" checks pass.
2. **Commit after every checkpoint:** `git add -A && git commit -m "<exact message from the checkpoint>" && git push`. If push fails (no remote or auth), keep going and note it in NOTES.md.
3. **Also commit mid-checkpoint** whenever a sub-step works and you're about to try something risky. Use the prefix `wip(cpNN): ...`.
4. **Never commit** `.env`, tokens, `data/cache/` or `data/raw/`. Commit `.env.example`.
5. **Cypher lives only in our code** (`chainbreaker/queries.py` plus module constants). LLM output is never executed as Cypher.
6. **GitHub writes only inside `DEMO_ORG`.** Enforce it in code: every write helper asserts `owner.lower() == DEMO_ORG.lower()`. At API level, writes also need `ADMIN_TOKEN`.
7. **Never fetch, print or store secret values.** Store only secret names, which already appear in public workflow files.
8. **CNCF dataset:** repo and workflow names are pseudonymized in the committed snapshot and in public mode (see 8.8). Action names stay visible.
9. **When FalkorDB differs from this plan:** check `CALL dbms.procedures()` and the docs, adapt, and log what you found in NOTES.md.
10. **Keep it simple:** typed Python, small modules, no frontend build step, no ORMs.
11. **STOP and tell Divy exactly what's wrong if:**
    - `.env` lacks `GITHUB_TOKEN`, `DEMO_ORG` or `ANTHROPIC_API_KEY`;
    - `GET /orgs/{DEMO_ORG}` fails;
    - the token lacks the `workflow` scope (seen in the `X-OAuth-Scopes` header).
12. **If you're running behind,** use the cut list in Appendix J. Never skip a commit.

---

## 3. Product behaviour (what the user can do)

| # | Flow | Where |
|---|---|---|
| 1 | Switch dataset: **demo** (live org), **cncf** (~1k real repos), **tj-actions 2025 replay**. Each is its own FalkorDB graph | top bar |
| 2 | Search an action and click **Simulate compromise** (creates an `Advisory`) | left panel |
| 3 | See exposure: depth slider 1–6, big numbers (grep vs. real, hidden, pinned-but-exposed, by severity), graph animation, list | left + center |
| 4 | Click a workflow to see its path hop by hop, with file and line, `uses:` value, triggers, permissions and secret names | drawer |
| 5 | **Compute minimal fix**: min-cut edges glow, fix list by type (PIN / REPIN / VENDOR), "N changes protect M (naive: M)", engine badge | right panel |
| 6 | **Simulate fix** (`GRAPH.COPY` what-if): shows before and after, which should be 0 | right panel |
| 7 | **Open PRs → Merge & continue → Rescan** (demo dataset, admin only): real PRs, then exposure 0 | right panel |
| 8 | **Ask the agent** in natural language: a tool-call timeline, a final answer with paths and a grounding badge | right panel tab |
| 9 | **Leaderboard**: most load-bearing actions (PageRank + transitive reach + share of mutable refs) | tab |
| 10 | **Replay**: step through the 2025 tj-actions chain with captions and the source link | tab |

---

## 4. Architecture

```mermaid
flowchart LR
  GH[(GitHub GraphQL + REST)] -->|crawl: workflows, action.yml at refs, reusable workflows| CR[crawler]
  CR --> CJ[crawl.json snapshot]
  CJ --> LD[loader]
  LD --> FDB[(FalkorDB 6.x\ncb:demo · cb:cncf · cb:replay-tj-2025\n+ scratch copies)]
  FDB --> AN[analysis: blast · paths · leaderboard]
  FDB --> FX[fix planner: algo.maxFlow min-cut\nGRAPH.COPY what-if]
  AN & FX --> TL[fixed tool catalogue]
  TL --> AG[agent loop: Anthropic tool use\n+ grounding validator + approval gate]
  TL --> MCP[MCP server stdio]
  AN & FX & AG --> API[FastAPI + SSE]
  API --> UI[web console: force-graph]
  FX --> PR[PR engine: demo org only]
  PR --> GH
```

**Stack** (pin these):

- **Python 3.12**, with `FalkorDB==1.8.0` (import `from falkordb import FalkorDB`), `fastapi`, `uvicorn[standard]`, `httpx`, `ruamel.yaml`, `pydantic>=2`, `typer`, `networkx`, `anthropic`, `mcp[cli]`, `python-dotenv`, `pytest`
- **FalkorDB server:** Docker `falkordb/falkordb:latest` (v6.0.x; DB on 6379, Browser on 3000). Do not use Neo4j drivers or Bolt (Bolt support was removed).
- **Frontend:** static `web/index.html`, `web/app.js` and `web/styles.css`. force-graph 1.52.0 from `https://unpkg.com/force-graph@1.52.0`. Google Fonts: Inter and JetBrains Mono.
- **LLM:** Anthropic Messages API with tool use. The model comes from env `ANTHROPIC_MODEL` (default `claude-sonnet-5-5`; check https://docs.claude.com/en/docs/about-claude/models if it errors).

---

## 5. Repo layout

```
chainbreaker/
  PLAN.md  NOTES.md  README.md  DEMO.md  LICENSE(MIT)
  pyproject.toml  .env.example  .gitignore
  docker-compose.yml  Dockerfile  Caddyfile
  chainbreaker/
    __init__.py
    config.py          # env + constants
    db.py              # FalkorDB connection, graph names, timed query helpers
    queries.py         # ALL Cypher strings (constants / small builders)
    cli.py             # Typer CLI: `cb ...`
    github/
      gql.py           # GraphQL client: batching, cache, retry, rate limit
      rest.py          # REST helpers (demo-org writes guarded)
      discover.py      # repo discovery (orgs)
    parse/
      uses.py          # parse a `uses:` string
      workflow.py      # workflow YAML → facts (+ severity)
      action.py        # action.yml → facts
    ingest/
      crawl.py         # crawl pipeline → crawl.json
      load.py          # crawl.json → FalkorDB graph
      snapshot.py      # export/import (+ redaction)
    analysis/
      advisory.py      # simulate compromise, relink
      blast.py         # blast radius, depth, pinned-but-exposed, paths, viz subgraph
      fix.py           # capacities, maxFlow (FalkorDB) + networkx fallback, cut → fixes, simulate
      leaderboard.py   # pagerank, reach, stats
      redact.py
    demo/
      scenario.py      # Appendix A files as Python data
      seed.py          # create/reset demo org
      apply.py         # PRs, merge, tag moves, rescan
    agent/
      tools.py         # tool registry: pydantic args + functions + Anthropic schemas
      validator.py     # grounding check
      prompts.py
      loop.py          # tool-use loop → event generator
      memory.py        # Finding nodes
    mcp_server.py
    api.py             # FastAPI app (+ static web)
  web/  index.html  app.js  styles.css
  scripts/ (optional helpers)
  data/
    snapshots/  demo.crawl.json.gz  cncf.crawl.json.gz (redacted)
    replay_tj_2025.json
    demo_ground_truth.json
    cache/ (gitignored)
  eval/  RESULTS.md  results.json
  tests/  fixtures/  test_parse.py  test_cut.py  test_tools.py  test_demo_truth.py
```

---

## 6. Environment variables (`config.py` reads `.env` with python-dotenv)

| Var | Default | Use |
|---|---|---|
| `GITHUB_TOKEN` | required | GraphQL crawl + demo writes |
| `DEMO_ORG` | required | the only org we write to |
| `ANTHROPIC_API_KEY` | required for agent | |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | agent model |
| `FALKORDB_HOST` / `FALKORDB_PORT` / `FALKORDB_PASSWORD` | `localhost` / `6379` / `chainbreaker` | DB |
| `PUBLIC_MODE` | `0` | `1` = redact CNCF names + disable writes without admin |
| `ADMIN_TOKEN` | `change-me` | header `X-Admin-Token` for write endpoints |
| `REDACTION_SALT` | `change-me` | pseudonyms |
| `FIX_ENGINE` | `auto` | `auto` / `falkordb` / `networkx` |
| `MAX_DEPTH` | `6` | traversal cap (clamp 1..8) |
| `CNCF_MAX_REPOS_PER_ORG` | `30` | crawl size |
| `AGENT_RATE_LIMIT` | `12` | agent requests / 10 min / IP in public mode |

---

## 7. Graph model

**Graphs** (multi-graph, one per dataset):

- `cb:demo`
- `cb:cncf`
- `cb:sample` (dev only)
- `cb:replay-tj-2025`
- scratch copies: `cb:<ds>:scratch:<8hex>`, created with `GRAPH.COPY`, always deleted after use

**Nodes** (all have a string `id`; property values must be primitives or lists of primitives):

| Label | Key props |
|---|---|
| `Repo` | `id` (`owner/repo`, lowercase), `stars`, `default_branch`, `redacted` (bool) |
| `Workflow` | `id` (`owner/repo:.github/workflows/x.yml`, or `…@ref` for a reusable workflow at a ref), `repo_id`, `path`, `name`, `triggers` (list), `secrets` (list of names), `perms` (`write`/`read`/`default`), `id_token_write` (bool), `prt` (bool), `severity` (`HIGH`/`MED`/`LOW`), `severity_reasons` (list), `entry` (bool), `at_ref` (null for HEAD), `pinned` (bool, at-ref only) |
| `Action` | `id` (`owner/repo` or `owner/repo/path`, lowercase), `owner`, `repo`, `path`, `search` (space-separated words for full-text) |
| `ActionRef` | `id` (`<action_id>@<ref>`), `action_id`, `ref`, `pinned` (40-hex SHA), `local` (bool), `kind` (`composite`/`node`/`docker`/`unknown`/`unresolved`) |
| `DockerImage` | `id` (`docker://…`), `pinned` (has `@sha256:`) |
| `Advisory` | `id` (`CB-ADV-<n>`), `action_id`, `refs` (list or empty = all mutable), `known_good_sha`, `created_at`, `summary` |
| `FixPlan` | `id`, `advisory_id`, `targets` (`high`/`all`), `cut_size`, `protected`, `naive`, `engine`, `created_at` |
| `Fix` | `id`, `plan_id`, `type` (`PIN`/`REPIN`/`VENDOR`), `src_id`, `src_label`, `dst_id`, `dst_label`, `file_repo`, `file_path`, `lines` (list), `old_uses`, `new_uses`, `protects`, `phase` (1/2/0 = manual) |
| `FixPR` | `id`, `url`, `number`, `repo`, `phase`, `status` |
| `Finding` | `id`, `question`, `answer`, `created_at`, `action_id` |

**Relationships:**

| Type | From → To | Props |
|---|---|---|
| `HAS_WORKFLOW` | Repo → Workflow | |
| `USES` | Workflow\|ActionRef → ActionRef\|Workflow(at ref)\|DockerImage | `kind` (`step`/`call`/`image`), `file_repo`, `file_path`, `lines` (list of 1-based ints), `uses` (raw string), `src_immutable` (bool), `weight` (=1) |
| `VERSION_OF` | ActionRef → Action | |
| `COMPROMISES` | Advisory → ActionRef | |
| `INCLUDES` | FixPlan → Fix | |
| `FOR` | FixPlan → Advisory | |
| `IMPLEMENTS` | FixPR → Fix | |
| `ABOUT` | Finding → Action | |

> Use **one** relationship type `USES` (property `kind`) for step uses, reusable-workflow calls and docker images. That keeps var-length traversals and `algo.maxFlow` to a single type.

**Indexes:** create them before loading, wrapped in try/except "already exists".

```
CREATE INDEX FOR (n:Repo) ON (n.id)
CREATE INDEX FOR (n:Workflow) ON (n.id)
CREATE INDEX FOR (n:Action) ON (n.id)
CREATE INDEX FOR (n:ActionRef) ON (n.id)
CREATE INDEX FOR (n:DockerImage) ON (n.id)
CREATE INDEX FOR (n:Advisory) ON (n.id)
CREATE INDEX FOR (n:FixPlan) ON (n.id)
CALL db.idx.fulltext.createNodeIndex('Action', 'search')
```

Full-text indexes build asynchronously. If a full-text query fails right after creation, fall back to `WHERE a.id CONTAINS $q`.

---

## 8. Core semantics (implement exactly as written)

### 8.1 Parsing a `uses:` string (`parse/uses.py`)

`parse_uses(s, ctx_owner, ctx_repo, ctx_ref, in_action: bool) -> UsesRef | None`

- Strip whitespace. If it starts with `${{`, it is **dynamic**: record it but create no edge, and count it in stats.
- `docker://image[:tag][@sha256:…]` → `DockerImage`, with `pinned` = contains `@sha256:`.
- `./path` (local):
  - In a **workflow** file:
    - If the path matches `.github/workflows/*.ya?ml` → reusable workflow in the same repo at `ctx_ref`.
    - Otherwise → local action `ctx_owner/ctx_repo/<path>` at `ctx_ref`, with `local=true`.
  - Inside an **action** file: mark it `unresolved` (GitHub resolves it against the caller's workspace). Create a leaf `ActionRef` with `kind=unresolved`.
- Otherwise match `^([^/@\s]+)/([^/@\s]+)((?:/[^@\s]+)?)@(\S+)$`:
  - `owner`, `repo`, `path` (strip `/`), `ref`. Lowercase owner, repo and path; keep `ref` as written.
  - If the path matches `.github/workflows/[^/]+\.ya?ml` → **reusable workflow** at ref.
  - Else → **action** `owner/repo[/path]` at ref.
- `pinned = re.fullmatch(r"[0-9a-f]{40}", ref) is not None`. Tags and branches are **mutable**.
- Anything else is invalid: log it and skip.

### 8.2 Workflow facts and severity (`parse/workflow.py`)

- **YAML:** use `ruamel.yaml` (`YAML(typ="safe")`, YAML 1.2), so `on:` stays a string key. Still accept a `True` key as `on` defensively.
- **`triggers`:**
  - a string → `[s]`
  - a list → the list
  - a map → its keys
- **`permissions`** (top level and per job) can be a string (`read-all`, `write-all`) or a map.
  - `perms = "write"` if `write-all` appears or any scope is `write` (top or any job).
  - Otherwise `perms = "default"` if there is no top-level `permissions` **and** at least one job has no job-level `permissions`.
  - Otherwise `perms = "read"`.
  - `id_token_write = id-token: write` anywhere.
- **`secrets`:** regex over the **raw text**, `\$\{\{\s*secrets\.([A-Za-z0-9_]+)\s*\}\}`, unique and sorted. Keep `GITHUB_TOKEN` in the list, but it doesn't count as a secret for severity.
- **Uses sites:**
  - `jobs.<id>.steps[i].uses` → `kind=step`
  - `jobs.<id>.uses` → `kind=call` (reusable workflow)
  - Record `job` and `step` index.
- **Line numbers:** scan the raw text lines. For each uses value, take the next unused line containing `uses:` and the exact value. Store 1-based line numbers. If the same (src, dst) pair repeats, merge the line lists.
- **`prt`** = `pull_request_target` in triggers.
- **`entry`** = `False` if `triggers == ["workflow_call"]`, else `True`. Called-only workflows are not entry points.
- **Severity** is deterministic. Keep a list of reasons.
  - `has_secrets` = any secret other than `GITHUB_TOKEN`.
  - **HIGH** if any of these:
    - `prt`;
    - `has_secrets and perms in ("write","default")`;
    - `has_secrets and id_token_write`.
  - **MED** if `has_secrets or perms in ("write","default")`.
  - **LOW** otherwise.
  - Reasons are strings like `"pull_request_target trigger"`, `"secrets: AWS_ACCESS_KEY_ID, …"`, `"contents: write"` or `"no permissions block (repo default)"`.

### 8.3 Action facts and recursive resolution (`parse/action.py`, `ingest/crawl.py`)

- Fetch `action.yml`, then `action.yaml`, at `"{ref}:{path}/action.yml"` (no leading slash when the path is empty). If neither exists → `kind=unresolved`.
- `runs.using`:
  - `composite` → parse `runs.steps[*].uses` (with `in_action=True`), lines from raw text;
  - `docker` → if `runs.image` starts with `docker://`, add an edge to a `DockerImage`; else leaf;
  - `node*` → leaf `node`;
  - else `unknown`.
- **Reusable workflow at a ref:** fetch `"{ref}:{workflow_path}"` and parse like a workflow. Its node id is `owner/repo:<path>@<ref>`, with `at_ref=ref`, `pinned=is_sha(ref)`, `entry=False`, and no severity.
- **BFS** over discovered refs up to `MAX_DEPTH` levels, memoized by id, batched 25 per GraphQL query (Appendix C).
- **`src_immutable`** for an edge is `True` only when its **source** is an `ActionRef` or at-ref `Workflow` whose ref is a SHA (a file at an immutable commit). Edges from HEAD workflows and from mutable refs are changeable.

### 8.4 Exposure (`analysis/advisory.py`, `analysis/blast.py`)

- **Advisory:** `simulate_compromise(action_id, refs=None)` creates `Advisory` with `COMPROMISES` edges to every `ActionRef` of that action with `pinned=false` (or only the listed refs). It is idempotent: an existing advisory for the same action is returned unless `new=True`. In the demo dataset, set `known_good_sha` from `data/demo_ground_truth.json` when the action is `<org>/cb-changed-files`.
- **Exposed workflow** = a HEAD workflow with `entry=true` that can reach a compromised `ActionRef` via `USES*1..D`. `depth` = minimum path length.
- **Hidden** = exposed with `depth ≥ 2`. **Depth-1 ("grep") count** = exposed with `depth = 1`.
- **Pinned-but-exposed** = exposed workflows where the first hop of **every** exposing path is a pinned node (`nodes(p)[1].pinned = true`). They pinned their direct dependency to a SHA and are still exposed.
- **Relink after every rebuild:** delete `COMPROMISES` edges, then recreate them to the current mutable refs of `adv.action_id`. If an action no longer has mutable refs, the advisory compromises nothing and exposure is 0.

### 8.5 Fix planning: min-cut (`analysis/fix.py`)

The max-flow/min-cut theorem: give every changeable `uses:` line a capacity equal to the cost of changing it. The max flow from the target workflows (sources) to the compromised refs (sinks) then equals the minimum total cost of changes that disconnect them, and the saturated cut edges are the change list.

**Steps:**

1. **Sources:**
   - `targets="high"` → exposed workflows with `severity="HIGH"`;
   - `targets="all"` → all exposed.

   **Sinks:** the advisory's compromised `ActionRef`s.
2. `scratch = GRAPH.COPY` the dataset graph to `cb:<ds>:scratch:<8hex>`. In Python: `g.copy(name)`, then `db.select_graph(name)`. Time it and report `copy_ms`.
3. **Capacities** in the scratch graph (Appendix D, Q-CAP-1 and Q-CAP-2):
   - `src_immutable = true` → **10000**. The line lives in an immutable commit and can't be changed.
   - else, destination is **compromised** → **1** (**PIN**: pin to the known-good SHA).
   - else, destination is **pinned** → **1** (**REPIN**: move the pin to the commit that contains the upstream fix).
   - else → **3** (**VENDOR**: vendor or replace the intermediate action. This is manual, so it costs more).
4. **Max flow:**
   - **FalkorDB first.** Use `algo.maxFlow({sourceNodes, targetNodes, relationshipTypes:['USES'], capacityProperty:'cap'})` with `YIELD nodes, edges, edgeFlows, maxFlow` (Appendix D, Q-MAXFLOW). The output shape is **unverified on v6.0.x**. In CP6, first run the probe (Appendix D, Q-PROBE) and print the raw result, then write the parser for what it actually returns. Log it in NOTES.md.
   - **Cut extraction** (Python): export all `USES` edges of the scratch graph (`id(e), id(s), id(d), e.cap, s.id, d.id, labels`). Map flows by edge id (missing = 0). BFS the residual graph from the sources: follow a forward edge if `flow < cap`, and a backward edge if `flow > 0`. Cut = edges with `src` reachable and `dst` not reachable.
   - **Validate:** (a) the sum of cut capacities equals `maxFlow`; (b) removing the cut edges leaves no path from any source to any sink. If either check fails, or the procedure is missing, use the **networkx fallback**: `nx.minimum_cut` with super-source and super-sink edges of capacity `10**6`, using finite capacities only. Record `engine = "falkordb.algo.maxFlow"` or `"networkx (fallback)"`. The UI must show it.
5. **Cut edge → Fix:**
   - **type** follows from the capacity rule.
   - **`old_uses`** = edge `uses`.
   - **`new_uses`:**
     - PIN → `<action_id>@<known_good_sha>`, or the placeholder `<VERIFIED-SHA>` and phase 0 if unknown;
     - REPIN → decided at apply time (phase 2);
     - VENDOR → none (phase 0, manual recommendation).
   - **`phase`:** PIN with a known SHA → 1; REPIN → 2; else 0.
   - **`protects`** = the number of sources that have at least one path through this edge.
   - **`naive`** = the number of sources (one fix per pipeline).
6. **Persist** `FixPlan`, `INCLUDES` and `Fix` nodes in the **main** graph, then delete the scratch graph (always, in `finally`).

### 8.6 Simulate a fix (what-if with `GRAPH.COPY`)

Copy the graph to a scratch graph. Delete the plan's cut edges, matching by `src_id`/`dst_id` with labels (`MATCH (s:<L> {id:$s})-[e:USES]->(d:<L> {id:$d}) DELETE e`). Re-run blast for the plan's sources, then delete the scratch graph. Return `{before, after, copy_ms, graph_ms}`. For valid plans, `after` must be 0.

### 8.7 Applying fixes in the demo org (`demo/apply.py`, admin only)

- **Phase 1** (`open`): for each phase-1 fix:
  - The file is the `file_repo`'s default branch at `file_path`. For an `ActionRef` source, that is the action repo's `<path>/action.yml`.
  - Create branch `chainbreaker/<plan_id>-<n>`.
  - Edit **only the recorded lines**: replace `old_uses` with `new_uses` and append ` # <old_ref>` if the line has no comment.
  - Commit through the contents API, open a PR (body template in Appendix A.6) and record a `FixPR` node.
- **Merge & continue** (`merge`):
  1. Squash-merge the phase-1 PRs. If a fix's source is an `ActionRef` whose ref is a **tag** (check `git/ref/tags/<ref>`), move that tag to the merge commit (`PATCH git/refs/tags/<ref>` with `force:true`). Remember `fixed_sha[action_id]`.
  2. For REPIN fixes: `new_sha = fixed_sha[dst action_id]`, or the head of the action repo's default branch. Then open and merge the PR the same way.
  3. **Rescan**: crawl the demo with no cache, rebuild, relink advisories, run blast and return the counts.
- **Reset** (`reset-demo`):
  - close open `chainbreaker/*` PRs and delete those branches;
  - rewrite every scenario file to its original content;
  - recreate the commit SHAs, move the tags back;
  - rewrite `data/demo_ground_truth.json`.

  The topology and expected numbers stay the same; only the SHAs change.

### 8.8 Redaction (`analysis/redact.py`)

- `pseudo(name) = "repo-" + sha1(SALT + name)[:6]`.
- For the CNCF dataset, redact:
  - `Repo.id`;
  - HEAD `Workflow.id`, which becomes `repo-xxxxxx:<basename>.yml`;
  - **local** actions (`local=true`).
- **Never redact** non-local `Action`/`ActionRef` ids. These are public actions, and the leaderboard depends on them.
- `cb snapshot-export --dataset cncf --redact` writes the redacted snapshot that gets committed and deployed. Raw crawl data stays in gitignored `data/cache/`.

### 8.9 Agent rules (`agent/*`)

- **Fixed tool catalogue** (Appendix E). The LLM never writes Cypher.
- **Four outcome shapes**, taken from the organizers' guide:
  - `answered_with_path`
  - `answered_from_memory` (with date)
  - `not_in_graph`
  - `unknown_entity` (with suggestions)
- **Grounding validator:** extract `owner/repo[/path][@ref]` and `repo-xxxxxx` tokens from the final text and compare them with all ids seen in this turn's tool results.
  - If any are unverified, retry once with the message "These names were not returned by any tool: […]. Rewrite using only tool results."
  - If they are still unverified, replace them with `[unverified]`.
  - Emit `grounding: {verified, total, unverified[]}`.
- **Approval gate:** the agent can only call `request_fix_approval`. Opening and merging PRs happens through UI buttons that call admin endpoints.
- **Memory:** after each answered question, write a `Finding` node (question, answer, date, action). `recall_findings` returns past findings with dates.

---

## 9. Checkpoints

> Each checkpoint lists: **Goal → Build → Done when → Commit.** Commit and push after every one.

---

### CP0: Scaffold, config, FalkorDB up, capability check

**Goal:** the project runs, FalkorDB is up, and we know which algorithms this server has.

**Build:**

- `pyproject.toml`: package `chainbreaker`, console script `cb = "chainbreaker.cli:app"`, extras `dev = ["pytest"]`. Install with `python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`.
- `.gitignore`: `.env`, `.venv/`, `__pycache__/`, `data/cache/`, `data/raw/`, `*.log`.
- `.env.example` with every var from section 6.
- `docker-compose.yml` (Appendix H.1). Bring up `falkordb` only: `docker compose up -d falkordb`.
- `config.py`, `db.py`:
  - `get_db()` returns a singleton `FalkorDB(host, port, password)`;
  - `graph(ds)` → `select_graph(f"cb:{ds}")`;
  - `q(ds, cypher, params, ro=False)` runs `ro_query` when `ro` is true, times the call, and accumulates a per-request `graph_ms` and `query_count` (contextvar).
- **`cb check`:**
  - prints the FalkorDB module version (`MODULE LIST` through `db.connection.execute_command`);
  - runs `CALL dbms.procedures() YIELD name RETURN name` on a temp graph;
  - prints yes/no for `algo.maxFlow`, `algo.HarmonicCentrality`, `algo.SPpaths`, `algo.pageRank`, `algo.betweenness`, `algo.WCC`;
  - checks GitHub: `GET /user`, prints the `X-OAuth-Scopes` header, `GET /orgs/{DEMO_ORG}`;
  - checks that `ANTHROPIC_API_KEY` is present;
  - appends the results to `NOTES.md`.
- `NOTES.md` with the headings: Decisions, Surprises, FalkorDB capabilities, Measured numbers.

**Done when:**

- `docker compose ps` shows falkordb running.
- `cb check` prints the procedure list with yes/no for each algorithm, `scopes` including `repo` and `workflow`, and `org OK`. If the org or a scope is missing → **STOP**.
- `pytest -q` runs (0 tests is fine).

**Commit:** `cp00: scaffold, config, falkordb up, capability check`

---

### CP1: Parsers and severity (with tests)

**Goal:** correct parsing of `uses:`, workflows and action files.

**Build:**

- `parse/uses.py`, `parse/workflow.py` and `parse/action.py`, exactly per 8.1–8.3.
- `demo/scenario.py`: the Appendix A files as Python dicts, with tokens `__ORG__`, `__SHA_CHANGED_FILES_GOOD__` and `__SHA_LINT_REPORTER_V1__`. Use plain `str.replace` (`str.format`/`Template` break on `${{ }}`).
- `tests/fixtures/` plus `tests/test_parse.py` covering:
  - uses forms: `actions/checkout@v4`, `github/codeql-action/init@v3`, `./.github/actions/setup`, `./.github/workflows/reusable.yml`, `org/repo/.github/workflows/ci.yml@main`, `docker://alpine:3.19`, `docker://alpine@sha256:<64hex>`, `${{ matrix.x }}`, a 40-hex SHA vs a tag;
  - `on:` as a string, a list and a map;
  - permissions summaries: `write-all`, scope maps, missing (`default`);
  - the secrets regex;
  - line numbers;
  - **severity of every demo workflow** in Appendix A, matching the expected values in Appendix B.

**Done when:** `pytest tests/test_parse.py -q` → all pass.

**Commit:** `cp01: parsers for uses, workflows, actions + severity with tests`

---

### CP2: GitHub GraphQL crawler

**Goal:** crawl repos → workflows → action files at refs (recursively) into a normalized `crawl.json`.

**Build:**

- **`github/gql.py`:**
  - `post(query)` sends `Authorization: bearer`;
  - adds `rateLimit { remaining resetAt }` to every query and sleeps when `remaining < 50`;
  - retries on 502/403-secondary with exponential backoff (max 5);
  - halves the batch size on timeouts;
  - logs `errors` and treats NOT_FOUND as missing;
  - **disk cache** at `data/cache/github/<sha1(query)>.json` (on by default; `--no-cache` bypasses it).
- **`github/discover.py`:** `org_repos(login, limit)` uses the org query from Appendix C.1, skips archived and fork repos, and orders by stars.
- **`ingest/crawl.py`:**
  - `crawl(dataset, orgs, max_repos, no_cache) -> dict`
  - Batch-fetch workflows (Appendix C.2, 25 repos per query).
  - Parse them, then BFS-resolve `ActionRef`s and reusable workflows (Appendix C.3, 25 per query) up to `MAX_DEPTH`.
  - Output the schema in Appendix C.4 to `data/cache/<dataset>/crawl.json`.
  - Print a summary: repos, workflows (entry/total), action refs by kind, unresolved, dynamic uses, edges, cache hits and elapsed time.
- **CLI:** `cb crawl --dataset <name> [--orgs a,b] [--max-repos N] [--no-cache]`.
  - `dataset=demo` → orgs `[DEMO_ORG]`, `--no-cache` forced.
  - `dataset=cncf` → `CNCF_ORGS` from Appendix C.5.

**Done when:**

- `cb crawl --dataset sample --orgs open-telemetry,cilium --max-repos 5` prints a summary with >0 workflows, >0 action refs and at least one `composite`.
- Running it a second time shows cache hits and finishes in under 5 seconds.

**Commit:** `cp02: github graphql crawler with batching, cache, recursive action resolution`

---

### CP3: Loader into FalkorDB, plus start the CNCF crawl

**Goal:** `crawl.json` → graph `cb:<dataset>`, with indexes and stats.

**Build:**

- **`ingest/load.py`:** `load(dataset, crawl)`:
  - ensure indexes;
  - `DETACH DELETE` crawl-derived labels (`Repo`, `Workflow`, `Action`, `ActionRef`, `DockerImage`), one label at a time;
  - `UNWIND` batch inserts of 1,000 (Appendix D, Q-LOAD-*);
  - relink advisories (8.4).

  It never deletes `Advisory`, `FixPlan`, `Fix`, `FixPR` or `Finding` nodes.
- **`analysis/leaderboard.py::stats(ds)`:**
  - counts per label;
  - `USES` edge count;
  - share of mutable vs pinned third-party references (from HEAD workflows, `local=false`);
  - entry workflows;
  - crawl date.
- **CLI:** `cb load --dataset X` and `cb stats --dataset X`.
- **Then start the full CNCF crawl in the background** (it takes a while): `nohup cb crawl --dataset cncf > data/cache/crawl_cncf.log 2>&1 &`. Keep building while it runs.

**Done when:**

- `cb load --dataset sample && cb stats --dataset sample` prints counts that match the crawl summary.
- Running the load twice gives identical counts.
- In FalkorDB Browser (http://localhost:3000), graph `cb:sample` returns paths for `MATCH p=(w:Workflow)-[:USES*1..3]->(:ActionRef) RETURN p LIMIT 5`.
- The CNCF crawl is running (`tail data/cache/crawl_cncf.log` shows progress).

**Commit:** `cp03: falkordb loader, indexes, stats; cncf crawl started`

---

### CP4: Demo org seeder and the demo dataset

**Goal:** a real GitHub org with the scenario from Appendix A, loaded as `cb:demo`, plus ground truth.

**Build:**

- **`github/rest.py`:** helpers from Appendix C.6. Every write helper asserts `owner == DEMO_ORG`.
- **`demo/seed.py::seed()`** (idempotent; existing repos are reused):
  1. Create the repos in the order given in Appendix A.1 (`auto_init: true`), retrying the contents API for ~10 s after creation.
  2. `cb-changed-files`: put `action.yml` → commit **G** → create tag `v3` → G.
  3. `cb-setup-reviewer`: put `action.yml` → tag `v1`.
  4. `cb-lint-reporter`: put `action.yml` (references `@v3` and `@v1`) → commit **L1** → tag `v1` → L1.
  5. `cb-ci-toolkit` → tag `v2`. `cb-release-kit` (pins `@G`) → tag `v1`. `cb-shared-workflows` (`.github/workflows/ci.yml` on main).
  6. App repos: put their workflow files (`mobile-app` pins `@L1`), plus a README in every repo: "Synthetic repo for the ChainBreaker lab. No real secrets."
  7. Write `data/demo_ground_truth.json` (Appendix B) with the real org name and SHAs.
- **`demo/seed.py::reset()`** per 8.7.
- **CLI:** `cb seed-demo`, `cb reset-demo`, then `cb crawl --dataset demo && cb load --dataset demo`.

**Done when:**

- `cb seed-demo` prints 18 repo URLs and the SHAs G and L1.
- `cb crawl --dataset demo && cb load --dataset demo && cb stats --dataset demo` prints:
  - **Repo 18**
  - **Workflow 14** (13 HEAD, of which 12 are entry, + 1 at-ref)
  - **ActionRef 7**
  - **Action 5**
  - **USES 20**

  If different, explain why in NOTES.md and fix the scenario or parser until they match.
- Sanity Cypher in Browser on `cb:demo`: `MATCH p=(w:Workflow)-[:USES*1..6]->(r:ActionRef) WHERE r.id CONTAINS 'cb-changed-files@v3' RETURN p` shows the chains.

**Commit:** `cp04: demo org seeder, reset, demo dataset + ground truth`

---

### CP5: Advisories, blast radius, depth, paths

**Goal:** the core "hidden depth" analysis.

**Build:**

- **`analysis/advisory.py`:** `simulate_compromise(ds, action_id, refs=None, new=False)` and `relink(ds)`.
- **`analysis/blast.py`:**
  - `blast(ds, adv_id, max_depth)` returns `{exposed:[{workflow, repo, severity, depth, reasons}], by_depth:{1:n,…}, by_severity, exposed_total, depth1, hidden, pinned_but_exposed:[…], high_total, graph_ms}` (Appendix D, Q-BLAST and Q-PINNED). Inline the depth integer after clamping, because a parameter can't be a var-length bound.
  - `explain(ds, adv_id, workflow_id)` uses `algo.SPpaths` (Q-PATH). If that fails, fall back to plain shortest var-length (Q-PATH-FALLBACK). It returns hops with `{from, to, uses, file_repo, file_path, lines, pinned}`.
  - `viz_subgraph(ds, adv_id, max_depth)` returns nodes and links for all paths to **any** ref of the action (compromised **and** pinned/safe), with flags `compromised`, `exposed`, `severity`, `depth`, `pinned`, `kind` (Q-VIZ). Cap at 600 nodes and report the total.
- **Redaction:** applied at the output layer only when `PUBLIC_MODE=1` and the dataset is `cncf`. The committed snapshot is already redacted.
- **CLI:** `cb advisory --dataset demo --action <org>/cb-changed-files`, `cb blast --dataset demo --advisory <id> [--depth N]`, `cb path --dataset demo --advisory <id> --workflow <wid>`.
- **`tests/test_demo_truth.py`** (skipped if `cb:demo` is missing): compare against `data/demo_ground_truth.json`.

**Done when:**

- `cb blast --depth 6` on the demo prints **exposed 11, depth-1 2, hidden 9, HIGH 9, pinned-but-exposed 1 (`mobile-app`)**, with the depths in Appendix B.
- `cb blast --depth 1` prints 2.
- `cb path` for `infra-terraform` prints **4 hops** with file:line, through `cb-shared-workflows … ci.yml@main → cb-ci-toolkit@v2 → cb-lint-reporter@v1 → cb-changed-files@v3`.
- `pytest tests/test_demo_truth.py -q` passes.

**Commit:** `cp05: advisories, blast radius, depth comparison, pinned-but-exposed, path evidence`

---

### CP6: Min-cut fix planner and what-if simulation

**Goal:** "N changes protect M", computed in FalkorDB, plus a `GRAPH.COPY` what-if.

**Build:**

- First run **Q-PROBE** (Appendix D) on a tiny scratch graph with a known answer, and print the raw `algo.maxFlow` output. Write `parse_maxflow()` for the real output shape and log it in NOTES.md. If the procedure is missing, set `engine=networkx` and log that.
- **`analysis/fix.py`:**
  - `plan_fix(ds, adv_id, targets)` exactly per 8.5, with validation and fallback;
  - `simulate_fix(ds, plan_id)` per 8.6;
  - scratch graphs are always deleted in `finally`, and an `atexit` sweep deletes leftover `cb:*:scratch:*` graphs.
- **`tests/test_cut.py`:** on a synthetic in-memory edge list, residual-cut extraction (given flows) and the networkx fallback produce the same cut value. Include one case with a parallel chokepoint.
- **CLI:** `cb plan --dataset demo --advisory <id> --targets high|all` and `cb simulate --dataset demo --plan <id>`.

**Done when:**

- `--targets high` → **cut 3**, fixes `PIN web-frontend pr-check.yml`, `PIN cb-lint-reporter action.yml` and `REPIN mobile-app build.yml`, with naive 9 and the engine printed.
- `--targets all` → **cut 4** (adds `PIN docs-site docs.yml`), naive 11.
- `cb simulate` → **after = 0** for both plans; prints `copy_ms`.
- `pytest tests/test_cut.py -q` passes.
- NOTES.md records which engine ran and the real `algo.maxFlow` output shape.

**Commit:** `cp06: min-cut fix planner (falkordb algo.maxFlow + fallback), what-if via GRAPH.COPY`

---

### CP7: CNCF dataset, leaderboard, eval, snapshots

**Goal:** scale proof with measured numbers.

**Build:**

- When the CNCF crawl finishes: `cb load --dataset cncf`. If the crawl failed, fix it, resume from the cache and rerun.
- **`leaderboard(ds, top_k)`:**
  - PageRank (Q-PR) aggregated per `Action`;
  - for the top 25: direct users (Q-DIRECT), transitive reach (Q-REACH) and mutable reach;
  - `algo.betweenness` (optional; for "bridge" composites).

  Cache the result in memory keyed by dataset load time.
- **`cb eval`** writes `eval/results.json` and `eval/RESULTS.md`:
  - **Demo:** PASS/FAIL table vs. ground truth (exposure set, depths, pinned-but-exposed, cut high = 3, cut all = 4, simulate → 0).
  - **CNCF**, for the 20 actions with the highest transitive reach: simulate a compromise, then report `exposed_total`, `depth1`, `hidden`, hidden %, `high_total`, `pinned_but_exposed`, the naive count (HIGH) vs `cut_size` (high), and the engine. Plus ecosystem stats: repos, entry workflows, share of mutable third-party refs, share of workflows with ≥1 transitive mutable ref, max depth seen.
  - **Aggregates and action names only.** Never list CNCF repo names.
- **`cb snapshot-export --dataset cncf --redact`** → `data/snapshots/cncf.crawl.json.gz`; `cb snapshot-export --dataset demo` → `data/snapshots/demo.crawl.json.gz`. `cb snapshot-import --dataset X` loads a snapshot.

**Done when:**

- `cb stats --dataset cncf` shows ≥500 repos (if fewer, note why).
- `cb leaderboard --dataset cncf` prints the top 15.
- `eval/RESULTS.md` exists, all demo rows are PASS, and the CNCF table has 20 rows.
- Both snapshots exist. A grep of `cncf.crawl.json.gz` (zcat) for 3 known CNCF repo names returns nothing (they are redacted).
- Copy 5 headline numbers into NOTES.md › Measured numbers.

**Commit:** `cp07: cncf dataset, leaderboard, measured eval, redacted snapshots`

---

### CP8: Real PRs in the demo org (act), rescan, reset

**Goal:** the agent's real-world action, plus the proof.

**Build:**

- **`demo/apply.py`:** `open_phase1(plan_id)`, `merge_and_continue(plan_id)` and `rescan()`, per 8.7. PR body per Appendix A.6. Store `FixPR` nodes. Print each PR URL as it's created.
- **CLI:** `cb apply-demo --plan <id> --open`, `cb apply-demo --plan <id> --merge`, `cb rescan-demo`, `cb reset-demo`.

**Done when:**

- With the `targets=all` plan, `--open` creates **3 PRs** (web-frontend, docs-site, cb-lint-reporter) in `DEMO_ORG`, and the URLs open in a browser.
- `--merge` merges them, moves the `cb-lint-reporter` tag `v1`, opens and merges the **REPIN PR** for mobile-app, rescans and prints **exposed 0**.
- `cb reset-demo && cb crawl --dataset demo && cb load --dataset demo && cb blast …` shows **11** again, and `data/demo_ground_truth.json` has the new SHAs.

**Commit:** `cp08: real fix PRs in demo org (pin, repin, tag moves), rescan, reset`

---

### CP9: Fixed tool catalogue, grounding validator, MCP server

**Goal:** one tool registry, used by the in-app agent and served over MCP.

**Build:**

- **`agent/tools.py`:** the 10 tools in Appendix E. Each has:
  - a pydantic args model;
  - a function `(ds, **args) -> dict` that always includes `outcome` and `graph_ms`;
  - an Anthropic tool schema generated from the model.

  Name resolution: `find_action` uses the full-text index, then a `CONTAINS` fallback, and returns `unknown_entity` with up to 5 suggestions when nothing matches exactly.
- **`agent/validator.py`:** per 8.9, with unit tests.
- **`mcp_server.py`:** FastMCP (`from mcp.server.fastmcp import FastMCP`). Expose the same tools with a `dataset` arg (default `demo`), except `request_fix_approval`. Run with `mcp.run()` (stdio). If the import path differs in the installed `mcp` version, check `pip show mcp` and adapt.
- **`cb mcp-selftest`:** start the server over stdio with the `mcp` client (`ClientSession` + `stdio_client`), list the tools, call `blast_radius` on the demo, and print the result.
- **README snippet for Claude Desktop** (Appendix H.4).

**Done when:**

- `pytest tests/test_tools.py -q` passes:
  - an unknown action → `unknown_entity` with suggestions;
  - `blast_radius` → `answered_with_path` shape;
  - the validator flags an invented `foo/bar`.
- `cb mcp-selftest` lists 9 tools and returns demo exposure 11.

**Commit:** `cp09: fixed tool catalogue, grounding validator, MCP server`

---

### CP10: Agent loop, approval gate, memory

**Goal:** a natural-language agent that only acts through tools, shows paths and stays grounded.

**Build:**

- **`agent/prompts.py`:** the system prompt from Appendix E.1, with `{dataset}` and `{public_note}` filled in.
- **`agent/loop.py`:** `run_agent(ds, message, history) -> Iterator[event]`. A standard Anthropic tool-use loop, max 8 rounds:
  - **Each round:**
    - Call `client.messages.create(model, max_tokens=1500, system, tools, messages)`.
    - For every `tool_use` block:
      - yield `{"type":"tool_call","name","args"}`;
      - run the tool;
      - yield `{"type":"tool_result","name","summary","ms","rows"}`;
      - append the `tool_result` blocks.
  - **When `stop_reason != "tool_use"`:**
    - Run the validator (retry once).
    - Yield `{"type":"final","text","outcome","grounding","paths"}`.
    - Write a `Finding`.
  - **On any exception,** yield `{"type":"error","message"}`.
- **`agent/memory.py`:** `save_finding`, `recall_findings`.
- **CLI:** `cb ask --dataset demo "<question>"` prints events as they stream.

**Done when:**

- `cb ask "What happens if <org>/cb-changed-files is compromised?"` → tool calls (`find_action`, `simulate_compromise`, `blast_radius`, `explain_exposure`) and a final answer that leads with "11 exposed (9 hidden)", shows one path, and reports grounding N/N.
- `cb ask "Is evil-corp/backdoor-action in our CI?"` → says it is not in the graph and suggests alternatives (no invented data).
- `cb ask "Fix it with the fewest changes"` → calls `plan_fix`, `simulate_fix` and `request_fix_approval`. It opens **no** PRs.
- A new session, `cb ask "What did we find about cb-changed-files?"`, answers from memory with the date.

**Commit:** `cp10: agent loop with tool use, grounding, approval gate, memory`

---

### CP11: FastAPI endpoints and SSE

**Goal:** an API for the UI and for judges.

**Build** (`api.py`; the lifespan handler auto-imports snapshots when graphs are missing):

| Method | Path | Notes |
|---|---|---|
| GET | `/healthz` | `{ok, falkordb}` |
| GET | `/api/datasets` | `db.list_graphs()` filtered to `cb:*` (no scratch) + stats |
| GET | `/api/{ds}/stats` | |
| GET | `/api/{ds}/actions/search?q=` | |
| POST | `/api/{ds}/advisories` `{action_id, refs?}` | simulate compromise (allowed in public mode; it only writes an Advisory) |
| GET | `/api/{ds}/advisories/{adv}/blast?depth=` | |
| GET | `/api/{ds}/advisories/{adv}/graph?depth=` | viz subgraph |
| GET | `/api/{ds}/advisories/{adv}/path?workflow=` | |
| POST | `/api/{ds}/advisories/{adv}/plan` `{targets}` | |
| POST | `/api/{ds}/plans/{pid}/simulate` | |
| GET | `/api/{ds}/plans/{pid}` | plan + fixes + PRs |
| POST | `/api/demo/plans/{pid}/open` | **admin** |
| POST | `/api/demo/plans/{pid}/merge` | **admin** (merge + repin + rescan) |
| POST | `/api/demo/rescan` | **admin** |
| POST | `/api/demo/reset` | **admin** |
| GET | `/api/{ds}/leaderboard` | |
| GET | `/api/replay/tj-2025` | |
| POST | `/api/agent` `{dataset, message, history}` | SSE `text/event-stream`, `data: <json>\n\n` per event (sync generator in `StreamingResponse`) |

- **Admin:** header `X-Admin-Token == ADMIN_TOKEN`, else 401.
- **Rate limit:** in-memory, per IP, `AGENT_RATE_LIMIT`/10 min on `/api/agent` when `PUBLIC_MODE=1`.
- Every JSON response includes `graph_ms` and `queries` (the FalkorDB time counter).
- Mount `web/` as static at `/`, after the API routes.

**Done when:**

- `uvicorn chainbreaker.api:app --reload` is running.
- `curl` checks pass for each GET.
- The demo flow via `curl` works: advisory → blast (11) → plan (4) → simulate (0).
- An admin endpoint without the header returns 401.
- `curl -N -X POST localhost:8000/api/agent -H 'content-type: application/json' -d '{"dataset":"demo","message":"what is exposed if cb-changed-files is compromised?"}'` streams events.

**Commit:** `cp11: fastapi endpoints, sse agent stream, admin auth, rate limit`

---

### CP12a: Web console, exposure view

**Goal:** the "hidden depth" moment, made visual. Follow Appendix F.

**Build:**

- Layout, theme and top bar (dataset switcher with a stats strip and the FalkorDB time counter).
- Left panel: action search with autocomplete, **Simulate compromise**, the depth slider and the big numbers.
- Center: the force-graph with DAG layout and the infection-wave animation.
- Workflow drawer with the path hops.

**Done when:** in the browser at http://localhost:8000, on the demo, simulate a compromise of `cb-changed-files`:

- with the slider at 1, the graph shows 2 exposed;
- slide to 4: the big numbers animate to 11 / 9 hidden / 1 pinned-but-exposed and the wave animates;
- clicking `infra-terraform` shows 4 hops with file:line;
- there are no console errors.

**Commit:** `cp12a: web console exposure view (depth slider, wave animation, path drawer)`

---

### CP12b: Web console, fix and act

**Build:**

- Fix panel: target toggle, **Compute minimal fix**, glowing cut edges, the fix list with type badges, "N changes protect M (naive M)" and the engine badge.
- **Simulate fix** shows before → after.
- Admin section (only when an admin token is entered, stored in `sessionStorage` wrapped in try/catch): **Open PRs** → links; **Merge & continue** → progress; **Rescan** → numbers drop to 0 and nodes turn green; **Reset demo**.

**Done when:** the full demo loop works in the browser: compromise → 11 → fix (4, engine badge) → simulate 0 → open 3 PRs → merge & continue (REPIN) → rescan 0 → reset → 11.

**Commit:** `cp12b: web console fix planner, what-if, real PR flow`

---

### CP12c: Web console, agent, leaderboard, mobile

**Build:**

- **Agent tab:** suggested prompts (Appendix F), a streaming timeline of tool cards (tool, args, ms, rows), the final answer with path chips and the grounding badge, and an approval card (when the agent requests approval, show an **Approve** button that runs the admin open flow).
- **Leaderboard tab:** a table plus a mini bar chart in CSS.
- **Mobile layout:** panels stacked, graph at 50vh.

**Done when:**

- The agent answers the three CP10 questions in the UI.
- The leaderboard shows CNCF data.
- At 390 px width, nothing overflows horizontally.

**Commit:** `cp12c: web console agent tab, leaderboard, mobile layout`

---

### CP13: tj-actions 2025 replay (graph + view)

**Build:**

- `data/replay_tj_2025.json` (Appendix G) → `cb load-replay` creates graph `cb:replay-tj-2025`.
- **Replay tab:** step through the chain with captions, highlight one edge per step, and show the source link.

**Done when:**

- The tab steps 1→5 with captions.
- `GRAPH.LIST` (or `/api/datasets`) shows `cb:replay-tj-2025`.
- Browser query `MATCH p=()-[*]->() RETURN p` on that graph shows the chain.

**Commit:** `cp13: tj-actions 2025 replay graph and view`

---

### CP14: Deploy files, README, demo script

**Build:**

- `Dockerfile` (Appendix H.2), the full `docker-compose.yml` (H.1, with the `prod` profile for Caddy) and `Caddyfile` (H.3).
- On startup the app imports the snapshots into an empty volume.
- `README.md` from the template in Appendix I (fill every section with real numbers from `eval/RESULTS.md`, real Cypher from `queries.py`, and the CP0 capability check). `DEMO.md` (Appendix K). `LICENSE` (MIT).

**Done when:**

- `docker compose down -v && docker compose up -d --build falkordb app` → http://localhost:8000 works from the snapshots alone (no crawling), on the demo and CNCF datasets.
- The README contains every Rule 10 item.
- `git push` succeeded.

**Commit:** `cp14: docker deploy with snapshot autoload, README, demo script`

---

## Appendix A: Demo org scenario (exact files)

Replace `__ORG__` with `DEMO_ORG`. All workflow steps are harmless `echo`s, and no real secrets exist in these repos.

### A.1 Repos, in creation order

**Actions:**

1. `cb-changed-files`
2. `cb-setup-reviewer`
3. `cb-lint-reporter`
4. `cb-ci-toolkit`
5. `cb-release-kit`
6. `cb-shared-workflows`

**Apps:**

7. `web-frontend`
8. `docs-site`
9. `analytics`
10. `mobile-app`
11. `payments-api`
12. `auth-service`
13. `orders-api`
14. `billing-worker`
15. `search-api`
16. `notifications`
17. `infra-terraform`
18. `data-pipeline`

### A.2 Action repos (file `action.yml` at repo root)

`cb-changed-files` (commit **G**, tag `v3` → G):

```yaml
name: cb-changed-files
description: ChainBreaker lab demo action. Harmless.
runs:
  using: composite
  steps:
    - run: echo "cb-changed-files (demo)"
      shell: bash
```

`cb-setup-reviewer` (tag `v1`):

```yaml
name: cb-setup-reviewer
description: ChainBreaker lab demo action. Harmless.
runs:
  using: composite
  steps:
    - run: echo "cb-setup-reviewer (demo)"
      shell: bash
```

`cb-lint-reporter` (commit **L1**, tag `v1` → L1):

```yaml
name: cb-lint-reporter
description: ChainBreaker lab demo composite action.
runs:
  using: composite
  steps:
    - uses: __ORG__/cb-setup-reviewer@v1
    - uses: __ORG__/cb-changed-files@v3
    - run: echo "lint report (demo)"
      shell: bash
```

`cb-ci-toolkit` (tag `v2`):

```yaml
name: cb-ci-toolkit
description: ChainBreaker lab demo composite action.
runs:
  using: composite
  steps:
    - uses: __ORG__/cb-lint-reporter@v1
    - run: echo "ci toolkit (demo)"
      shell: bash
```

`cb-release-kit` (tag `v1`), safe because it pins G:

```yaml
name: cb-release-kit
description: ChainBreaker lab demo composite action.
runs:
  using: composite
  steps:
    - uses: __ORG__/cb-changed-files@__SHA_CHANGED_FILES_GOOD__ # v3
    - run: echo "release kit (demo)"
      shell: bash
```

`cb-shared-workflows`, file `.github/workflows/ci.yml` on `main`:

```yaml
name: shared-ci
on:
  workflow_call:
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-ci-toolkit@v2
```

### A.3 App workflows

`web-frontend` → `.github/workflows/pr-check.yml`

```yaml
name: pr-check
on:
  pull_request_target:
    types: [opened, synchronize]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-changed-files@v3
      - run: echo "publish preview (demo)"
        env:
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

`docs-site` → `.github/workflows/docs.yml`

```yaml
name: docs
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-changed-files@v3
      - run: echo "build docs (demo)"
```

`analytics` → `.github/workflows/lint.yml`

```yaml
name: lint
on:
  pull_request:
permissions:
  contents: read
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-lint-reporter@v1
```

`mobile-app` → `.github/workflows/build.yml`. It is pinned to a SHA and **still exposed**:

```yaml
name: build
on:
  push:
    branches: [main]
permissions:
  contents: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-lint-reporter@__SHA_LINT_REPORTER_V1__ # v1
      - run: echo "sign app (demo)"
        env:
          APPLE_SIGNING_KEY: ${{ secrets.APPLE_SIGNING_KEY }}
```

`payments-api` → `.github/workflows/deploy.yml`

```yaml
name: deploy
on:
  push:
    branches: [main]
permissions:
  contents: write
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-ci-toolkit@v2
      - run: echo "deploy (demo)"
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

The next five use the **same shape as `payments-api`** (uses `__ORG__/cb-ci-toolkit@v2`), differing only in the `permissions` block and one secret:

- `auth-service`: `permissions: {contents: write}`, `JWT_SIGNING_KEY`
- `orders-api`: **no permissions block**, `DATABASE_URL`
- `billing-worker`: **no permissions block**, `STRIPE_API_KEY`
- `search-api`: `permissions: {contents: write}`, `ELASTIC_API_KEY`
- `notifications`: `permissions: {contents: write}`, `TWILIO_AUTH_TOKEN`

`infra-terraform` → `.github/workflows/plan.yml`

```yaml
name: plan
on:
  push:
    branches: [main]
permissions:
  contents: write
jobs:
  shared:
    uses: __ORG__/cb-shared-workflows/.github/workflows/ci.yml@main
    secrets: inherit
  plan:
    runs-on: ubuntu-latest
    steps:
      - run: echo "terraform plan (demo)"
        env:
          TF_API_TOKEN: ${{ secrets.TF_API_TOKEN }}
```

`data-pipeline` → `.github/workflows/etl.yml`. It is safe: the chain ends at a pinned ref.

```yaml
name: etl
on:
  push:
    branches: [main]
permissions:
  contents: write
jobs:
  etl:
    runs-on: ubuntu-latest
    steps:
      - uses: __ORG__/cb-release-kit@v1
      - run: echo "etl (demo)"
        env:
          SNOWFLAKE_PASSWORD: ${{ secrets.SNOWFLAKE_PASSWORD }}
```

### A.4 Resulting graph (for sanity)

```
web-frontend ─────────────────────────────────────────────▶ cb-changed-files@v3  (d1, HIGH)
docs-site ────────────────────────────────────────────────▶ cb-changed-files@v3  (d1, LOW)
analytics ──▶ cb-lint-reporter@v1 ─────────────────────────▶ cb-changed-files@v3  (d2, LOW)
mobile-app ─▶ cb-lint-reporter@L1(SHA, immutable file) ────▶ cb-changed-files@v3  (d2, HIGH, pinned-but-exposed)
payments/auth/orders/billing/search/notifications
          ──▶ cb-ci-toolkit@v2 ─▶ cb-lint-reporter@v1 ─────▶ cb-changed-files@v3  (d3, HIGH ×6)
infra-terraform ─call─▶ shared ci.yml@main ─▶ cb-ci-toolkit@v2 ─▶ cb-lint-reporter@v1 ─▶ cb-changed-files@v3 (d4, HIGH)
data-pipeline ─▶ cb-release-kit@v1 ─▶ cb-changed-files@G (pinned) → NOT exposed
```

**Capacities that matter:**

| Edge | Capacity | Fix type |
|---|---|---|
| `web→changed@v3` | 1 | PIN |
| `docs→changed@v3` | 1 | PIN |
| `lint@v1→changed@v3` | 1 | PIN, in `cb-lint-reporter` (then move tag v1) |
| `mobile→lint@L1` | 1 | REPIN |
| `lint@L1→changed@v3` | 10000 | immutable |
| `ci@v2→lint@v1`, `app→ci@v2`, `infra→ci.yml@main`, `ci.yml@main→ci@v2` | 3 each | VENDOR |

**Min-cut:**

- high = **3**: PIN web, PIN lint-reporter, REPIN mobile
- all = **4**: the three above + PIN docs

### A.5 After the fix (expected)

- `web-frontend` → `cb-changed-files@G # v3`
- `docs-site` → `@G # v3`
- `cb-lint-reporter/action.yml` → `cb-changed-files@G # v3`, merged as L2, tag `v1` moved to L2
- `mobile-app` → `cb-lint-reporter@L2 # v1`

Rescan: exposed **0**.

### A.6 PR body template

```
**ChainBreaker fix · {advisory_id}**

`{old_uses}` → `{new_uses}` in `{file_path}` (line {lines})

Why: this line is one of the {cut_size} changes in the minimum cut computed by {engine}. Together they disconnect {protected} pipelines from the compromised `{action_id}` refs (a naive fix would touch {naive} pipelines).

This line protects {protects} pipeline(s), e.g.
{one example path, hop by hop}

Type: {PIN|REPIN} · Opened by ChainBreaker (demo lab, synthetic repos).
```

---

## Appendix B: Ground truth (`data/demo_ground_truth.json`, written by the seeder)

```json
{
  "org": "__ORG__",
  "advisory_action": "__ORG__/cb-changed-files",
  "known_good_sha": "<G>",
  "lint_reporter_v1_sha": "<L1>",
  "exposed": {
    "__ORG__/web-frontend:.github/workflows/pr-check.yml":   {"depth": 1, "severity": "HIGH"},
    "__ORG__/docs-site:.github/workflows/docs.yml":          {"depth": 1, "severity": "LOW"},
    "__ORG__/analytics:.github/workflows/lint.yml":          {"depth": 2, "severity": "LOW"},
    "__ORG__/mobile-app:.github/workflows/build.yml":        {"depth": 2, "severity": "HIGH", "pinned_but_exposed": true},
    "__ORG__/payments-api:.github/workflows/deploy.yml":     {"depth": 3, "severity": "HIGH"},
    "__ORG__/auth-service:.github/workflows/deploy.yml":     {"depth": 3, "severity": "HIGH"},
    "__ORG__/orders-api:.github/workflows/deploy.yml":       {"depth": 3, "severity": "HIGH"},
    "__ORG__/billing-worker:.github/workflows/deploy.yml":   {"depth": 3, "severity": "HIGH"},
    "__ORG__/search-api:.github/workflows/deploy.yml":       {"depth": 3, "severity": "HIGH"},
    "__ORG__/notifications:.github/workflows/deploy.yml":    {"depth": 3, "severity": "HIGH"},
    "__ORG__/infra-terraform:.github/workflows/plan.yml":    {"depth": 4, "severity": "HIGH"}
  },
  "not_exposed": ["__ORG__/data-pipeline:.github/workflows/etl.yml"],
  "exposed_count": 11, "depth1_count": 2, "hidden_count": 9, "high_exposed_count": 9,
  "pinned_but_exposed_count": 1,
  "min_cut_high": 3, "min_cut_all": 4,
  "cut_high": [
    {"type": "PIN",   "file": "__ORG__/web-frontend:.github/workflows/pr-check.yml"},
    {"type": "PIN",   "file": "__ORG__/cb-lint-reporter:action.yml"},
    {"type": "REPIN", "file": "__ORG__/mobile-app:.github/workflows/build.yml"}
  ],
  "after_fix_exposed_count": 0
}
```

**Expected severities** (unit test in CP1):

- HIGH: `web-frontend` (pull_request_target), `mobile-app`, `payments-api`, `auth-service`, `search-api`, `notifications`, `infra-terraform`, `data-pipeline` (secrets + write); `orders-api`, `billing-worker` (secrets + default).
- LOW: `docs-site`, `analytics`.
- `cb-shared-workflows` `ci.yml` (HEAD) has `entry=false`.

---

## Appendix C: GitHub API

### C.1 Org repos (GraphQL)

```graphql
query($login: String!, $cursor: String) {
  rateLimit { remaining resetAt }
  organization(login: $login) {
    repositories(first: 50, after: $cursor, privacy: PUBLIC, isFork: false,
                 orderBy: {field: STARGAZERS, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { nameWithOwner stargazerCount isArchived defaultBranchRef { name } }
    }
  }
}
```

### C.2 Workflows, batched (build the string in Python; quote values with `json.dumps`)

```python
def workflows_query(repos):  # list[(owner, name)]
    parts = []
    for i, (o, n) in enumerate(repos):
        parts.append(f'''r{i}: repository(owner: {json.dumps(o)}, name: {json.dumps(n)}) {{
          nameWithOwner stargazerCount isArchived defaultBranchRef {{ name }}
          object(expression: "HEAD:.github/workflows") {{
            ... on Tree {{ entries {{ name type object {{ ... on Blob {{ text isTruncated }} }} }} }}
          }}
        }}''')
    return "query { rateLimit { remaining resetAt } " + "\n".join(parts) + " }"
```

Keep entries whose name ends in `.yml` or `.yaml` and whose type is `blob`.

### C.3 Action files and reusable workflows at refs, batched

```python
def blobs_query(items):  # list[(owner, repo, [expr1, expr2, ...])]
    parts = []
    for i, (o, n, exprs) in enumerate(items):
        objs = " ".join(f'y{j}: object(expression: {json.dumps(e)}) {{ ... on Blob {{ text }} }}'
                        for j, e in enumerate(exprs))
        parts.append(f'a{i}: repository(owner: {json.dumps(o)}, name: {json.dumps(n)}) {{ {objs} }}')
    return "query { rateLimit { remaining resetAt } " + "\n".join(parts) + " }"
```

- **Action:** `exprs = [f"{ref}:{p}action.yml", f"{ref}:{p}action.yaml"]`, where `p = path + "/"` if `path` else `""`.
- **Reusable workflow:** `exprs = [f"{ref}:{workflow_path}"]`.
- **Local action from a HEAD workflow:** `ref = "HEAD"`.

### C.4 `crawl.json` schema

```json
{
  "dataset": "demo", "crawled_at": "ISO8601", "orgs": ["..."],
  "repos": [{"id": "o/r", "stars": 1, "default_branch": "main"}],
  "workflows": [{"id": "o/r:.github/workflows/x.yml", "repo_id": "o/r", "path": ".github/workflows/x.yml",
                 "name": "x", "triggers": ["push"], "secrets": ["NPM_TOKEN"], "perms": "write",
                 "id_token_write": false, "prt": false, "severity": "HIGH", "severity_reasons": ["..."],
                 "entry": true, "at_ref": null, "pinned": false}],
  "actions": [{"id": "o/r/path", "owner": "o", "repo": "r", "path": "path", "search": "o r path"}],
  "action_refs": [{"id": "o/r/path@v3", "action_id": "o/r/path", "ref": "v3", "pinned": false,
                   "local": false, "kind": "composite"}],
  "docker_images": [{"id": "docker://alpine:3.19", "pinned": false}],
  "edges": [{"src": "<id>", "src_label": "Workflow|ActionRef", "dst": "<id>",
             "dst_label": "ActionRef|Workflow|DockerImage", "kind": "step|call|image",
             "file_repo": "o/r", "file_path": ".github/workflows/x.yml", "lines": [12],
             "uses": "o/r@v3", "src_immutable": false}],
  "stats": {"dynamic_uses": 0, "unresolved": 0, "invalid": 0}
}
```

### C.5 CNCF orgs (missing orgs: warn and skip)

```
kubernetes kubernetes-sigs prometheus open-telemetry envoyproxy istio cilium argoproj fluxcd helm
containerd etcd-io grpc jaegertracing linkerd coredns cri-o fluent open-policy-agent thanos-io
cortexproject vitessio rook kedacore knative dapr falcosecurity cert-manager backstage crossplane
kubevirt kyverno buildpacks cloudevents opencost chaos-mesh litmuschaos longhorn spiffe nats-io
kubeedge karmada-io volcano-sh openkruise tikv kubeflow cncf
```

### C.6 REST helpers (`https://api.github.com`)

Send `Authorization: Bearer <token>`, `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28` on every call.

| Helper | Call |
|---|---|
| create repo | `POST /orgs/{org}/repos` `{"name","description","auto_init":true,"has_issues":false,"has_wiki":false}` (422 already exists → reuse) |
| get file | `GET /repos/{o}/{r}/contents/{path}?ref={branch}` → base64 `content`, `sha` |
| put file | `PUT /repos/{o}/{r}/contents/{path}` `{"message","content":b64,"branch","sha"?}` → `commit.sha` |
| get ref | `GET /repos/{o}/{r}/git/ref/heads/{b}` or `/git/ref/tags/{t}` → `object.sha` |
| create ref | `POST /repos/{o}/{r}/git/refs` `{"ref":"refs/tags/v3" or "refs/heads/x","sha"}` |
| move ref | `PATCH /repos/{o}/{r}/git/refs/tags/{t}` `{"sha","force":true}` |
| delete branch | `DELETE /repos/{o}/{r}/git/refs/heads/{b}` |
| open PR | `POST /repos/{o}/{r}/pulls` `{"title","head","base","body"}` → `html_url`, `number` |
| merge PR | `PUT /repos/{o}/{r}/pulls/{n}/merge` `{"merge_method":"squash"}` → `sha` |
| list/close PRs | `GET /repos/{o}/{r}/pulls?state=open`, `PATCH /repos/{o}/{r}/pulls/{n}` `{"state":"closed"}` |

---

## Appendix D: Cypher library (`queries.py`)

`{D}` = a clamped integer (1..8) inlined with Python formatting. **Never** use a parameter in a var-length bound, `LIMIT` or `SKIP`.

**Q-LOAD** (batches of 1,000):

```
UNWIND $rows AS row CREATE (n:Repo) SET n += row
UNWIND $rows AS row CREATE (n:Workflow) SET n += row
UNWIND $rows AS row CREATE (n:Action) SET n += row
UNWIND $rows AS row CREATE (n:ActionRef) SET n += row
UNWIND $rows AS row CREATE (n:DockerImage) SET n += row
UNWIND $rows AS row MATCH (r:Repo {id: row.src}), (w:Workflow {id: row.dst}) CREATE (r)-[:HAS_WORKFLOW]->(w)
UNWIND $rows AS row MATCH (a:ActionRef {id: row.src}), (b:Action {id: row.dst}) CREATE (a)-[:VERSION_OF]->(b)
// USES: one query per (src_label, dst_label) pair present in the data, e.g.
UNWIND $rows AS row MATCH (s:Workflow {id: row.src}), (d:ActionRef {id: row.dst}) CREATE (s)-[e:USES]->(d) SET e += row.props
```

`row.props` = `{kind, file_repo, file_path, lines, uses, src_immutable, weight: 1}`. Values must be primitives or lists.

**Q-ADV-LINK:**

```
MATCH (adv:Advisory {id: $adv})
MATCH (:Action {id: adv.action_id})<-[:VERSION_OF]-(r:ActionRef)
WHERE r.pinned = false AND (size(adv.refs) = 0 OR r.ref IN adv.refs)
CREATE (adv)-[:COMPROMISES]->(r)
RETURN count(r) AS compromised
```

**Q-BLAST:**

```
MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(bad:ActionRef)
MATCH p = (w:Workflow)-[:USES*1..{D}]->(bad)
WHERE w.at_ref IS NULL AND w.entry = true
RETURN w.id AS workflow, w.repo_id AS repo, w.severity AS severity,
       w.severity_reasons AS reasons, min(length(p)) AS depth
```

**Q-PINNED:**

```
MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(bad:ActionRef)
MATCH p = (w:Workflow)-[:USES*1..{D}]->(bad)
WHERE w.at_ref IS NULL AND w.entry = true
WITH w, collect(DISTINCT nodes(p)[1].pinned) AS first_pins
WHERE size([x IN first_pins WHERE x <> true]) = 0
RETURN w.id AS workflow
```

**Q-PATH** (shortest exposing path, with algorithm):

```
MATCH (w:Workflow {id: $wid})
MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(bad:ActionRef)
CALL algo.SPpaths({sourceNode: w, targetNode: bad, relTypes: ['USES'], weightProp: 'weight',
                   relDirection: 'outgoing', maxLen: {D}, pathCount: 1})
YIELD path, pathWeight
RETURN path, pathWeight ORDER BY pathWeight ASC LIMIT 1
```

**Q-PATH-FALLBACK:**

```
MATCH (w:Workflow {id: $wid}), (:Advisory {id: $adv})-[:COMPROMISES]->(bad:ActionRef)
MATCH p = (w)-[:USES*1..{D}]->(bad)
RETURN p ORDER BY length(p) ASC LIMIT 1
```

**Q-VIZ** (paths to any ref of the action, safe and exposed):

```
MATCH (:Action {id: $aid})<-[:VERSION_OF]-(r:ActionRef)
MATCH p = (w:Workflow)-[:USES*1..{D}]->(r)
WHERE w.at_ref IS NULL AND w.entry = true
WITH p LIMIT 5000
UNWIND relationships(p) AS e
WITH DISTINCT e
RETURN startNode(e).id AS src, endNode(e).id AS dst, e.kind AS kind, e.uses AS uses,
       e.file_path AS file_path, e.lines AS lines
```

Then fetch the node properties for the id set, plus the compromised ids (`MATCH (:Advisory {id:$adv})-[:COMPROMISES]->(r) RETURN r.id`).

**Q-CAP-1, Q-CAP-2** (scratch graph only):

```
MATCH ()-[e:USES]->(b)
SET e.cap = CASE WHEN e.src_immutable = true THEN 10000 WHEN b.pinned = true THEN 1 ELSE 3 END
```

```
MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(b:ActionRef)
MATCH ()-[e:USES]->(b)
WHERE e.src_immutable = false
SET e.cap = 1
```

**Q-MAXFLOW** (scratch graph):

```
MATCH (w:Workflow) WHERE w.id IN $sources
WITH collect(w) AS srcs
MATCH (:Advisory {id: $adv})-[:COMPROMISES]->(b:ActionRef)
WITH srcs, collect(b) AS tgts
CALL algo.maxFlow({sourceNodes: srcs, targetNodes: tgts, relationshipTypes: ['USES'], capacityProperty: 'cap'})
YIELD nodes, edges, edgeFlows, maxFlow
RETURN nodes, edges, edgeFlows, maxFlow
```

**Q-PROBE** (tiny known graph: max flow = 2):

```
CREATE (s:P {id:'s'}), (a:P {id:'a'}), (b:P {id:'b'}), (t:P {id:'t'}),
       (s)-[:R {cap: 1}]->(a), (s)-[:R {cap: 1}]->(b), (a)-[:R {cap: 5}]->(t), (b)-[:R {cap: 5}]->(t)
```

```
MATCH (s:P {id:'s'}), (t:P {id:'t'})
CALL algo.maxFlow({sourceNodes: [s], targetNodes: [t], relationshipTypes: ['R'], capacityProperty: 'cap'})
YIELD nodes, edges, edgeFlows, maxFlow
RETURN nodes, edges, edgeFlows, maxFlow
```

**Q-EDGES-EXPORT** (scratch graph, for the residual cut or networkx):

```
MATCH (s)-[e:USES]->(d)
RETURN id(e) AS eid, id(s) AS sid, id(d) AS did, e.cap AS cap, s.id AS s_key, d.id AS d_key,
       labels(s)[0] AS s_label, labels(d)[0] AS d_label
```

**Q-PR** (PageRank as an agent tool):

```
CALL algo.pageRank(null, 'USES') YIELD node, score
WITH node, score WHERE 'ActionRef' IN labels(node)
MATCH (node)-[:VERSION_OF]->(a:Action)
RETURN a.id AS action, sum(score) AS pagerank
ORDER BY pagerank DESC LIMIT 25
```

**Q-DIRECT / Q-REACH:**

```
MATCH (:Action {id: $aid})<-[:VERSION_OF]-(:ActionRef)<-[:USES]-(w:Workflow)
WHERE w.at_ref IS NULL AND w.entry = true RETURN count(DISTINCT w) AS direct
```

```
MATCH (:Action {id: $aid})<-[:VERSION_OF]-(r:ActionRef)
MATCH (w:Workflow)-[:USES*1..{D}]->(r)
WHERE w.at_ref IS NULL AND w.entry = true
RETURN count(DISTINCT w) AS reach,
       count(DISTINCT CASE WHEN r.pinned = false THEN w END) AS mutable_reach
```

**Q-FT** (full-text search, with fallback):

```
CALL db.idx.fulltext.queryNodes('Action', $q) YIELD node, score RETURN node.id AS id, score LIMIT 10
```

```
MATCH (a:Action) WHERE a.id CONTAINS toLower($q) RETURN a.id AS id LIMIT 10
```

---

## Appendix E: Agent

### E.1 System prompt (`agent/prompts.py`)

```
You are ChainBreaker, an incident agent for GitHub Actions supply-chain attacks.
Everything you know comes from tools that query a FalkorDB graph of repositories, workflows,
actions and the `uses:` links between them. Dataset: {dataset}. {public_note}

Rules:
1. Every fact must come from a tool result in this conversation. Never guess names, counts, versions or paths.
2. You cannot write database queries. Choose tools.
3. If find_action returns unknown_entity, say "<name> is not in the graph" and offer the suggestions it returned. Do not continue as if it existed.
4. When you say a workflow is exposed, show at least one path hop by hop (explain_exposure), with file and line.
5. For "what if X is compromised", call simulate_compromise first, then blast_radius.
6. Always contrast depth 1 (what a grep finds) with the full depth: that difference is the point.
7. For fixes: call plan_fix, then simulate_fix to prove it reaches 0, then explain "N changes protect M (naive: M)" and what PIN / REPIN / VENDOR mean in one line each. Name the engine that computed the cut.
8. You never open, merge or apply PRs. Call request_fix_approval; a human approves in the UI.
9. If recall_findings returns something relevant, start with "From an earlier investigation on <date>:".
10. Lead with numbers in one sentence, then the path, then the fix. Max 180 words unless asked for more.
```

`public_note` (in public mode, CNCF dataset): `"Some repositories appear as pseudonyms (repo-xxxxxx) to protect the projects. Never try to identify them."`

### E.2 Tools (pydantic args → Anthropic `input_schema`)

| Name | Args | Returns (always includes `outcome`, `graph_ms`) |
|---|---|---|
| `find_action` | `query: str` | `found` + `matches[{id, refs, direct_users}]` or `unknown_entity` + `suggestions[]` |
| `simulate_compromise` | `action_id: str`, `refs: list[str] = []` | `advisory_id`, `compromised_refs[]`, `known_good_sha?` |
| `blast_radius` | `advisory_id: str`, `max_depth: int = 6` | `exposed_total`, `depth1`, `hidden`, `high_total`, `by_depth`, `by_severity`, `pinned_but_exposed[]`, `top[≤12]{workflow, severity, depth}` |
| `explain_exposure` | `advisory_id: str`, `workflow_id: str` | `answered_with_path`, `hops[{from, to, uses, file, lines, pinned}]`, `depth` |
| `workflow_risk` | `workflow_id: str` | `triggers`, `perms`, `secrets` (names), `severity`, `reasons` |
| `plan_fix` | `advisory_id: str`, `targets: "high" \| "all" = "all"` | `plan_id`, `cut_size`, `protected`, `naive`, `engine`, `fixes[{type, file, lines, old_uses, new_uses, protects, phase}]` |
| `simulate_fix` | `plan_id: str` | `before`, `after`, `copy_ms` |
| `request_fix_approval` | `plan_id: str` | `awaiting_human_approval` + summary (no side effects except an event the UI shows) |
| `load_bearing_actions` | `top_k: int = 10` | leaderboard rows |
| `recall_findings` | `action_id: str = ""` | `answered_from_memory` + `findings[{date, question, answer}]` or `none` |

The MCP server exposes all of these except `request_fix_approval` (9 tools).

---

## Appendix F: UI spec (`web/`)

**Theme:** a dark security console.

- **Colours:**
  - `--bg #0b0f17`, `--panel #111827`, `--line #1f2937`, `--text #e5e7eb`, `--muted #9ca3af`
  - `--red #ef4444` (compromised), `--orange #f97316` (HIGH), `--amber #f59e0b` (MED), `--yellow #eab308` (LOW)
  - `--green #22c55e` (safe/fixed), `--cyan #22d3ee` (cut edges), `--violet #a78bfa` (intermediate actions)
- **Fonts:** Inter for UI, JetBrains Mono for ids and code.
- **Body:** explicit background.

**Layout (desktop):**

- **Top bar:** logo "ChainBreaker", the dataset switcher (pills: Demo org · CNCF (1k repos) · tj-actions 2025 replay, plus the caption "each is its own FalkorDB graph"), the stats strip (repos · workflows · action refs · USES edges · % mutable refs), and the counter "FalkorDB: X ms · Y queries" (from responses).
- **Left (320 px), Incident:**
  - action search (debounced, `/actions/search`) and the **Simulate compromise** button;
  - **depth slider 1–6** with live numbers;
  - **big-number cards**: "grep finds (depth 1)" vs "ChainBreaker finds", "hidden", "pinned to a SHA and still exposed", HIGH/MED/LOW chips;
  - the exposed list (sortable by depth or severity).
- **Center, graph** (`force-graph`):
  - **Layout:** `dagMode('lr')`, `dagLevelDistance(120)`. On `onDagError`, switch to the free layout.
  - **Direction:** display links reversed (dependency → consumer) so infection flows left → right, with the compromised node on the left.
  - **Nodes** (`nodeCanvasObject`):
    - workflows are rounded rectangles coloured by severity if exposed, grey if safe, green if fixed;
    - action refs are circles: red for compromised, violet for intermediates on exposed paths, grey otherwise, with a lock ring if pinned;
    - labels are short (`repo` or `action@ref`).
  - **Links:** dashed (`linkLineDash([4,3])`) if the consumer-side ref is mutable; solid if pinned; **cyan, width 3** if in the current cut; green after the fix.
  - **Wave animation** after loading: BFS layers from the compromised node; for layer k, after k×350 ms, `emitParticle(link)` on that layer's links.
  - **Interaction:** click a workflow to open the drawer with its path. `zoomToFit(600, 40)` after layout.
- **Right (380 px), tabs:**
  - **Fix:**
    - targets toggle (All / High-value only);
    - **Compute minimal fix**: shows the headline "**4 changes** protect **11** pipelines (naive: 11)" and the engine badge ("FalkorDB algo.maxFlow" or "networkx fallback");
    - fix cards with type badges (PIN/REPIN/VENDOR), `file:line`, `old → new` and "protects N";
    - **Simulate fix (GRAPH.COPY)** shows before → after and `copy_ms`;
    - **Admin**: token input, then **Open PRs** → PR links; **Merge & continue** → step log; **Rescan** → animate the numbers to 0 and turn the graph green; **Reset demo**.
  - **Agent:**
    - suggested prompts:
      - "What happens if `<org>/cb-changed-files` is compromised?"
      - "Show me the deepest exposed pipeline and why."
      - "Fix it with the fewest changes."
      - "Is evil-corp/backdoor-action in our CI?"
      - "Which actions are the most load-bearing?"
      - "What did we find last time?"
    - streaming timeline cards (tool icon, name, args, ms, rows);
    - the final answer with path chips;
    - the **grounding badge** ("✓ Grounded: 7/7 names verified in FalkorDB", amber if any unverified);
    - the approval card.
  - **Leaderboard:** top 15 actions: PageRank bar, direct users, transitive reach, mutable reach.
  - **Replay:** the 5-step stepper (Appendix G).
- **Footer:** "Public data + synthetic demo org · Aggregates only for CNCF · Built for Graph Hacks (Track 01)".
- **Mobile (<900 px):** stack top bar → incident → graph (50vh) → tabs. No horizontal scroll.
- **No browser storage** except the admin token in `sessionStorage` (try/catch).

---

## Appendix G: Replay data (`data/replay_tj_2025.json`)

Use only these facts. Every caption links to the source.

```json
{
  "source": "https://unit42.paloaltonetworks.com/github-actions-supply-chain-attack/",
  "nodes": [
    {"id": "spotbugs-token", "label": "Token", "name": "Leaked SpotBugs maintainer token"},
    {"id": "reviewdog/action-setup@v1", "label": "ActionRef", "name": "reviewdog/action-setup@v1"},
    {"id": "tj-actions/eslint-changed-files", "label": "Action", "name": "tj-actions/eslint-changed-files"},
    {"id": "tj-actions/changed-files", "label": "Action", "name": "tj-actions/changed-files (used by 23,000+ repos)"},
    {"id": "coinbase/agentkit", "label": "Repo", "name": "coinbase/agentkit (initial target)"}
  ],
  "steps": [
    {"edge": ["spotbugs-token", "reviewdog/action-setup@v1"], "caption": "A leaked token from the SpotBugs project is used to compromise reviewdog/action-setup@v1."},
    {"edge": ["reviewdog/action-setup@v1", "tj-actions/eslint-changed-files"], "caption": "tj-actions/eslint-changed-files depends on reviewdog/action-setup, so the compromise moves one hop."},
    {"edge": ["tj-actions/eslint-changed-files", "tj-actions/changed-files"], "caption": "From there the attackers reach tj-actions/changed-files, an action used by 23,000+ repositories."},
    {"edge": ["tj-actions/changed-files", "coinbase/agentkit"], "caption": "The initial target was Coinbase's agentkit repository."},
    {"edge": null, "caption": "Most victims never referenced the compromised action directly. That hidden depth is what ChainBreaker maps."}
  ]
}
```

---

## Appendix H: Deploy files

### H.1 `docker-compose.yml`

```yaml
services:
  falkordb:
    image: falkordb/falkordb:latest
    environment:
      - REDIS_ARGS=--requirepass ${FALKORDB_PASSWORD:-chainbreaker} --appendonly yes
    ports: ["127.0.0.1:6379:6379", "127.0.0.1:3000:3000"]
    volumes: ["falkordb_data:/var/lib/falkordb/data"]
    restart: unless-stopped
  app:
    build: .
    env_file: .env
    environment:
      - FALKORDB_HOST=falkordb
      - FALKORDB_PORT=6379
      - FALKORDB_PASSWORD=${FALKORDB_PASSWORD:-chainbreaker}
    depends_on: [falkordb]
    ports: ["127.0.0.1:8000:8000"]
    restart: unless-stopped
  caddy:
    image: caddy:2
    profiles: ["prod"]
    ports: ["80:80", "443:443"]
    environment: ["DOMAIN=${DOMAIN}"]
    volumes: ["./Caddyfile:/etc/caddy/Caddyfile", "caddy_data:/data"]
    depends_on: [app]
    restart: unless-stopped
volumes: { falkordb_data: {}, caddy_data: {} }
```

The volume must be mounted at `/var/lib/falkordb/data`. The `/data` path from some docs examples loses data.

### H.2 `Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY chainbreaker ./chainbreaker
COPY web ./web
COPY data/snapshots ./data/snapshots
COPY data/replay_tj_2025.json data/demo_ground_truth.json ./data/
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "chainbreaker.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### H.3 `Caddyfile`

```
{$DOMAIN} {
  encode gzip
  reverse_proxy app:8000
}
```

On a personal VPS, `DOMAIN` can be `chainbreaker.<ip-with-dashes>.sslip.io` to get automatic HTTPS. Use a personal VPS, never Gradr's servers. Set `PUBLIC_MODE=1` and a strong `ADMIN_TOKEN` in production.

### H.4 Claude Desktop MCP config (README snippet)

```json
{
  "mcpServers": {
    "chainbreaker": {
      "command": "/ABSOLUTE/PATH/chainbreaker/.venv/bin/python",
      "args": ["-m", "chainbreaker.mcp_server"],
      "env": { "FALKORDB_HOST": "localhost", "FALKORDB_PORT": "6379", "FALKORDB_PASSWORD": "chainbreaker" }
    }
  }
}
```

---

## Appendix I: README template (fill in real values)

1. **One-line pitch**, plus a GIF of the wave animation, the **live URL**, the **demo video** link, and "**Track 01: Agents That Act on Connected Data**".
2. **The problem in 4 lines:** the tj-actions 2025 chain, and the fact that most victims never referenced the compromised action directly.
3. **What it does:** the five moments (section 1), each with a screenshot.
4. **Measured results** (from `eval/RESULTS.md`): the demo PASS table; the CNCF headline numbers (hidden %, pinned-but-exposed, cut vs naive); the crawl date. State that numbers are aggregates and repo names are pseudonymized.
5. **Why a graph (Rule 3):** exposure is a multi-hop property, and cutting it optimally is a max-flow problem. Neither can be expressed as a flat lookup or a vector search. Without FalkorDB, nothing works.
6. **Graph data model:** the tables from section 7 and the mermaid diagram.
7. **Cypher queries and algorithms used:** Q-BLAST, Q-PINNED, Q-PATH (`algo.SPpaths`), Q-MAXFLOW (`algo.maxFlow`), Q-PR (`algo.pageRank`), `GRAPH.COPY` what-if, full-text index, multi-graph. Paste the real strings from `queries.py`, plus the CP0 capability output and which engine computed the cut.
8. **Agent design:** the fixed tool catalogue (no LLM-written Cypher), the 4 outcome shapes, the grounding validator, the human approval gate, memory (`Finding`) and the MCP server.
9. **Setup (local):** single-paste commands: venv + install, `docker compose up -d falkordb`, `cb snapshot-import` for both datasets, `uvicorn`. Optional live crawl and demo-org seeding.
10. **Deploy:** compose + Caddy on a VPS.
11. **Data and ethics:** public data, a synthetic demo org, no secret values ever, pseudonymized CNCF names, aggregates only, PRs only in our own org.
12. **AI disclosure (Rule 11):** "Built with AI assistance: Claude Code (Claude Opus 5.5) generated most of the code from a design plan; I (Divy) made the design decisions, reviewed and ran every checkpoint, and tested and deployed the system. Decisions and deviations are logged in NOTES.md." Divy should edit this to be accurate.
13. **Limitations:** JS-action npm dependencies are not traversed; local `./` uses inside actions are unresolved; org-default token permissions are unknown (shown as "default").
14. **License:** MIT.

---

## Appendix J: Cut list (if running behind, cut in this order; never cut commits)

1. CP13 replay view: use a static image of the chain in the README and the video instead.
2. `load_bearing_actions` betweenness (keep PageRank).
3. Memory (`Finding`, `recall_findings`).
4. `cb mcp-selftest` (keep the MCP server itself).
5. Mobile layout polish.
6. Agent rate limiting (keep the admin token).
7. **Never cut:** demo ground-truth checks, min-cut + simulate, real PR flow + rescan, grounding validator, README Rule 10 items.

---

## Appendix K: `DEMO.md` (2:30 video storyboard; the UI must make each beat possible)

| Time | Beat |
|---|---|
| 0:00 | **Hook.** Replay tab: "March 2025. One leaked token. 23,000 repos." Step through the chain. |
| 0:20 | "Most victims never used the compromised action directly. Let's see our org." Switch to Demo org and simulate a compromise of `cb-changed-files`. |
| 0:35 | **Depth 1 vs depth 4.** Slider at 1: 2 exposed (what grep finds). Slide to 4: 11, 9 hidden, and the wave animation. "mobile-app pinned to a SHA and is still exposed." |
| 0:55 | Click infra-terraform: 4 hops, file and line each. |
| 1:10 | **Agent.** "What happens if cb-changed-files is compromised?" Tool timeline, path, "Grounded 7/7". Then "Is evil-corp/backdoor-action in our CI?" → not in graph. |
| 1:30 | **Min-cut.** "4 changes protect 11 pipelines." Cut edges glow and the engine badge shows FalkorDB `algo.maxFlow`. Simulate fix (GRAPH.COPY) → 0. |
| 1:50 | **Act.** Open PRs (real GitHub tabs), Merge & continue (REPIN), Rescan → **0**. Everything turns green. |
| 2:10 | **Scale.** Switch to CNCF: "1,0xx real repos", measured hidden %, pinned-but-exposed, leaderboard. |
| 2:25 | **Close.** "ChainBreaker: the graph finds what grep can't, and fixes it in the fewest moves." Then the live URL. |

---

## Appendix L: FalkorDB gotchas (read before coding)

- **Cypher syntax:**
  - Var-length bounds, `LIMIT` and `SKIP` can't be parameters. Clamp the int and inline it.
  - Undirected `shortestPath()` is unsupported. Use `algo.SPpaths` with `relDirection`.
  - `NOT EXISTS { … }` subqueries fail. Use `OPTIONAL MATCH … WITH … count(x) = 0`.
  - Label expressions in `MATCH` are unsupported. Use `'Label' IN labels(n)` in `WHERE`.
- **Indexes:**
  - Full-text indexes build asynchronously. Retry or fall back to `CONTAINS`.
  - Range indexes don't help `<>`.
- **Algorithms:**
  - They follow edge direction. Betweenness on a directed bipartite graph returns zeros (fine here; PageRank is the main score).
  - `algo.maxFlow` and `algo.HarmonicCentrality` are documented but **not verified** on the server build you'll run. CP0 checks for them and CP6 probes the output shape.
- **Clients and operations:**
  - Use `ro_query` for every read tool. It refuses writes, which is a real guard.
  - Don't use `MULTI/EXEC`. It blocks every graph.
  - Bolt/Neo4j drivers don't work. Use the FalkorDB client only.
  - Docker data dir: `/var/lib/falkordb/data`.
- **Graph lifecycle:**
  - A graph is deleted with `GRAPH.DELETE` (`g.delete()`).
  - Scratch graphs must always be deleted.

---

## Appendix M: Manual test checklist (for Divy, after CP14)

1. **Fresh run:** `docker compose down -v && docker compose up -d --build falkordb app`. Both datasets load from snapshots, and http://localhost:8000 works.
2. **Demo loop:** compromise → 11 → depth 1 = 2 → path → fix 4 (engine badge) → simulate 0 → open 3 PRs (check them on GitHub) → merge & continue → rescan 0 → reset → 11.
3. **Agent:** run all 6 suggested prompts. Check grounding badges, the "not in graph" answer, and that no PR opens without approval.
4. **CNCF dataset:**
   - no real repo names visible with `PUBLIC_MODE=1`;
   - the leaderboard loads;
   - the eval numbers match the README.
5. **MCP:** add the server to Claude Desktop (H.4) and ask "Using chainbreaker, how exposed is the demo org to cb-changed-files?"
6. **Phone:** open the deployed URL on a phone. No horizontal scroll, and the graph is usable.
7. **Repo:** the README covers every Rule 10 item, there's an AI disclosure, NOTES.md is filled in, and the commit history shows steady checkpoint commits.
