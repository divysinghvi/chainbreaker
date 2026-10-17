# Demo video storyboard (2:30)

Before recording: `cb reset-demo` (or **Reset demo** in the UI), browser at 1440 × 900, the admin token pasted in the Fix tab.

| Time | Beat | Do this |
|---|---|---|
| 0:00 | **Hook.** "March 2025. One leaked token. 23,000 repos." | Pill **tj-actions 2025 replay** → Replay tab → step 1 → 5. |
| 0:20 | "Most victims never used the compromised action directly. Let's see our org." | Pill **Demo org** → **Simulate compromise** (`chainbreaker-lab-divy/cb-changed-files` is prefilled). |
| 0:35 | **Depth 1 vs depth 4.** | Slider at 1: **2 exposed** (what grep finds). Slide to 4: **11**, **9 hidden**, the red wave runs left → right. Point at `mobile-app` (SHA-pinned tag): "pinned to a SHA and still exposed". |
| 0:55 | **Path evidence.** | Click `infra-terraform/plan.yml` → 4 hops, file:line each (`algo.SPpaths`). |
| 1:10 | **Agent.** | Agent tab → "What happens if … cb-changed-files is compromised?" → tool timeline, path chips, "Grounded N/N". Then "Is evil-corp/backdoor-action in our CI?" → not in the graph, suggestions. |
| 1:30 | **Min-cut.** | Fix tab → **Compute minimal fix** → "**4 changes** protect **11** pipelines (naive: 11)", cyan cut edges, badge "FalkorDB algo.maxFlow". **Simulate fix (GRAPH.COPY)** → 11 → 0. |
| 1:50 | **Act.** | **Open PRs** (open one PR on GitHub in a tab) → **Merge & continue** (tag move + REPIN PR) → numbers drop to **0**, graph turns green. |
| 2:10 | **Scale.** | Pill **CNCF (1,129 repos)** → simulate `actions/github-script` (85 grep vs 99, 14 hidden, 6 SHA-pinned still exposed) → Leaderboard tab. Mention: 17.6% of exposure across the top 20 actions is hidden; `actions/create-github-app-token` is 82% hidden. |
| 2:25 | **Close.** | "ChainBreaker: the graph finds what grep can't, and fixes it in the fewest moves." Live URL. |

After recording: **Reset demo** so the org is back to the compromised scenario.
