"""V5: add Divy's per-scene voice clips to the cut.

    python video/assemble.py --voice video/voice/

Reads video/out/timeline.json (from post.py) and video/voice/scene_XX.(m4a|wav|mp3). Each clip is cleaned
(highpass, denoise, loudness -16 LUFS) and placed at its scene's start. A scene whose clip is longer than the
scene is stretched by freezing its last frame (clip length + 0.4 s), so nothing is cut off. Scenes without a
clip stay silent (warned). Writes video/out/chainbreaker_demo_final.mp4 plus the matching SRT and chapters.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
from post import ENC, concat_with_xfades, duration, ff, write_texts  # noqa: E402

LEAD = 0.25  # the voice starts just after the scene's caption appears
TAIL = 0.4
# dead air before and after the words is trimmed, so a late start on the record button does not delay the voice
TRIM = ("silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,areverse,"
        "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,areverse")
CLEAN = f"highpass=f=80,afftdn,{TRIM},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"


def voice_for(d: Path, sid: str) -> Path | None:
    for ext in ("m4a", "wav", "mp3"):
        p = d / f"scene_{sid}.{ext}"
        if p.exists():
            return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default=str(C.VOICE))
    args = ap.parse_args()
    vdir = Path(args.voice)
    tl = json.loads((C.OUT / "timeline.json").read_text())
    values = json.loads((C.RAW / "values.json").read_text())
    work, cleaned = C.OUT / "scenes_final", C.OUT / "voice_clean"
    work.mkdir(parents=True, exist_ok=True)
    cleaned.mkdir(parents=True, exist_ok=True)

    clips, voices = [], {}
    for s in tl["scenes"]:
        sid, src = s["id"], Path(s["file"])
        v = voice_for(vdir, sid)
        if v is None:
            print(f"  warning: no voice for scene {sid}, keeping it silent")
            clips.append(src)
            continue
        c = cleaned / f"scene_{sid}.wav"
        ff("-i", v, "-af", CLEAN, "-ac", "1", c)
        vd = duration(c)
        if vd < 0.3:
            print(f"  warning: scene_{sid} is silent after trimming, keeping the scene silent")
            clips.append(src)
            continue
        voices[sid] = (c, vd)
        need = LEAD + vd + TAIL - s["duration"]
        if need > 0.05:
            out = work / f"scene_{sid}.mp4"
            ff("-i", src, "-vf", f"tpad=stop_mode=clone:stop_duration={need:.3f}", *ENC, out)
            print(f"  scene {sid}: voice {vd:.1f} s > scene {s['duration']:.1f} s, stretched by {need:.1f} s")
            clips.append(out)
        else:
            clips.append(src)

    video = C.OUT / "_final_video.mp4"
    starts = concat_with_xfades(clips, video)
    total = duration(video)
    timeline = []
    for k, s in enumerate(tl["scenes"]):
        end = starts[k + 1] if k + 1 < len(starts) else total
        timeline.append({**s, "t_start": round(starts[k], 2), "t_end": round(end, 2), "file": str(clips[k])})

    out = C.OUT / "chainbreaker_demo_final.mp4"
    if voices:
        ins, chains, labels = [], [], []
        for i, s in enumerate(timeline):
            if s["id"] not in voices:
                continue
            n = len(labels) + 1
            ms = int((s["t_start"] + LEAD) * 1000)
            ins += ["-i", voices[s["id"]][0]]
            chains.append(f"[{n}:a]adelay={ms}|{ms}[a{n}]")
            labels.append(f"[a{n}]")
        graph = ";".join(chains) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest," \
                                   f"apad=whole_dur={total:.3f},atrim=0:{total:.3f}[aout]"
        ff("-i", video, *ins, "-filter_complex", graph, "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
           "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", out)
    else:
        print("  warning: no voice clips at all; the final cut is silent")
        ff("-i", video, "-c", "copy", "-movflags", "+faststart", out)
    video.unlink()
    write_texts(timeline, {**values, "repo_url": None}, total, suffix="_final")
    print(f"final cut: {total:.1f} s ({C.fmt_ts(total)}) with {len(voices)}/{len(timeline)} voice clips -> {out}")


if __name__ == "__main__":
    main()
