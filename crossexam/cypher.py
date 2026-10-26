"""Optional export of the money-flow graph as Cypher statements.

Every account that appears in a transaction becomes an :Account node, including external counterparties
(merchants, senders and beneficiaries outside the bank), and every transaction with two non-empty ends and finite day and amount becomes a :PAID relationship (others are skipped).
Tested against Neo4j 5: node and relationship counts match the SQLite source (see tests/test_neo4j_live.py)."""
import json
import math
import sys

from .model import prepare

BATCH = 500


def _valid(r):
    """A payment is exported only if both ends are non-empty ids and day and amount are finite numbers.
    Cypher has no literal for NaN or infinity, and a payment without both ends cannot be a relationship."""
    s, d, day, amt, kind = r
    return (isinstance(s, str) and s != "" and isinstance(d, str) and d != "" and isinstance(day, (int, float)) and isinstance(amt, (int, float))
            and math.isfinite(day) and math.isfinite(amt) and isinstance(kind, str))


def _lit(r):
    """One payment as a Cypher map literal (Cypher keys are unquoted, unlike JSON)."""
    s, d, day, amt, kind = r
    return f"{{s:{json.dumps(s)},d:{json.dumps(d)},day:{float(day)!r},amt:{float(amt)!r},kind:{json.dumps(kind)}}}"


def payments(con):
    return [r for r in con.execute("select src, dst, day, amount, kind from transactions order by txn_id") if _valid(r)]


def statements(con):
    """Yield Cypher statements: a uniqueness constraint, the account nodes, then the payments in batches."""
    yield "CREATE CONSTRAINT account_id IF NOT EXISTS FOR (a:Account) REQUIRE a.id IS UNIQUE;"
    rows = payments(con)
    ids = sorted({r[0] for r in rows} | {r[1] for r in rows} | {x for (x,) in con.execute("select acc_id from customers") if x})
    for i in range(0, len(ids), BATCH):
        yield f"UNWIND {json.dumps(ids[i:i + BATCH])} AS id MERGE (:Account {{id: id}});"
    for i in range(0, len(rows), BATCH):
        yield f"UNWIND [{','.join(_lit(r) for r in rows[i:i + BATCH])}] AS r MATCH (a:Account {{id: r.s}}), (b:Account {{id: r.d}}) CREATE (a)-[:PAID {{day: r.day, amount: r.amt, kind: r.kind}}]->(b);"


def export(data, path):
    with open(path, "w", encoding="utf-8") as f:
        for s in statements(data["con"]):
            f.write(s + "\n")


if __name__ == "__main__":
    export(prepare(1), sys.argv[1] if len(sys.argv) > 1 else "graph.cypher")
