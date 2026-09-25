"""Figure 1 teaser: enumeration vs choice-frontier contract, with the validated M1 mini-ladder.

Numbers are read from pinned evidence files in the evidence repository:
  outputs/native-arms/v1/identity-audit.json            (pairs_identical / pairs_checked)
  outputs/native-arms/v1/identity-audit-submission-order.json
      (rules.submission_order.pairs_divergent / pairs_checked: same-runtime counterfactual)
  docs/experiments/expanded-study/synthesis-v1/baseline-contrasts.csv
      (random_valid_minus_exact_reference rows for best_first_add_{greedy,w3}: problems = task count)
  outputs/choice-frontier/v1/evaluation/identity-audit.json (pairs_divergent / pairs_checked, task ids)
  outputs/choice-frontier/v4/panels/metrics/analysis.json  (arms.p135.<arm>.m1, validation panel)
Every printed number is asserted against its expected value (3 dp, half-up, as in fig_ladder.py).
Run: python fig_contracts.py [EVIDENCE_ROOT]  -> fig_contracts.pdf, fig_contracts.svg, fig_contracts.png
"""
import csv
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
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


def f3(v):
    """3-dp string, half-up (the paper's convention; Python round() is half-even on binary floats)."""
    return str(Decimal(repr(v)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


# ---- (a) enumeration contract -------------------------------------------------------------
enum = load("outputs/native-arms/v1/identity-audit.json")
assert (enum["pairs_identical"], enum["pairs_checked"]) == (48, 48), enum
sub = load("outputs/native-arms/v1/identity-audit-submission-order.json")
sub_div = sub["rules"]["submission_order"]["pairs_divergent"]
sub_n = sub["pairs_checked"]
assert (sub_div, sub_n) == (19, 48), (sub_div, sub_n)
with open(ROOT / "docs/experiments/expanded-study/synthesis-v1/baseline-contrasts.csv") as fh:
    add_rows = [r for r in csv.DictReader(fh)
                if r["contrast"] == "random_valid_minus_exact_reference"
                and r["algorithm"] in ("best_first_add_greedy", "best_first_add_w3")]
enum_tasks = {int(r["problems"]) for r in add_rows}
assert enum_tasks == {24}, enum_tasks
enum_tasks = enum_tasks.pop()
assert enum["pairs_checked"] == 2 * enum_tasks, (enum["pairs_checked"], enum_tasks)

# ---- (b) choice-frontier contract ---------------------------------------------------------
cf_id = load("outputs/choice-frontier/v1/evaluation/identity-audit.json")
assert (cf_id["pairs_divergent"], cf_id["pairs_checked"]) == (18, 18), cf_id
cf_tasks = len({p["cell"].split("|")[0] for p in cf_id["pairs"]})
assert cf_tasks == 9, cf_tasks

arms = load("outputs/choice-frontier/v4/panels/metrics/analysis.json")["arms"]["p135"]
# (short label, key, expected 3-dp M1, colour index; None = adapter)
LADDER = [("exact reference", "exact_reference", "0.875", 0),
          ("exact-\u03b5 0.25", "exact-eps-0.25", "0.793", 1),
          ("exact-\u03b5 0.50", "exact-eps-0.50", "0.603", 2),
          ("exact-\u03b5 0.75", "exact-eps-0.75", "0.347", 3),
          ("random-valid", "random_valid", "0.021", 4),
          ("adapter", "learned_adapter_seed_mean", "0.306", None)]
m1 = {}
for label, k, exp, _ in LADDER:
    got = f3(arms[k]["m1"])
    assert got == exp, f"p135/{k}: got {got}, expected {exp}"
    m1[k] = arms[k]["m1"]

enum_txt = [f"{enum['pairs_identical']}/{enum['pairs_checked']} additive pairs identical"
            f" ({enum_tasks} tasks)",
            f"submission-order serials: {sub_div}/{sub_n} divergent"]
cf_txt = f"{cf_id['pairs_divergent']}/{cf_id['pairs_checked']} pairs divergent ({cf_tasks} tasks)"
LADDER_TITLE = "validation M1, adapter = 3-seed mean"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
                     "pdf.fonttype": 42, "svg.fonttype": "none"})
BLUE, ORANGE, GREY = "#0072B2", "#E69F00", "#555555"
LADDER_COLS = ["#003F66", "#0072B2", "#3B97CF", "#7FBDE3", "#B7D9EE"]


def box(ax, x, y, w, h, text, fc, ec=GREY, bold=False, fs=8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.02",
                                fc=fc, ec=ec, lw=0.8))
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
                weight="bold" if bold else "normal", linespacing=1.15)


def arrow(ax, p, q, label=None):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=8, lw=0.9, color=GREY))
    if label:
        ax.text((p[0] + q[0]) / 2, p[1] - 0.07, label, ha="center", va="top",
                fontsize=7, color=GREY)


def panel(ax, title, left, left_fc, verb, right, ec):
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.02, 0.995, title, weight="bold", fontsize=9, va="top")
    box(ax, 0.02, 0.60, 0.24, 0.28, left, left_fc, fs=7.5)
    box(ax, 0.32, 0.645, 0.15, 0.19, "Policy", "white", bold=True)
    box(ax, 0.64, 0.60, 0.34, 0.28, right, "#EEEEEE", fs=7.5)
    arrow(ax, (0.26, 0.74), (0.32, 0.74))
    arrow(ax, (0.47, 0.74), (0.64, 0.74), verb)
    box(ax, 0.02, 0.02, 0.96, 0.52, None, "white", ec=ec)


def takeaway(ax, text, c):
    ax.text(0.50, 0.065, text, ha="center", va="center", fontsize=8, weight="bold", color=c)


fig, axes = plt.subplots(1, 2, figsize=(5.5, 2.15))
panel(axes[0], "(a) Enumeration contract", "Grounded\ncandidate\nmenu", "#DCEBF5",
      "one op", "Sorted-serial\nfrontier\n(order-invariant)", BLUE)
axes[0].text(0.50, 0.44, enum_txt[0], ha="center", va="center", fontsize=8)
axes[0].text(0.50, 0.30, enum_txt[1], ha="center", va="center", fontsize=8)
axes[0].text(0.50, 0.17, "additive cells, sorted ties", ha="center", va="center", fontsize=7.5, color=BLUE)
takeaway(axes[0], "success measures validity", BLUE)

ax = axes[1]
panel(ax, "(b) Choice-frontier contract", "Runtime\nfrontier\nstates", "#FBEBCB",
      "select", "Expand chosen\nstate", ORANGE)
ax.text(0.50, 0.475, cf_txt, ha="center", va="center", fontsize=8)
ax.text(0.05, 0.395, LADDER_TITLE, ha="left", va="center", fontsize=7, color=GREY)
takeaway(ax, "success measures choice", ORANGE)

# Mini-ladder: one horizontal M1 axis. Label side and alignment are fixed per point so that no
# two labels collide and the dotted 0.75 rung line (drawn below the axis only) stays visible.
ins = ax.inset_axes([0.07, 0.12, 0.89, 0.25])
ins.set_xlim(-0.30, 0.92); ins.set_ylim(-1, 1); ins.axis("off")
ins.plot([0, 0.9], [0, 0], color="#BBBBBB", lw=0.6, zorder=0)
ins.axvline(m1["exact-eps-0.75"], ymin=0.1, ymax=0.5, color=GREY, lw=0.7, ls=":", zorder=1)
# In-axis labels are shortened so the six labels do not collide on a ~2.3 in axis.
SHORT = {"exact_reference": "exact ref.", "exact-eps-0.25": "exact-\u03b5 0.25",
         "exact-eps-0.50": "\u03b5 0.50", "exact-eps-0.75": "\u03b5 0.75",
         "random_valid": "random-valid", "learned_adapter_seed_mean": "adapter"}
# key -> (label above the axis?, horizontal alignment at the point)
PLACE = {"random_valid": (None, "right"), "learned_adapter_seed_mean": (False, "right"),
         "exact-eps-0.75": (True, "center"), "exact-eps-0.50": (True, "right"),
         "exact-eps-0.25": (False, "center"), "exact_reference": (True, "right")}
for label, k, _, ci in LADDER:
    m = m1[k]
    if ci is None:
        ins.plot(m, 0, "s", ms=4.0, mfc="black", mec="black", mew=0.8, zorder=4)
    else:
        ec = "#003F66" if ci == 4 else LADDER_COLS[ci]
        ins.plot(m, 0, "o", ms=4.2, mfc=LADDER_COLS[ci], mec=ec, mew=0.8, zorder=3)
    up, ha = PLACE[k]
    if up is None:  # left of the marker, on the axis line
        ins.annotate(f"{SHORT[k]}\n{f3(m)}", (m, 0), xytext=(-5, 0), textcoords="offset points",
                     ha=ha, va="center", fontsize=7, linespacing=1.0)
        continue
    ins.annotate(f"{SHORT[k]}\n{f3(m)}", (m, 0), xytext=(0, 4 if up else -4),
                 textcoords="offset points", ha=ha, va="bottom" if up else "top",
                 fontsize=7, linespacing=1.0, weight="bold" if ci is None else "normal")

fig.subplots_adjust(left=0.01, right=0.99, top=0.98, bottom=0.02, wspace=0.08)
for ext in ("pdf", "svg"):
    fig.savefig(HERE / f"fig_contracts.{ext}")
fig.savefig(HERE / "fig_contracts.png", dpi=300)

print("(a) " + " | ".join(enum_txt) + " | additive cells, sorted ties | success measures validity")
print("(b) " + cf_txt + f" | {LADDER_TITLE} | "
      + " | ".join(f"{l.replace(chr(10), ' ')} {f3(m1[k])}" for l, k, _, _ in LADDER)
      + " | success measures choice")
