"""Figure: M1 solve-versus-budget AUC ladder, three panels (validation, held-out P2, unscreened P2u),
with task-clustered 95% intervals.

Numbers are read from pinned evidence files in the evidence repository:
  outputs/choice-frontier/v4/panels/metrics/analysis.json
      arms.<panel>.<arm>.m1 and arms.<panel>.<arm>.ci95
          panel in p135, p2, p2u
          arm in exact_reference, exact-eps-0.25, exact-eps-0.50, exact-eps-0.75, random_valid,
                 learned_adapter_seed_mean
      arms.<panel>.learned_adapter_s17.m1, .learned_adapter_s29.m1, .learned_adapter_s71.m1
          (per-seed points, m1 only)
  outputs/choice-frontier/v2/metrics/analysis.json
      arms.exact_reference.tasks_present  (validation-panel task count)
  outputs/choice-frontier/v6/metrics/analysis.json
      per_panel.v2.m1_arm / per_panel.v2.m1_arm_ci95  (zero-shot base, validation panel)
      per_panel.p2.m1_arm / per_panel.p2.m1_arm_ci95  (zero-shot base, P2 panel)
Run: python fig_ladder.py [EVIDENCE_ROOT]  -> fig_ladder.pdf, fig_ladder.svg, fig_ladder.png
"""
from pathlib import Path

from _style import ARM_STYLE, assert_3dp, f3, load_json

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent

v2 = load_json("outputs/choice-frontier/v2/metrics/analysis.json")
v4 = load_json("outputs/choice-frontier/v4/panels/metrics/analysis.json")
v6 = load_json("outputs/choice-frontier/v6/metrics/analysis.json")

PANELS = [("p135", "Validation (12 tasks)"), ("p2", "Held-out P2 (11 tasks)"),
          ("p2u", "Unscreened P2u (12 tasks)")]
# Evidence: v2 arms.exact_reference.tasks_present; v4 ladder_p2.tasks and
# unscreened_p2u.ladder.tasks support the displayed panel sizes.
assert v2["arms"]["exact_reference"]["tasks_present"] == 12
assert v4["ladder_p2"]["tasks"] == 11
assert v4["unscreened_p2u"]["ladder"]["tasks"] == 12
LADDER = [("exact reference", "exact_reference"), ("exact-\u03b5 0.25", "exact-eps-0.25"),
          ("exact-\u03b5 0.50", "exact-eps-0.50"), ("exact-\u03b5 0.75", "exact-eps-0.75"),
          ("random-valid", "random_valid"), ("adapter, 3-seed mean", "learned_adapter_seed_mean")]
SEEDS = ["learned_adapter_s17", "learned_adapter_s29", "learned_adapter_s71"]

EXPECTED = {
    "p135": {"exact_reference": (0.875, 0.875, 0.875), "exact-eps-0.25": (0.793, 0.764, 0.824),
             "exact-eps-0.50": (0.603, 0.528, 0.670), "exact-eps-0.75": (0.347, 0.252, 0.445),
             "random_valid": (0.021, 0.007, 0.038),
             "learned_adapter_seed_mean": (0.306, 0.158, 0.455),
             "learned_adapter_s17": 0.349, "learned_adapter_s29": 0.250,
             "learned_adapter_s71": 0.318},
    "p2": {"exact_reference": (0.875, 0.875, 0.875), "exact-eps-0.25": (0.745, 0.685, 0.805),
           "exact-eps-0.50": (0.507, 0.445, 0.566), "exact-eps-0.75": (0.205, 0.145, 0.269),
           "random_valid": (0.016, 0.000, 0.048),
           "learned_adapter_seed_mean": (0.432, 0.273, 0.602),
           "learned_adapter_s17": 0.506, "learned_adapter_s29": 0.284,
           "learned_adapter_s71": 0.506},
    "p2u": {"exact_reference": (0.875, 0.875, 0.875), "exact-eps-0.25": (0.678, 0.632, 0.721),
            "exact-eps-0.50": (0.397, 0.331, 0.478), "exact-eps-0.75": (0.149, 0.091, 0.227),
            "random_valid": (0.002, 0.000, 0.006),
            "learned_adapter_seed_mean": (0.151, 0.030, 0.288),
            "learned_adapter_s17": 0.198, "learned_adapter_s29": 0.120,
            "learned_adapter_s71": 0.135},
}


# data[panel] = {"rows": [(label, m, lo, hi)], "seeds": [m...], "zero": (m, lo, hi) or None}
data = {}
for pk, _ in PANELS:
    arms = v4["arms"][pk]
    rows = []
    for label, k in LADDER:
        m, (lo, hi) = arms[k]["m1"], arms[k]["ci95"]
        assert_3dp((m, lo, hi), EXPECTED[pk][k])
        rows.append((label, m, lo, hi))
    seeds = []
    for k in SEEDS:
        m = arms[k]["m1"]
        assert_3dp(m, EXPECTED[pk][k])
        seeds.append(m)
    data[pk] = {"rows": rows, "seeds": seeds, "zero": None}

ZERO_EXPECTED = {"p135": ("v2", (0.026, 0.000, 0.063)), "p2": ("p2", (0.017, 0.000, 0.051))}
for pk, (v6k, exp) in ZERO_EXPECTED.items():
    zp = v6["per_panel"][v6k]
    zero = (zp["m1_arm"], *zp["m1_arm_ci95"])
    assert_3dp(zero, exp)
    data[pk]["zero"] = zero

GREY, SEED_GREY = "#555555", "#AAAAAA"
YS = [0, 1, 2, 3, 4, 5.3, 6.3]  # ladder x5, adapter 3-seed mean, zero-shot base
LABELS = [l for l, _ in LADDER] + ["zero-shot base"]
XMIN, XMAX = -0.02, 1.08

fig, axes = plt.subplots(1, 3, sharey=True, figsize=(6.0, 2.35))


def draw(ax, key, y, m, lo, hi):
    style = ARM_STYLE[key]
    c = style["color"]
    mk = style["marker"]
    fc = style["facecolor"]
    ec = style["edgecolor"]
    ms = 3.8 if mk == "D" else 4.0 if mk == "s" else 4.2
    ax.plot([lo, hi], [y, y], color=c, lw=1.1, solid_capstyle="butt", zorder=2)
    ax.plot(m, y, mk, ms=ms, mfc=fc, mec=ec, mew=0.8, zorder=4)
    right = max(hi, m)
    # The dotted 0.75 rung crosses the low-valued random-valid label on P2/P2u.
    label_box = dict(facecolor="white", edgecolor="none", pad=0.1) if key == "random_valid" else None
    if right > 0.85:  # no room to the right: place label left of the interval
        ax.text(min(lo - 0.035, m - 0.045), y, f3(m), va="center", ha="right",
                fontsize=8, bbox=label_box)
    else:
        ax.text(max(right + 0.035, m + 0.045), y, f3(m), va="center", ha="left",
                fontsize=8, bbox=label_box)


for j, (ax, (pk, title)) in enumerate(zip(axes, PANELS)):
    d = data[pk]
    rung = d["rows"][3][1]
    ax.axvline(rung, color=GREY, lw=0.7, ls=":", zorder=0)
    ax.axhline(4.65, color="#BBBBBB", lw=0.5)
    ax.plot(d["seeds"], [YS[5]] * len(d["seeds"]), "o", ms=2.6, mfc=SEED_GREY, mec="none",
            alpha=0.8, zorder=3)
    for i, (_, m, lo, hi) in enumerate(d["rows"]):
        draw(ax, LADDER[i][1], YS[i], m, lo, hi)
    if d["zero"] is not None:
        draw(ax, "zero_shot_base", YS[6], *d["zero"])
    ax.set_title(title, fontsize=8, pad=3)
    ax.set_xlim(XMIN, XMAX)
    ax.set_xticks([0, 0.5, 1.0])
    ax.set_xticklabels(["0", "0.5", "1.0"])
    ax.set_xlabel("M1 AUC")
    ax.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_linewidth(0.6)
    ax.spines["bottom"].set_bounds(0, 1.0)
    if j > 0:
        ax.tick_params(axis="y", labelleft=False)

axes[0].set_yticks(YS)
axes[0].set_yticklabels(LABELS)
axes[0].set_ylim(6.8, -0.6)
fig.tight_layout(pad=0.4, w_pad=0.8)
for ext in ("pdf", "svg"):
    fig.savefig(HERE / f"fig_ladder.{ext}", bbox_inches="tight", pad_inches=0.02)
fig.savefig(HERE / "fig_ladder.png", dpi=300, bbox_inches="tight", pad_inches=0.02)

for pk, title in PANELS:
    d = data[pk]
    print(f"== {pk}: {title}")
    for name, m, lo, hi in d["rows"]:
        print(f"  {name}: {f3(m)} [{f3(lo)}, {f3(hi)}]")
    print("  per-seed s17/s29/s71: " + " / ".join(f3(m) for m in d["seeds"]))
    if d["zero"] is not None:
        m, lo, hi = d["zero"]
        print(f"  zero-shot base: {f3(m)} [{f3(lo)}, {f3(hi)}]")
