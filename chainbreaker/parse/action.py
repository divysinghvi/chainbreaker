"""action.yml -> facts (PLAN 8.3)."""
from dataclasses import dataclass, field

from .uses import parse_uses
from .workflow import LineFinder, UsesSite, load_yaml


@dataclass
class ActionFacts:
    kind: str  # composite | node | docker | unknown | unresolved
    uses: list[UsesSite] = field(default_factory=list)
    dynamic: int = 0
    invalid: int = 0


def parse_action(text: str | None, owner: str, repo: str, ref: str) -> ActionFacts:
    if text is None:
        return ActionFacts("unresolved")
    try:
        doc = load_yaml(text)
    except Exception:  # noqa: BLE001
        return ActionFacts("unknown")
    runs = doc.get("runs") if isinstance(doc, dict) else None
    if not isinstance(runs, dict):
        return ActionFacts("unknown")
    using = str(runs.get("using") or "")
    lf = LineFinder(text)
    if using == "composite":
        facts = ActionFacts("composite")
        for i, step in enumerate(runs.get("steps") or []):
            if not (isinstance(step, dict) and "uses" in step):
                continue
            u = parse_uses(step["uses"], owner, repo, ref, in_action=True)
            lines = lf.find(str(step["uses"]))
            if u is None:
                facts.invalid += 1
            elif u.kind == "dynamic":
                facts.dynamic += 1
            else:
                facts.uses.append(UsesSite(u, "image" if u.kind == "docker" else "step", lines, "", i))
        return facts
    if using == "docker":
        facts = ActionFacts("docker")
        image = str(runs.get("image") or "")
        if image.startswith("docker://"):
            u = parse_uses(image, owner, repo, ref, in_action=True)
            facts.uses.append(UsesSite(u, "image", lf.find(image)))
        return facts
    if using.startswith("node"):
        return ActionFacts("node")
    return ActionFacts("unknown")
