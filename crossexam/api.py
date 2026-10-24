"""FastAPI service. The system recommends; only an analyst call to /decide changes a case status."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .agents import Investigator
from .model import alerts, prepare, train

app = FastAPI(title="CrossExam")
_state = {}


def _init(seed=1):
    d = prepare(seed)
    _, score = train(d)
    _state.update(d=d, al=alerts(d, score), inv=Investigator(d))


class Decision(BaseModel):
    analyst: str
    decision: str
    reason: str = ""


@app.on_event("startup")
def startup():
    _init()


@app.get("/alerts")
def list_alerts():
    return [{"acc": a, "score": round(i["score"], 3), "rules": i["rules"]} for a, i in sorted(_state["al"].items())]


@app.post("/investigate/{acc}")
def investigate(acc: str):
    if acc not in _state["al"]:
        raise HTTPException(404, "no alert for this account")
    i = _state["al"][acc]
    r = _state["inv"].investigate(acc, i["score"], i["rules"])
    return {k: r[k] for k in ("case_id", "verdict", "note", "status")}


@app.post("/decide/{case_id}")
def decide(case_id: str, body: Decision):
    inv = _state["inv"]
    if case_id not in inv.cases:
        raise HTTPException(404, "unknown case")
    try:
        c = inv.decide(case_id, body.analyst, body.decision, body.reason)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"case_id": case_id, "status": c["status"]}


@app.get("/audit/{case_id}")
def audit(case_id: str):
    inv = _state["inv"]
    return {"chain_valid": inv.audit.verify()["ok"], "entries": inv.audit.entries(case_id)}
