"""Loads the Cypher export into a throwaway Neo4j container and checks the counts against SQLite.
Skipped when Docker or the neo4j:5 image is not available. Run it with: python -m pytest tests/test_neo4j_live.py -q"""
import shutil
import subprocess
import time
import uuid

import pytest

from crossexam.cypher import BATCH, export, payments, statements
from crossexam.model import prepare


def _docker(*args, **kw):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=kw.pop("timeout", 120), **kw)


def _has_neo4j_image():
    if not shutil.which("docker"):
        return False
    try:
        return bool(_docker("images", "-q", "neo4j:5").stdout.strip())
    except Exception:
        return False


@pytest.fixture(scope="module")
def data():
    return prepare(1)


def test_export_has_every_endpoint_and_payment(data, tmp_path):
    con = data["con"]
    path = tmp_path / "g.cypher"
    export(data, str(path))
    text = path.read_text(encoding="utf-8")
    assert "REQUIRE a.id IS UNIQUE" in text
    stmts = list(statements(con))
    assert all(s.endswith(";") and "\n" not in s for s in stmts)
    rows = payments(con)
    assert len(rows) == con.execute("select count(*) from transactions where src is not null and dst is not null").fetchone()[0]
    for (x,) in con.execute("select distinct dst from transactions where dst like 'MER_%'"):
        assert f'"{x}"' in text      # every external counterparty gets a node
    n_pay_stmts = sum(1 for s in stmts if "CREATE (a)-[:PAID" in s)
    assert n_pay_stmts == -(-len(rows) // BATCH)


def test_export_skips_rows_cypher_cannot_express():
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.execute("create table customers(acc_id text)")
    con.execute("create table transactions(txn_id integer, day real, src text, dst text, amount real, kind text)")
    con.executemany("insert into transactions values (?,?,?,?,?,?)", [
        (1, 1.0, "A", "B", 10.0, "transfer"),
        (2, 1.0, "A", "", 10.0, "transfer"),               # empty end
        (3, 1.0, None, "B", 10.0, "transfer"),             # missing end
        (4, float("inf"), "A", "B", 10.0, "transfer"),     # not a Cypher literal
        (5, 1.0, "A", "B", None, "transfer"),              # missing amount
        (6, 1.0, 'a"b\\c', "B", 5.0, "transfer")])        # quote and backslash stay inside the string
    con.execute("insert into customers values ('A')")
    rows = payments(con)
    assert [r[0] for r in rows] == ["A", 'a"b\\c']
    text = "\n".join(statements(con))
    assert "inf" not in text and "nan" not in text
    assert r'"a\"b\\c"' in text


@pytest.mark.skipif(not _has_neo4j_image(), reason="Docker with the neo4j:5 image is not available")
def test_live_neo4j_counts_match_sqlite(data, tmp_path):
    con = data["con"]
    name, pw = f"crossexam-neo4j-{uuid.uuid4().hex[:8]}", "crossexam-test-only"
    rows = payments(con)
    expected_edges = len(rows)
    expected_nodes = len({r[0] for r in rows} | {r[1] for r in rows} | {x for (x,) in con.execute("select acc_id from customers")})
    path = tmp_path / "g.cypher"
    export(data, str(path))
    assert _docker("run", "-d", "--rm", "--name", name, "-e", f"NEO4J_AUTH=neo4j/{pw}", "neo4j:5").returncode == 0
    try:
        shell = ["exec", name, "cypher-shell", "-u", "neo4j", "-p", pw]
        for _ in range(60):
            if _docker(*shell, "RETURN 1").returncode == 0:
                break
            time.sleep(3)
        else:
            pytest.fail("Neo4j did not start")
        assert _docker("cp", str(path), f"{name}:/tmp/g.cypher").returncode == 0
        load = _docker(*shell, "-f", "/tmp/g.cypher", timeout=300)
        assert load.returncode == 0, load.stderr[-500:]
        out = _docker(*shell, "--format", "plain", "MATCH (n:Account) WITH count(n) AS nodes MATCH ()-[r:PAID]->() RETURN nodes, count(r) AS edges").stdout.split()
        assert (int(out[-2].rstrip(",")), int(out[-1])) == (expected_nodes, expected_edges)
    finally:
        _docker("rm", "-f", name)
