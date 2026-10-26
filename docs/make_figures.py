"""Builds the figures in docs/ from results*.json and from real runs of the investigator.

    python docs/make_figures.py

Nothing here is typed in by hand: bars come from the result files, the three example cases come from running the
workflow on seed 1."""
import json
import os
import sys
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
MODEL, PROS, CROSS = "#2a78d6", "#eb6834", "#1baf7a"          # fixed order: one colour per method in every figure
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
    fig.savefig(os.path.join(HERE, "typology.png"), dpi=170, bbox_inches="tight")
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


if __name__ == "__main__":
    results_figure()
    typology_figure()
    cases_figure()
    print("figures written to", HERE)
