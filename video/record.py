"""Record the demo scenes from the live app with Playwright (V2/V3).

    python video/record.py                 # all 12 scenes (creates + merges real PRs in the demo org)
    python video/record.py --scenes 01-04  # dry run

Capture is a CDP Page.startScreencast (JPEG q92, 1920x1080 from a 1600x900 @2x page), re-timed to constant
30 fps: Playwright's own recorder pads a 1600x900 viewport into a 1920x1080 frame and its VP9 is soft.
Writes video/raw/{main,github}.mp4, markers.json (seconds since the main video's t=0) and values.json
(every number shown in captions / narration, read from the page).
"""
import argparse
import base64
import json
import subprocess
import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import preflight  # noqa: E402

sys.path.insert(0, str(C.ROOT))
from chainbreaker import config  # noqa: E402

APP = "http://localhost:8000"
ACTION = f"{config.DEMO_ORG}/cb-changed-files"
Q1 = "What happens if cb-changed-files is compromised?"
Q2 = "Is evil-corp/backdoor-action in our CI?"
REPO_URL = os.getenv("REPO_URL", "https://github.com/divysinghvi/chainbreaker")
LIVE_URL = os.getenv("LIVE_URL", "https://chainbreaker-rose.vercel.app")
HOLD = 0.8  # seconds after every visible change
W = lambda sel: f"[data-demo={sel}]"  # noqa: E731


class Screencast:
    """JPEG frames with wall-clock timestamps -> constant-fps mp4 (holds included, since Chrome only sends
    frames when the page repaints)."""

    def __init__(self, page, name: str, t0: float):
        self.name, self.t0, self.dir = name, t0, C.RAW / f"frames_{name}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.frames: list[tuple[float, str]] = []
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080,
                                               "everyNthFrame": 1})

    def _frame(self, ev) -> None:
        fn = f"{len(self.frames):06d}.jpg"
        (self.dir / fn).write_bytes(base64.b64decode(ev["data"]))
        self.frames.append((ev["metadata"]["timestamp"] - self.t0, fn))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:  # noqa: BLE001 - page closing
            pass

    def stop(self) -> None:
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:  # noqa: BLE001
            pass

    def build(self, out: Path, start: float, end: float) -> None:
        """Frames between start..end (seconds on the main timeline) -> out.mp4 whose t=0 is `start`."""
        fr = [f for f in self.frames if f[0] <= end]
        if not fr:
            return
        lines = ["ffconcat version 1.0"]
        times = [max(start, t) for t, _ in fr] + [end]
        lines += [f"file '{fr[0][1]}'", f"duration {max(0.001, times[0] - start):.4f}"] if times[0] > start else []
        for i, (_, fn) in enumerate(fr):
            lines += [f"file '{fn}'", f"duration {max(0.001, times[i + 1] - times[i]):.4f}"]
        lines.append(f"file '{fr[-1][1]}'")
        (self.dir / "list.ffconcat").write_text("\n".join(lines) + "\n")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i",
                        str(self.dir / "list.ffconcat"), "-t", f"{end - start:.3f}",  # concat holds the last image too long
                        "-vf", "scale=1920:1080:flags=lanczos,fps=30",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-pix_fmt", "yuv420p", str(out)], check=True)


class Rec:
    def __init__(self, ctx, page):
        self.ctx, self.page, self.t0 = ctx, page, time.time()
        self.markers: list[dict] = []
        self.values: dict = {**preflight.read_results(), "engine": preflight.read_engine()}
        self.scenes: dict[str, dict] = {}
        self.saved = 0.0
        self.github_cast = None
        self.cast = Screencast(page, "main", self.t0)

    # ---------- timeline ----------
    def now(self) -> float:
        return round(time.time() - self.t0, 3)

    def mark(self, kind: str, **kw) -> None:
        self.markers.append({"t": self.now(), "kind": kind, **kw})

    def pause(self, s: float) -> None:
        self.page.wait_for_timeout(int(s * 1000))

    # ---------- overlay ----------
    def caption(self, text, sub=None, pos=None):
        self.page.evaluate("([t, s, p]) => __demo.caption(t, s, {pos: p})", [text, sub, pos])

    def spot(self, sel, pad=8, n=1, hold=HOLD * 2):
        loc = self.page.locator(sel).first
        if loc.count():
            loc.scroll_into_view_if_needed()
        self.page.evaluate("([s, p, n]) => __demo.spotlight(s, p, n)", [sel, pad, n])
        self.pause(hold)

    # ---------- input (the cursor always travels before a click) ----------
    def move_to(self, loc):
        loc.scroll_into_view_if_needed()
        b = loc.bounding_box()
        self.page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=25)
        return b

    def move_click(self, sel, hold=HOLD):
        loc = self.page.locator(sel).first
        b = self.move_to(loc)
        self.pause(0.15)
        self.page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        self.pause(hold)

    def type_slow(self, sel, text, clear=True):
        self.move_click(sel, hold=0.2)
        loc = self.page.locator(sel).first
        if clear:
            loc.press("ControlOrMeta+a")
            loc.press("Backspace")
        loc.press_sequentially(text, delay=35)
        self.pause(0.3)

    def drag_slider(self, sel, from_v, to_v, lo=1, hi=6):
        b = self.move_to(self.page.locator(sel).first)
        thumb = 16
        x = lambda v: b["x"] + thumb / 2 + (v - lo) / (hi - lo) * (b["width"] - thumb)  # noqa: E731
        y = b["y"] + b["height"] / 2
        self.page.mouse.move(x(from_v), y, steps=10)
        self.page.mouse.down()
        for v in range(from_v + 1, to_v + 1):
            self.page.mouse.move(x(v), y, steps=14)
            self.pause(0.9)
        self.page.mouse.up()

    def wait_logged(self, name, fn, chip="⏩"):
        """Every wait on the app or the LLM; post.py speeds up the ones longer than 3 s."""
        self.mark("wait_start", scene=self.cur, name=name)
        self.page.evaluate("(t) => __demo.chip(t)", chip)
        t = time.monotonic()
        fn()
        self.page.evaluate("() => __demo.chip(null)")
        self.mark("wait_end", scene=self.cur, name=name)
        d = time.monotonic() - t
        if d > 3:
            self.saved += d - 2.0

    def num(self, card) -> int:
        return int(self.page.locator(f"{W(card)} .num").text_content())

    @contextmanager
    def scene(self, sid):
        s = next(x for x in C.SCENES if x["id"] == sid)
        self.cur, self.saved = sid, 0.0
        start = self.now()
        self.mark("scene_start", scene=sid)
        print(f"scene {sid} {s['title']}", flush=True)
        yield s
        nar = C.narration(s, self.values)
        target = max(C.narration_s(nar), s["min_hold_s"])
        while self.now() - start - self.saved < target:  # hold live (animations keep running) until narration fits
            self.pause(0.1)
        self.page.evaluate("() => __demo.clear()")
        self.mark("scene_end", scene=sid)
        self.scenes[sid] = {"title": s["title"], "start": start, "end": self.now(), "target_s": target,
                            "narration": nar, "captions": C.captions(s, self.values)}
        self.pause(0.35)  # caption fade-out stays outside the cut

    def cap_at_start(self, s, i=0):
        self.pause(0.3)
        self.caption(C.captions(s, self.values)[i])


# ---------- scenes ----------
def s01(r):
    with r.scene("01"):
        r.pause(0.1)


def s02(r):
    r.page.goto(APP)
    r.page.wait_for_selector(f"{W('ds-replay')}:not([disabled])")
    r.page.locator(W("ds-replay")).click()
    r.page.wait_for_selector(f"{W('replay-caption')}:has-text('SpotBugs')")
    r.pause(2.5)  # graph settles + zoom-to-fit before the cut starts
    with r.scene("02") as s:
        r.cap_at_start(s)
        r.pause(2.2)
        for _ in range(4):
            r.move_click(W("replay-next"), hold=2.8)


def s03(r):
    with r.scene("03") as s:
        r.move_click(W("ds-demo"))
        r.page.wait_for_selector(f"{W('stats')}:has-text('repos')")
        r.values["pipelines"] = r.page.evaluate("async () => (await (await fetch('/api/demo/stats')).json()).workflows_entry")
        r.type_slow(W("action-input"), ACTION)
        r.page.keyboard.press("Escape")
        r.move_click(W("simulate"), hold=1.6)
        r.page.wait_for_selector(f"{W('card-total')}:visible")
        r.values["depth1"] = r.num("card-depth1")
        r.caption(C.captions(s, r.values)[0])
        r.spot(W("card-depth1"), hold=2.0)


def s04(r):
    with r.scene("04") as s:
        r.page.evaluate("() => __demo.spotlight(null)")
        r.drag_slider(W("depth-slider"), 1, 4)
        r.pause(1.6)
        r.values.update(total=r.num("card-total"), hidden=r.num("card-hidden"), pinned=r.num("card-pinned"))
        r.caption(C.captions(s, r.values)[0])
        r.spot(W("card-total"), hold=2.0)
        r.spot(W("card-hidden"), hold=2.0)


def s05(r):
    with r.scene("05") as s:
        r.page.evaluate("() => __demo.spotlight(null)")
        r.move_click(f"{W('exposed-row')}[data-wf*='infra-terraform']")
        r.page.wait_for_selector(f"{W('path-hops')}")
        r.values["infra_hops"] = r.page.locator(f"{W('path-hops')} li").count()
        r.caption(C.captions(s, r.values)[0])
        r.spot(W("path-hops"), hold=4.5)
        r.page.evaluate("() => __demo.spotlight(null)")
        r.move_click("#drawer-x")
        r.caption(C.captions(s, r.values)[1])
        r.spot(f"{W('exposed-row')}[data-wf*='mobile-app']", hold=3.0)


def _wait_final(r, before):
    r.page.wait_for_function("(n) => document.querySelectorAll('.ev.final, .ev.err').length > n", arg=before,
                             timeout=240_000)


def s06(r):
    with r.scene("06") as s:
        r.move_click(W("tab-agent"))
        r.move_click(W("agent-new-chat"), hold=0.4)
        r.cap_at_start(s)
        r.type_slow(W("agent-input"), Q1, clear=False)
        r.page.keyboard.press("Enter")
        r.wait_logged("agent Q1", lambda: _wait_final(r, 0))
        if r.page.locator(".ev.err").count():
            raise SystemExit(f"agent error: {r.page.locator('.ev.err').last.text_content()}")
        r.values["grounding_q1"] = r.page.locator(f"{W('agent-final')} {W('agent-grounding')}").text_content()
        r.pause(0.6)
        r.spot(f"{W('agent-final')} {W('agent-paths')}", hold=2.4)
        r.spot(f"{W('agent-final')} {W('agent-grounding')}", hold=2.0)


def s07(r):
    with r.scene("07") as s:
        r.page.evaluate("() => __demo.spotlight(null)")
        r.cap_at_start(s)
        before = r.page.locator(".ev.final, .ev.err").count()
        r.type_slow(W("agent-input"), Q2, clear=False)
        r.page.keyboard.press("Enter")
        r.wait_logged("agent Q2", lambda: _wait_final(r, before))
        text = r.page.locator(W("agent-final")).text_content() or ""
        if re.search(r"correct(ion| my)|disregard", text, re.I):
            raise SystemExit("STOP: the agent's second answer 'corrects' the first; the multi-turn history fix is not done")
        r.values["grounding_q2"] = r.page.locator(f"{W('agent-final')} {W('agent-grounding')}").text_content()
        r.spot(W("agent-final"), pad=6, hold=3.0)


def s08(r):
    with r.scene("08") as s:
        r.page.evaluate("() => __demo.spotlight(null)")
        r.move_click(W("tab-fix"))
        r.move_click(W("targets-all"), hold=0.4)
        r.move_click(W("compute-fix"))
        r.wait_logged("plan", lambda: r.page.wait_for_selector(W("fix-headline"), timeout=60_000))
        m = re.search(r"(\d+) changes? protect (\d+)", r.page.locator(W("fix-headline")).text_content())
        r.values.update(changes=int(m.group(1)), protected=int(m.group(2)),
                        engine_short=r.page.locator(W("engine-badge")).text_content().strip())
        r.caption(C.captions(s, r.values)[0])
        lint = r.page.locator(".fix", has_text="cb-lint-reporter:action.yml").first.text_content()
        r.values["lint_protects"] = int(re.search(r"protects (\d+)", lint).group(1))
        r.spot(W("fix-headline"), hold=2.2)
        r.spot(W("engine-badge"), pad=6, hold=1.8)
        r.page.evaluate("() => __demo.spotlight(null)")
        r.move_click(W("simulate-fix"))
        r.wait_logged("simulate", lambda: r.page.wait_for_selector(W("sim-result"), timeout=60_000))
        sim = r.page.locator(W("sim-result")).text_content()
        r.values["after"] = int(re.search(r"→\s*(\d+)", sim).group(1))
        r.spot(W("sim-result"), hold=2.4)


def s09(r):
    with r.scene("09") as s:
        r.page.evaluate("() => __demo.spotlight(null)")
        r.cap_at_start(s)
        r.move_click(W("open-prs"))
        r.wait_logged("open PRs", lambda: r.page.wait_for_function(
            "() => document.querySelectorAll('[data-demo=pr-log] a[href*=\"/pull/\"]').length >= 3", timeout=180_000))
        r.values["prs_opened"] = r.page.locator(f"{W('pr-log')} a[href*='/pull/']").count()
        r.spot(W("pr-log"), hold=2.0)
        url = r.page.locator(f"{W('pr-log')} a[href*='cb-lint-reporter/pull/']").first.get_attribute("href")
        r.values["lint_pr_url"] = url
        gp = r.ctx.new_page()
        r.mark("tab_open", scene="09", url=url)
        r.github_cast = Screencast(gp, "github", r.t0)
        gp.goto(url + "/files", wait_until="domcontentloaded")
        gp.wait_for_timeout(2500)
        found = gp.evaluate("""(needle) => {
            const els = [...document.querySelectorAll('td, span, div')].filter(e => (e.textContent || '').includes(needle));
            els.sort((a, b) => a.textContent.length - b.textContent.length);
            const row = els[0] && (els[0].closest('tr') || els[0]);
            if (row) row.setAttribute('data-demo', 'gh-diff-line');
            return !!row; }""", "cb-changed-files@" + r.values.get("known_good_sha", "67f879c")[:7])
        if found:
            gp.locator("[data-demo=gh-diff-line]").first.scroll_into_view_if_needed()
            b = gp.locator("[data-demo=gh-diff-line]").first.bounding_box()
            gp.mouse.move(b["x"] + 220, b["y"] + b["height"] / 2, steps=25)
            gp.evaluate("() => __demo.spotlight('[data-demo=gh-diff-line]', 6)")
        gp.evaluate("(t) => __demo.caption(t)",
                    f"One pinned line in a shared action protects {r.values['lint_protects']} pipelines")
        gp.wait_for_timeout(6000)
        r.values["gh_diff_spotlit"] = found
        r.mark("tab_close", scene="09")
        r.github_cast.stop()
        gp.close()
        r.page.bring_to_front()
        r.pause(0.5)


def s10(r):
    with r.scene("10") as s:
        r.page.evaluate("() => __demo.spotlight(null)")
        r.move_click(W("merge"))
        r.wait_logged("merge + rescan", lambda: r.page.wait_for_function(
            "() => document.querySelector('[data-demo=card-total] .num').textContent === '0'"
            " && !document.querySelector('[data-demo=merge]').textContent.includes('…')", timeout=360_000))
        r.pause(1.6)
        r.values["total_after"] = r.num("card-total")
        if r.values["total_after"] != 0:
            raise SystemExit(f"rescan left {r.values['total_after']} exposed; the narration says nothing is exposed")
        r.caption(C.captions(s, r.values)[0])
        r.spot(W("card-total"), hold=2.5)


def s11(r):
    with r.scene("11") as s:
        r.page.evaluate("() => __demo.spotlight(null)")
        r.move_click(W("ds-cncf"))
        r.page.wait_for_selector(f"{W('stats')}:has-text('1,')")
        r.values["cncf_repos"] = re.search(r"([\d,]+)\s*repos", r.page.locator(W("stats")).text_content()).group(1)
        r.caption(C.captions(s, r.values)[0])
        r.spot(W("stats"), pad=6, hold=2.4)
        r.page.evaluate("() => __demo.spotlight(null)")
        r.move_click(W("tab-leader"))
        r.page.wait_for_selector(f"{W('leaderboard')} tbody tr")
        r.pause(0.6)
        r.values["top_action"] = r.page.locator(f"{W('leaderboard')} tbody tr td.act").first.text_content()
        r.spot(f"{W('leaderboard')} tbody tr", pad=6, n=5, hold=3.0)


def s12(r):
    qs = "&".join(f"{k}={v}" for k, v in (("live", LIVE_URL), ("repo", REPO_URL)) if v)
    r.page.goto((C.VIDEO / "cards/outro.html").as_uri() + f"?{qs}")
    r.page.wait_for_timeout(1200)
    with r.scene("12"):
        r.pause(0.1)


SCENES = {"01": s01, "02": s02, "03": s03, "04": s04, "05": s05, "06": s06, "07": s07, "08": s08, "09": s09,
          "10": s10, "11": s11, "12": s12}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", default=None, help="e.g. 01-04 (default: all)")
    args = ap.parse_args()
    ids = C.scene_ids(args.scenes)
    shutil.rmtree(C.RAW, ignore_errors=True)
    C.RAW.mkdir(parents=True)
    gt = json.loads(config.GROUND_TRUTH.read_text())
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=2)
        ctx.add_init_script(path=str(C.VIDEO / "overlay.js"))
        # the admin token reaches the UI through sessionStorage on the app origin only; it is never on screen
        ctx.add_init_script(f"if (location.origin === {json.dumps(APP)}) "
                            f"try {{ sessionStorage.setItem('cb-admin', {json.dumps(config.ADMIN_TOKEN)}) }} catch (e) {{}}")
        page = ctx.new_page()
        r = Rec(ctx, page)
        r.values["known_good_sha"] = gt["known_good_sha"]
        page.goto((C.VIDEO / "cards/intro.html").as_uri())
        page.wait_for_timeout(600)
        try:
            for sid in ids:
                SCENES[sid](r)
        finally:
            end = r.now()
            r.cast.stop()
            page.close()
            ctx.close()
            browser.close()
            print("building raw videos…", flush=True)
            r.cast.build(C.RAW / "main.mp4", 0.0, end)
            gh = None
            if r.github_cast:
                o = next(m["t"] for m in r.markers if m["kind"] == "tab_open")
                c = next(m["t"] for m in r.markers if m["kind"] == "tab_close")
                r.github_cast.build(C.RAW / "github.mp4", o, c)
                gh = "github.mp4"
            (C.RAW / "markers.json").write_text(json.dumps({
                "main_video": "main.mp4", "github_video": gh, "duration": end,
                "scenes": r.scenes, "markers": r.markers}, indent=2))
            (C.RAW / "values.json").write_text(json.dumps(r.values, indent=2))
    print(json.dumps({k: v for k, v in r.values.items() if k != "lint_pr_url"}, indent=1))


if __name__ == "__main__":
    main()
