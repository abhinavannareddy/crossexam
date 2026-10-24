import pytest
from fastapi.testclient import TestClient

from crossexam.agents import Investigator, check_note
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
    assert not check_note(bad.replace("Evidence:", "Evidence:", 1) + " [E99]", r["evidence"])["ok"]


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


def test_api_flow():
    from crossexam import api
    with TestClient(api.app) as c:
        al = c.get("/alerts").json()
        assert al
        r = c.post(f"/investigate/{al[0]['acc']}").json()
        assert r["status"] == "awaiting_analyst"
        assert c.post(f"/decide/{r['case_id']}", json={"analyst": "a", "decision": "close", "reason": "r"}).json()["status"] == "closed"
        assert c.get(f"/audit/{r['case_id']}").json()["chain_valid"] is True
        assert c.post("/investigate/NOPE").status_code == 404
