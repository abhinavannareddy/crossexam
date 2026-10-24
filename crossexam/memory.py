"""Precedent memory: closed cases with their features and the analyst's outcome."""
import numpy as np

KEYS = ["n_txn", "vol_vs_expected", "share_near", "n_near", "n_cp_in", "n_cp_out", "out_conc", "passthrough", "vol_ratio_prior", "chain_len", "cycle_flag"]
SCALE = np.array([30, 5, 1, 10, 10, 5, 1, 1, 8, 4, 1], float)


def vector(ev: dict) -> np.ndarray:
    return np.array([ev.get(k, 0.0) for k in KEYS], float) / SCALE


class CaseMemory:
    def __init__(self):
        self.vecs, self.outcomes, self.ids = [], [], []

    def add(self, case_id, ev: dict, outcome: str):
        self.vecs.append(vector(ev))
        self.outcomes.append(outcome)
        self.ids.append(case_id)

    def __len__(self):
        return len(self.ids)

    def nearest(self, ev: dict, k: int = 7):
        if not self.ids:
            return []
        v = vector(ev)
        d = np.linalg.norm(np.array(self.vecs) - v, axis=1)
        order = np.argsort(d)[:k]
        return [(self.ids[i], self.outcomes[i], float(d[i])) for i in order]
