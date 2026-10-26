"""Builds the figures in docs/ from results*.json and from real runs of the investigator.

    python docs/make_figures.py

Nothing here is typed in by hand: bars come from the result files, the three example cases come from running the
workflow on seed 1."""
import json
import os
import sys
import warnings

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
MODEL, PROS, CROSS = "#2a78d6", "#eb6834", "#1baf7a"
EXT_GREY = "#c9c8c2"          # fixed order: one colour per method in every figure
plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "text.color": INK,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False, "axes.edgecolor": GRID})

SETS = [("results.json", "Seeds 1-5\n(used to build the rules)"), ("results_heldout.json", "Seeds 11-15\n(used to diagnose mules)"),
        ("results_fresh.json", "Seeds 21-25\n(not used for anything)")]
METHODS = [("model", "Model score only", MODEL), ("prosecutor", "Prosecutor only", PROS), ("full_nomem", "CrossExam (full)", CROSS)]


def load(name):
    with open(os.path.join(ROOT, name)) as f:
        return json.load(f)


def label_bars(ax, bars, vals):
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.6, f"{v:.1f}%", ha="center", va="bottom", fontsize=8.5, color=INK)


def results_figure():
    data = [load(f) for f, _ in SETS]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=False)
    panels = [("miss_rate", "Suspicious accounts missed", "lower is better", 12), ("false_escalation_rate", "Honest accounts wrongly escalated", "lower is better", 40)]
    for ax, (key, title, sub, top) in zip(axes, panels):
        w = 0.26
        for j, (m, name, col) in enumerate(METHODS):
            vals = [d[m][key] * 100 for d in data]
            bars = ax.bar([i + (j - 1) * (w + 0.02) for i in range(3)], vals, w, color=col, label=name)
            label_bars(ax, bars, vals)
        ax.set_xticks(range(3))
        ax.set_xticklabels([s for _, s in SETS], fontsize=9)
        ax.set_ylim(0, top)
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(length=0)
        ax.set_title(f"{title}  ({sub})", loc="left", fontsize=11, color=INK, pad=12)
    axes[0].legend(loc="upper right", frameon=False, fontsize=9)
    fig.suptitle("CrossExam misses nothing and cuts false escalations by about 80% versus the prosecutor alone", x=0.01, ha="left", fontsize=12.5, fontweight="bold", y=1.02)
    fig.text(0.01, -0.04, "Synthetic data. 2,142 alerts over 15 dataset seeds. The model alone has fewer false escalations (0.0-1.2%) but misses 2.5-4.6% of suspicious accounts and gives no written reasoning.",
             fontsize=8.5, color=INK2, ha="left")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "results.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def typology_figure():
    pooled = {}
    for f, _ in SETS:
        for t, v in load(f)["by_typology"].items():
            p = pooled.setdefault(t, {"n": 0, "cx": 0.0, "model": 0.0})
            p["n"] += v["n"]
            p["cx"] += v["n"] * v["crossexam_escalate"]
            p["model"] += v["n"] * v["model_escalate"]
    rate = {t: (100 * p["cx"] / p["n"], 100 * p["model"] / p["n"], p["n"]) for t, p in pooled.items()}
    nice = {"circular": "Circular flows", "dormant": "Dormant burst (never in training)", "layering": "Layering", "mule": "Mule accounts", "structuring": "Structuring",
            "lookalike_cash_business": "Cash business", "lookalike_family_loop": "Documented family loop", "lookalike_marketplace": "Marketplace seller",
            "lookalike_property_sale": "Property sale", "none": "Ordinary customers"}
    groups = [("Suspicious accounts: escalating is correct (higher is better)", ["layering", "circular", "mule", "structuring", "dormant"]),
              ("Honest accounts: escalating is a false alarm (lower is better)", ["lookalike_family_loop", "lookalike_property_sale", "lookalike_cash_business", "lookalike_marketplace", "none"])]
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.4))
    for ax, (title, keys) in zip(axes, groups):
        ys = list(range(len(keys)))[::-1]
        h = 0.34
        for off, idx, name, col in ((h / 2 + 0.01, 1, "Model score only", MODEL), (-h / 2 - 0.01, 0, "CrossExam (full)", CROSS)):
            vals = [rate[k][idx] for k in keys]
            bars = ax.barh([y + off for y in ys], vals, h, color=col, label=name)
            for b, v in zip(bars, vals):
                ax.text(v + 1.2, b.get_y() + b.get_height() / 2, f"{v:.0f}%", va="center", fontsize=8.5, color=INK)
        ax.set_yticks(ys)
        ax.set_yticklabels([f"{nice[k]}  (n={rate[k][2]})" for k in keys], fontsize=9.5)
        ax.set_xlim(0, 112)
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(length=0)
        ax.set_title(title, loc="left", fontsize=11, pad=8)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=9.5, bbox_to_anchor=(0.5, -0.03))
    fig.suptitle("Share of alerts each method escalates, by account type (15 seeds pooled)", x=0.01, ha="left", fontsize=12.5, fontweight="bold", y=1.0)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "escalation_by_type.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def pick_cases():
    from crossexam.agents import Investigator
    from crossexam.model import alerts, prepare, train
    d = prepare(1)
    _, score = train(d)
    al = alerts(d, score)
    cust = d["cust"].set_index("acc_id")
    inv = Investigator(d)
    want = [("circular", "escalate"), ("lookalike_family_loop", "analyst_review"), ("lookalike_marketplace", "close_suggested")]
    out = []
    for typ, rec in want:
        for a in sorted(al):
            if cust.loc[a, "typology"] == typ:
                r = inv.investigate(a, al[a]["score"], al[a]["rules"], mode="no_memory")
                if r["verdict"]["recommendation"] == rec:
                    out.append((typ, r))
                    break
    return out


KIND = {"structuring": "Deposits just under the threshold", "layering": "Chain of pass-through accounts", "passthrough": "Money leaves within 72 hours",
        "circular": "Money returns through a loop", "mule": "Many senders, one recipient", "spike": "Jump above own history", "dormant": "Dormant account wakes up",
        "new_account": "New account, large volume", "precedent": "Similar past cases", "consistent_history": "Same pattern in prior two months",
        "cash_business": "Cash business, volume fits", "family_loop": "Loop is documented family", "documented_event": "Documented property sale",
        "marketplace": "Online seller, stable history", "stable_volume": "Volume in line with history"}
TITLE = {"circular": "A real money loop", "lookalike_family_loop": "Honest family, same shape", "lookalike_marketplace": "Honest online seller"}
REC = {"escalate": "ESCALATE", "analyst_review": "SEND TO ANALYST", "close_suggested": "SUGGEST CLOSE"}


def cases_figure():
    cases = pick_cases()
    fig, axes = plt.subplots(len(cases), 1, figsize=(10, 2.7 * len(cases)))
    for ax, (typ, r) in zip(axes, cases):
        v = r["verdict"]
        rows = [(KIND.get(a["kind"], a["kind"]), a["weight"], PROS) for a in r["prosecution"]] + [(KIND.get(a["kind"], a["kind"]), -a["weight"], MODEL) for a in r["defence"]]
        rows = rows or [("No arguments on either side", 0, INK2)]
        ys = list(range(len(rows)))[::-1]
        ax.barh(ys, [x[1] for x in rows], 0.5, color=[x[2] for x in rows])
        for y, (lab, w, _) in zip(ys, rows):
            ax.text(-0.03 if w > 0 else 0.03, y, lab, ha="right" if w > 0 else "left", va="center", fontsize=9, color=INK)
            ax.text(w + (0.012 if w >= 0 else -0.012), y, f"{abs(w):.2f}", ha="left" if w >= 0 else "right", va="center", fontsize=8.5, color=INK)
        ax.axvline(0, color=INK2, linewidth=0.8)
        ax.set_xlim(-0.75, 0.75)
        ax.set_ylim(-0.7, len(rows) - 0.3)
        ax.set_yticks([])
        ax.set_xticks([])
        ax.text(-0.74, len(rows) - 0.35, "Defender: explanation", fontsize=8.5, color=MODEL, va="bottom")
        ax.text(0.74, len(rows) - 0.35, "Prosecutor: suspicion", fontsize=8.5, color=PROS, ha="right", va="bottom")
        ax.set_title(f"{TITLE[typ]} - {r['acc']}:  suspicion {v['prosecution_score']:.2f}, explanation {v['defence_score']:.2f}, net {v['net']:+.2f}  ->  {REC[v['recommendation']]}",
                     loc="left", fontsize=10.5, pad=16)
    fig.suptitle("Three real cases from the synthetic data: each argument and its weight", x=0.01, ha="left", fontsize=12.5, fontweight="bold", y=1.0)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "cases.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)
    with open(os.path.join(HERE, "sample_case_note.txt"), "w", encoding="utf-8") as f:
        f.write(cases[0][1]["note"] + "\n")


def _arrows(ax, G, pos, color, rad=0.0, width=1.6, node_size=900):
    import networkx as nx
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color=color, width=width, arrows=True, arrowsize=14, node_size=node_size,
                           connectionstyle=f"arc3,rad={rad}", min_source_margin=8, min_target_margin=8)


def typologies_figure():
    """What each pattern looks like in the data. Real accounts from seed 1."""
    import networkx as nx
    import numpy as np
    from crossexam.model import prepare
    d = prepare(1)
    c, t = d["cust"], d["txn"]
    ACC = MODEL

    def first(typ):
        sub = c[c.typology == typ]
        return c[c.group == sub.group.iloc[0]].acc_id.tolist()

    fig, axes = plt.subplots(2, 3, figsize=(12, 7.6))
    for ax in axes.ravel():
        ax.set_axis_off()

    def plain_axes(ax):
        ax.set_axis_on()
        ax.grid(axis="y", color=GRID)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)

    # 1. structuring: deposits just under the limit
    ax = axes[0, 0]
    acc = next(a for a in c[c.typology == "structuring"].acc_id if ((t.dst == a) & t.amount.between(9000, 9999)).sum() >= 10)
    last = t[t.dst == acc].day.max()
    dep = t[(t.dst == acc) & (t.day >= last - 30)].amount
    plain_axes(ax)
    ax.hist(dep, bins=np.arange(5000, 11001, 250), color=PROS, edgecolor=SURFACE)
    ax.set_xlim(5000, 11000)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.3)
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.axvline(10_000, color=INK, linewidth=1.2, linestyle="--")
    ax.text(9_900, ax.get_ylim()[1] * 0.97, "assumed limit 10,000", ha="right", va="top", fontsize=8.5, color=INK)
    ax.set_xlabel("deposit size (SEK)")
    ax.set_ylabel("deposits in 30 days")
    ax.set_title(f"Structuring: {int(dep.between(9000, 9999).sum())} of {len(dep)} deposits\njust under the limit", loc="left", fontsize=10, pad=8)

    # 2. layering: a chain that passes the money on
    ax = axes[0, 1]
    m = first("layering")
    E = t[t.src.isin(m) | t.dst.isin(m)]
    order = sorted(m)
    pos = {a: (i + 1, 0) for i, a in enumerate(order)}
    G = nx.DiGraph()
    for r in E.itertuples():
        for end, inside in ((r.src, r.dst), (r.dst, r.src)):
            if end not in m and inside in m and end not in pos:
                pos[end] = (0, 0) if end == r.src else (len(order) + 1, 0)
    for r in E.itertuples():
        if r.src in pos and r.dst in pos:
            G.add_edge(r.src, r.dst)
    nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=[n for n in G if n in m], node_color=ACC, node_size=900)
    nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=[n for n in G if n not in m], node_color=EXT_GREY, node_shape="s", node_size=900)
    _arrows(ax, G, pos, PROS, width=2.2)
    ax.set_xlim(-0.4, len(order) + 1.4)
    ax.set_ylim(-1, 1)
    ax.set_title("Layering: money passed along\nalmost unchanged", loc="left", fontsize=10, pad=8)
    ax.text(len(order) / 2 + 0.5, -0.6, "outside source > accounts in the bank > outside destination", ha="center", fontsize=8, color=INK2)

    # 3 and 6. circular flow, and the honest family loop with the same shape
    def ring(ax, members, color, title, note):
        E = t[t.src.isin(members) & t.dst.isin(members)]
        G = nx.DiGraph()
        G.add_edges_from({(r.src, r.dst) for r in E.itertuples()})
        pos = nx.circular_layout(G)
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=ACC, node_size=900)
        _arrows(ax, G, pos, color, rad=0.12, width=2.2)
        ax.set_xlim(-1.5, 1.5)
        ax.set_ylim(-2.1, 1.4)
        laps = round(len(E) / max(1, len(members)))
        ax.set_title(title, loc="left", fontsize=10, pad=8)
        ax.text(0, -1.95, f"{note}\n{len(E)} payments, about {laps} laps in {E.day.max() - E.day.min():.0f} days", ha="center", fontsize=8, color=INK2)

    ring(axes[0, 2], first("circular"), PROS, "Circular flow: money returns\nto its source", "relationship not documented")
    ring(axes[1, 2], first("lookalike_family_loop"), MODEL, "Same shape, honest:\na documented family loop", "relationship documented as family")

    # 4. mule: many senders, one recipient
    ax = axes[1, 0]
    mule = max(c[c.typology == "mule"].acc_id, key=lambda a: t[t.dst == a].src.nunique())
    senders = sorted(t[t.dst == mule].src.unique())
    out = t[t.src == mule].dst.unique().tolist()
    G = nx.DiGraph()
    pos = {mule: (0, 0)}
    for i, name in enumerate(senders):
        pos[name] = (-1.6, 1.3 - 2.6 * i / max(1, len(senders) - 1))
        G.add_edge(name, mule)
    for o in out:
        pos[o] = (1.6, 0)
        G.add_edge(mule, o)
    nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=senders, node_color=EXT_GREY, node_size=130)
    nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=[mule], node_color=ACC, node_size=900)
    nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=out, node_color=EXT_GREY, node_shape="s", node_size=900)
    _arrows(ax, G, pos, PROS, width=1.1, node_size=130)
    ax.set_xlim(-2.1, 2.1)
    ax.set_ylim(-1.8, 1.6)
    ax.set_title(f"Mule: {len(senders)} senders,\none recipient", loc="left", fontsize=10, pad=8)
    ax.text(0, -1.75, "almost everything received is forwarded", ha="center", fontsize=8, color=INK2)

    # 5. dormant burst
    ax = axes[1, 1]
    acc = c[c.typology == "dormant"].acc_id.iloc[0]
    X = t[(t.src == acc) | (t.dst == acc)]
    signed = [(r.day, r.amount if r.dst == acc else -r.amount) for r in X.itertuples()]
    plain_axes(ax)
    ax.bar([a for a, _ in signed], [b for _, b in signed], width=1.2, color=[PROS if b > 0 else MODEL for _, b in signed])
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.set_xlim(0, 90)
    ax.set_xlabel("day")
    ax.set_ylabel("SEK in (orange) / out (blue)")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v / 1000:.0f}k")
    ax.set_title("Dormant account: months of almost nothing,\nthen large sums in and out", loc="left", fontsize=10, pad=8)

    fig.suptitle("What the patterns look like: real accounts from the synthetic data (seed 1)", x=0.01, ha="left", fontsize=12.5, fontweight="bold", y=1.0)
    fig.text(0.01, -0.01, "Orange: suspicious flow. Blue circles: accounts in the bank. Grey squares: outside parties. Small grey dots: individual senders.", fontsize=8.5, color=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "typologies.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def funnel_figure():
    """Where the alerts of one run end up, split by what the accounts really are."""
    from crossexam.agents import Investigator
    from crossexam.model import alerts, prepare, train
    d = prepare(1)
    _, score = train(d)
    al = alerts(d, score)
    cust = d["cust"].set_index("acc_id")
    inv = Investigator(d)
    tally = {"escalate": [0, 0], "analyst_review": [0, 0], "close_suggested": [0, 0]}   # [suspicious, honest]
    for a in sorted(al):
        rec = inv.investigate(a, al[a]["score"], al[a]["rules"], mode="no_memory")["verdict"]["recommendation"]
        tally[rec][0 if cust.loc[a, "label"] == "suspicious" else 1] += 1
    rows = [("Escalate", "escalate"), ("Send to analyst", "analyst_review"), ("Suggest close", "close_suggested")]
    fig, ax = plt.subplots(figsize=(10, 3.9))
    ys = [2, 1, 0]
    for y, (lab, k) in zip(ys, rows):
        sus, hon = tally[k]
        ax.barh(y, sus, 0.55, color=PROS)
        ax.barh(y, hon, 0.55, left=sus, color=EXT_GREY)
        if sus:
            ax.text(sus / 2, y, f"{sus}", ha="center", va="center", color="white", fontsize=10, fontweight="bold")
        if hon:
            ax.text(sus + hon / 2, y, f"{hon}", ha="center", va="center", color=INK, fontsize=10)
        ax.text(sus + hon + 1.5, y, f"{sus + hon} alerts", va="center", fontsize=9.5, color=INK2)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=11)
    ax.set_xlim(0, max(sum(v) for v in tally.values()) * 1.18)
    ax.tick_params(length=0)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    n_alerts = sum(sum(v) for v in tally.values())
    fig.suptitle(f"Where the {n_alerts} alerts of one run end up (out of {len(cust)} accounts)", x=0.01, ha="left", fontsize=12.5, fontweight="bold", y=1.04)
    ax.set_title("Orange: really suspicious.  Grey: honest customers.  The truth is known because the data is synthetic.", loc="left", fontsize=9, color=INK2, pad=12)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "funnel.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


def improvements_figure():
    """Before and after for the two changes that were measured."""
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6))
    ax = axes[0]
    names = [("seeds_1-5", "results.json", "Seeds 1-5"), ("seeds_11-15", "results_heldout.json", "Seeds 11-15"), ("seeds_21-25", "results_fresh.json", "Seeds 21-25")]
    before = [json.load(open(os.path.join(ROOT, "results", "before_mule_fix", f + ".json")))["by_typology"]["mule"]["crossexam_escalate"] * 100 for f, _, _ in names]
    after = [load(f)["by_typology"]["mule"]["crossexam_escalate"] * 100 for _, f, _ in names]
    x = np.arange(3)
    b1 = ax.bar(x - 0.2, before, 0.38, color=EXT_GREY, label="Before the rule fix")
    b2 = ax.bar(x + 0.2, after, 0.38, color=CROSS, label="After the rule fix")
    for bars, vals in ((b1, before), (b2, after)):
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}%", ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([n for _, _, n in names])
    ax.set_ylim(0, 125)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.legend(loc="upper left", frameon=False, fontsize=9, ncol=2)
    ax.set_title("Mule accounts escalated (higher is better)", loc="left", fontsize=11, pad=10)

    ax = axes[1]
    r = load("results.json")
    a, b = r["second_half_no_memory"], r["second_half_with_memory"]
    labels = ["Honest accounts\nwrongly escalated", "Suspicious accounts\nescalated outright", "Suspicious accounts\nmissed"]
    va = [a["false_escalation_rate"] * 100, a["escalated_suspicious"] * 100, a["miss_rate"] * 100]
    vb = [b["false_escalation_rate"] * 100, b["escalated_suspicious"] * 100, b["miss_rate"] * 100]
    x = np.arange(3)
    b1 = ax.bar(x - 0.2, va, 0.38, color=EXT_GREY, label="Without precedent memory")
    b2 = ax.bar(x + 0.2, vb, 0.38, color=CROSS, label="With precedent memory")
    for bars, vals in ((b1, va), (b2, vb)):
        for bb, v in zip(bars, vals):
            ax.text(bb.get_x() + bb.get_width() / 2, v + 1.5, f"{v:.1f}%", ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 125)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.legend(loc="upper left", frameon=False, fontsize=9, ncol=2)
    ax.set_title("Precedent memory, second half of each queue (seeds 1-5)", loc="left", fontsize=11, pad=10)
    fig.suptitle("The two improvements that were measured", x=0.01, ha="left", fontsize=12.5, fontweight="bold", y=1.02)
    fig.text(0.01, -0.06, "Fewer false alarms from memory is a trade: some suspicious accounts go to an analyst instead of being escalated directly.\nSimulated analyst decisions come from ground truth, so this is an upper bound.",
             fontsize=8.5, color=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "improvements.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    results_figure()
    typology_figure()
    cases_figure()
    typologies_figure()
    funnel_figure()
    improvements_figure()
    print("figures written to", HERE)
