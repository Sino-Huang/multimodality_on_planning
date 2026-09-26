"""Solve-versus-budget curves on three development panels.

Evidence: outputs/choice-frontier/v2/metrics/all-episode-metrics.json records[].solves,
outputs/choice-frontier/v4/seeds/metrics/all-episode-metrics.json records[].solves
(including the training-seed-17 records also present at v3/metrics/all-episode-metrics.json),
outputs/choice-frontier/v4/panels/metrics/all-episode-metrics.json p2/p2u[].solves,
outputs/choice-frontier/v4/panels/metrics/analysis.json arms.<panel>.<arm>.m1,
outputs/choice-frontier/v6/metrics/zero-shot-episode-metrics.json v2/p2[].solves,
outputs/choice-frontier/v6/metrics/analysis.json per_panel.v2/p2.m1_arm.

The orange envelope is the minimum-to-maximum of three TRAINING-seed curves, not a
confidence interval. Other repeated records are evaluation seeds; all episodes are
pooled equally within an arm. The privileged exact-epsilon rungs validate the
measurement; they do not represent policies.
Run: python fig_budget_curves.py [EVIDENCE_ROOT]
"""
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

from _style import ARM_STYLE, assert_3dp, load_json


HERE = Path(__file__).resolve().parent
BASE = "outputs/choice-frontier/"
# Evidence: the five solve-budget keys in every pinned episode's `solves` dict.
BUDGET_KEYS = ("1", "1.25", "1.5", "1.75", "2")
BUDGETS = tuple(float(key) for key in BUDGET_KEYS)
PANELS = (("p135", "a  Validation"), ("p2", "b  Held-out P2"),
          ("p2u", "c  Unscreened P2u"))
ARMS = (("exact_reference", "exact reference"),
        ("exact-eps-0.25", "exact-ε 0.25"),
        ("exact-eps-0.50", "exact-ε 0.50"),
        ("exact-eps-0.75", "exact-ε 0.75"),
        ("random_valid", "random-valid"),
        ("learned_adapter_seed_mean", "adapter (3 seeds; range)"),
        ("zero_shot_base", "zero-shot base"))
TRAINING_SEEDS = (17, 29, 71)
# Evidence: v4/panels/metrics/analysis.json arms.<panel>.<arm>.m1;
# v6/metrics/analysis.json per_panel.v2/p2.m1_arm for zero-shot base.
EXPECTED_M1 = {
    "p135": (0.875, 0.793, 0.603, 0.347, 0.021, 0.306, 0.026),
    "p2": (0.875, 0.745, 0.507, 0.205, 0.016, 0.432, 0.017),
    "p2u": (0.875, 0.678, 0.397, 0.149, 0.002, 0.151, None),
}


def solve_curve(rows):
    assert rows
    assert all(tuple(row["solves"]) == BUDGET_KEYS for row in rows)
    return [sum(row["solves"][key] for row in rows) / len(rows) for key in BUDGET_KEYS]


def trapezoid_area(ys):
    return sum((left + right) * (xright - xleft) / 2
               for xleft, xright, left, right in zip(BUDGETS, BUDGETS[1:], ys, ys[1:]))


def evidence_curves():
    analysis = load_json(BASE + "v4/panels/metrics/analysis.json")
    v2 = load_json(BASE + "v2/metrics/all-episode-metrics.json")["records"]
    seeds = load_json(BASE + "v4/seeds/metrics/all-episode-metrics.json")["records"]
    v3 = load_json(BASE + "v3/metrics/all-episode-metrics.json")["records"]
    # Evidence: v3 seed-17 adapter outcomes and their migrated copies in v4/seeds.
    v3_by_episode = {(r["task"], r["algorithm"]): r for r in v3}
    seed17 = {(r["task"], r["algorithm"]): r for r in seeds if r["training_seed"] == 17}
    assert len(v3_by_episode) == len(seed17) == 24
    for key, row in v3_by_episode.items():
        assert row["solves"] == seed17[key]["solves"]
        assert_3dp(row["auc"], seed17[key]["auc"])

    other_panels = load_json(BASE + "v4/panels/metrics/all-episode-metrics.json")
    zero = load_json(BASE + "v6/metrics/zero-shot-episode-metrics.json")
    zero_analysis = load_json(BASE + "v6/metrics/analysis.json")
    records = {"p135": v2 + seeds + zero["v2"],
               "p2": other_panels["p2"] + zero["p2"],
               "p2u": other_panels["p2u"]}
    curves = {}
    for panel, rows in records.items():
        tasks = {row["task"] for row in rows}
        # Evidence: v4/panels/metrics/analysis.json concentration.per_panel.<panel>.domains.
        assert tasks == set(analysis["concentration"]["per_panel"][panel]["domains"])
        assert len(tasks) == {"p135": 12, "p2": 11, "p2u": 12}[panel]
        by_arm = defaultdict(list)
        for row in rows:
            by_arm[row["arm"]].append(row)
        panel_curves = {}
        for i, (arm, _) in enumerate(ARMS):
            if arm == "zero_shot_base" and panel == "p2u":
                continue  # The pinned zero-shot evaluation covers validation and P2 only.
            source_arm = "learned_adapter" if arm == "learned_adapter_seed_mean" else arm
            episodes = by_arm[source_arm]
            curve = solve_curve(episodes)
            area = trapezoid_area(curve)
            # Evidence: each episode's own precomputed trapezoidal AUC.
            assert_3dp(area, sum(row["auc"] for row in episodes) / len(episodes))
            pinned = (zero_analysis["per_panel"]["v2" if panel == "p135" else "p2"]["m1_arm"]
                      if arm == "zero_shot_base" else analysis["arms"][panel][arm]["m1"])
            assert_3dp(area, pinned)
            assert_3dp(pinned, EXPECTED_M1[panel][i])
            panel_curves[arm] = curve
        seeded = {s: solve_curve([row for row in by_arm["learned_adapter"]
                                 if row["training_seed"] == s]) for s in TRAINING_SEEDS}
        assert all(len([row for row in by_arm["learned_adapter"]
                        if row["training_seed"] == s]) == len(tasks) * 2 for s in TRAINING_SEEDS)
        for seed, curve in seeded.items():
            assert_3dp(trapezoid_area(curve), analysis["arms"][panel][f"learned_adapter_s{seed}"]["m1"])
        assert all(all(0 <= value <= 1 for value in curve) for curve in panel_curves.values())
        curves[panel] = (panel_curves, seeded)
    return curves


def draw(curves):
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 3.08), sharex=True, sharey=True)
    for ax, (panel, title) in zip(axes, PANELS):
        plot_curves, seeded = curves[panel]
        adapter_color = ARM_STYLE["learned_adapter_seed_mean"]["color"]
        # Evidence: training_seed=17/29/71 rows' solves, min/max across their curves.
        ax.fill_between(BUDGETS,
                        [min(seeded[s][i] for s in TRAINING_SEEDS) for i in range(len(BUDGETS))],
                        [max(seeded[s][i] for s in TRAINING_SEEDS) for i in range(len(BUDGETS))],
                        color=adapter_color, alpha=0.14, linewidth=0, zorder=1)
        for arm, label in ARMS:
            if arm not in plot_curves:
                continue
            style = ARM_STYLE[arm]
            ax.plot(BUDGETS, plot_curves[arm], color=style["color"],
                    marker=style["marker"], markerfacecolor=style["facecolor"],
                    markeredgecolor=style["edgecolor"], markersize=3.5,
                    markeredgewidth=0.8, linewidth=1.35 if arm == "learned_adapter_seed_mean" else 1.0,
                    linestyle="--" if arm in ("random_valid", "zero_shot_base") else "-",
                    label=label, zorder=3 if arm == "learned_adapter_seed_mean" else 2)
        ax.set_title(title, loc="left", fontsize=8, fontweight="bold", pad=5)
        ax.set_xlim(0.98, 2.02)
        ax.set_ylim(-0.025, 1.04)
        ax.set_xticks(BUDGETS, ("1", "1.25", "1.5", "1.75", "2"))
        ax.set_yticks((0, .25, .5, .75, 1), ("0", ".25", ".5", ".75", "1"))
        ax.set_xlabel("Budget multiplier")
        ax.tick_params(axis="both", labelsize=7, length=2.5, width=0.6)
        ax.spines[["top", "right"]].set_visible(False)
        for side in ("bottom", "left"):
            ax.spines[side].set_linewidth(0.6)
    axes[0].set_ylabel("Fraction solved")
    handles, labels = axes[0].get_legend_handles_labels()
    # Matplotlib lays legend items down columns; this restores row-major rung order.
    order = (0, 4, 1, 5, 2, 6, 3)
    handles, labels = [handles[i] for i in order], [labels[i] for i in order]
    fig.legend(handles, labels, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1),
               frameon=False, fontsize=7, columnspacing=1.2, handlelength=2)
    fig.subplots_adjust(top=0.76, bottom=0.16, left=0.075, right=0.99, wspace=0.14)
    for extension in ("pdf", "svg"):
        fig.savefig(HERE / f"fig_budget_curves.{extension}", bbox_inches="tight", pad_inches=0.035)
    fig.savefig(HERE / "fig_budget_curves.png", dpi=300, bbox_inches="tight", pad_inches=0.035)
    plt.close(fig)


if __name__ == "__main__":
    draw(evidence_curves())
