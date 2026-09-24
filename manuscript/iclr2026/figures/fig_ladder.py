"""Figure: M1 solve-versus-budget AUC ladder with task-clustered 95% intervals (12-task validation panel).

Numbers are read from pinned evidence files in the evidence repository:
  outputs/choice-frontier/v2/metrics/analysis.json
      arms.<arm>.m1_auc, arms.<arm>.m1_task_cluster_95pct_ci_10000_seed133
          for exact_reference, exact-eps-0.25, exact-eps-0.50, exact-eps-0.75, random_valid
      adapter_reevaluation.learned_adapter.m1_auc / .m1_task_cluster_95pct_ci_10000_seed133  (first adapter)
  outputs/choice-frontier/v3/metrics/analysis.json
      per_seed.17.m1_auc / per_seed.17.ci95  (scaled adapter, single seed)
Run: python fig_ladder.py [EVIDENCE_ROOT]  -> fig_ladder.pdf, fig_ladder.svg, fig_ladder.png
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning")


def load(rel):
    return json.loads((ROOT / rel).read_text())


CI = "m1_task_cluster_95pct_ci_10000_seed133"
v2 = load("outputs/choice-frontier/v2/metrics/analysis.json")
v3 = load("outputs/choice-frontier/v3/metrics/analysis.json")

ladder = [("exact reference", "exact_reference"), ("exact-\u03b5 0.25", "exact-eps-0.25"),
          ("exact-\u03b5 0.50", "exact-eps-0.50"), ("exact-\u03b5 0.75", "exact-eps-0.75"),
          ("random-valid", "random_valid")]
rows = [(name, v2["arms"][k]["m1_auc"], *v2["arms"][k][CI]) for name, k in ladder]
first = v2["adapter_reevaluation"]["learned_adapter"]
scaled = v3["per_seed"]["17"]
rows.append(("scaled adapter (1 seed)", scaled["m1_auc"], *scaled["ci95"]))
rows.append(("first adapter", first["m1_auc"], *first[CI]))

EXPECTED = [(0.875, 0.875, 0.875), (0.793, 0.764, 0.824), (0.603, 0.528, 0.670),
            (0.347, 0.252, 0.445), (0.021, 0.007, 0.038), (0.349, 0.172, 0.531),
            (0.026, 0.010, 0.042)]
for (name, m, lo, hi), exp in zip(rows, EXPECTED):
    got = tuple(round(v, 3) for v in (m, lo, hi))
    assert got == exp, (name, got, exp)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7,
                     "pdf.fonttype": 42, "svg.fonttype": "none"})
BLUE, GREY = "#0072B2", "#555555"
LADDER_COLS = ["#003F66", "#0072B2", "#3B97CF", "#7FBDE3", "#B7D9EE"]
YS = [0, 1, 2, 3, 4, 5.3, 6.3]

fig, ax = plt.subplots(figsize=(3.4, 1.9))
rung = rows[3][1]
ax.axvline(rung, color=GREY, lw=0.7, ls=":", zorder=0)
ax.text(rung + 0.012, 7.05, "exact-\u03b5 0.75 rung", color=GREY, fontsize=7, va="center")
ax.axhline(4.65, color="#BBBBBB", lw=0.5)

for i, ((name, m, lo, hi), y) in enumerate(zip(rows, YS)):
    if i < 5:
        c, mk, fc, ms = LADDER_COLS[i], "o", LADDER_COLS[i], 4.2
        ec = "#003F66" if i == 4 else c
    elif i == 5:
        c, mk, fc, ec, ms = "black", "s", "black", "black", 4.0
    else:
        c, mk, fc, ec, ms = "black", "s", "white", "black", 4.0
    ax.plot([lo, hi], [y, y], color=c if i != 4 else ec, lw=1.1, solid_capstyle="butt")
    ax.plot(m, y, mk, ms=ms, mfc=fc, mec=ec, mew=0.8, zorder=3)
    ax.text(max(hi, m) + 0.025, y, f"{m:.3f}", va="center", ha="left", fontsize=7)

ax.set_yticks(YS)
ax.set_yticklabels([r[0] for r in rows])
ax.set_ylim(7.5, -0.6)
ax.set_xlim(-0.02, 1.0)
ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
ax.set_xticklabels(["0", "0.25", "0.50", "0.75", "1.00"])
ax.set_xlabel("M1 AUC, 12-task validation panel")
ax.tick_params(axis="y", length=0)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_linewidth(0.6)
fig.tight_layout(pad=0.4)
for ext in ("pdf", "svg"):
    fig.savefig(HERE / f"fig_ladder.{ext}", bbox_inches="tight", pad_inches=0.02)
fig.savefig(HERE / "fig_ladder.png", dpi=300, bbox_inches="tight", pad_inches=0.02)
for name, m, lo, hi in rows:
    print(f"{name}: {m:.3f} [{lo:.3f}, {hi:.3f}]")
