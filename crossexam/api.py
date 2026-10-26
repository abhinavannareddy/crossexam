"""FastAPI service. The system recommends; only an analyst call to /decide changes a case status."""
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .agents import CaseAlreadyDecided, Investigator
from .audit import AuditLog
from .model import alerts, prepare, train

_state = {}
_lock = threading.Lock()


def _init(seed=1):
    """The audit log is written to CROSSEXAM_AUDIT_DB (default crossexam_audit.db) so it survives restarts."""
    d = prepare(seed)
    _, score = train(d)
    audit = AuditLog(os.environ.get("CROSSEXAM_AUDIT_DB", "crossexam_audit.db"))
    _state.update(d=d, al=alerts(d, score), inv=Investigator(d, audit=audit))


@asynccontextmanager
async def lifespan(_app):
    _init()
    yield


app = FastAPI(title="CrossExam", lifespan=lifespan)


class Decision(BaseModel):
    analyst: str = Field(min_length=1, max_length=100)
    decision: str = Field(max_length=20)
    reason: str = Field(default="", max_length=2000)


@app.get("/health")
def health():
    return {"status": "ok", "alerts": len(_state.get("al", {}))}


@app.get("/alerts")
def list_alerts():
    return [{"acc": a, "score": round(i["score"], 3), "rules": i["rules"]} for a, i in sorted(_state["al"].items())]


@app.post("/investigate/{acc}")
def investigate(acc: str):
    if acc not in _state["al"]:
        raise HTTPException(404, "no alert for this account")
    i = _state["al"][acc]
    try:
        with _lock:
            r = _state["inv"].investigate(acc, i["score"], i["rules"])
    except CaseAlreadyDecided as e:
        raise HTTPException(409, str(e))
    return {k: r[k] for k in ("case_id", "verdict", "note", "status")}


@app.post("/decide/{case_id}")
def decide(case_id: str, body: Decision):
    inv = _state["inv"]
    if case_id not in inv.cases:
        raise HTTPException(404, "unknown case")
    try:
        with _lock:
            c = inv.decide(case_id, body.analyst, body.decision, body.reason)
    except CaseAlreadyDecided as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"case_id": case_id, "status": c["status"]}


@app.get("/audit/{case_id}")
def audit(case_id: str):
    inv = _state["inv"]
    with _lock:
        return {"chain_valid": inv.audit.verify()["ok"], "head": inv.audit.head(), "entries": inv.audit.entries(case_id)}
