import pytest
from fastapi.testclient import TestClient

from crossexam.agents import CaseAlreadyDecided, Investigator, check_note
from crossexam.audit import AuditLog
from crossexam.model import alerts, prepare, train


@pytest.fixture(scope="module")
def world():
    d = prepare(1)
    _, score = train(d)
    al = alerts(d, score)
    cust = d["cust"].set_index("acc_id")
    return d, al, cust


def pick(al, cust, typ):
    return next(a for a in sorted(al) if cust.loc[a, "typology"] == typ)


def test_generator_is_deterministic():
    a, b = prepare(3), prepare(3)
    assert a["cust"].equals(b["cust"])


def test_agents_cannot_see_labels(world):
    d, _, _ = world
    cols = [r[1] for r in d["con"].execute("pragma table_info(customers)")]
    assert not {"label", "typology", "group"} & set(cols)


def test_dormant_held_out_of_training(world):
    d, al, cust = world
    import inspect
    from crossexam import model
    assert 'typology != "dormant"' in inspect.getsource(model.train)
    assert any(cust.loc[a, "typology"] == "dormant" for a in al)


def test_circular_escalated_and_explained(world):
    d, al, cust = world
    a = pick(al, cust, "circular")
    r = Investigator(d).investigate(a, al[a]["score"], al[a]["rules"])
    assert r["verdict"]["recommendation"] == "escalate"
    assert "closed loop" in r["note"]
    assert check_note(r["note"], r["evidence"])["ok"]


def test_marketplace_not_escalated(world):
    d, al, cust = world
    a = pick(al, cust, "lookalike_marketplace")
    r = Investigator(d).investigate(a, al[a]["score"], al[a]["rules"])
    assert r["verdict"]["recommendation"] != "escalate"


def test_no_automatic_final_decision(world):
    d, al, cust = world
    inv = Investigator(d)
    a = pick(al, cust, "structuring")
    r = inv.investigate(a, al[a]["score"], al[a]["rules"])
    assert r["status"] == "awaiting_analyst"
    assert "does not close or escalate" in r["note"]
    with pytest.raises(ValueError):
        inv.decide(r["case_id"], "x", "approve")
    inv.decide(r["case_id"], "analyst1", "escalate", "ok")
    assert inv.cases[r["case_id"]]["status"] == "escalated"


def test_citation_check_catches_fabrication(world):
    d, al, cust = world
    a = pick(al, cust, "layering")
    r = Investigator(d).investigate(a, al[a]["score"], al[a]["rules"])
    bad = r["note"] + "\n- E99: invented 123,456,789 SEK"
    assert not check_note(bad + " [E99]", r["evidence"])["ok"]


def test_citation_check_catches_wrong_weights_and_referee_line(world):
    d, al, cust = world
    a = pick(al, cust, "layering")
    r = Investigator(d).investigate(a, al[a]["score"], al[a]["rules"])
    args = (r["evidence"], r["prosecution"], r["defence"], r["verdict"])
    assert check_note(r["note"], *args)["ok"]
    altered = r["note"].replace("(weight 0.40,", "(weight 0.99,", 1)
    assert check_note(altered, *args)["mismatched_weights"]
    altered = r["note"].replace("Referee: suspicion", "Referee: suspicion 9.99 vs", 1)
    assert check_note(altered, *args)["mismatched_referee_line"]


def test_decided_case_cannot_be_reopened_or_decided_twice(world):
    d, al, cust = world
    inv = Investigator(d)
    a = pick(al, cust, "structuring")
    r = inv.investigate(a, al[a]["score"], al[a]["rules"])
    inv.decide(r["case_id"], "analyst1", "escalate")
    assert len(inv.memory) == 1
    with pytest.raises(CaseAlreadyDecided):
        inv.investigate(a, al[a]["score"], al[a]["rules"])
    with pytest.raises(CaseAlreadyDecided):
        inv.decide(r["case_id"], "analyst2", "close")
    assert inv.cases[r["case_id"]]["status"] == "escalated"
    assert len(inv.memory) == 1


def test_undecided_case_can_be_reinvestigated(world):
    d, al, cust = world
    inv = Investigator(d)
    a = pick(al, cust, "mule")
    inv.investigate(a, al[a]["score"], al[a]["rules"])
    assert inv.investigate(a, al[a]["score"], al[a]["rules"])["status"] == "awaiting_analyst"


def test_audit_anchor_detects_deleted_tail_and_persists(tmp_path):
    path = str(tmp_path / "audit.db")
    log = AuditLog(path)
    for i in range(4):
        log.add("C1", "x", "step", {"i": i})
    anchor = log.head()
    assert log.verify(anchor)["ok"]
    log.db.execute("DELETE FROM audit WHERE id=4")
    log.db.commit()
    assert log.verify()["ok"]  # the chain alone cannot see a deleted tail
    assert log.verify(anchor) == {"ok": False, "broken_at": "anchor"}
    reopened = AuditLog(path)
    reopened.add("C1", "x", "step", {"i": 99})
    assert reopened.verify()["ok"] and reopened.head()["count"] == 4


def test_audit_chain_detects_tampering(world):
    d, al, cust = world
    inv = Investigator(d)
    a = pick(al, cust, "mule")
    inv.investigate(a, al[a]["score"], al[a]["rules"])
    assert inv.audit.verify()["ok"]
    inv.audit.db.execute("UPDATE audit SET payload='{\"x\":1}' WHERE id=2")
    v = inv.audit.verify()
    assert not v["ok"] and v["broken_at"] == 2


def test_memory_changes_plan(world):
    d, al, cust = world
    inv = Investigator(d)
    a, b = [x for x in sorted(al) if cust.loc[x, "typology"] == "none"][:2]
    r1 = inv.investigate(a, al[a]["score"], al[a]["rules"])
    inv.decide(r1["case_id"], "an", "close")
    r2 = inv.investigate(b, al[b]["score"], al[b]["rules"])
    assert len(inv.memory) == 1
    assert any(e["kind"] == "precedent" for e in r2["evidence"])


def test_api_flow(tmp_path, monkeypatch):
    from crossexam import api
    monkeypatch.setenv("CROSSEXAM_AUDIT_DB", str(tmp_path / "audit.db"))
    with TestClient(api.app) as c:
        assert c.get("/health").json()["status"] == "ok"
        al = c.get("/alerts").json()
        assert al
        r = c.post(f"/investigate/{al[0]['acc']}").json()
        assert r["status"] == "awaiting_analyst"
        assert c.post(f"/decide/{r['case_id']}", json={"analyst": "a", "decision": "close", "reason": "r"}).json()["status"] == "closed"
        assert c.get(f"/audit/{r['case_id']}").json()["chain_valid"] is True
        assert c.post(f"/investigate/{al[0]['acc']}").status_code == 409
        assert c.post(f"/decide/{r['case_id']}", json={"analyst": "a", "decision": "escalate"}).status_code == 409
        assert c.post(f"/decide/{r['case_id']}", json={"analyst": "a", "decision": "bogus"}).status_code == 422
        assert c.post("/investigate/NOPE").status_code == 404


def test_slow_forwarding_mule_is_escalated(world):
    """A mule whose outflow lands more than 72 hours after the inflows has passthrough 0 but still forwards the money."""
    d, al, cust = world
    slow = [a for a in sorted(al) if cust.loc[a, "typology"] == "mule" and d["stats"][a]["passthrough"] < 0.6 and d["stats"][a]["n_cp_in"] >= 8]
    assert slow
    inv = Investigator(d)
    for a in slow:
        r = inv.investigate(a, al[a]["score"], al[a]["rules"], mode="no_memory")
        assert r["verdict"]["recommendation"] == "escalate"
        assert any(p["kind"] == "mule" for p in r["prosecution"])


def test_guidance_label_matches_argument_kind(world):
    d, al, cust = world
    a = pick(al, cust, "circular")
    r = Investigator(d).investigate(a, al[a]["score"], al[a]["rules"], mode="no_memory")
    got = {x["kind"]: x["policy"] for x in r["prosecution"]}
    assert got.get("layering") == "P2" and got.get("circular") == "P3"
    assert got["spike"] == "P5"
    assert "1 counterparties" not in r["note"] and "1 inflows" not in r["note"]


def test_decision_is_refused_after_restart_when_audit_log_has_one(world, tmp_path):
    d, al, cust = world
    path = str(tmp_path / "audit.db")
    a = pick(al, cust, "structuring")
    first = Investigator(d, audit=AuditLog(path))
    r = first.investigate(a, al[a]["score"], al[a]["rules"])
    first.decide(r["case_id"], "analyst1", "escalate")
    restarted = Investigator(d, audit=AuditLog(path))       # in-memory cases are gone, the audit log is not
    with pytest.raises(CaseAlreadyDecided):
        restarted.investigate(a, al[a]["score"], al[a]["rules"])


def test_failed_audit_write_leaves_case_undecided(world):
    d, al, cust = world
    a = pick(al, cust, "layering")

    class Broken(AuditLog):
        fail = False

        def add(self, *args, **kw):
            if self.fail and args[2] == "analyst_decision":
                raise RuntimeError("disk full")
            return super().add(*args, **kw)

    inv = Investigator(d, audit=Broken())
    r = inv.investigate(a, al[a]["score"], al[a]["rules"])
    inv.audit.fail = True
    with pytest.raises(RuntimeError):
        inv.decide(r["case_id"], "analyst1", "close")
    assert inv.cases[r["case_id"]]["status"] == "awaiting_analyst" and len(inv.memory) == 0
    inv.audit.fail = False
    assert inv.decide(r["case_id"], "analyst1", "close")["status"] == "closed"


def test_api_validation_and_unknown_case(tmp_path, monkeypatch):
    from crossexam import api
    monkeypatch.setenv("CROSSEXAM_AUDIT_DB", str(tmp_path / "audit.db"))
    with TestClient(api.app) as c:
        assert c.post("/decide/CASE-NOPE", json={"analyst": "a", "decision": "close"}).status_code == 404
        acc = c.get("/alerts").json()[0]["acc"]
        case = c.post(f"/investigate/{acc}").json()["case_id"]
        assert c.post(f"/decide/{case}", json={"analyst": "", "decision": "close"}).status_code == 422
        assert c.post(f"/decide/{case}", json={"analyst": "a" * 101, "decision": "close"}).status_code == 422
        assert c.post(f"/decide/{case}", json={"analyst": "a", "decision": "close", "reason": "x" * 2001}).status_code == 422
