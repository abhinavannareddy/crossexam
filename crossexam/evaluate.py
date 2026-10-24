"""Evaluation on synthetic data with planted ground truth, over several dataset seeds.

Compares: model score only, prosecutor only, and the full CrossExam workflow (with and without precedent memory).
"escalate" is the action under test. Analyst review is counted separately (it is not an automatic decision)."""
import json
import sys

import numpy as np

from .agents import Investigator, check_note
from .memory import CaseMemory
from .model import ALERT_THRESHOLD, alerts, prepare, train

SEEDS = [1, 2, 3, 4, 5]


def rates(rows):
    """rows: list of (is_suspicious, action) with action in escalate/close/review."""
    sus = [a for s, a in rows if s]
    ben = [a for s, a in rows if not s]
    return {
        "n_alerts": len(rows),
        "miss_rate": round(sum(a == "close" for a in sus) / max(1, len(sus)), 3),
        "escalated_suspicious": round(sum(a == "escalate" for a in sus) / max(1, len(sus)), 3),
        "false_escalation_rate": round(sum(a == "escalate" for a in ben) / max(1, len(ben)), 3),
        "review_share": round(sum(a == "review" for _, a in rows) / max(1, len(rows)), 3),
    }


ACT = {"escalate": "escalate", "close_suggested": "close", "analyst_review": "review"}


def run_seed(seed, scale=1.0):
    d = prepare(seed, scale)
    _, score = train(d)
    al = alerts(d, score)
    cust = d["cust"].set_index("acc_id")
    ids = sorted(al)
    truth = {a: (cust.loc[a, "label"] == "suspicious", cust.loc[a, "typology"]) for a in ids}
    out = {"model": [], "prosecutor": [], "full_nomem": [], "full_mem": [], "typ": {}, "faith": []}

    inv_p = Investigator(d)
    inv_n = Investigator(d)
    inv_m = Investigator(d, memory=CaseMemory())
    half = len(ids) // 2
    for i, a in enumerate(ids):
        info = al[a]
        sus, typ = truth[a]
        out["model"].append((sus, "escalate" if info["score"] >= 0.5 else "close"))
        out["prosecutor"].append((sus, ACT[inv_p.investigate(a, info["score"], info["rules"], mode="prosecutor_only")["verdict"]["recommendation"]]))
        r = inv_n.investigate(a, info["score"], info["rules"], mode="no_memory")
        act = ACT[r["verdict"]["recommendation"]]
        out["full_nomem"].append((sus, act))
        out["typ"].setdefault(typ, []).append((act, info["score"] >= 0.5))
        out["faith"].append(check_note(r["note"], r["evidence"])["ok"])
        # memory arm: analyst decisions (simulated from ground truth) are fed back into memory as the queue is worked
        rm = inv_m.investigate(a, info["score"], info["rules"], mode="full")
        actm = ACT[rm["verdict"]["recommendation"]]
        if i >= half:
            out["full_mem"].append((sus, actm))
            out.setdefault("half_nomem", []).append((sus, act))
        inv_m.decide(rm["case_id"], "simulated_analyst", "escalate" if sus else "close", "ground truth")
    out["chain_ok"] = inv_n.audit.verify()["ok"] and inv_m.audit.verify()["ok"]
    return out


def summarize(seeds=SEEDS):
    runs = [run_seed(s) for s in seeds]
    agg = {}
    for k in ("model", "prosecutor", "full_nomem"):
        agg[k] = rates([r for run in runs for r in run[k]])
    agg["second_half_no_memory"] = rates([r for run in runs for r in run["half_nomem"]])
    agg["second_half_with_memory"] = rates([r for run in runs for r in run["full_mem"]])
    typ = {}
    for run in runs:
        for t, v in run["typ"].items():
            typ.setdefault(t, []).extend(v)
    agg["by_typology"] = {t: {"n": len(v), "crossexam_escalate": round(sum(a == "escalate" for a, _ in v) / len(v), 3),
                              "crossexam_close": round(sum(a == "close" for a, _ in v) / len(v), 3),
                              "model_escalate": round(sum(m for _, m in v) / len(v), 3)} for t, v in sorted(typ.items())}
    faith = [f for run in runs for f in run["faith"]]
    agg["citation_faithfulness"] = {"notes": len(faith), "all_tags_and_numbers_supported": round(sum(faith) / len(faith), 3)}
    agg["audit_chain_valid"] = all(r["chain_ok"] for r in runs)
    agg["seeds"] = list(seeds)
    return agg


if __name__ == "__main__":
    res = summarize()
    print(json.dumps(res, indent=2))
    with open("results.json", "w") as f:
        json.dump(res, f, indent=2)
