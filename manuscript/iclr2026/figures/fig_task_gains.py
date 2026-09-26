"""Per-task adapter three-training-seed mean minus random-valid M1, development panels.

Evidence: outputs/choice-frontier/v2/metrics/all-episode-metrics.json records[].auc,
outputs/choice-frontier/v4/seeds/metrics/all-episode-metrics.json records[].auc,
outputs/choice-frontier/v4/panels/metrics/all-episode-metrics.json p2/p2u[].auc,
outputs/choice-frontier/v4/panels/metrics/analysis.json
  arms.<panel>.learned_adapter_seed_mean.per_task,
  concentration.per_panel.<panel>.{per_task_difference,domains,counts},
  concentration.all_36_counts.

Each task pools its two algorithms, three training seeds for the adapter and five
control evaluation seeds for random-valid. Colours encode domains, while text also
names each domain so the comparison remains legible without colour. The task-ID
suffix is copied from the pinned evidence; these are descriptive, not effect tests.
Run: python fig_task_gains.py [EVIDENCE_ROOT]
"""
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

from _style import ARM_STYLE, assert_3dp, load_json


HERE = Path(__file__).resolve().parent
BASE = "outputs/choice-frontier/"
PANELS = (("p135", "a  Validation"), ("p2", "b  Held-out P2"),
          ("p2u", "c  Unscreened P2u"))
# Evidence: the domain names in analysis.json concentration.per_panel.<panel>.domains.
# Consistent hues identify, but do not rank, the domains; labels redundantly encode them.
DOMAIN_COLOURS = {
    "15puzzle": "#3B5B92", "blocksworld": "#8C3A62", "depot": "#2F7770",
    "driverlog": "#895819", "elevators": "#743F91", "ferry": "#AF5360",
    "grid": "#216F9D", "storage": "#727433", "towers_of_hanoi": "#536C3E",
    "visitall": "#594A94",
}


def task_gains():
    analysis = load_json(BASE + "v4/panels/metrics/analysis.json")
    validation = load_json(BASE + "v2/metrics/all-episode-metrics.json")["records"]
    adapters = load_json(BASE + "v4/seeds/metrics/all-episode-metrics.json")["records"]
    newer = load_json(BASE + "v4/panels/metrics/all-episode-metrics.json")
    records = {"p135": validation + adapters, "p2": newer["p2"], "p2u": newer["p2u"]}
    results = {}
    all_counts = {"positive": 0, "zero": 0, "negative": 0}
    for panel, _ in PANELS:
        evidence = analysis["concentration"]["per_panel"][panel]
        by_arm_task = defaultdict(list)
        for row in records[panel]:
            if row["arm"] in ("random_valid", "learned_adapter"):
                by_arm_task[(row["arm"], row["task"])].append(row)
        tasks = sorted(evidence["domains"], key=lambda task: (evidence["domains"][task], task))
        assert len(tasks) == {"p135": 12, "p2": 11, "p2u": 12}[panel]
        assert set(tasks) == set(evidence["per_task_difference"])
        assert set(tasks) == set(analysis["arms"][panel]["learned_adapter_seed_mean"]["per_task"])
        points = []
        panel_counts = {"positive": 0, "zero": 0, "negative": 0}
        for task in tasks:
            trained = by_arm_task["learned_adapter", task]
            random = by_arm_task["random_valid", task]
            # Evidence: two declared algorithms, three training seeds and five
            # control evaluation seeds in the respective all-episode-metrics JSONs.
            assert len(trained) == 6 and {r["training_seed"] for r in trained} == {17, 29, 71}
            assert len(random) == 10 and {r["seed"] for r in random} == {17, 5077, 6131, 7409, 8527}
            assert {r["algorithm"] for r in trained} == {r["algorithm"] for r in random} == {
                "best_first_add_greedy", "best_first_add_w3"}
            trained_m1 = sum(row["auc"] for row in trained) / len(trained)
            control_m1 = sum(row["auc"] for row in random) / len(random)
            gain = trained_m1 - control_m1
            # Evidence: v4/panels/metrics/analysis.json per-task M1 and concentration.
            assert_3dp(trained_m1, analysis["arms"][panel]["learned_adapter_seed_mean"]["per_task"][task])
            assert_3dp(gain, evidence["per_task_difference"][task])
            domain = evidence["domains"][task]
            assert domain in DOMAIN_COLOURS and task.split("/")[-1].startswith(domain + "-expanded-")
            category = "positive" if gain > 0 else "negative" if gain < 0 else "zero"
            panel_counts[category] += 1
            points.append((task, domain, gain))
        assert panel_counts == evidence["counts"]
        for category in all_counts:
            all_counts[category] += panel_counts[category]
        results[panel] = points
    # Evidence: v4/panels/metrics/analysis.json concentration.all_36_counts
    # (historical key name; actually 35 tasks in three panels).
    assert all_counts == analysis["concentration"]["all_36_counts"]
    assert all_counts == {"positive": 22, "zero": 12, "negative": 1}
    assert analysis["concentration"]["per_panel"]["p2u"]["counts"] == {
        "positive": 4, "zero": 8, "negative": 0}
    return results, all_counts


def draw(results, counts):
    fig, axes = plt.subplots(3, 1, figsize=(6.35, 6.98), sharex=True,
                             gridspec_kw={"height_ratios": [12, 11, 12]})
    for ax, (panel, title) in zip(axes, PANELS):
        rows = results[panel]
        ys = list(range(len(rows) - 1, -1, -1))
        ax.axvline(0, color=ARM_STYLE["random_valid"]["color"], linewidth=0.75, zorder=0)
        for y, (task, domain, value) in zip(ys, rows):
            color = DOMAIN_COLOURS[domain]
            ax.plot([0, value], [y, y], color=ARM_STYLE["learned_adapter_seed_mean"]["color"],
                    linewidth=1.0, alpha=.78, zorder=1)
            ax.scatter(value, y, color=color, edgecolor="white", linewidth=0.35,
                       s=24, zorder=2)
        labels = [f"{domain.replace('_', ' ')} ·{task.rsplit('-', 1)[-1]}"
                  for task, domain, _ in rows]
        ax.set_yticks(ys, labels, fontsize=7.1)
        for text, (_, domain, _) in zip(ax.get_yticklabels(), rows):
            text.set_color(DOMAIN_COLOURS[domain])
        ax.set_xlim(-.13, 1.04)
        ax.set_ylim(-.65, len(rows) - .32)
        ax.set_title(f"{title}  ({len(rows)} tasks)", loc="left", fontsize=8,
                     fontweight="bold", pad=5)
        ax.tick_params(axis="y", length=0, pad=4)
        ax.tick_params(axis="x", labelsize=7, length=2.5, width=.6)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_linewidth(.6)
    # Evidence: exact counts in analysis.json concentration.all_36_counts and
    # concentration.per_panel.p2u.counts; equality checked in task_gains().
    fig.text(.35, .977, f"{counts['positive']} > 0     {counts['zero']} = 0     {counts['negative']} < 0",
             fontsize=8, color="#303030", ha="left", va="top")
    p2u_positive = sum(value > 0 for _, _, value in results["p2u"])
    p2u_zero = sum(value == 0 for _, _, value in results["p2u"])
    axes[-1].text(.99, 1.025, f"{p2u_positive} > 0  ·  {p2u_zero} = 0",
                  transform=axes[-1].transAxes, fontsize=7.2, ha="right", va="bottom")
    axes[-1].set_xticks((0, .25, .5, .75, 1), ("0", ".25", ".5", ".75", "1"))
    axes[-1].set_xlabel("Adapter − random-valid M1 (per task)", fontsize=8)
    fig.subplots_adjust(left=.35, right=.975, top=.915, bottom=.087, hspace=.34)
    for extension in ("pdf", "svg"):
        fig.savefig(HERE / f"fig_task_gains.{extension}", bbox_inches="tight", pad_inches=.04)
    fig.savefig(HERE / "fig_task_gains.png", dpi=300, bbox_inches="tight", pad_inches=.04)
    plt.close(fig)


if __name__ == "__main__":
    draw(*task_gains())
