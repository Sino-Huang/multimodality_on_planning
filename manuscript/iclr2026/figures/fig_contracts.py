"""Figure: enumeration vs choice-frontier contract schematic.

Facts: outputs/native-arms/v1/identity-audit.json (48/48 additive pairs identical);
outputs/choice-frontier/v1/evaluation/analysis.json (random - exact = -0.644 [-0.856, -0.422]).
Run: python fig_contracts.py  -> fig_contracts.pdf, fig_contracts.svg, fig_contracts.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7,
                     "pdf.fonttype": 42, "svg.fonttype": "none"})
BLUE, ORANGE, GREY = "#0072B2", "#E69F00", "#555555"


def box(ax, x, y, w, h, text, fc, ec=GREY, bold=False, fs=7):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.02",
                                fc=fc, ec=ec, lw=0.7))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            weight="bold" if bold else "normal")


def arrow(ax, p, q, label=None, off=(0, 0.03)):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=7, lw=0.8, color=GREY))
    if label:
        ax.text((p[0] + q[0]) / 2 + off[0], (p[1] + q[1]) / 2 + off[1], label,
                ha="center", va="bottom", fontsize=7, color=GREY)


fig, axes = plt.subplots(2, 1, figsize=(3.25, 3.3))
for ax in axes:
    ax.set_xlim(-0.03, 1.03); ax.set_ylim(0, 1); ax.axis("off")

# (a) enumeration contract
ax = axes[0]
ax.text(0, 0.97, "(a) Enumeration contract", weight="bold", fontsize=8, va="top")
box(ax, 0.00, 0.40, 0.27, 0.34, "Grounded\ncandidate\nmenu", "#DCEBF5")
box(ax, 0.33, 0.45, 0.20, 0.24, "Policy", "white", bold=True)
box(ax, 0.69, 0.40, 0.31, 0.34, "Submission-order\ninvariant heap", "#EEEEEE")
arrow(ax, (0.27, 0.57), (0.33, 0.57))
arrow(ax, (0.53, 0.57), (0.69, 0.57), "one op")
box(ax, 0.05, 0.04, 0.90, 0.22,
    "random-valid \u2261 exact reference, 48/48 additive pairs", "white", ec=BLUE, fs=7)

# (b) choice-frontier contract
ax = axes[1]
ax.text(0, 0.97, "(b) Choice-frontier contract", weight="bold", fontsize=8, va="top")
box(ax, 0.00, 0.40, 0.27, 0.34, "Runtime-owned\nfrontier\nstates", "#FBEBCB")
box(ax, 0.33, 0.45, 0.20, 0.24, "Policy", "white", bold=True)
box(ax, 0.69, 0.40, 0.31, 0.34, "Expand chosen\nstate (binding\ndecision budget)", "#EEEEEE")
arrow(ax, (0.27, 0.57), (0.33, 0.57))
arrow(ax, (0.53, 0.57), (0.69, 0.57), "select")
box(ax, 0.05, 0.04, 0.90, 0.22,
    "random \u2212 exact = \u22120.644 [\u22120.856, \u22120.422]", "white", ec=ORANGE, fs=7)

fig.tight_layout(pad=0.2, h_pad=0.6)
for ext in ("pdf", "svg"):
    fig.savefig(f"fig_contracts.{ext}")
fig.savefig("fig_contracts.png", dpi=300)
