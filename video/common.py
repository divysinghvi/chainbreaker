"""Shared by record.py / post.py / assemble.py: scenes, placeholder filling, narration timing."""
import json
import re
from pathlib import Path

VIDEO = Path(__file__).resolve().parent
ROOT = VIDEO.parent
RAW, OUT, VOICE = VIDEO / "raw", VIDEO / "out", VIDEO / "voice"
CFG = json.loads((VIDEO / "scenes.json").read_text())
SCENES = CFG["scenes"]
PH = re.compile(r"\{(\w+)\}")


def fill(text: str | None, values: dict) -> str | None:
    """Fill {placeholders}; drop [[optional]] chunks whose placeholders are unavailable."""
    if text is None:
        return None

    def opt(m):
        chunk = m.group(1)
        return chunk if all(values.get(k) not in (None, "") for k in PH.findall(chunk)) else ""

    text = re.sub(r"\[\[(.*?)\]\]", opt, text)
    text = PH.sub(lambda m: str(values.get(m.group(1)) if values.get(m.group(1)) is not None else "—"), text)
    return re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def narration(scene: dict, values: dict) -> str:
    n = scene["narration"]
    if isinstance(n, dict):
        n = n["maxflow" if "maxflow" in str(values.get("engine", "")).lower() else "fallback"]
    return fill(n, values)


def captions(scene: dict, values: dict) -> list[str]:
    c = scene.get("caption")
    return [fill(x, values) for x in (c if isinstance(c, list) else [c] if c else [])]


def words(text: str) -> int:
    return len(text.split())


def narration_s(text: str) -> float:
    return round(words(text) / CFG["words_per_s"] + CFG["pad_s"], 2)


def scene_ids(spec: str | None) -> list[str]:
    """'01-04' / '03,05' / None (all)."""
    ids = [s["id"] for s in SCENES]
    if not spec:
        return ids
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += [i for i in ids if a <= i <= (b or a)]
    return out


def fmt_ts(s: float, srt: bool = False) -> str:
    h, rem = divmod(max(0.0, s), 3600)
    m, sec = divmod(rem, 60)
    if srt:
        return f"{int(h):02d}:{int(m):02d}:{int(sec):02d},{int(round((sec % 1) * 1000)) % 1000:03d}"
    return f"{int(m)}:{int(sec):02d}" if not h else f"{int(h)}:{int(m):02d}:{int(sec):02d}"
