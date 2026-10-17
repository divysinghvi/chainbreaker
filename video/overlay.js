/* Demo overlay, injected with page.add_init_script: fake cursor, lower-third captions, spotlight, wait chip.
   Everything is pointer-events: none and sits above the app. */
(() => {
  if (window.__demo) return;
  const CSS = `
  #__d_cursor { position: fixed; z-index: 2147483647; left: 0; top: 0; width: 20px; height: 20px; margin: -10px 0 0 -10px;
    border-radius: 50%; background: rgba(255,255,255,.92); box-shadow: 0 0 0 6px rgba(34,211,238,.28), 0 2px 8px rgba(0,0,0,.5);
    pointer-events: none; transition: transform .08s ease-out; }
  #__d_cursor.down { transform: scale(.78); }
  .__d_ripple { position: fixed; z-index: 2147483646; width: 20px; height: 20px; margin: -10px 0 0 -10px; border-radius: 50%;
    border: 2px solid rgba(34,211,238,.9); pointer-events: none; animation: __d_rip .55s ease-out forwards; }
  @keyframes __d_rip { from { transform: scale(1); opacity: 1 } to { transform: scale(3.4); opacity: 0 } }
  #__d_cap { position: fixed; z-index: 2147483645; left: 50%; bottom: 40px; transform: translate(-50%, 8px); max-width: 70%;
    padding: 14px 24px; border-radius: 8px; background: rgba(8,12,20,.86); border: 1px solid rgba(255,255,255,.08);
    color: #f3f4f6; font: 600 30px/1.25 Inter, system-ui, sans-serif; text-align: center; opacity: 0;
    transition: opacity .25s ease, transform .25s ease; pointer-events: none; box-shadow: 0 10px 40px rgba(0,0,0,.45); }
  #__d_cap.on { opacity: 1; transform: translate(-50%, 0); }
  #__d_cap.top { bottom: auto; top: 120px; }
  #__d_cap small { display: block; margin-top: 6px; font: 400 20px/1.3 Inter, system-ui, sans-serif; color: #9ca3af; }
  #__d_spot { position: fixed; z-index: 2147483640; border-radius: 10px; pointer-events: none; opacity: 0;
    box-shadow: 0 0 0 9999px rgba(0,0,0,.55); outline: 2px solid #22d3ee; outline-offset: 0;
    transition: opacity .3s ease, left .3s ease, top .3s ease, width .3s ease, height .3s ease; }
  #__d_spot.on { opacity: 1; }
  #__d_chip { position: fixed; z-index: 2147483645; top: 16px; right: 16px; padding: 6px 12px; border-radius: 999px;
    background: rgba(8,12,20,.9); border: 1px solid #22d3ee; color: #22d3ee; font: 600 18px/1 Inter, sans-serif;
    opacity: 0; transition: opacity .2s ease; pointer-events: none; }
  #__d_chip.on { opacity: 1; }`;

  const el = {};
  let spotSel = null, spotPad = 8, spotN = 1;

  function ensure() {
    if (el.cursor || !document.body) return;
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.append(style);
    for (const id of ["cursor", "cap", "spot", "chip"]) {
      el[id] = document.createElement("div");
      el[id].id = `__d_${id}`;
      document.body.append(el[id]);
    }
    el.cursor.style.transform = "";
    el.cursor.style.left = "-40px";
    el.cursor.style.top = "-40px";
    requestAnimationFrame(trackSpot);
  }

  function trackSpot() {
    if (spotSel) {
      // union box of the first n matches (e.g. the top 5 leaderboard rows)
      const rs = [...document.querySelectorAll(spotSel)].slice(0, spotN).map((t) => t.getBoundingClientRect());
      if (rs.length) {
        const l = Math.min(...rs.map((r) => r.left)), t = Math.min(...rs.map((r) => r.top));
        const r = Math.max(...rs.map((x) => x.right)), b = Math.max(...rs.map((x) => x.bottom));
        Object.assign(el.spot.style, { left: `${l - spotPad}px`, top: `${t - spotPad}px`,
          width: `${r - l + 2 * spotPad}px`, height: `${b - t + 2 * spotPad}px` });
      }
    }
    requestAnimationFrame(trackSpot);
  }

  document.addEventListener("DOMContentLoaded", ensure);
  addEventListener("mousemove", (e) => { ensure(); el.cursor.style.left = `${e.clientX}px`; el.cursor.style.top = `${e.clientY}px`; }, true);
  addEventListener("mousedown", (e) => {
    ensure();
    el.cursor.classList.add("down");
    const r = document.createElement("div");
    r.className = "__d_ripple";
    r.style.left = `${e.clientX}px`; r.style.top = `${e.clientY}px`;
    document.body.append(r);
    setTimeout(() => r.remove(), 600);
  }, true);
  addEventListener("mouseup", () => el.cursor && el.cursor.classList.remove("down"), true);

  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

  window.__demo = {
    caption(text, sub, opts = {}) {
      ensure();
      if (!text) { el.cap.classList.remove("on"); return; }
      el.cap.innerHTML = esc(text) + (sub ? `<small>${esc(sub)}</small>` : "");
      el.cap.classList.toggle("top", opts.pos === "top");
      el.cap.classList.add("on");
    },
    spotlight(selector, padding = 8, n = 1) {
      ensure();
      spotSel = selector; spotPad = padding; spotN = n;
      if (!selector || !document.querySelector(selector)) { el.spot.classList.remove("on"); spotSel = null; return false; }
      el.spot.classList.add("on");
      return true;
    },
    chip(text) { ensure(); if (text) el.chip.textContent = text; el.chip.classList.toggle("on", !!text); },
    clear() { this.caption(null); this.spotlight(null); this.chip(null); },
  };
})();
