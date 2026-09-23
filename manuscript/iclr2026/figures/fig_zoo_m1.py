"""Figure: comparator-zoo M1 AUC with task-clustered 95% CIs.

Source: outputs/choice-frontier/o4/metrics/analysis.json,
arms.*.m1_auc and arms.*.m1_task_cluster_95pct_ci_10000_seed133 (values copied verbatim).
Annotation counts: Results table tab:results-primary-matrix.
Run: python fig_zoo_m1.py -> fig_zoo_m1.pdf, fig_zoo_m1.svg, fig_zoo_m1.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7,
                     "pdf.fonttype": 42, "svg.fonttype": "none"})

# (arm, auc, lo, hi, color)  Okabe-Ito palette
ARMS = [
    ("exact_reference", 0.8472, 0.7917, 0.875, "#009E73"),
    ("random_valid", 0.1389, 0.0250, 0.2722, "#999999"),
    ("learned_adapter", 0.1042, 0.0278, 0.2014, "#000000"),
    ("novelty-first", 0.1250, 0.0, 0.2778, "#56B4E9"),
    ("bfs-order", 0.0694, 0.0, 0.1528, "#56B4E9"),
    ("worst-first", 0.0556, 0.0, 0.1389, "#56B4E9"),
    ("pretrained_base", 0.0, 0.0, 0.0, "#E69F00"),
]
FLOOR = 0.1389

fig, ax = plt.subplots(figsize=(3.25, 2.5))
n = len(ARMS)
ax.axvline(FLOOR, color="#999999", ls="--", lw=0.8, zorder=0)
ax.text(FLOOR + 0.01, n - 0.35, "random_valid floor", fontsize=7, color="#666666", va="center")
for i, (name, m, lo, hi, c) in enumerate(ARMS):
    y = n - 1 - i
    ax.errorbar(m, y, xerr=[[m - lo], [hi - m]], fmt="s" if name == "learned_adapter" else "o",
                color=c, ms=4, capsize=2, lw=1.0, mec="black", mew=0.4)
    ax.text(hi + 0.02, y, f"{m:.4f}" if m else "0",
            fontsize=7, va="center")
ax.set_yticks(range(n))
ax.set_yticklabels([a[0] for a in ARMS][::-1])
ax.set_xlim(-0.02, 1.05)
ax.set_ylim(-0.6, n - 0.1)
ax.set_xlabel("M1 solve-vs-budget AUC (9-task choice-frontier panel)", loc="right")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.text(0.99, 0.27, "Enumeration-contract\nBFS/BFWS random-valid\nalready registered choice\n"
        "(15/24, 17/24 vs\nexact 24/24)", fontsize=7, va="center", ha="right", transform=ax.transAxes,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#BBBBBB", lw=0.6))
fig.tight_layout(pad=0.3)
for ext in ("pdf", "svg"):
    fig.savefig(f"fig_zoo_m1.{ext}")
fig.savefig("fig_zoo_m1.png", dpi=300)
