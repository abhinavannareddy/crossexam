"""Append-only, hash-chained audit log of everything the agents do and every analyst decision."""
import hashlib
import json
import sqlite3
import time


class AuditLog:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.execute("CREATE TABLE audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, case_id TEXT, actor TEXT, action TEXT, payload TEXT, prev TEXT, hash TEXT)")

    @staticmethod
    def _h(prev, ts, case_id, actor, action, payload):
        return hashlib.sha256(f"{prev}|{ts}|{case_id}|{actor}|{action}|{payload}".encode()).hexdigest()

    def add(self, case_id, actor, action, payload):
        row = self.db.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        prev, ts, body = (row[0] if row else "GENESIS"), time.time(), json.dumps(payload, sort_keys=True, default=str)
        self.db.execute("INSERT INTO audit(ts,case_id,actor,action,payload,prev,hash) VALUES (?,?,?,?,?,?,?)",
                        (ts, case_id, actor, action, body, prev, self._h(prev, ts, case_id, actor, action, body)))

    def entries(self, case_id=None):
        q, a = ("SELECT id,ts,case_id,actor,action,payload FROM audit WHERE case_id=? ORDER BY id", (case_id,)) if case_id else \
               ("SELECT id,ts,case_id,actor,action,payload FROM audit ORDER BY id", ())
        return [dict(zip(("id", "ts", "case_id", "actor", "action", "payload"), r)) for r in self.db.execute(q, a)]

    def verify(self):
        prev = "GENESIS"
        for r in self.db.execute("SELECT id,ts,case_id,actor,action,payload,prev,hash FROM audit ORDER BY id"):
            if r[6] != prev or r[7] != self._h(prev, r[1], r[2], r[3], r[4], r[5]):
                return {"ok": False, "broken_at": r[0]}
            prev = r[7]
        return {"ok": True}
