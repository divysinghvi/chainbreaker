"""V0 preflight: the app, datasets, redaction, eval numbers, engine, agent sanity, then a fresh demo reset.

    python video/preflight.py            # checks + reset
    python video/preflight.py --no-reset # checks only
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
APP = "http://localhost:8000"
CB = str(ROOT / ".venv/bin/cb")
OK, BAD = "\033[32m✓\033[0m", "\033[31m✗\033[0m"


def read_results() -> dict:
    """CNCF headline numbers from eval/RESULTS.md (None when missing: the narration then drops that clause)."""
    p = ROOT / "eval/RESULTS.md"
    txt = p.read_text() if p.exists() else ""
    repos = re.search(r"\| Repos \| ([\d,]+) \|", txt)
    hidden = re.search(r"\*\*[\d,]+ hidden \(([\d.]+)%\)\*\*", txt)
    return {"cncf_repos": repos.group(1) if repos else None, "hidden_pct": f"{hidden.group(1)}%" if hidden else None}


def read_engine() -> str:
    notes = (ROOT / "NOTES.md").read_text()
    ran = re.search(r"engine that ran is\s+`falkordb\.algo\.maxFlow`", notes)
    return "falkordb.algo.maxFlow" if ran else "networkx (fallback)"


def ask(message: str, chat_id: str | None) -> dict:
    out = {"tools": [], "chat_id": chat_id}
    with httpx.stream("POST", f"{APP}/api/agent", json={"dataset": "demo", "message": message, "chat_id": chat_id},
                      timeout=300) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            if ev["type"] == "chat":
                out["chat_id"] = ev["chat_id"]
            elif ev["type"] == "tool_call":
                out["tools"].append(ev["name"])
            elif ev["type"] in ("final", "error"):
                out["final"] = ev
    return out


def main() -> int:
    fails: list[str] = []

    def check(ok: bool, label: str, detail: str = "") -> bool:
        print(f"  {OK if ok else BAD} {label}{f'  ({detail})' if detail else ''}")
        if not ok:
            fails.append(label)
        return ok

    print("preflight")
    try:
        check(httpx.get(f"{APP}/healthz", timeout=10).json().get("falkordb") is True, "app answers /healthz")
    except Exception as e:  # noqa: BLE001
        check(False, "app answers /healthz", str(e))
        return 1
    ds = httpx.get(f"{APP}/api/datasets", timeout=30).json()
    have = {d["id"] for d in ds["datasets"]}
    check({"demo", "cncf", "replay-tj-2025"} <= have, "datasets demo, cncf, replay-tj-2025", ", ".join(sorted(have)))
    check(ds["public_mode"] is True, "PUBLIC_MODE=1 on the app")
    adv = httpx.post(f"{APP}/api/cncf/advisories", json={"action_id": "actions/github-script"}, timeout=60).json()
    exposed = httpx.get(f"{APP}/api/cncf/advisories/{adv['id']}/blast", timeout=60).json()["exposed"]
    real = [x["workflow"] for x in exposed if not re.match(r"^repo-[0-9a-f]{6}:", x["workflow"])]
    check(bool(exposed) and not real, "CNCF exposed list is pseudonymized", f"{len(exposed)} rows, {len(real)} real names")

    res, engine = read_results(), read_engine()
    check((ROOT / "eval/RESULTS.md").exists(), "eval/RESULTS.md exists",
          f"repos {res['cncf_repos'] or 'unavailable'} · hidden {res['hidden_pct'] or 'unavailable'}")
    check(True, "min-cut engine from NOTES.md", engine)

    a = ask("What happens if cb-changed-files is compromised?", None)
    check("final" in a and a["final"]["type"] == "final", "agent Q1 answers", " → ".join(a["tools"]))
    b = ask("Is evil-corp/backdoor-action in our CI?", a["chat_id"])
    text = (b.get("final") or {}).get("text", "")
    check(b["chat_id"] == a["chat_id"], "agent Q2 runs in the same chat")
    check(not re.search(r"correct(ion| my)|disregard", text, re.I), "agent Q2 does not 'correct' Q1")
    check((b.get("final") or {}).get("outcome") == "unknown_entity" and "not in the graph" in text.lower(),
          "agent Q2 reports evil-corp/backdoor-action as absent", f"grounding {b.get('final', {}).get('grounding')}")

    if "--no-reset" not in sys.argv:
        print("resetting demo org: cb reset-demo && cb crawl --dataset demo && cb load --dataset demo")
        for args in (["reset-demo"], ["crawl", "--dataset", "demo"], ["load", "--dataset", "demo"]):
            r = subprocess.run([CB, *args], cwd=ROOT, capture_output=True, text=True)
            if not check(r.returncode == 0, f"cb {' '.join(args)}", r.stderr.strip()[-200:]):
                break
        adv = httpx.post(f"{APP}/api/demo/advisories", json={"action_id": "chainbreaker-lab-divy/cb-changed-files"},
                         timeout=60).json()
        d1 = httpx.get(f"{APP}/api/demo/advisories/{adv['id']}/blast?depth=1", timeout=60).json()["exposed_total"]
        full = httpx.get(f"{APP}/api/demo/advisories/{adv['id']}/blast?depth=6", timeout=60).json()["exposed_total"]
        check(d1 == 2 and full == 11, "demo reset: depth-1 2, exposed 11", f"{d1} / {full}")

    print(json.dumps({**res, "engine": engine}, indent=2))
    if fails:
        print(f"\nSTOP: {len(fails)} check(s) failed: {fails}")
        return 1
    print("\nall green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
