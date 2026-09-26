"""Figure: comparator-zoo M1 AUC with task-clustered 95% CIs.

Source: outputs/choice-frontier/o4/metrics/analysis.json,
arms.*.m1_auc, arms.*.m1_task_cluster_95pct_ci_10000_seed133,
and arms.*.tasks_present. Every plotted M1 and CI is asserted at 3 dp, half-up.
Run: python fig_zoo_m1.py [EVIDENCE_ROOT] -> fig_zoo_m1.pdf, fig_zoo_m1.svg, fig_zoo_m1.png
"""
from pathlib import Path

from _style import ARM_STYLE, assert_3dp, f3, load_json
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
CI = "m1_task_cluster_95pct_ci_10000_seed133"
arms = load_json("outputs/choice-frontier/o4/metrics/analysis.json")["arms"]
# (display name, JSON arm key, expected M1 and CI at 3 dp, style key)
ROWS = [
    ("exact reference", "exact_reference", (0.847, 0.792, 0.875), "exact_reference"),
    ("random-valid", "random_valid", (0.139, 0.025, 0.272), "random_valid"),
    ("learned adapter", "learned_adapter", (0.104, 0.028, 0.201), "learned_adapter_seed_mean"),
    ("novelty-first", "novelty-first", (0.125, 0.000, 0.278), None),
    ("bfs-order", "bfs-order", (0.069, 0.000, 0.153), None),
    ("worst-first", "worst-first", (0.056, 0.000, 0.139), None),
    ("pretrained base", "pretrained_base", (0.000, 0.000, 0.000), None),
]
ARMS = []
for name, key, expected, style_key in ROWS:
    record = arms[key]
    m, (lo, hi) = record["m1_auc"], record[CI]
    assert_3dp((m, lo, hi), expected)
    assert record["tasks_present"] == 9, (key, record["tasks_present"])
    ARMS.append((name, m, lo, hi, style_key))
FLOOR = arms["random_valid"]["m1_auc"]

fig, ax = plt.subplots(figsize=(3.25, 2.5))
n = len(ARMS)
ax.axvline(FLOOR, color=ARM_STYLE["random_valid"]["color"], ls="--", lw=0.8, zorder=0)
ax.text(FLOOR + 0.01, n - 0.35, "random-valid reference", fontsize=7, color="#666666", va="center")
for i, (name, m, lo, hi, key) in enumerate(ARMS):
    y = n - 1 - i
    style = ARM_STYLE[key] if key else None
    color = style["color"] if style else "#E69F00" if name == "pretrained base" else "#56B4E9"
    ax.errorbar(m, y, xerr=[[m - lo], [hi - m]],
                fmt=style["marker"] if style else "o", color=color, ms=4, capsize=2, lw=1.0,
                mfc=style["facecolor"] if style else color,
                mec=style["edgecolor"] if style else "black", mew=0.6)
    ax.text(hi + 0.02, y, f3(m), fontsize=7, va="center")
ax.set_yticks(range(n))
ax.set_yticklabels([a[0] for a in ARMS][::-1])
ax.set_xlim(-0.02, 1.05)
ax.set_ylim(-0.6, n - 0.1)
ax.set_xlabel("M1 solve-vs-budget AUC (9-task choice-frontier panel)", loc="right")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout(pad=0.3)
for ext in ("pdf", "svg"):
    fig.savefig(HERE / f"fig_zoo_m1.{ext}")
fig.savefig(HERE / "fig_zoo_m1.png", dpi=300)
