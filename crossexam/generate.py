"""Synthetic bank data with planted money-laundering typologies and benign look-alikes.

Nothing here is real. Customers are numbered pseudonyms, and every typology is a simplified,
generic pattern. Ground truth is stored so detection can be measured."""
import sqlite3

import numpy as np
import pandas as pd

DAYS = 90
WINDOW_START = 60           # alerts look at days 60 to 90, days 0 to 60 are history
THRESHOLD = 10_000          # reporting threshold that structuring stays under
CASH_BUSINESS = ["restaurant", "kiosk", "hair_salon"]

SEEN = ["structuring", "layering", "circular", "mule"]
UNSEEN = ["dormant"]
LOOKALIKES = ["cash_business", "family_loop", "marketplace", "property_sale"]


class _Builder:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.cust, self.txn = [], []
        self.n = 0

    def acc(self, segment="private", btype="none", expected=None, age=None, label="benign", typology="none",
            family="", events="", country="SE", group=None):
        self.n += 1
        aid = f"A{self.n:04d}"
        if expected is None:
            expected = float(self.rng.lognormal(10.1, 0.35)) if segment == "private" else float(self.rng.lognormal(11.8, 0.4))
        if age is None:
            age = int(self.rng.integers(12, 120))
        self.cust.append(dict(acc_id=aid, segment=segment, business_type=btype, expected_monthly_volume=round(expected),
                              account_age_months=age, country=country, family_ids=family, documented_events=events,
                              label=label, typology=typology, group=group or aid))
        return aid

    def t(self, day, src, dst, amount, kind="transfer"):
        self.txn.append(dict(day=float(day), src=src, dst=dst, amount=round(float(amount), 2), kind=kind))

    def ext(self, prefix):
        return f"{prefix}_{int(self.rng.integers(1, 400)):03d}"


def _background(b: _Builder, aid: str, seg: str, expected: float, days=(0, DAYS), activity: float = 1.0):
    rng = b.rng
    lo, hi = days
    if seg == "private":
        d0 = rng.uniform(0, 28)
        for k in range(int((hi - d0) // 30) + 1):
            d = d0 + 30 * k
            if lo <= d < hi:
                b.t(d, b.ext("EMP"), aid, expected * 0.8)
        for _ in range(int(rng.poisson(24 * (hi - lo) / 30 * activity))):
            b.t(rng.uniform(lo, hi), aid, b.ext("MER"), max(30, rng.lognormal(np.log(expected * 0.03), 0.6)))
    else:
        for _ in range(int(rng.poisson(40 * (hi - lo) / 30 * activity))):
            b.t(rng.uniform(lo, hi), b.ext("CUS"), aid, max(50, rng.lognormal(np.log(expected / 45), 0.5)))
        for _ in range(int(rng.poisson(9 * (hi - lo) / 30 * activity))):
            b.t(rng.uniform(lo, hi), aid, b.ext("SUP"), max(500, rng.lognormal(np.log(expected / 12), 0.5)))


def build(seed: int = 1, scale: float = 1.0):
    b = _Builder(seed)
    rng = b.rng
    sc = lambda n: max(1, int(round(n * scale)))
    benign_private, benign_business = [], []
    for _ in range(sc(320)):
        a = b.acc("private")
        benign_private.append(a)
        _background(b, a, "private", b.cust[-1]["expected_monthly_volume"])
    for _ in range(sc(100)):
        a = b.acc("business", btype=str(rng.choice(["consulting", "retail", "workshop", "software"])))
        benign_business.append(a)
        _background(b, a, "business", b.cust[-1]["expected_monthly_volume"])
    victims = benign_private

    # ---- benign look-alikes (hard negatives) ----
    for _ in range(sc(30)):                                    # cash business: deposits just under the threshold, for months
        bt = str(rng.choice(CASH_BUSINESS))
        a = b.acc("business", btype=bt, expected=float(rng.uniform(150_000, 260_000)), age=int(rng.integers(18, 100)), typology="lookalike_cash_business")
        _background(b, a, "business", b.cust[-1]["expected_monthly_volume"] * 0.5)
        for d in np.arange(rng.uniform(0, 2), DAYS, 2.4):
            b.t(d, "CASH", a, rng.uniform(8200, 9950), "cash_deposit")
        b.t(rng.uniform(70, 89), a, b.ext("SUP"), 120_000)
    for _ in range(sc(10)):                                    # family allowance loop
        gid = f"G{b.n}"
        ids = [b.acc("private", typology="lookalike_family_loop", age=int(rng.integers(30, 120)), group=gid) for _ in range(3)]
        documented = rng.random() < 0.85
        for i, a in enumerate(ids):
            b.cust[int(a[1:]) - 1]["family_ids"] = ",".join(x for x in ids if x != a) if documented else ""
            _background(b, a, "private", b.cust[int(a[1:]) - 1]["expected_monthly_volume"])
        for month in range(3):
            base = 8 + 30 * month + rng.uniform(0, 3)
            amt = rng.uniform(25_000, 60_000)
            for j in range(3):
                b.t(base + j * 1.5, ids[j], ids[(j + 1) % 3], amt * (1 - 0.01 * j))
    for _ in range(sc(24)):                                    # marketplace seller: many small buyers, weekly payout
        a = b.acc("business", btype="online_seller", expected=float(rng.uniform(80_000, 160_000)), age=int(rng.integers(14, 80)), typology="lookalike_marketplace")
        own = b.ext("OWN")
        for d in np.arange(0, DAYS, 7):
            n_buyers = int(rng.integers(8, 16))
            total = 0.0
            for _ in range(n_buyers):
                amt = rng.uniform(150, 900)
                total += amt
                b.t(d + rng.uniform(0, 6.5), b.ext("BUY"), a, amt)
            b.t(d + 6.9, a, own, total * 0.92)
        _background(b, a, "business", b.cust[-1]["expected_monthly_volume"] * 0.3, activity=0.3)
    for _ in range(sc(24)):                                    # property sale: large inflow, split outflows, documented
        documented = rng.random() < 0.8
        a = b.acc("private", typology="lookalike_property_sale", events="property_sale" if documented else "", age=int(rng.integers(40, 160)))
        _background(b, a, "private", b.cust[-1]["expected_monthly_volume"])
        d = rng.uniform(64, 84)
        amt = rng.uniform(1_500_000, 3_500_000)
        b.t(d, b.ext("NOT"), a, amt)
        parts = rng.dirichlet(np.ones(int(rng.integers(3, 6)))) * amt * 0.96
        for p in parts:
            b.t(d + rng.uniform(0.5, 6), a, b.ext("DST"), p)

    # ---- suspicious typologies ----
    def sus_acc(typology, segment="private", aged=False, group=None):
        age = int(rng.integers(30, 90)) if aged else int(rng.integers(1, 9))
        a = b.acc(segment, btype="consulting" if segment == "business" else "none", age=age, label="suspicious", typology=typology, group=group)
        if aged:                                               # a compromised or sleeper account with normal history
            _background(b, a, segment, b.cust[-1]["expected_monthly_volume"], days=(0, WINDOW_START), activity=0.8)
        return a

    for _ in range(sc(24)):                                    # structuring
        a = sus_acc("structuring", aged=rng.random() < 0.25, segment=str(rng.choice(["private", "business"], p=[0.6, 0.4])))
        start = rng.uniform(WINDOW_START + 2, 80)
        n = int(rng.integers(8, 20))
        total = 0.0
        for d in np.sort(rng.uniform(start, start + rng.uniform(4, 14), n)):
            amt = rng.uniform(9000, 9950)
            total += amt
            b.t(d, "CASH", a, amt, "cash_deposit")
        out_day = start + 15
        for share in rng.dirichlet(np.ones(int(rng.integers(1, 4)))) * total * 0.92:
            b.t(out_day + rng.uniform(0, 4), a, b.ext("DST"), share)
    for _ in range(sc(18)):                                    # layering through a chain of accounts
        gid = f"G{b.n}"
        chain = [sus_acc("layering", aged=rng.random() < 0.2, group=gid) for _ in range(int(rng.integers(3, 5)))]
        amt = rng.uniform(400_000, 1_500_000)
        d = rng.uniform(WINDOW_START + 2, 82)
        b.t(d, b.ext("SRC"), chain[0], amt)
        for i in range(len(chain)):
            d += rng.uniform(0.05, 0.4)
            amt *= rng.uniform(0.97, 0.995)
            b.t(d, chain[i], chain[i + 1] if i + 1 < len(chain) else b.ext("SNK"), amt)
    for _ in range(sc(8)):                                     # circular flows
        gid = f"G{b.n}"
        ring = [sus_acc("circular", aged=rng.random() < 0.3, group=gid) for _ in range(int(rng.integers(3, 5)))]
        d = rng.uniform(WINDOW_START + 2, 80)
        amt = rng.uniform(80_000, 300_000)
        for _round in range(int(rng.integers(2, 4))):
            for i in range(len(ring)):
                d += rng.uniform(0.2, 1.0)
                amt *= rng.uniform(0.98, 0.995)
                b.t(d, ring[i], ring[(i + 1) % len(ring)], amt)
    for _ in range(sc(14)):                                    # mule: many senders, one beneficiary
        m = sus_acc("mule", aged=rng.random() < 0.2)
        start = rng.uniform(WINDOW_START + 2, 80)
        total = 0.0
        for s in rng.choice(victims, size=int(rng.integers(10, 25)), replace=False):
            amt = rng.uniform(2000, 9000)
            total += amt
            b.t(start + rng.uniform(0, 9), s, m, amt)
        b.t(start + 10.5 + rng.uniform(0, 2), m, b.ext("BEN"), total * 0.93)
    for _ in range(sc(16)):                                    # dormant account suddenly active (held out of model training)
        a = b.acc("private", age=int(rng.integers(24, 60)), label="suspicious", typology="dormant")
        for _ in range(int(rng.integers(0, 3))):
            b.t(rng.uniform(0, WINDOW_START), a, b.ext("MER"), rng.uniform(50, 400))
        d = rng.uniform(WINDOW_START + 3, 82)
        tot = 0.0
        for _ in range(int(rng.integers(2, 4))):
            amt = rng.uniform(200_000, 900_000)
            tot += amt
            b.t(d + rng.uniform(0, 3), b.ext("SRC"), a, amt)
        for p in rng.dirichlet(np.ones(int(rng.integers(2, 4)))) * tot * 0.95:
            b.t(d + 3 + rng.uniform(0, 3), a, b.ext("DST"), p, "transfer")

    cust = pd.DataFrame(b.cust)
    txn = pd.DataFrame(b.txn).sort_values("day").reset_index(drop=True)
    txn.insert(0, "txn_id", range(len(txn)))
    return cust, txn


def to_sqlite(cust: pd.DataFrame, txn: pd.DataFrame) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:", check_same_thread=False)
    cust.drop(columns=["label", "typology", "group"]).to_sql("customers", con, index=False)       # ground truth is not visible to agents
    txn.to_sql("transactions", con, index=False)
    con.execute("CREATE INDEX idx_src ON transactions(src, day)")
    con.execute("CREATE INDEX idx_dst ON transactions(dst, day)")
    return con
