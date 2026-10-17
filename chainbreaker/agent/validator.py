"""Grounding validator (PLAN 8.9): every owner/repo[/path][@ref] or repo-xxxxxx name in an answer must have
come back from a tool this turn (or from the user's own question)."""
import re

TOKEN_RE = re.compile(r"[A-Za-z0-9_.@:/-]+")
PSEUDO_RE = re.compile(r"repo-[0-9a-f]{6}")
STOP = {"pin", "repin", "vendor", "and", "or", "high", "med", "low", "read", "write", "yes", "no", "n", "a", "s",
        "before", "after", "depth", "grep", "tags", "branches", "input", "output", "ci", "cd", "i", "o"}


def strings(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in strings(v)]
    if isinstance(obj, (list, tuple)):
        return [s for v in obj for s in strings(v)]
    return []


def extract(text: str) -> list[str]:
    text = re.sub(r"https?://\S+", " ", text)
    out = []
    for raw in TOKEN_RE.findall(text):
        tok = raw.strip(".,;:()'\"`*")
        if PSEUDO_RE.search(tok):
            out.append(tok)
            continue
        if "/" not in tok:
            continue
        first, _, rest = tok.partition("/")
        if not re.search(r"[A-Za-z]", first) or not re.search(r"[A-Za-z]", rest) or first.startswith("."):
            continue
        if all(p.lower() in STOP for p in tok.split("/")):
            continue
        out.append(tok)
    return list(dict.fromkeys(out))


def check(text: str, known: list[str]) -> dict:
    hay = "\n".join(k.lower() for k in known)
    names = extract(text)
    unverified = [n for n in names if n.lower() not in hay]
    return {"verified": len(names) - len(unverified), "total": len(names), "unverified": unverified}


def scrub(text: str, unverified: list[str]) -> str:
    for n in sorted(unverified, key=len, reverse=True):
        text = text.replace(n, "[unverified]")
    return text
