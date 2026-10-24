"""CrossExam investigation workflow (LangGraph).

supervisor -> [history | graph | profile | policy | precedent sub-agents, as needed] ->
prosecutor -> defender -> referee -> case writer. A human analyst always makes the final decision."""
import math
import re
from typing import TypedDict

from langgraph.graph import END, StateGraph

from .audit import AuditLog
from .features import MoneyGraph, account_stats
from .memory import CaseMemory
from .policy_docs import PolicySearch

CASH_TYPES = {"restaurant", "kiosk", "hair_salon"}
ESCALATE_NET, CLOSE_NET, PROSECUTION_MIN = 0.25, -0.15, 0.35


class State(TypedDict, total=False):
    case_id: str
    acc: str
    score: float
    rules: list
    plan: list
    evidence: list
    facts: dict
    prosecution: list
    defence: list
    verdict: dict
    note: str
    mode: str


def fmt(x):
    return f"{x:,.0f}"


class Investigator:
    def __init__(self, data: dict, memory: CaseMemory | None = None, audit: AuditLog | None = None):
        self.d = data
        self.con, self.graph = data["con"], data["graph"]
        self.memory = memory if memory is not None else CaseMemory()
        self.audit = audit or AuditLog()
        self.policy = PolicySearch()
        self.cases = {}
        self.app = self._build()

    # ---------- helpers ----------
    def _ev(self, s, kind, text, **values):
        ev = s["evidence"]
        eid = f"E{len(ev) + 1}"
        ev.append({"id": eid, "kind": kind, "text": text, "values": values})
        return eid

    def _log(self, s, actor, action, payload):
        self.audit.add(s["case_id"], actor, action, payload)

    # ---------- nodes ----------
    def supervisor(self, s: State) -> State:
        st = self.d["stats"].get(s["acc"]) or account_stats(self.con, s["acc"])
        plan = ["history"]
        if st["n_cp_in"] >= 3 or st["sum_in"] >= 100_000 or self.graph.cycle_of(s["acc"]):
            plan.append("graph")
        plan += ["profile", "policy"]
        if len(self.memory) and s.get("mode", "full") == "full":
            plan.append("precedent")
        self._log(s, "supervisor", "plan", {"alert_rules": s["rules"], "score": round(s["score"], 3), "delegates": plan})
        return {"plan": plan, "evidence": [], "facts": {"stats": st}}

    def dispatch(self, s: State) -> str:
        return s["plan"][0] if s["plan"] else "prosecutor"

    def history(self, s: State) -> State:
        st, f = s["facts"]["stats"], dict(s["facts"])
        refs = st["txn_ids_in_window"][:6]
        self._ev(s, "history", f"In the last 30 days the account received {fmt(st['sum_in'])} SEK in {st['n_in']} inflows from {st['n_cp_in']} counterparties and sent {fmt(st['sum_out'])} SEK to {st['n_cp_out']}.",
                 sum_in=st["sum_in"], n_in=st["n_in"], n_cp_in=st["n_cp_in"], sum_out=st["sum_out"], n_cp_out=st["n_cp_out"], txn_refs=refs)
        if st["n_near"]:
            self._ev(s, "history", f"{st['n_near']} inflows were between 9,000 and 9,999 SEK, which is {st['share_near']*100:.0f}% of all inflows.",
                     n_near=st["n_near"], share_near=st["share_near"])
        self._ev(s, "history", f"{st['passthrough']*100:.0f}% of the money received left the account within 72 hours of an inflow, and {st['out_conc']*100:.0f}% of outgoing money went to one counterparty.",
                 passthrough=st["passthrough"], out_conc=st["out_conc"])
        self._ev(s, "history", f"In the previous 60 days the account had {st['prior_n_in']} inflows averaging {fmt(st['prior_monthly_in'])} SEK per month, of which {st['prior_n_near']} were between 9,000 and 9,999 SEK.",
                 prior_n_in=st["prior_n_in"], prior_monthly_in=st["prior_monthly_in"], prior_n_near=st["prior_n_near"], prior_share_near=st["prior_share_near"],
                 vol_ratio_prior=st["vol_ratio_prior"])
        for k in ("n_txn", "vol_vs_expected", "share_near", "n_near", "n_cp_in", "n_cp_out", "out_conc", "passthrough", "vol_ratio_prior",
                  "prior_n_near", "prior_share_near", "prior_n_in", "sum_in"):
            f[k] = st[k]
        self._log(s, "history_agent", "sql_summary", {"evidence": [e["id"] for e in s["evidence"]]})
        return {"plan": s["plan"][1:], "facts": f}

    def graph_agent(self, s: State) -> State:
        f, acc = dict(s["facts"]), s["acc"]
        cyc = self.graph.cycle_of(acc)
        ch = self.graph.chain(acc)
        f["cycle_flag"], f["chain_len"] = (1.0 if cyc else 0.0), ch["length"]
        f["cycle_members"] = sorted(cyc[0]) if cyc else []
        if cyc:
            self._ev(s, "graph", f"Money moved around a closed loop of {len(cyc[0])} accounts ({', '.join(sorted(cyc[0]))}) within 7 days.", members=sorted(cyc[0]))
        if ch["length"] >= 3:
            self._ev(s, "graph", f"The account sits in a chain of {ch['length']} accounts where almost the full amount was passed on within 36 hours.", chain_len=ch["length"], txn_refs=ch["txn_ids"])
        self._log(s, "graph_agent", "money_flow", {"cycle": bool(cyc), "chain_len": ch["length"]})
        return {"plan": s["plan"][1:], "facts": f}

    def profile(self, s: State) -> State:
        f = dict(s["facts"])
        p = f["stats"]["profile"]
        f.update(segment=p["segment"], business_type=p["business_type"], documented_events=p["documented_events"], family_ids=p["family_ids"],
                 account_age=p["account_age_months"], expected=p["expected_monthly_volume"])
        self._ev(s, "profile", f"Customer profile: {p['segment']} account, business type '{p['business_type']}', {p['account_age_months']} months old, expected monthly volume {fmt(p['expected_monthly_volume'])} SEK, documented events: {p['documented_events'] or 'none'}.",
                 segment=p["segment"], business_type=p["business_type"], age=p["account_age_months"], expected=p["expected_monthly_volume"])
        fam_doc = False
        if f.get("cycle_members"):
            members = f["cycle_members"]
            profs = {m: (self.d["stats"].get(m) or account_stats(self.con, m))["profile"] for m in members}
            fam_doc = all(set(x for x in members if x != m) <= set(filter(None, profs[m]["family_ids"].split(","))) for m in members)
            self._ev(s, "profile", f"The relationship between the accounts in the loop is {'documented as family' if fam_doc else 'not documented'}.", documented_family=fam_doc)
        f["ring_family_documented"] = fam_doc
        self._log(s, "profile_agent", "lookup", {"documented_events": p["documented_events"], "family_loop_documented": fam_doc})
        return {"plan": s["plan"][1:], "facts": f}

    def policy_agent(self, s: State) -> State:
        self._log(s, "policy_agent", "ready", {"snippets": list(self.policy.ids)})
        return {"plan": s["plan"][1:]}

    def precedent(self, s: State) -> State:
        f = dict(s["facts"])
        near = self.memory.nearest(f)
        legit = sum(1 for _, o, _ in near if o == "legitimate")
        sus = len(near) - legit
        f["precedent"] = {"n": len(near), "legit": legit, "suspicious": sus}
        self._ev(s, "precedent", f"Of the {len(near)} most similar closed cases, {legit} were closed as legitimate and {sus} were escalated.", n=len(near), legit=legit, suspicious=sus,
                 cases=[c for c, _, _ in near])
        self._log(s, "precedent_agent", "retrieve", {"cases": [c for c, _, _ in near]})
        return {"plan": s["plan"][1:], "facts": f}

    # ---------- arguments ----------
    def _arg(self, s, kind, claim, w, evs, ptype):
        pid = f"{'PA' if ptype == 'pro' else 'DA'}{len(s['prosecution' if ptype == 'pro' else 'defence']) + 1}"
        return {"id": pid, "claim": claim, "weight": w, "evidence": evs, "policy": self.policy.top(claim), "kind": kind}

    def _eid(self, s, kind, **match):
        for e in s["evidence"]:
            if e["kind"] == kind and all(k in e["values"] for k in match):
                return e["id"]
        return None

    def prosecutor(self, s: State) -> State:
        f, args = s["facts"], []
        add = lambda kind, claim, w, ev: args.append({"id": f"PA{len(args) + 1}", "claim": claim, "weight": w, "evidence": [e for e in ev if e],
                                                      "policy": self.policy.top(claim), "kind": kind})
        if f["n_near"] >= 5 and f["share_near"] >= 0.5:
            add("structuring", "Repeated inflows just under the reporting threshold.", 0.40, [self._eid(s, "history", n_near=1)])
        if f.get("chain_len", 1) >= 3:
            add("layering", "The money passed through a chain of accounts almost unchanged.", 0.40, [self._eid(s, "graph", chain_len=1)])
        if f["passthrough"] >= 0.8 and f["sum_in"] >= 50_000:
            add("passthrough", "Most of the money left the account within 72 hours of arriving.", 0.25, [self._eid(s, "history", passthrough=1)])
        if f.get("cycle_flag"):
            add("circular", "Money returned to its source through a short loop of accounts.", 0.35, [self._eid(s, "graph", members=1)])
        if f["n_cp_in"] >= 8 and f["out_conc"] >= 0.8 and f["passthrough"] >= 0.6:
            add("mule", "Many senders paid in and almost everything went on to one recipient.", 0.40, [self._eid(s, "history", n_in=1), self._eid(s, "history", passthrough=1)])
        if f["vol_ratio_prior"] >= 8 and f["sum_in"] >= 100_000:
            add("spike", "Inflows jumped far above the account's own history.", 0.30, [self._eid(s, "history", prior_n_in=1)])
            if f.get("account_age", 0) >= 24 and f["prior_n_in"] <= 3:
                add("dormant", "A long-held account with almost no earlier activity suddenly moved large sums.", 0.15, [self._eid(s, "history", prior_n_in=1), self._eid(s, "profile", age=1)])
        if f.get("account_age", 99) <= 6 and f["sum_in"] >= 5 * max(1, f.get("expected", 1)):
            add("new_account", "A very new account is handling many times its expected volume.", 0.15, [self._eid(s, "profile", age=1)])
        pr = f.get("precedent")
        if pr and pr["n"] >= 5 and pr["suspicious"] / pr["n"] >= 0.7:
            add("precedent", "Most similar earlier cases were escalated.", 0.25, [self._eid(s, "precedent", n=1)])
        self._log(s, "prosecutor", "arguments", [{"id": a["id"], "kind": a["kind"], "w": a["weight"], "evidence": a["evidence"]} for a in args])
        return {"prosecution": args}

    def defender(self, s: State) -> State:
        if s.get("mode") == "prosecutor_only":
            return {"defence": []}
        f, args = s["facts"], []
        add = lambda kind, claim, w, ev: args.append({"id": f"DA{len(args) + 1}", "claim": claim, "weight": w, "evidence": [e for e in ev if e],
                                                      "policy": self.policy.top(claim), "kind": kind})
        prof = self._eid(s, "profile", segment=1)
        if f["prior_n_near"] >= 5 and f["prior_share_near"] >= 0.4:
            add("consistent_history", "The same deposit pattern appears throughout the previous two months.", 0.45, [self._eid(s, "history", prior_n_in=1)])
            if f.get("business_type") in CASH_TYPES and f["vol_vs_expected"] <= 1.5:
                add("cash_business", "A cash-based business whose volume matches its stated activity.", 0.25, [prof])
        if f.get("ring_family_documented"):
            add("family_loop", "The accounts in the loop are documented as family members.", 0.40, [self._eid(s, "profile", documented_family=1)])
        if "property_sale" in (f.get("documented_events") or "") and f["sum_in"] >= 1_000_000:
            add("documented_event", "A large inflow from a documented property sale.", 0.40, [prof])
        if f.get("business_type") == "online_seller" and f["prior_n_in"] >= 20 and f["vol_ratio_prior"] <= 2.5:
            add("marketplace", "An online seller with a stable history of many small buyers and regular payouts.", 0.40, [prof, self._eid(s, "history", prior_n_in=1)])
        elif 0.5 <= f["vol_ratio_prior"] <= 2.0 and f["prior_n_in"] >= 10:
            add("stable_volume", "Volume is in line with the account's own history.", 0.20, [self._eid(s, "history", prior_n_in=1)])
        pr = f.get("precedent")
        if pr and pr["n"] >= 5 and pr["legit"] / pr["n"] >= 0.7:
            add("precedent", "Most similar earlier cases were closed as legitimate.", 0.25, [self._eid(s, "precedent", n=1)])
        self._log(s, "defender", "arguments", [{"id": a["id"], "kind": a["kind"], "w": a["weight"], "evidence": a["evidence"]} for a in args])
        return {"defence": args}

    def referee(self, s: State) -> State:
        noisy = lambda ws: 1 - math.prod(1 - w for w in ws)
        p = noisy([a["weight"] for a in s["prosecution"]])
        d = noisy([a["weight"] for a in s["defence"]])
        net = p - d
        if s.get("mode") == "prosecutor_only":
            rec = "escalate" if p >= PROSECUTION_MIN else "close_suggested"
        elif net >= ESCALATE_NET and p >= PROSECUTION_MIN:
            rec = "escalate"
        elif net <= CLOSE_NET:
            rec = "close_suggested"
        else:
            rec = "analyst_review"
        v = {"recommendation": rec, "prosecution_score": round(p, 3), "defence_score": round(d, 3), "net": round(net, 3)}
        self._log(s, "referee", "verdict", v)
        return {"verdict": v}

    def case_writer(self, s: State) -> State:
        ev = {e["id"]: e for e in s["evidence"]}
        lines = [f"Case {s['case_id']}: alert on account {s['acc']} (model score {s['score']:.2f}; rules: {'; '.join(s['rules']) or 'none'})", ""]
        cite = lambda ids: " ".join(f"[{i}]" for i in ids)
        lines.append("Case for suspicion:")
        lines += [f"- {a['claim']} (weight {a['weight']:.2f}, guidance {a['policy']}) {cite(a['evidence'])}" for a in s["prosecution"]] or ["- No warning signs found."]
        lines.append("Case for a legitimate explanation:")
        lines += [f"- {a['claim']} (weight {a['weight']:.2f}, guidance {a['policy']}) {cite(a['evidence'])}" for a in s["defence"]] or ["- No supporting explanation found."]
        v = s["verdict"]
        lines += ["", f"Referee: suspicion {v['prosecution_score']:.2f}, explanation {v['defence_score']:.2f}, net {v['net']:+.2f}. Recommendation: {v['recommendation'].replace('_', ' ')}.",
                  "Evidence:"] + [f"- {e['id']}: {e['text']}" for e in s["evidence"]] + ["", "Status: awaiting analyst decision. This system does not close or escalate cases by itself."]
        note = "\n".join(lines)
        self._log(s, "case_writer", "note", {"chars": len(note)})
        return {"note": note}

    def _build(self):
        g = StateGraph(State)
        for name, fn in (("supervisor", self.supervisor), ("history", self.history), ("graph", self.graph_agent), ("profile", self.profile),
                         ("policy", self.policy_agent), ("precedent", self.precedent), ("prosecutor", self.prosecutor),
                         ("defender", self.defender), ("referee", self.referee), ("writer", self.case_writer)):
            g.add_node(name, fn)
        g.set_entry_point("supervisor")
        targets = {n: n for n in ("history", "graph", "profile", "policy", "precedent", "prosecutor")}
        for n in ("supervisor", "history", "graph", "profile", "policy", "precedent"):
            g.add_conditional_edges(n, self.dispatch, targets)
        g.add_edge("prosecutor", "defender")
        g.add_edge("defender", "referee")
        g.add_edge("referee", "writer")
        g.add_edge("writer", END)
        return g.compile()

    # ---------- public API ----------
    def investigate(self, acc: str, score: float, rules: list, mode: str = "full") -> dict:
        case_id = f"CASE-{acc}"
        out = self.app.invoke({"case_id": case_id, "acc": acc, "score": score, "rules": rules, "mode": mode, "evidence": []})
        res = {"case_id": case_id, "acc": acc, "verdict": out["verdict"], "note": out["note"], "evidence": out["evidence"],
               "prosecution": out["prosecution"], "defence": out["defence"], "facts": out["facts"], "status": "awaiting_analyst"}
        self.cases[case_id] = res
        return res

    def decide(self, case_id: str, analyst: str, decision: str, reason: str = "") -> dict:
        if decision not in ("escalate", "close"):
            raise ValueError("decision must be 'escalate' or 'close'")
        c = self.cases[case_id]
        c["status"] = "escalated" if decision == "escalate" else "closed"
        c["analyst"] = {"user": analyst, "decision": decision, "reason": reason}
        self.audit.add(case_id, analyst, "analyst_decision", {"decision": decision, "reason": reason, "system_recommended": c["verdict"]["recommendation"]})
        self.memory.add(case_id, {k: c["facts"].get(k, 0.0) for k in ("n_txn", "vol_vs_expected", "share_near", "n_near", "n_cp_in", "n_cp_out", "out_conc", "passthrough", "vol_ratio_prior", "chain_len", "cycle_flag")},
                        "suspicious" if decision == "escalate" else "legitimate")
        return c


NUM = re.compile(r"\d[\d,]*\.?\d*")


def check_note(note: str, evidence: list) -> dict:
    """Every [E#] tag must exist and every number in the evidence lines must come from the evidence text."""
    ids = {e["id"] for e in evidence}
    tags = set(re.findall(r"\[(E\d+)\]", note))
    ev_nums = set(n.rstrip(".,") for e in evidence for n in NUM.findall(e["text"]))
    body = note.split("Evidence:")[1] if "Evidence:" in note else ""
    quoted = set(n.rstrip(".,") for line in body.splitlines() if line.startswith("- E") for n in NUM.findall(line.split(":", 1)[1]))
    return {"unknown_tags": sorted(tags - ids), "unsupported_numbers": sorted(quoted - ev_nums), "ok": not (tags - ids) and not (quoted - ev_nums)}
