"""Alert scoring model. Trained on the four known typologies against benign accounts (look-alikes
included). The 'dormant' typology is held out of training entirely and appears only in testing."""
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

from .features import FEATURES, MoneyGraph, account_stats, model_features
from .generate import SEEN, build, to_sqlite

ALERT_THRESHOLD = 0.25


def split_groups(cust: pd.DataFrame, seed=0):
    """Accounts of one planted pattern (ring, chain, family loop) always land on the same side."""
    rng = np.random.default_rng(seed)
    side = {g: ("train" if rng.random() < 0.6 else "test") for g in sorted(cust.group.unique())}
    return cust.group.map(side)


def prepare(seed=1, scale=1.0):
    cust, txn = build(seed, scale)
    con = to_sqlite(cust, txn)
    graph = MoneyGraph(con)
    stats = {a: account_stats(con, a) for a in cust.acc_id}
    X = pd.DataFrame([model_features(stats[a], graph) for a in cust.acc_id], columns=FEATURES, index=cust.acc_id)
    cust = cust.assign(split=split_groups(cust, seed).values)
    return {"cust": cust, "txn": txn, "con": con, "graph": graph, "stats": stats, "X": X}


def train(data, seed=0):
    c, X = data["cust"].set_index("acc_id"), data["X"]
    tr = c[(c.split == "train") & (c.typology != "dormant")].index
    y = (c.loc[tr, "label"] == "suspicious").astype(int)
    m = GradientBoostingClassifier(n_estimators=120, max_depth=3, learning_rate=0.08, random_state=seed)
    m.fit(X.loc[tr], y)
    score = pd.Series(m.predict_proba(X)[:, 1], index=X.index)
    return m, score


def rule_triggers(st: dict, graph: MoneyGraph) -> list:
    """First-line monitoring rules, deliberately broad (as real ones are)."""
    hit = []
    if st["n_near"] >= 5:
        hit.append("R1 repeated deposits just under the reporting threshold")
    if graph.cycle_of(st["acc"]):
        hit.append("R2 money returns to its source through a short cycle")
    if st["n_cp_in"] >= 8:
        hit.append("R3 many different senders in 30 days")
    if st["vol_vs_expected"] >= 5:
        hit.append("R4 inflow far above expected volume")
    if st["vol_ratio_prior"] >= 8 and st["sum_in"] > 100_000:
        hit.append("R5 sudden jump against history")
    return hit


def alerts(data, score):
    """An alert is raised when a rule fires or the model score is high. Test accounts only."""
    c = data["cust"].set_index("acc_id")
    out = {}
    for a in c[c.split == "test"].index:
        rules = rule_triggers(data["stats"][a], data["graph"])
        if rules or score[a] >= ALERT_THRESHOLD:
            out[a] = {"score": float(score[a]), "rules": rules}
    return out
