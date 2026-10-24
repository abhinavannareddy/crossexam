"""Account statistics from SQL and money-flow features from a transaction graph."""
import math
import sqlite3

import networkx as nx
import numpy as np
import pandas as pd

from .generate import THRESHOLD, WINDOW_START

NEAR_LO = 9000
FORWARD_SHARE = 0.85       # an onward transfer keeps at least this share of what came in
FORWARD_WINDOW_DAYS = 1.5


def _rows(con, acc):
    q = "SELECT txn_id, day, src, dst, amount, kind FROM transactions WHERE src=? OR dst=? ORDER BY day"
    return pd.read_sql(q, con, params=(acc, acc))


def account_stats(con: sqlite3.Connection, acc: str) -> dict:
    prof = pd.read_sql("SELECT * FROM customers WHERE acc_id=?", con, params=(acc,)).iloc[0].to_dict()
    t = _rows(con, acc)
    t["dir"] = np.where(t.dst == acc, "in", "out")
    win, prior = t[t.day >= WINDOW_START], t[t.day < WINDOW_START]
    inn, out = win[win.dir == "in"], win[win.dir == "out"]
    near = inn[(inn.amount >= NEAR_LO) & (inn.amount < THRESHOLD)]
    p_in = prior[prior.dir == "in"]
    p_near = p_in[(p_in.amount >= NEAR_LO) & (p_in.amount < THRESHOLD)]
    sum_in, sum_out = float(inn.amount.sum()), float(out.amount.sum())
    # share of money out that left within 72 hours of some inflow
    fast = 0.0
    in_days = inn.day.to_numpy()
    for o in out.itertuples():
        if len(in_days) and np.any((in_days <= o.day) & (in_days >= o.day - 3)):
            fast += o.amount
    prior_monthly = float(p_in.amount.sum()) / 2
    return {
        "acc": acc, "profile": prof,
        "n_txn": len(win), "n_in": len(inn), "n_out": len(out), "sum_in": sum_in, "sum_out": sum_out,
        "n_near": len(near), "share_near": len(near) / max(1, len(inn)),
        "n_cp_in": inn.src.nunique(), "n_cp_out": out.dst.nunique(),
        "out_conc": float(out.groupby("dst").amount.sum().max() / sum_out) if sum_out else 0.0,
        "passthrough": min(1.0, fast / sum_in) if sum_in else 0.0,
        "vol_vs_expected": sum_in / max(1.0, prof["expected_monthly_volume"]),
        "prior_monthly_in": prior_monthly, "prior_n_in": len(p_in), "prior_n_near": len(p_near),
        "prior_share_near": len(p_near) / max(1, len(p_in)),
        "vol_ratio_prior": sum_in / max(1.0, prior_monthly),
        "txn_ids_in_window": win.txn_id.tolist(),
    }


class MoneyGraph:
    """Customer-to-customer transfers in the alert window, with cycle and chain queries."""

    def __init__(self, con: sqlite3.Connection):
        accs = {r[0] for r in con.execute("SELECT acc_id FROM customers")}
        df = pd.read_sql("SELECT txn_id, day, src, dst, amount FROM transactions WHERE day >= ?", con, params=(WINDOW_START - 40,))
        self.edges = df[df.src.isin(accs) & df.dst.isin(accs) & (df.day >= WINDOW_START)]
        self.out_by_src = {k: g.sort_values("day") for k, g in df.groupby("src")}
        self.in_by_dst = {k: g.sort_values("day") for k, g in df.groupby("dst")}
        self.G = nx.DiGraph()
        for r in self.edges.itertuples():
            self.G.add_edge(r.src, r.dst)
        self.cycles = self._cycles()

    def _cycles(self):
        found = {}
        for cyc in nx.simple_cycles(self.G, length_bound=4):
            if len(cyc) < 3:
                continue
            days = []
            for i, u in enumerate(cyc):
                v = cyc[(i + 1) % len(cyc)]
                e = self.edges[(self.edges.src == u) & (self.edges.dst == v)]
                days.append(float(e.day.min()))
            if max(days) - min(days) <= 7 and max(days) >= WINDOW_START:
                for a in cyc:
                    found.setdefault(a, []).append(cyc)
        return found

    def cycle_of(self, acc):
        return self.cycles.get(acc, [])

    def _forward(self, acc, day, amount, hops=0, seen=None):
        seen = seen or {acc}
        o = self.out_by_src.get(acc)
        if o is None or hops > 6:
            return hops, []
        cand = o[(o.day > day) & (o.day <= day + FORWARD_WINDOW_DAYS) & (o.amount >= FORWARD_SHARE * amount)]
        for r in cand.itertuples():
            if r.dst in seen:
                continue
            h, path = self._forward(r.dst, r.day, r.amount, hops + 1, seen | {r.dst})
            return h, [r.txn_id] + path
        return hops, []

    def _backward(self, acc, day, amount, hops=0, seen=None):
        seen = seen or {acc}
        i = self.in_by_dst.get(acc)
        if i is None or hops > 6:
            return hops, []
        cand = i[(i.day < day) & (i.day >= day - FORWARD_WINDOW_DAYS) & (i.amount * 1.0 >= amount)]
        for r in cand.itertuples():
            if r.src in seen:
                continue
            h, path = self._backward(r.src, r.day, r.amount, hops + 1, seen | {r.src})
            return h, [r.txn_id] + path
        return hops, []

    def chain(self, acc):
        """Longest forward and backward onward-transfer chain through this account in the window."""
        i, o = self.in_by_dst.get(acc), self.out_by_src.get(acc)
        best = {"length": 1, "txn_ids": []}
        if i is None or o is None:
            return best
        i, o = i[i.day >= WINDOW_START], o[o.day >= WINDOW_START]
        for r in i.itertuples():
            f, fpath = self._forward(acc, r.day, r.amount)
            if f >= 1:
                b, bpath = self._backward(r.src, r.day, r.amount, 0, {acc, r.src}) if r.src in self.in_by_dst else (0, [])
                length = 1 + f + b
                if length > best["length"]:
                    best = {"length": length, "txn_ids": bpath[::-1] + [r.txn_id] + fpath}
        return best


FEATURES = ["n_txn", "vol_vs_expected", "share_near", "n_near", "n_cp_in", "n_cp_out", "cycle_flag", "account_age", "is_business"]


def model_features(stats: dict, graph: MoneyGraph) -> list:
    """Simple window-only features, like a first-line monitoring model. History, documentation and
    onward-transfer chains are deliberately left out: those are what the investigation agents look at."""
    return [stats["n_txn"], stats["vol_vs_expected"], stats["share_near"], stats["n_near"], stats["n_cp_in"],
            stats["n_cp_out"], 1.0 if graph.cycle_of(stats["acc"]) else 0.0, stats["profile"]["account_age_months"],
            1.0 if stats["profile"]["segment"] == "business" else 0.0]
