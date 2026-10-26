"""Append-only, hash-chained audit log of everything the agents do and every analyst decision."""
import hashlib
import json
import sqlite3
import threading
import time


class AuditLog:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.execute("CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, case_id TEXT, actor TEXT, action TEXT, payload TEXT, prev TEXT, hash TEXT)")

    @staticmethod
    def _h(prev, ts, case_id, actor, action, payload):
        return hashlib.sha256(f"{prev}|{ts}|{case_id}|{actor}|{action}|{payload}".encode()).hexdigest()

    def add(self, case_id, actor, action, payload):
        with self.lock:
            self._add(case_id, actor, action, payload)

    def _add(self, case_id, actor, action, payload):
        row = self.db.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        prev, ts, body = (row[0] if row else "GENESIS"), time.time(), json.dumps(payload, sort_keys=True, default=str)
        self.db.execute("INSERT INTO audit(ts,case_id,actor,action,payload,prev,hash) VALUES (?,?,?,?,?,?,?)",
                        (ts, case_id, actor, action, body, prev, self._h(prev, ts, case_id, actor, action, body)))
        self.db.commit()

    def entries(self, case_id=None):
        q, a = ("SELECT id,ts,case_id,actor,action,payload FROM audit WHERE case_id=? ORDER BY id", (case_id,)) if case_id else \
               ("SELECT id,ts,case_id,actor,action,payload FROM audit ORDER BY id", ())
        return [dict(zip(("id", "ts", "case_id", "actor", "action", "payload"), r)) for r in self.db.execute(q, a)]

    def head(self):
        """Latest hash and entry count. Store this outside the database (a ticket, a signed message) to anchor the chain."""
        row = self.db.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        return {"hash": row[0] if row else "GENESIS", "count": self.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0]}

    def verify(self, anchor=None):
        """Check the chain. With an anchor from head(), also detect deleted newest entries or a rebuilt chain."""
        prev = "GENESIS"
        for r in self.db.execute("SELECT id,ts,case_id,actor,action,payload,prev,hash FROM audit ORDER BY id"):
            if r[6] != prev or r[7] != self._h(prev, r[1], r[2], r[3], r[4], r[5]):
                return {"ok": False, "broken_at": r[0]}
            prev = r[7]
        if anchor is not None:
            h = self.head()
            if h["count"] < anchor["count"] or self._hash_at(anchor["count"]) != anchor["hash"]:
                return {"ok": False, "broken_at": "anchor"}
        return {"ok": True}

    def _hash_at(self, n):
        row = self.db.execute("SELECT hash FROM audit ORDER BY id LIMIT 1 OFFSET ?", (n - 1,)).fetchone() if n else None
        return row[0] if row else "GENESIS"
