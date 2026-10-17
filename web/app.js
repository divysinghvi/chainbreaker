/* ChainBreaker web console. No build step: one file, force-graph from unpkg. */
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const C = { red: "#ef4444", orange: "#f97316", amber: "#f59e0b", yellow: "#eab308", green: "#22c55e",
            cyan: "#22d3ee", violet: "#a78bfa", grey: "#4b5563", line: "#273244", text: "#e5e7eb", bg: "#0b0f17" };
const SEV = { HIGH: C.orange, MED: C.amber, LOW: C.yellow };
const SEV_ORDER = { HIGH: 0, MED: 1, LOW: 2 };

const S = {
  ds: "demo", org: "", publicMode: false, adv: null, action: null, depth: 1, blast: null, viz: null,
  sort: "sev", targets: "all", plan: null, cut: new Set(), fixed: new Set(), wasExposed: new Set(),
  chatId: null, replay: null, step: 0, graphMode: "viz", showSafe: false, big: false,
};
const BIG = 150;

// ---------- helpers ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const shortSha = (s) => String(s || "").replace(/@([0-9a-f]{40})/g, (_, h) => "@" + h.slice(0, 7));
const shortWf = (id) => { const [repo, path] = id.split(":"); return `${repo.split("/").pop()}/${(path || "").split("/").pop()}`; };
const ghLink = (repo, path, lines) =>
  repo && !repo.startsWith("repo-") ? `https://github.com/${repo}/blob/HEAD/${path}${lines && lines.length ? "#L" + lines[0] : ""}` : null;

function tokenGet() { try { return sessionStorage.getItem("cb-admin") || ""; } catch { return ""; } }
function tokenSet(v) { try { sessionStorage.setItem("cb-admin", v); } catch { /* storage blocked */ } }

function setCounter(ms, q) { if (ms !== undefined) $("#counter").textContent = `FalkorDB: ${ms} ms · ${q} queries`; }

async function api(path, { method = "GET", body, admin = false } = {}) {
  const headers = { "content-type": "application/json" };
  if (admin) headers["X-Admin-Token"] = $("#admin-token").value || tokenGet();
  const r = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  setCounter(j.graph_ms, j.queries);
  if (!r.ok) {
    const d = j.detail;
    const err = new Error(typeof d === "string" ? d : (d && d.error) || r.statusText);
    err.detail = d; err.status = r.status;
    throw err;
  }
  return j;
}

function animate(el, to) {
  const from = Number(el.textContent) || 0, t0 = performance.now(), dur = 550;
  if (from === to) { el.textContent = to; return; }
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function mdLite(text) {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^#{1,4} (.+)$/gm, "<strong>$1</strong>")
    .replace(/^\s*[-*] (.+)$/gm, "• $1")
    .replace(/\n/g, "<br>");
}

// ---------- graph ----------
let G = null, fitted = false;

function initGraph() {
  if (typeof ForceGraph === "undefined") { $("#graph-empty").textContent = "force-graph failed to load."; return; }
  G = ForceGraph()($("#graph"))
    .backgroundColor(C.bg)
    .nodeId("id")
    .dagMode("lr").dagLevelDistance(130)
    .onDagError(() => G.dagMode(null))
    .nodeRelSize(5)
    .nodeCanvasObject(drawNode)
    .nodePointerAreaPaint((n, color, ctx) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(n.x, n.y, 9, 0, 2 * Math.PI); ctx.fill(); })
    .nodeLabel((n) => esc(n.id))
    .linkColor(linkColor)
    .linkWidth((l) => (S.cut.has(l.key) ? 3 : l.hot ? 1.6 : 1))
    .linkLineDash((l) => (l.mutable ? [4, 3] : null))
    .linkDirectionalArrowLength(3.5).linkDirectionalArrowRelPos(0.92)
    .linkDirectionalParticleWidth(3.2).linkDirectionalParticleSpeed(0.012)
    .linkDirectionalParticleColor(() => C.red)
    .linkLabel((l) => esc(`${l.uses || ""}\n${l.file_path || ""}${l.lines && l.lines.length ? ":" + l.lines.join(",") : ""}`))
    .cooldownTicks(120)
    .onEngineStop(() => { if (!fitted) { G.zoomToFit(600, 40); fitted = true; } })
    .onNodeClick((n) => {
      if (S.graphMode === "viz" && n.label === "Workflow" && !n.at_ref) openDrawer(n.id);
    });
  G.d3Force("charge").strength(-140);
  if (window.d3) {  // keep labels apart and disconnected (safe) chains from drifting off-screen
    G.d3Force("collide", d3.forceCollide(14));
    G.d3Force("y", d3.forceY(0).strength(0.05));
  }
  new ResizeObserver(() => { const el = $("#graph"); G.width(el.clientWidth).height(el.clientHeight); }).observe($("#graph"));
}

function nodeColor(n) {
  if (S.graphMode === "replay") return n.lit ? C.red : C.grey;
  if (n.label === "Workflow" && !n.at_ref) {
    if (n.exposed) return SEV[n.severity] || C.amber;
    return S.fixed.has(n.id) ? C.green : C.grey;
  }
  if (n.compromised) return C.red;
  if (n.exposed) return C.violet;
  return S.fixed.size && S.fixed.has(n.id) ? C.green : C.grey;
}

function drawNode(n, ctx, scale) {
  const col = nodeColor(n);
  const fs = Math.max(10 / scale, 2.4);
  const showLabel = S.graphMode === "replay" || n.compromised ||
    (S.big ? scale > 2.2 : scale > 0.9 || (n.exposed && n.label === "Workflow"));
  ctx.font = `${fs}px Inter, sans-serif`;
  if (n.label === "Workflow" && !n.at_ref) {
    const w = showLabel ? Math.max(ctx.measureText(n.short).width + 8 / scale, 18) : 14;
    const h = showLabel ? fs + 6 / scale : 7;
    ctx.fillStyle = col;
    roundRect(ctx, n.x - w / 2, n.y - h / 2, w, h, 3 / scale);
    ctx.fill();
    if (n.pinned_but_exposed) { ctx.strokeStyle = C.cyan; ctx.lineWidth = 1.5 / scale; ctx.stroke(); }
    if (showLabel) { ctx.fillStyle = "#0b0f17"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(n.short, n.x, n.y); }
    return;
  }
  const r = n.compromised ? 7 : 5.5;
  ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI); ctx.fillStyle = col; ctx.fill();
  if (n.pinned) { ctx.beginPath(); ctx.arc(n.x, n.y, r + 2.2, 0, 2 * Math.PI); ctx.strokeStyle = C.green; ctx.lineWidth = 1.4; ctx.stroke(); }
  if (n.at_ref) { ctx.strokeStyle = C.text; ctx.lineWidth = 0.8; ctx.strokeRect(n.x - r, n.y - r, 2 * r, 2 * r); }
  if (showLabel) {
    ctx.fillStyle = C.text; ctx.textAlign = "center"; ctx.textBaseline = "top";
    ctx.fillText(n.short, n.x, n.y + r + 3);
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

function linkColor(l) {
  if (S.graphMode === "replay") return l.lit ? C.red : C.line;
  if (S.cut.has(l.key)) return C.cyan;
  if (S.fixed.size && l.wasHot && !l.hot) return C.green;
  return l.hot ? "rgba(239,68,68,.55)" : C.line;
}

function renderViz(v) {
  S.graphMode = "viz";
  // big graphs: show the exposed subgraph only, unless the viewer asks for the safe paths too
  let nodesIn = v.nodes;
  const tooBig = v.nodes.length > BIG;
  if (tooBig && !S.showSafe) nodesIn = v.nodes.filter((n) => n.compromised || n.exposed);
  S.big = nodesIn.length > 60;
  $("#graph-note").hidden = !tooBig;
  $("#graph-note").innerHTML = tooBig ? `${S.showSafe ? "All" : "Exposed subgraph:"} ${nodesIn.length} of ${v.total_nodes} nodes · <button class="mini" id="toggle-safe">${S.showSafe ? "hide" : "show"} safe paths</button>` : "";
  const t = $("#toggle-safe");
  if (t) t.onclick = () => { S.showSafe = !S.showSafe; renderViz(S.viz); };
  const byId = Object.fromEntries(nodesIn.map((n) => [n.id, n]));
  v = { ...v, nodes: nodesIn, links: v.links.filter((l) => byId[l.source] && byId[l.target]) };
  // display links reversed (dependency -> consumer) so infection flows left to right
  const links = v.links.map((l) => {
    const dep = byId[l.target], con = byId[l.source];
    const hot = (dep.compromised || dep.exposed) && con.exposed;
    return { source: l.target, target: l.source, key: `${l.target}|${l.source}`, uses: l.uses, file_path: l.file_path,
             lines: l.lines, mutable: !dep.pinned, hot, wasHot: S.wasExposed.has(con.id) };
  });
  $("#graph-empty").hidden = v.nodes.length > 0;
  if (!v.nodes.length) $("#graph-empty").textContent = "No pipeline reaches this action within this depth.";
  if (!G) return;
  fitted = false;
  G.dagMode("lr").graphData({ nodes: v.nodes.map((n) => ({ ...n })), links });
  fitSoon();
  setTimeout(wave, 700);
}

function fitSoon() {
  // onEngineStop can fire before the DAG has spread out; fit again once the layout has settled
  [900, 2200].forEach((ms) => setTimeout(() => G && G.zoomToFit(500, 40), ms));
}

function wave() {
  if (!G || S.graphMode !== "viz") return;
  const { nodes, links } = G.graphData();
  const out = new Map();
  links.forEach((l) => { const s = l.source.id ?? l.source; if (!out.has(s)) out.set(s, []); out.get(s).push(l); });
  let layer = nodes.filter((n) => n.compromised).map((n) => n.id);
  const seen = new Set(layer);
  for (let k = 0; layer.length && k < 10; k++) {
    const next = [];
    const batch = [];
    layer.forEach((id) => (out.get(id) || []).forEach((l) => {
      if (!l.hot) return;
      batch.push(l);
      const t = l.target.id ?? l.target;
      if (!seen.has(t)) { seen.add(t); next.push(t); }
    }));
    setTimeout(() => batch.forEach((l) => G.emitParticle(l)), k * 350);
    layer = next;
  }
}

// ---------- datasets & stats ----------
async function loadDatasets() {
  const d = await api("/api/datasets");
  S.org = d.demo_org; S.publicMode = d.public_mode;
  const cncf = d.datasets.find((x) => x.id === "cncf");
  if (cncf && cncf.stats) $("#cncf-count").textContent = `(${cncf.stats.counts.Repo.toLocaleString()} repos)`;
  $$(".pill").forEach((p) => { p.disabled = !d.datasets.some((x) => x.id === p.dataset.ds); });
  renderPrompts();
}

async function selectDataset(ds) {
  S.ds = ds;
  $$(".pill").forEach((p) => p.classList.toggle("on", p.dataset.ds === ds));
  closeDrawer();
  const replay = ds === "replay-tj-2025";
  $("#incident").hidden = replay; $("#replay-left").hidden = !replay;
  if (replay) { selectTab("replay"); await showReplay(); return; }
  if ($("#tab-replay").hidden === false) selectTab("fix");
  Object.assign(S, { adv: null, blast: null, viz: null, plan: null, cut: new Set(), fixed: new Set(), wasExposed: new Set(), chatId: null });
  $("#timeline").innerHTML = ""; $("#plan-out").innerHTML = ""; $("#admin-log").innerHTML = "";
  ["#depth-box", "#cards", "#list-head"].forEach((s) => ($(s).hidden = true));
  $("#exposed").innerHTML = ""; $("#sev-chips").innerHTML = ""; $("#adv-info").textContent = "";
  $("#plan").disabled = true;
  $("#admin").hidden = ds !== "demo";
  renderPrompts();
  if (G) G.graphData({ nodes: [], links: [] });
  $("#graph-empty").hidden = false;
  $("#graph-empty").textContent = "Pick an action and simulate a compromise. Infection flows left → right, from the compromised action to every pipeline that runs it.";
  const st = await api(`/api/${ds}/stats`);
  $("#stats").innerHTML = [
    ["repos", st.counts.Repo], ["workflows", st.workflows_head], ["action refs", st.counts.ActionRef],
    ["USES edges", st.uses_edges], ["mutable refs", st.mutable_ref_pct + "%"],
  ].map(([k, v]) => `<span><b>${typeof v === "number" ? v.toLocaleString() : v}</b> ${k}</span>`).join("");
  $("#action-q").value = ds === "demo" ? `${S.org}/cb-changed-files` : "actions/github-script";
  if (!$("#tab-leader").hidden) loadLeaderboard();
}

// ---------- action search ----------
let searchT = null, sel = -1;
async function searchActions() {
  const q = $("#action-q").value.trim();
  const list = $("#action-list");
  try {
    const r = await api(`/api/${S.ds}/actions/search?q=${encodeURIComponent(q)}`);
    sel = -1;
    list.innerHTML = r.results.map((x, i) => `<li role="option" id="opt-${i}" data-id="${esc(x.id)}">${esc(x.id)}${x.direct ? ` <span class="muted">· ${x.direct} direct</span>` : ""}</li>`).join("");
    list.hidden = !r.results.length;
  } catch { list.hidden = true; }
}
function pickSuggestion(id) { $("#action-q").value = id; $("#action-list").hidden = true; }

async function compromise() {
  const action_id = $("#action-q").value.trim();
  if (!action_id) return;
  $("#action-list").hidden = true;
  try {
    const a = await api(`/api/${S.ds}/advisories`, { method: "POST", body: { action_id } });
    S.adv = a.id; S.action = a.action_id; S.plan = null; S.cut = new Set(); S.fixed = new Set(); S.wasExposed = new Set();
    $("#plan-out").innerHTML = "";
    $("#adv-info").innerHTML = `<b class="mono">${esc(a.id)}</b> · compromised: ${a.compromised_refs.map((r) => `<code>${esc(shortSha(r))}</code>`).join(", ") || "<i>no mutable refs</i>"}`;
    S.depth = 1; $("#depth").value = 1;
    ["#depth-box", "#cards", "#list-head"].forEach((s) => ($(s).hidden = false));
    $("#plan").disabled = false;
    $("#open-prs").disabled = true; $("#merge").disabled = true;
    await refresh();
  } catch (e) {
    const sug = e.detail && e.detail.suggestions;
    $("#adv-info").innerHTML = `<span style="color:var(--red)">${esc(e.message)}</span>` +
      (sug && sug.length ? `<br>Did you mean: ${sug.map((s) => `<a href="#" data-sug="${esc(s)}">${esc(s)}</a>`).join(", ")}` : "");
  }
}

async function refresh() {
  if (!S.adv) return;
  const d = S.depth;
  const [b, v] = await Promise.all([
    api(`/api/${S.ds}/advisories/${S.adv}/blast?depth=${d}`),
    api(`/api/${S.ds}/advisories/${S.adv}/graph?depth=${d}`),
  ]);
  if (d !== S.depth) return; // a newer slider value is already loading
  S.blast = b; S.viz = v;
  $("#depth-val").textContent = d;
  renderNumbers(b);
  renderList();
  renderViz(v);
}

function renderNumbers(b) {
  animate($("#n-grep"), b.depth1);
  animate($("#n-total"), b.exposed_total);
  animate($("#n-hidden"), b.hidden);
  animate($("#n-pinned"), b.pinned_but_exposed.length);
  $("#sev-chips").innerHTML = ["HIGH", "MED", "LOW"].map((s) => `<span class="chip ${s}">${s} ${b.by_severity[s] || 0}</span>`).join("");
}

function renderList() {
  const xs = [...(S.blast ? S.blast.exposed : [])];
  xs.sort(S.sort === "depth" ? (a, b) => b.depth - a.depth || SEV_ORDER[a.severity] - SEV_ORDER[b.severity]
                             : (a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity] || b.depth - a.depth);
  $("#exposed").innerHTML = xs.slice(0, 300).map((x) => `<li tabindex="0" data-demo="exposed-row" data-wf="${esc(x.workflow)}">
    <span class="sev ${x.severity}">${x.severity}</span><span class="name">${esc(shortWf(x.workflow))}</span>
    ${x.pinned_but_exposed ? '<span class="tag" title="pinned its direct dependency to a SHA, still exposed">SHA-pinned</span>' : ""}
    <span class="d">d${x.depth}</span></li>`).join("") + (xs.length > 300 ? `<li class="muted">…and ${xs.length - 300} more</li>` : "");
}

// ---------- drawer ----------
async function openDrawer(wid) {
  if (!S.adv) return;
  const r = await api(`/api/${S.ds}/advisories/${S.adv}/path?workflow=${encodeURIComponent(wid)}&depth=8`);
  $("#drawer-h").textContent = wid;
  const p = r.path, risk = r.risk || {};
  const hops = p ? `<p>${p.depth} hop${p.depth > 1 ? "s" : ""} to the compromised ref <span class="engine">${esc(p.engine)}</span></p><ol class="hops" data-demo="path-hops">${p.hops.map((h) => {
    const link = ghLink(h.file_repo, h.file_path, h.lines);
    const where = `${esc(h.file_repo)}:${esc(h.file_path)}:${h.lines.join(",")}`;
    return `<li class="hop"><div class="uses">uses: ${esc(shortSha(h.uses))}${h.pinned ? '<span class="badge pin">SHA</span>' : '<span class="badge mut">mutable</span>'}</div>
      <div class="file">${link ? `<a href="${esc(link)}" target="_blank" rel="noopener">${where}</a>` : where}${h.src_immutable ? " · immutable commit" : ""}</div>
      <div class="to">→ ${esc(shortSha(h.to))}</div></li>`;
  }).join("")}</ol>` : `<p class="muted">Not exposed within the traversal depth.</p>`;
  $("#drawer-body").innerHTML = hops + `<dl class="kv">
    <dt>severity</dt><dd><span class="sev ${esc(risk.severity)}">${esc(risk.severity || "–")}</span></dd>
    <dt>triggers</dt><dd class="mono">${esc((risk.triggers || []).join(", "))}</dd>
    <dt>token perms</dt><dd class="mono">${esc(risk.perms || "")}${risk.id_token_write ? " · id-token: write" : ""}</dd>
    <dt>secrets</dt><dd class="mono">${esc((risk.secrets || []).join(", ") || "none")} <span class="muted">(names only)</span></dd>
    <dt>why</dt><dd>${esc((risk.severity_reasons || []).join(" · "))}</dd></dl>`;
  $("#drawer").hidden = false;
}
function closeDrawer() { $("#drawer").hidden = true; }

// ---------- fix ----------
async function computePlan() {
  if (!S.adv) return;
  $("#plan").disabled = true; $("#plan").textContent = "Computing min-cut…";
  try {
    const p = await api(`/api/${S.ds}/advisories/${S.adv}/plan`, { method: "POST", body: { targets: S.targets } });
    S.plan = p;
    S.cut = new Set(p.fixes.map((f) => `${f.dst_id}|${f.src_id}`));
    const fb = p.engine.includes("fallback");
    $("#plan-out").innerHTML = `<p class="headline" data-demo="fix-headline"><b>${p.cut_size} change${p.cut_size === 1 ? "" : "s"}</b> protect <b>${p.protected}</b> pipelines <span class="muted">(naive: ${p.naive})</span></p>
      <span class="engine ${fb ? "fallback" : ""}" data-demo="engine-badge">${fb ? "networkx fallback" : "FalkorDB algo.maxFlow"}</span>
      <span class="muted mono" style="font-size:11px"> maxFlow ${p.max_flow} · GRAPH.COPY ${p.copy_ms} ms</span>
      <ul class="fixes">${p.fixes.slice(0, 40).map(fixCard).join("")}</ul>
      ${p.fixes.length > 40 ? `<p class="muted">…and ${p.fixes.length - 40} more</p>` : ""}
      <button class="btn" id="simulate" data-demo="simulate-fix">Simulate fix (GRAPH.COPY)</button><div id="sim-out"></div>
      <p class="hint"><b>PIN</b> = pin the compromised ref to the known-good SHA · <b>REPIN</b> = move an existing SHA pin to the fixed commit · <b>VENDOR</b> = replace or vendor an intermediate action (manual).</p>`;
    $("#simulate").onclick = simulateFix;
    $("#open-prs").disabled = !(S.ds === "demo" && p.fixes.some((f) => f.phase === 1));
    $("#merge").disabled = true;
    if (G) G.linkColor(G.linkColor()).linkWidth(G.linkWidth());
  } catch (e) { $("#plan-out").innerHTML = `<p style="color:var(--red)">${esc(e.message)}</p>`; }
  $("#plan").disabled = false; $("#plan").textContent = "Compute minimal fix";
}

function fixCard(f) {
  const link = ghLink(f.file_repo, f.file_path, f.lines);
  const where = `${esc(f.file_repo)}:${esc(f.file_path)}:${f.lines.join(",")}`;
  const nu = f.new_uses ? `<ins>${esc(shortSha(f.new_uses))}</ins>` : `<span class="muted">${f.type === "REPIN" ? "fixed commit, chosen at apply time" : "manual"}</span>`;
  return `<li class="fix"><div class="top"><span class="type ${f.type}">${f.type}</span><span class="muted" style="font-size:11px">protects ${f.protects} · phase ${f.phase}</span></div>
    <div class="file">${link ? `<a href="${esc(link)}" target="_blank" rel="noopener">${where}</a>` : where}</div>
    <div class="chg"><del>${esc(shortSha(f.old_uses))}</del> → ${nu}</div></li>`;
}

async function simulateFix() {
  const s = await api(`/api/${S.ds}/plans/${S.plan.id}/simulate`, { method: "POST" });
  $("#sim-out").innerHTML = `<div class="sim" data-demo="sim-result">What-if on a scratch copy: exposed <b>${s.before}</b> → <b style="color:${s.after ? C.red : C.green}">${s.after}</b>
    <span class="muted">(all targets: ${s.before_total} → ${s.after_total}) · GRAPH.COPY ${s.copy_ms} ms · scratch graph deleted</span></div>`;
}

// ---------- admin (real GitHub writes in the demo org) ----------
function logLines(lines) {
  $("#admin-log").innerHTML += lines.map((l) => `<li>${esc(l).replace(/(https:\/\/github\.com\/\S+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')}</li>`).join("");
  $("#admin-log").scrollTop = 1e9;
}
async function adminCall(btn, label, path) {
  tokenSet($("#admin-token").value);
  const old = btn.textContent; btn.disabled = true; btn.textContent = label;
  try { const r = await api(path, { method: "POST", admin: true }); logLines(r.log || []); return r; }
  catch (e) { logLines([`error: ${e.message}`]); return null; }
  finally { btn.textContent = old; btn.disabled = false; }
}
async function openPRs() {
  const r = await adminCall($("#open-prs"), "Opening PRs…", `/api/demo/plans/${S.plan.id}/open`);
  $("#open-prs").disabled = !!r;
  if (r) $("#merge").disabled = false;
  return r;
}
async function mergeContinue() {
  S.wasExposed = new Set((S.blast?.exposed || []).map((x) => x.workflow));
  const r = await adminCall($("#merge"), "Merging, moving tags, REPIN, rescan…", `/api/demo/plans/${S.plan.id}/merge`);
  if (r) { $("#merge").disabled = true; await afterRescan(); }
}
async function rescan() {
  S.wasExposed = new Set((S.blast?.exposed || []).map((x) => x.workflow));
  const r = await adminCall($("#rescan"), "Rescanning…", "/api/demo/rescan");
  if (r) await afterRescan();
}
async function afterRescan() {
  S.fixed = new Set([...S.wasExposed, ...(S.viz?.nodes || []).filter((n) => n.exposed).map((n) => n.id)]);
  S.cut = new Set();
  await refresh();
  if (S.blast && S.blast.exposed_total === 0) logLines([`✓ exposure is now 0 for ${S.adv}`]);
}
async function resetDemo() {
  const r = await adminCall($("#reset"), "Resetting demo org…", "/api/demo/reset");
  if (r) { S.fixed = new Set(); S.wasExposed = new Set(); S.cut = new Set(); S.plan = null; $("#plan-out").innerHTML = ""; await refresh(); }
}

// ---------- agent ----------
function prompts() {
  const org = S.org || "<org>";
  return S.ds === "demo"
    ? [`What happens if ${org}/cb-changed-files is compromised?`, "Show me the deepest exposed pipeline and why.",
       "Fix it with the fewest changes.", "Is evil-corp/backdoor-action in our CI?", "Which actions are the most load-bearing?",
       "What did we find last time?"]
    : ["What happens if actions/github-script is compromised?", "Which actions are the most load-bearing?",
       "Is evil-corp/backdoor-action used anywhere?", "Fix it with the fewest changes for high-value pipelines."];
}
function renderPrompts() {
  $("#prompts").innerHTML = prompts().map((p) => `<button type="button">${esc(p)}</button>`).join("");
}

function evCard(cls, html) { const d = document.createElement("div"); d.className = `ev ${cls}`; d.innerHTML = html; $("#timeline").append(d); d.scrollIntoView({ block: "nearest" }); return d; }

async function ask(q) {
  q = q.trim();
  if (!q) return;
  $("#ask-q").value = ""; $("#ask-go").disabled = true;
  evCard("user", esc(q));
  const pending = {};
  try {
    const res = await fetch("/api/agent", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ dataset: S.ds, message: q, chat_id: S.chatId }) });
    if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(j.detail || res.statusText); }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        if (chunk.startsWith("data: ")) handleEvent(JSON.parse(chunk.slice(6)), pending, q);
      }
    }
  } catch (e) { evCard("err", esc(e.message)); }
  $("#ask-go").disabled = false;
}

const ICON = { find_action: "🔎", simulate_compromise: "☣", blast_radius: "💥", explain_exposure: "🧭", workflow_risk: "🛡",
               plan_fix: "✂", simulate_fix: "🧪", request_fix_approval: "✋", load_bearing_actions: "🏗", recall_findings: "🧠" };

function handleEvent(ev, pending, q) {
  setCounter(ev.graph_ms, ev.queries);
  if (ev.type === "chat") {
    S.chatId = ev.chat_id;
  } else if (ev.type === "tool_call") {
    pending[ev.name] = evCard("call", `<span class="tool">${ICON[ev.name] || "•"} ${esc(ev.name)}</span><div class="args">${esc(JSON.stringify(ev.args))}</div><div class="res muted">running…</div>`);
  } else if (ev.type === "tool_result") {
    const c = pending[ev.name];
    if (c) c.querySelector(".res").outerHTML = `<div class="res"><span class="ms">${ev.ms} ms · ${ev.rows} rows</span>${esc(ev.summary)}</div>`;
    if (ev.name === "simulate_compromise" && S.adv === null) { /* agent's advisory shows on the next manual compromise */ }
  } else if (ev.type === "grounding_retry") {
    evCard("call", `↻ grounding check: rewriting without ${esc(ev.unverified.join(", "))}`);
  } else if (ev.type === "approval") {
    const d = evCard("approval", `<b>Approval needed</b> · ${esc(ev.plan_id)}<br>${esc(ev.summary)}
      ${ev.can_apply ? `<div class="row"><button class="btn primary" data-approve="${esc(ev.plan_id)}">Approve: open PRs</button></div>` : ""}`);
    const b = d.querySelector("[data-approve]");
    if (b) b.onclick = () => approve(ev.plan_id, d);
  } else if (ev.type === "final") {
    const g = ev.grounding, warn = g.unverified.length > 0;
    const chips = (ev.paths || []).slice(0, 3).map((p) => `<div class="pathchips" data-demo="agent-paths"><span class="pc" data-wf="${esc(p.workflow)}">${esc(shortWf(p.workflow))}</span>${
      p.hops.map((h) => `<span class="arrow">→</span><span class="pc">${esc(shortSha(h.to.split("/").slice(1).join("/") || h.to))}</span>`).join("")}</div>`).join("");
    $$("[data-demo=agent-final]").forEach((e) => e.removeAttribute("data-demo"));
    evCard("final", `<div class="answer">${mdLite(ev.text)}</div>${chips}
      <span class="ground ${warn ? "warn" : ""}" data-demo="agent-grounding">${warn ? "⚠" : "✓"} Grounded: ${g.verified}/${g.total} names verified in FalkorDB${warn ? ` · unverified: ${esc(g.unverified.join(", "))}` : ""}</span>
      <span class="muted" style="font-size:11px"> · ${esc(ev.outcome)}</span>`).setAttribute("data-demo", "agent-final");
  } else if (ev.type === "error") {
    evCard("err", esc(ev.message));
  }
}

async function approve(pid, card) {
  const token = $("#admin-token").value || tokenGet();
  if (!token) { card.insertAdjacentHTML("beforeend", `<p class="hint">Enter the admin token in the Fix tab first.</p>`); return; }
  try {
    const r = await api(`/api/demo/plans/${pid}/open`, { method: "POST", admin: true });
    card.insertAdjacentHTML("beforeend", `<ol class="log mono">${(r.log || []).map((l) => `<li>${esc(l).replace(/(https:\/\/github\.com\/\S+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')}</li>`).join("")}</ol>`);
    S.plan = r.plan; $("#merge").disabled = false;
  } catch (e) { card.insertAdjacentHTML("beforeend", `<p style="color:var(--red)">${esc(e.message)}</p>`); }
}

// ---------- leaderboard ----------
async function loadLeaderboard() {
  if (S.ds === "replay-tj-2025") return;
  $("#leader").innerHTML = `<p class="muted">Loading…</p>`;
  const r = await api(`/api/${S.ds}/leaderboard?top=15`);
  const max = Math.max(...r.rows.map((x) => x.pagerank), 1e-9);
  $("#leader").innerHTML = `<table class="lb"><thead><tr><th>Action</th><th class="n">direct</th><th class="n">reach</th><th class="n">hidden</th><th class="n">mutable</th></tr></thead><tbody>${
    r.rows.map((x) => `<tr><td class="act">${esc(x.action)}<div class="bar" style="width:${Math.round(100 * x.pagerank / max)}%" title="PageRank ${x.pagerank}"></div></td>
      <td class="n">${x.direct}</td><td class="n">${x.reach}</td><td class="n">${x.hidden_reach}</td><td class="n">${x.mutable_pct}%</td></tr>`).join("")}</tbody></table>
    <p class="hint">Bar = PageRank. Hidden = workflows that reach the action only through other actions.</p>`;
}

// ---------- replay ----------
async function showReplay() {
  if (!S.replay) S.replay = await api("/api/replay/tj-2025");
  $("#stats").innerHTML = `<span><b>${S.replay.nodes.length}</b> nodes</span><span><b>${S.replay.steps.filter((s) => s.edge).length}</b> edges</span><span class="mono">${esc(S.replay.graph)}</span>`;
  $("#replay-src").href = S.replay.source;
  $("#stepper").innerHTML = S.replay.steps.map((_, i) => `<button data-step="${i}" data-demo="replay-step" aria-label="Step ${i + 1}">${i + 1}</button>`).join("");
  S.graphMode = "replay";
  const nodes = S.replay.nodes.map((n) => ({ id: n.id, short: n.name, label: n.label }));
  const links = S.replay.steps.filter((s) => s.edge).map((s) => ({ source: s.edge[0], target: s.edge[1], key: s.edge.join("|") }));
  $("#graph-empty").hidden = true;
  if (G) { fitted = false; G.dagMode("lr").graphData({ nodes, links }); fitSoon(); }
  goStep(0);
}
function goStep(i) {
  const steps = S.replay.steps;
  S.step = Math.max(0, Math.min(steps.length - 1, i));
  const lit = new Set(steps.slice(0, S.step + 1).filter((s) => s.edge).flatMap((s) => s.edge));
  const litE = new Set(steps.slice(0, S.step + 1).filter((s) => s.edge).map((s) => s.edge.join("|")));
  if (G) {
    const { nodes, links } = G.graphData();
    nodes.forEach((n) => (n.lit = lit.has(n.id)));
    links.forEach((l) => (l.lit = litE.has(l.key)));
    const cur = steps[S.step].edge && links.find((l) => l.key === steps[S.step].edge.join("|"));
    if (cur) setTimeout(() => G.emitParticle(cur), 50);
    G.nodeCanvasObject(drawNode);
  }
  $$("#stepper button").forEach((b, k) => { b.classList.toggle("on", k === S.step); b.classList.toggle("done", k < S.step); });
  $("#replay-cap").innerHTML = `${esc(steps[S.step].caption)} <a href="${esc(S.replay.source)}" target="_blank" rel="noopener">source</a>`;
}

// ---------- tabs & wiring ----------
function selectTab(t) {
  $$(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  ["fix", "agent", "leader", "replay"].forEach((k) => ($(`#tab-${k}`).hidden = k !== t));
  if (t === "leader") loadLeaderboard();
  if (t === "replay" && S.ds !== "replay-tj-2025") selectDataset("replay-tj-2025");
}

function wire() {
  $$(".pill").forEach((p) => (p.onclick = () => selectDataset(p.dataset.ds)));
  $$(".tab").forEach((b) => (b.onclick = () => selectTab(b.dataset.tab)));
  const q = $("#action-q");
  q.addEventListener("input", () => { clearTimeout(searchT); searchT = setTimeout(searchActions, 200); });
  q.addEventListener("focus", searchActions);
  q.addEventListener("keydown", (e) => {
    const items = $$("#action-list li");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % Math.max(items.length, 1);
      items.forEach((li, i) => li.setAttribute("aria-selected", i === sel));
    } else if (e.key === "Enter") {
      if (sel >= 0 && items[sel]) pickSuggestion(items[sel].dataset.id); else compromise();
    } else if (e.key === "Escape") $("#action-list").hidden = true;
  });
  $("#action-list").addEventListener("mousedown", (e) => { const li = e.target.closest("li"); if (li) pickSuggestion(li.dataset.id); });
  q.addEventListener("blur", () => setTimeout(() => ($("#action-list").hidden = true), 150));
  $("#adv-info").addEventListener("click", (e) => { const a = e.target.closest("[data-sug]"); if (a) { e.preventDefault(); pickSuggestion(a.dataset.sug); } });
  $("#compromise").onclick = compromise;
  let depthT = null;
  $("#depth").addEventListener("input", (e) => {
    S.depth = Number(e.target.value); $("#depth-val").textContent = S.depth;
    clearTimeout(depthT); depthT = setTimeout(refresh, 120);
  });
  $$("[data-sort]").forEach((b) => (b.onclick = () => { S.sort = b.dataset.sort; $$("[data-sort]").forEach((x) => x.classList.toggle("on", x === b)); renderList(); }));
  $("#exposed").addEventListener("click", (e) => { const li = e.target.closest("[data-wf]"); if (li) openDrawer(li.dataset.wf); });
  $("#exposed").addEventListener("keydown", (e) => { const li = e.target.closest("[data-wf]"); if (li && e.key === "Enter") openDrawer(li.dataset.wf); });
  $("#drawer-x").onclick = closeDrawer;
  $$("[data-targets]").forEach((b) => (b.onclick = () => { S.targets = b.dataset.targets; $$("[data-targets]").forEach((x) => x.classList.toggle("on", x === b)); }));
  $("#plan").onclick = computePlan;
  $("#admin-token").value = tokenGet();
  $("#open-prs").onclick = openPRs;
  $("#merge").onclick = mergeContinue;
  $("#rescan").onclick = rescan;
  $("#reset").onclick = resetDemo;
  $("#new-chat").onclick = () => { S.chatId = null; $("#timeline").innerHTML = ""; $("#ask-q").focus(); };
  $("#prompts").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) ask(b.textContent); });
  $("#ask").addEventListener("submit", (e) => { e.preventDefault(); ask($("#ask-q").value); });
  $("#timeline").addEventListener("click", (e) => { const c = e.target.closest("[data-wf]"); if (c) openDrawer(c.dataset.wf); });
  $("#stepper").addEventListener("click", (e) => { const b = e.target.closest("[data-step]"); if (b) goStep(Number(b.dataset.step)); });
  $("#rp-prev").onclick = () => goStep(S.step - 1);
  $("#rp-next").onclick = () => goStep(S.step + 1);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
}

(async function main() {
  wire();
  initGraph();
  try { await loadDatasets(); await selectDataset("demo"); }
  catch (e) { $("#graph-empty").textContent = `API unavailable: ${e.message}`; }
})();
