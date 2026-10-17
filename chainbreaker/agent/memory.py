"""Agent memory: Finding nodes (question, answer, date, action)."""
import datetime as dt
import secrets

from .. import db, queries as Q


def save_finding(ds: str, question: str, answer: str, action_id: str = "") -> str:
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    fid = f"F-{now[:10]}-{secrets.token_hex(3)}"
    db.q(ds, Q.FINDING_CREATE, {"id": fid, "question": question[:500], "answer": answer[:2000], "now": now,
                                "aid": action_id.lower()})
    return fid


def recall_findings(ds: str, action_id: str = "") -> list[dict]:
    rows = db.q(ds, Q.FINDINGS, {"aid": action_id.strip().lower()}, ro=True)
    return [{"date": r["date"][:10], "question": r["question"], "answer": r["answer"], "action_id": r["action_id"]}
            for r in rows]
