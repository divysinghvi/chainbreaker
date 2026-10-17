"""The 2025 tj-actions chain (data/replay_tj_2025.json) as its own graph, cb:replay-tj-2025."""
import json

from .. import config, db

DS = "replay-tj-2025"
LABELS = {"Token", "ActionRef", "Action", "Repo"}
CREATE_NODE = "CREATE (n:{label} {{id: $id, name: $name}})"  # label from LABELS only
CREATE_STEP = """MATCH (a {id: $src}), (b {id: $dst})
CREATE (a)-[:LEADS_TO {step: $step, caption: $caption, source: $source}]->(b)"""


def load_replay() -> dict:
    data = json.loads(config.REPLAY.read_text())
    if db.graph_exists(DS):
        db.graph(DS).delete()
    for n in data["nodes"]:
        assert n["label"] in LABELS
        db.run(DS, CREATE_NODE.format(label=n["label"]), {"id": n["id"], "name": n["name"]})
    steps = 0
    for i, s in enumerate(data["steps"], 1):
        if s["edge"]:
            db.run(DS, CREATE_STEP, {"src": s["edge"][0], "dst": s["edge"][1], "step": i, "caption": s["caption"],
                                     "source": data["source"]})
            steps += 1
    return {"graph": db.gname(DS), "nodes": len(data["nodes"]), "edges": steps}
