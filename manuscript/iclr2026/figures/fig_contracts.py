"""Figure: enumeration vs choice-frontier contract schematic (wide, two panels side by side).

Numbers are read from the pinned evidence JSONs in the evidence repository:
  outputs/native-arms/v1/identity-audit.json            (pairs_identical / pairs_checked)
  outputs/choice-frontier/v1/evaluation/identity-audit.json (pairs_divergent / pairs_checked)
  outputs/choice-frontier/v1/evaluation/analysis.json   (contrasts.random_valid_minus_exact_reference)
Run: python fig_contracts.py [EVIDENCE_ROOT]  -> fig_contracts.pdf, fig_contracts.svg, fig_contracts.png
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/data/scratch/projects/punim0478/sukaih/multimodality_on_planning")


def load(rel):
    return json.loads((ROOT / rel).read_text())


enum = load("outputs/native-arms/v1/identity-audit.json")
cf_id = load("outputs/choice-frontier/v1/evaluation/identity-audit.json")
diff = load("outputs/choice-frontier/v1/evaluation/analysis.json")["contrasts"][
    "random_valid_minus_exact_reference"]
lo, hi = diff["ci95"]
MINUS = "\u2212"


def f3(v):
    return f"{v:.3f}".replace("-", MINUS)


enum_txt = (f"random-valid \u2261 exact reference\n"
            f"{enum['pairs_identical']}/{enum['pairs_checked']} additive pairs identical")
cf_txt = (f"{cf_id['pairs_divergent']}/{cf_id['pairs_checked']} cells divergent\n"
          f"random-valid {MINUS} exact reference\n"
          f"= {f3(diff['mean'])} [{f3(lo)}, {f3(hi)}]")

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
                     "pdf.fonttype": 42, "svg.fonttype": "none"})
BLUE, ORANGE, GREY = "#0072B2", "#E69F00", "#555555"


def box(ax, x, y, w, h, text, fc, ec=GREY, bold=False, fs=8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.02",
                                fc=fc, ec=ec, lw=0.8))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            weight="bold" if bold else "normal", linespacing=1.15)


def arrow(ax, p, q, label=None):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=8, lw=0.9, color=GREY))
    if label:
        ax.text((p[0] + q[0]) / 2, p[1] + 0.04, label, ha="center", va="bottom",
                fontsize=7.5, color=GREY)


def panel(ax, title, left, left_fc, verb, right, result, ec):
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.02, 0.99, title, weight="bold", fontsize=9, va="top")
    box(ax, 0.02, 0.44, 0.24, 0.36, left, left_fc, fs=7.5)
    box(ax, 0.32, 0.50, 0.15, 0.24, "Policy", "white", bold=True)
    box(ax, 0.64, 0.44, 0.34, 0.36, right, "#EEEEEE", fs=7.5)
    arrow(ax, (0.26, 0.62), (0.32, 0.62))
    arrow(ax, (0.47, 0.62), (0.64, 0.62), verb)
    box(ax, 0.02, 0.03, 0.96, 0.33, result, "white", ec=ec)


fig, axes = plt.subplots(1, 2, figsize=(5.5, 1.67))
panel(axes[0], "(a) Enumeration contract", "Grounded\ncandidate\nmenu", "#DCEBF5",
      "one op", "Order-invariant\nheap", enum_txt, BLUE)
panel(axes[1], "(b) Choice-frontier contract", "Runtime\nfrontier\nstates", "#FBEBCB",
      "select", "Expand chosen\nstate", cf_txt, ORANGE)
fig.subplots_adjust(left=0.01, right=0.99, top=0.98, bottom=0.02, wspace=0.08)
for ext in ("pdf", "svg"):
    fig.savefig(HERE / f"fig_contracts.{ext}")
fig.savefig(HERE / "fig_contracts.png", dpi=300)
print(enum_txt.replace("\n", " | ")); print(cf_txt.replace("\n", " | "))
