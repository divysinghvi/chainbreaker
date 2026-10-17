# ChainBreaker eval results

Generated 2026-10-17T11:57:30+00:00 by `cb eval`. CNCF numbers are aggregates over public repos; only public action names are listed.

## Demo org vs ground truth

| Check | Result | Value |
|---|---|---|
| exposure set (11 workflows) | PASS | 11 exposed |
| data-pipeline not exposed (chain ends at a pinned ref) | PASS | safe |
| depth per workflow | PASS | {'1': 2, '2': 2, '3': 6, '4': 1} |
| severity per workflow | PASS | {'HIGH': 9, 'MED': 0, 'LOW': 2} |
| depth-1 (grep) count = 2 | PASS | 2 |
| hidden (depth >= 2) = 9 | PASS | 9 |
| pinned-but-exposed = {mobile-app} | PASS | mobile-app |
| min cut, high-value targets = 3 | PASS | 3 (naive 9) |
| cut edges = PIN web-frontend, PIN cb-lint-reporter, REPIN mobile-app | PASS | PIN · PIN · REPIN |
| min cut, all targets = 4 | PASS | 4 (naive 11) |
| cut computed by FalkorDB algo.maxFlow | PASS | falkordb.algo.maxFlow |
| simulate fix (high) on GRAPH.COPY -> 0 | PASS | 9 -> 0 |
| simulate fix (all) on GRAPH.COPY -> 0 | PASS | 11 -> 0 (85.0 ms copy) |

## CNCF ecosystem

Crawled 2026-10-17T11:47:53+00:00 · 47 orgs.

| Metric | Value |
|---|---|
| Repos | 1,129 |
| Entry workflows | 4,556 |
| Action refs / USES edges | 2,247 / 16,541 |
| External `uses:` refs from workflows that are mutable (tag/branch) | 28.9% of 13,485 |
| Entry workflows with ≥1 mutable ref anywhere in their chain | 1,586 (34.8%) |
| …of which reachable only through an intermediate action (hidden) | 385 (8.5%) |
| Deepest `uses:` chain seen | 6 hops |

## Simulated compromise of the 20 actions with the highest transitive reach

Totals: **3,017** exposed workflows, **532 hidden (17.6%)**, **34** pinned-but-exposed; fixing every HIGH pipeline takes **864** line changes (min-cut) vs **927** naive. Engine: falkordb.algo.maxFlow.

| Action | Reach | Exposed | Depth-1 | Hidden | Hidden % | HIGH | Pinned-but-exposed | Naive (HIGH) | Cut (HIGH) | Blast ms | Plan ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `actions/checkout` | 3951 | 1207 | 1068 | 139 | 11.5% | 336 | 5 | 336 | 314 | 66.2 | 558.4 |
| `actions/setup-go` | 1511 | 467 | 338 | 129 | 27.6% | 104 | 1 | 104 | 98 | 55.3 | 511.2 |
| `actions/upload-artifact` | 795 | 195 | 176 | 19 | 9.7% | 66 | 0 | 66 | 66 | 54.5 | 555.9 |
| `docker/login-action` | 479 | 130 | 116 | 14 | 10.8% | 81 | 1 | 81 | 77 | 55.0 | 548.7 |
| `actions/github-script` | 407 | 99 | 85 | 14 | 14.1% | 64 | 6 | 64 | 60 | 51.1 | 565.2 |
| `docker/setup-buildx-action` | 388 | 106 | 81 | 25 | 23.6% | 46 | 0 | 46 | 43 | 51.6 | 552.2 |
| `actions/download-artifact` | 378 | 101 | 85 | 16 | 15.8% | 43 | 0 | 43 | 42 | 51.7 | 556.4 |
| `actions/cache` | 364 | 109 | 78 | 31 | 28.4% | 14 | 9 | 14 | 13 | 50.4 | 557.4 |
| `actions/setup-python` | 312 | 155 | 109 | 46 | 29.7% | 27 | 4 | 27 | 27 | 50.5 | 567.7 |
| `docker/setup-qemu-action` | 282 | 68 | 63 | 5 | 7.4% | 42 | 0 | 42 | 39 | 50.2 | 550.5 |
| `step-security/harden-runner` | 267 | 0 | 0 | 0 | 0.0% | 0 | 0 | 0 | 0 | 53.5 | 0 |
| `actions/setup-node` | 266 | 82 | 76 | 6 | 7.3% | 17 | 2 | 17 | 17 | 43.1 | 517.0 |
| `docker/build-push-action` | 202 | 50 | 33 | 17 | 34.0% | 16 | 0 | 16 | 13 | 52.9 | 546.3 |
| `helm/kind-action` | 189 | 38 | 28 | 10 | 26.3% | 5 | 0 | 5 | 5 | 52.0 | 573.1 |
| `sigstore/cosign-installer` | 189 | 19 | 15 | 4 | 21.1% | 11 | 0 | 11 | 11 | 62.5 | 525.5 |
| `github/codeql-action/upload-sarif` | 181 | 9 | 9 | 0 | 0.0% | 3 | 0 | 3 | 3 | 41.1 | 467.7 |
| `actions/create-github-app-token` | 174 | 22 | 4 | 18 | 81.8% | 20 | 3 | 20 | 7 | 55.2 | 564.1 |
| `golangci/golangci-lint-action` | 162 | 60 | 42 | 18 | 30.0% | 7 | 0 | 7 | 5 | 50.8 | 548.9 |
| `peter-evans/create-pull-request` | 160 | 52 | 50 | 2 | 3.8% | 23 | 0 | 23 | 23 | 53.2 | 559.0 |
| `actions/stale` | 150 | 48 | 29 | 19 | 39.6% | 2 | 3 | 2 | 1 | 55.2 | 562.2 |
