"""V4: raw recording + markers -> scene clips, the silent cut, teleprompter, SRT, chapters, 30 s cut, stills.

    python video/post.py
"""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

SCN = C.OUT / "scenes"
FPS = 30
XFADE = 0.3
FAST_OVER, FAST_TO = 3.0, 2.0  # waits longer than 3 s play in about 2 s
GH_SKIP = 1.3  # the GitHub tab's first second is a blank page loading
STILL_AT = 0.8  # stills at 80% of a scene, where its caption and spotlight are on screen
ENC = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def ff(*args) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *map(str, args)], check=True)


def duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def pieces_for(sid: str, sc: dict, markers: list[dict]) -> list[dict]:
    """Split a scene into pieces: normal-speed main video, sped-up waits, and the GitHub page splice."""
    a, b = sc["start"], sc["end"]
    cuts = []  # (start, end, kind, extra)
    ws = [m for m in markers if m.get("scene") == sid and m["kind"] == "wait_start"]
    we = [m for m in markers if m.get("scene") == sid and m["kind"] == "wait_end"]
    for s, e in zip(ws, we):
        d = e["t"] - s["t"]
        if d > FAST_OVER:
            cuts.append((s["t"], e["t"], "fast", d / FAST_TO))
    to = [m for m in markers if m.get("scene") == sid and m["kind"] == "tab_open"]
    tc = [m for m in markers if m.get("scene") == sid and m["kind"] == "tab_close"]
    if to and tc:
        cuts.append((to[0]["t"], tc[0]["t"], "github", None))
    cuts.sort()
    out, t = [], a
    for s, e, kind, x in cuts:
        if s > t:
            out.append({"src": "main", "a": t, "b": s, "speed": 1.0})
        if kind == "fast":
            out.append({"src": "main", "a": s, "b": e, "speed": x})
        else:
            out.append({"src": "github", "a": min(GH_SKIP, (e - s) / 2), "b": e - s, "speed": 1.0})
        t = e
    if b > t:
        out.append({"src": "main", "a": t, "b": b, "speed": 1.0})
    return [p for p in out if p["b"] - p["a"] > 0.02]


def local_time(raw_t: float, pieces: list[dict], start: float) -> float:
    """Map a raw main-timeline time inside a scene to the scene clip's local time."""
    loc, cursor = 0.0, start
    for p in pieces:
        span = (p["b"] - p["a"])
        raw_span = span if p["src"] == "main" else span  # github piece replaces the same raw span
        if raw_t <= cursor + raw_span:
            return loc + (raw_t - cursor) / p["speed"]
        loc += span / p["speed"]
        cursor += raw_span
    return loc


def build_scene(sid: str, sc: dict, markers: list[dict], has_gh: bool) -> dict:
    pieces = pieces_for(sid, sc, markers)
    inputs = ["-i", C.RAW / "main.mp4"] + (["-i", C.RAW / "github.mp4"] if has_gh else [])
    chains, labels = [], []
    for i, p in enumerate(pieces):
        src = 0 if p["src"] == "main" else 1
        chains.append(f"[{src}:v]trim=start={p['a']:.3f}:end={p['b']:.3f},setpts=(PTS-STARTPTS)/{p['speed']:.4f},"
                      f"fps={FPS},scale=1920:1080:flags=lanczos,setsar=1[p{i}]")
        labels.append(f"[p{i}]")
    footage = sum((p["b"] - p["a"]) / p["speed"] for p in pieces)
    hold = max(0.0, sc["target_s"] - footage)
    tail = f",tpad=stop_mode=clone:stop_duration={hold:.3f}" if hold > 0.05 else ""
    graph = ";".join(chains) + f";{''.join(labels)}concat=n={len(pieces)}:v=1:a=0{tail}[v]"
    out = SCN / f"scene_{sid}.mp4"
    ff(*inputs, "-filter_complex", graph, "-map", "[v]", *ENC, out)
    events = {m["name"]: local_time(m["t"], pieces, sc["start"]) for m in markers
              if m.get("scene") == sid and m["kind"] == "wait_end"}
    return {"file": str(out), "duration": duration(out), "footage": round(footage, 2), "hold": round(hold, 2),
            "pieces": pieces, "events": events}


def concat_with_xfades(clips: list[Path], out: Path) -> list[float]:
    """Concat; 0.3 s crossfades only 01->02 and 11->12. Returns each scene's start time in the final cut."""
    durs = [duration(c) for c in clips]
    middle = C.OUT / "_middle.mp4"
    lst = C.OUT / "_middle.txt"
    lst.write_text("".join(f"file '{c}'\n" for c in clips[1:-1]))
    ff("-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", middle)
    dm = duration(middle)
    o1 = durs[0] - XFADE
    o2 = o1 + dm - XFADE
    graph = (f"[0:v][1:v]xfade=transition=fade:duration={XFADE}:offset={o1:.3f}[a];"
             f"[a][2:v]xfade=transition=fade:duration={XFADE}:offset={o2:.3f},scale=1920:1080:flags=lanczos[v]")
    ff("-i", clips[0], "-i", middle, "-i", clips[-1], "-filter_complex", graph, "-map", "[v]", *ENC,
       "-movflags", "+faststart", out)
    middle.unlink()
    lst.unlink()
    starts, t = [0.0], o1
    for d in durs[1:-1]:
        starts.append(t)
        t += d
    starts.append(o2)
    return starts


def srt_entries(text: str, a: float, b: float) -> list[tuple[float, float, str]]:
    """Spread a narration over [a, b] in chunks of <= 12 words, time proportional to words."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+|(?<=[,:;])\s+(?=\S)", text) if p.strip()]
    chunks: list[str] = []
    for p in parts:
        w = p.split()
        while len(w) > 12:
            chunks.append(" ".join(w[:10]))
            w = w[10:]
        if chunks and len(chunks[-1].split()) + len(w) <= 7:
            chunks[-1] += " " + " ".join(w)
        else:
            chunks.append(" ".join(w))
    total = sum(len(c.split()) for c in chunks) or 1
    span = max(0.5, (b - a) - 0.4)
    out, t = [], a + 0.2
    for c in chunks:
        d = span * len(c.split()) / total
        out.append((t, t + d, c))
        t += d
    return out


def write_texts(timeline: list[dict], values: dict, total: float, suffix: str = "") -> None:
    live = values.get("live_url") or "<LIVE URL>"
    repo = values.get("repo_url") or "https://github.com/divysinghvi/chainbreaker"
    vo = ["# ChainBreaker demo · voice-over", "",
          "Record one clip per scene (`video/voice/scene_XX.m4a`, `.wav` or `.mp3`), then run "
          "`python video/assemble.py --voice video/voice/`. A clip longer than its scene is fine: assemble.py "
          "freezes that scene's last frame so nothing is cut off.", ""]
    srt, n = [], 1
    for s in timeline:
        a, b = s["t_start"], s["t_end"]
        target_words = max(1, int((b - a - C.CFG["pad_s"]) * C.CFG["words_per_s"]))
        vo += [f"## Scene {s['id']} · {C.fmt_ts(a)}–{C.fmt_ts(b)} ({b - a:.1f} s) · {s['title']}", "",
               f"> {s['narration']}", "",
               f"{C.words(s['narration'])} words (fits about {target_words}) · record as `video/voice/scene_{s['id']}.m4a`",
               ""]
        for x, y, c in srt_entries(s["narration"], a, b):
            srt += [str(n), f"{C.fmt_ts(x, True)} --> {C.fmt_ts(y, True)}", c, ""]
            n += 1
    (C.OUT / f"VOICEOVER{suffix}.md").write_text("\n".join(vo))
    (C.OUT / f"chainbreaker_demo{suffix}.srt").write_text("\n".join(srt))
    # chapters: >= 10 s each, first at 0:00 (short scenes merge into the previous chapter)
    chapters: list[list] = []
    for s in timeline:
        if chapters and s["t_start"] - chapters[-1][0] < 10:
            chapters[-1][1] += f" · {s['title']}"
        else:
            chapters.append([0.0 if not chapters else s["t_start"], s["title"]])
    if len(chapters) > 1 and total - chapters[-1][0] < 10:
        last = chapters.pop()
        chapters[-1][1] += f" · {last[1]}"
    desc = [
        "ChainBreaker: when a GitHub Action gets hacked, find every pipeline that really runs it (even 4 hops deep),",
        "and fix them in the fewest line changes, using FalkorDB graph traversals and algo.maxFlow. Graph Hacks · Track 01.",
        "", f"Live: {live}", f"Code: {repo}", "Blog: <BLOG URL>", "", "Chapters:"]
    desc += [f"{C.fmt_ts(t)} {title}" for t, title in chapters]
    (C.OUT / f"youtube_description{suffix}.txt").write_text("\n".join(desc) + "\n")


def build_30s(scene_info: dict) -> Path:
    """02 (first 4 s), 04, 08 (headline part), 10, 12 -> ~28-32 s."""
    s08 = scene_info["08"]
    h = s08["events"].get("plan", 0.0)
    parts = [("02", 0.0, 4.0), ("04", 0.0, scene_info["04"]["duration"]), ("08", max(0.0, h - 0.3), h + 5.0),
             ("10", 0.0, scene_info["10"]["duration"]), ("12", 0.0, scene_info["12"]["duration"])]
    total = sum(b - a for _, a, b in parts)
    if total > 32:  # trim the start of 04 (the slider is still at 1-2 there) and the outro tail
        over = total - 31
        cut04 = min(over, 3.0)
        parts[1] = ("04", cut04, parts[1][2])
        over -= cut04
        if over > 0:
            parts[4] = ("12", 0.0, max(3.0, parts[4][2] - over))
    ins, chains = [], []
    for i, (sid, a, b) in enumerate(parts):
        ins += ["-i", SCN / f"scene_{sid}.mp4"]
        chains.append(f"[{i}:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[c{i}]")
    graph = ";".join(chains) + ";" + "".join(f"[c{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[v]"
    out = C.OUT / "chainbreaker_30s_silent.mp4"
    ff(*ins, "-filter_complex", graph, "-map", "[v]", *ENC, "-movflags", "+faststart", out)
    return out


def main() -> None:
    m = json.loads((C.RAW / "markers.json").read_text())
    values = json.loads((C.RAW / "values.json").read_text())
    SCN.mkdir(parents=True, exist_ok=True)
    (C.OUT / "frames").mkdir(parents=True, exist_ok=True)
    has_gh = bool(m.get("github_video")) and (C.RAW / "github.mp4").exists()
    info = {}
    for s in C.SCENES:
        sid = s["id"]
        if sid not in m["scenes"]:
            continue
        info[sid] = build_scene(sid, m["scenes"][sid], m["markers"], has_gh)
        print(f"scene {sid}: {info[sid]['duration']:.1f} s (footage {info[sid]['footage']} s, hold {info[sid]['hold']} s)")
    ids = list(info)
    out = C.OUT / "chainbreaker_demo_silent.mp4"
    starts = concat_with_xfades([Path(info[i]["file"]) for i in ids], out)
    total = duration(out)
    timeline = []
    for k, sid in enumerate(ids):
        end = starts[k + 1] if k + 1 < len(ids) else total
        sc = m["scenes"][sid]
        timeline.append({"id": sid, "title": sc["title"], "t_start": round(starts[k], 2), "t_end": round(end, 2),
                         "duration": info[sid]["duration"], "narration": sc["narration"], "captions": sc["captions"],
                         "file": info[sid]["file"], "events": info[sid]["events"]})
        ff("-ss", f"{info[sid]['duration'] * STILL_AT:.2f}", "-i", info[sid]["file"], "-frames:v", 1,
           C.OUT / "frames" / f"scene_{sid}.png")
    (C.OUT / "timeline.json").write_text(json.dumps({"total": total, "scenes": timeline}, indent=2))
    write_texts(timeline, values, total)
    if all(i in info for i in ("02", "04", "08", "10", "12")):
        t30 = build_30s(info)
        print(f"30 s cut: {duration(t30):.1f} s")
    print(f"silent cut: {total:.1f} s ({C.fmt_ts(total)}) -> {out}")


if __name__ == "__main__":
    main()
