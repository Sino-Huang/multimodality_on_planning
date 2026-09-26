"""Node-choice solve curves and held-out h_add rank preferences.

Run: source ~/cd_vlaplan && python /absolute/path/fig_node_choice.py [EVIDENCE_ROOT]
Panels a-c reuse fig_budget_curves.evidence_curves and all its evidence assertions.
Panel d pools all non-singleton menus from both held-out panels and three training
seeds. Recover h_add from prior trusted enqueued admissions, rank increasingly,
break ties by the recorded choice label, and bin floor(5 * zero_based_rank / n).
The uniform comparator averages 1/n over every member of these SAME menus.
Forced singleton decisions are excluded from both the histogram and heap-head
agreement, matching the stored teacher_decisions metrics. No images are used.
"""
from collections import Counter
import gzip
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.text import Text
from matplotlib.transforms import Bbox
import numpy as np
from PIL import Image

from _style import ARM_STYLE, EVIDENCE_ROOT, assert_3dp, load_json
from fig_budget_curves import BUDGETS, TRAINING_SEEDS, evidence_curves

HERE = Path(__file__).resolve().parent
BASE = "outputs/choice-frontier/"
W, H = 5.5, 2.05
PANELS = (("p135", "a  Development", 12, 7),
          ("p2", "b  Held-out 1", 11, 8),
          ("p2u", "c  Held-out 2", 12, 7))
ARMS = (("exact_reference", "Exact reference"),
        ("exact-eps-0.25", "Exact-ε 0.25"),
        ("exact-eps-0.50", "Exact-ε 0.50"),
        ("exact-eps-0.75", "Exact-ε 0.75"),
        ("learned_adapter_seed_mean", "Adapter (3 seeds; range)"),
        ("random_valid", "Random-valid (5 seeds)"),
        ("zero_shot_base", "Zero-shot base"))
# Each panel has a distinct population or diagnostic role; no fitted statistics.
PANEL_SPEC = (
    {"panel": "a", "claim": "Development solve-budget performance", "plot": "line"},
    {"panel": "b", "claim": "Screened held-out performance", "plot": "line"},
    {"panel": "c", "claim": "Unscreened held-out performance", "plot": "line"},
    {"panel": "d", "claim": "Held-out picks favour low h_add ranks", "plot": "histogram"},
)


def held_out_preferences():
    metrics = load_json(BASE + "v4/panels/metrics/all-episode-metrics.json")
    stats = {}
    for panel, episodes in (("p2", 66), ("p2u", 72)):
        rows = [r for r in metrics[panel] if r["arm"] == "learned_adapter"]
        assert len(rows) == episodes
        assert Counter(r["training_seed"] for r in rows) == {
            s: episodes // 3 for s in TRAINING_SEEDS}
        observed, uniform = np.zeros(5, dtype=int), np.zeros(5)
        agreements, chance, decisions, forced = 0, 0.0, 0, 0
        paths = []
        for row in rows:
            relative = (BASE + f"v4/panels/{panel}/evaluation/episodes/"
                        f"{row['task'].replace('/', '__')}/{row['algorithm']}-"
                        f"learned_adapter-s{row['training_seed']}-17.json.gz")
            paths.append(relative)
            with gzip.open(EVIDENCE_ROOT / relative, "rt") as stream:
                episode = json.load(stream)
            assert episode["task_id"] == row["task"]
            assert episode["training_seed"] == row["training_seed"]
            assert episode["algorithm"] == row["algorithm"]
            assert len(episode["events"]) == row["decisions"]
            heuristic, previous_head = {}, None
            n, a, c = 0, 0, 0.0
            for index, event in enumerate(episode["events"]):
                assert event["decision_index"] == index
                menu = event["menu"]
                runtime = event["trusted_runtime_result"]
                choice = json.loads(event["raw_output"])["expand_choice"]
                assert runtime["accepted"]
                assert len({v["choice"] for v in menu}) == len(menu)
                selected = next(v["state_ref"] for v in menu if v["choice"] == choice)
                assert selected == runtime["expanded_state_id"]
                if len(menu) > 1:
                    # Availability is checked for EVERY member of EVERY eligible menu.
                    assert all(v["state_ref"] in heuristic for v in menu)
                    ordered = sorted(menu, key=lambda v: (heuristic[v["state_ref"]], v["choice"]))
                    rank = next(i for i, v in enumerate(ordered) if v["choice"] == choice)
                    observed[min(4, 5 * rank // len(menu))] += 1
                    for position in range(len(menu)):
                        uniform[min(4, 5 * position // len(menu))] += 1 / len(menu)
                    assert previous_head["state_id"] in {v["state_ref"] for v in menu}
                    a += selected == previous_head["state_id"]
                    c += 1 / len(menu)
                    n += 1
                else:
                    assert len(menu) == 1
                    forced += 1
                for admission in runtime.get("admissions", []):
                    result = admission["trusted_runtime_result"]
                    if result.get("status") == "enqueued":
                        assert math.isfinite(result["h"]) and result["h"] >= 0
                        expected = (result["h"] if row["algorithm"] == "best_first_add_greedy"
                                    else result["g"] + 3 * result["h"])
                        assert result["priority"] == expected
                        heuristic[result["target_state_id"]] = result["h"]
                previous_head = runtime.get("frontier_after", {}).get("head")
            assert (a, n) == (row["teacher_agreements"], row["teacher_decisions"])
            assert math.isclose(c, row["teacher_chance_sum"], abs_tol=1e-10)
            agreements += a
            chance += c
            decisions += n
        assert observed.sum() == decisions
        assert math.isclose(uniform.sum(), decisions, abs_tol=1e-8)
        stats[panel] = dict(observed=observed.tolist(), uniform=uniform.tolist(),
                            decisions=decisions, agreements=agreements, chance=chance,
                            forced_omitted=forced, episode_paths=paths)
    observed = np.sum([v["observed"] for v in stats.values()], axis=0)
    uniform = np.sum([v["uniform"] for v in stats.values()], axis=0)
    n = sum(v["decisions"] for v in stats.values())
    assert int(observed.sum()) == n and math.isclose(uniform.sum(), n, abs_tol=1e-8)
    assert n == 3373 and observed.tolist() == [1566, 683, 447, 366, 311]
    assert_3dp(uniform.tolist(), [842.035, 685.283, 672.684, 685.283, 487.715])
    assert sum(v["agreements"] for v in stats.values()) == 813
    assert_3dp(sum(v["chance"] for v in stats.values()), 418.752)
    return observed, uniform, stats


def geometry(fig, axes, panel_bounds):
    """Check all visible labels, not just hand-placed annotations."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    texts = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text()]
    bounds = []
    for text in texts:
        assert text.get_fontsize() >= 6, text.get_text()
        box = text.get_window_extent(renderer)
        assert fig.bbox.contains(box.x0, box.y0) and fig.bbox.contains(box.x1, box.y1), text.get_text()
        bounds.append((text, box))
    for i, (a, box_a) in enumerate(bounds):
        for b, box_b in bounds[i + 1:]:
            intersection = Bbox.intersection(box_a, box_b)
            assert intersection is None or intersection.width <= .2 or intersection.height <= .2, (
                a.get_text(), b.get_text())
    for ax, limits in zip(axes, panel_bounds):
        panel_box = Bbox.from_extents(*limits).transformed(fig.transFigure)
        owned = [t for t in ax.findobj(Text) if t.get_visible() and t.get_text()]
        for text in owned:
            box = text.get_window_extent(renderer)
            assert panel_box.contains(box.x0, box.y0) and panel_box.contains(box.x1, box.y1), text.get_text()
    assert not any(ax.images for ax in axes), "This quantitative figure has no images."
    print(f"GEOMETRY PASS: {len(texts)} labels >=6 pt; canvas/panel containment; "
          f"no text-text overlap; no images; {W} x {H} in")


def draw(curves, observed, uniform):
    fig = plt.figure(figsize=(W, H), dpi=300, facecolor="white")
    # Slots include labels and gutters; the first three share the solve-fraction axis.
    positions = ((.065, .225, .195, .465), (.294, .225, .195, .465),
                 (.523, .225, .195, .465), (.815, .225, .175, .465))
    axes = []
    for i, position in enumerate(positions):
        axes.append(fig.add_axes(position, sharey=axes[0] if 0 < i < 3 else None))
    line_styles = {"exact_reference": "-", "exact-eps-0.25": (0, (4, 1)),
                   "exact-eps-0.50": (0, (2, 1)), "exact-eps-0.75": (0, (1, 1)),
                   "learned_adapter_seed_mean": "-", "random_valid": "--", "zero_shot_base": ":"}
    for ax, (panel, title, tasks, domains) in zip(axes, PANELS):
        plot_curves, seeded = curves[panel]
        color = ARM_STYLE["learned_adapter_seed_mean"]["color"]
        ax.fill_between(BUDGETS, np.min(list(seeded.values()), axis=0),
                        np.max(list(seeded.values()), axis=0), color=color, alpha=.15, lw=0)
        for arm, label in ARMS:
            if arm not in plot_curves:
                continue
            style = ARM_STYLE[arm]
            ax.plot(BUDGETS, plot_curves[arm], label=label, color=style["color"],
                    marker=style["marker"], markerfacecolor=style["facecolor"],
                    markeredgecolor=style["edgecolor"], markeredgewidth=.55, markersize=2.3,
                    linewidth=1.15 if arm == "learned_adapter_seed_mean" else .85,
                    linestyle=line_styles[arm], zorder=4 if arm == "learned_adapter_seed_mean" else 2)
        ax.set_xlim(.975, 2.025)
        ax.set_ylim(-.025, 1.04)
        ax.set_xticks(BUDGETS, ("1", "1.25", "1.5", "1.75", "2"))
        ax.set_yticks((0, .25, .5, .75, 1), ("0", ".25", ".5", ".75", "1"))
        ax.set_xlabel("Budget multiplier", fontsize=6.5, labelpad=3)
        ax.text(0, 1.205, title, transform=ax.transAxes, fontsize=7, weight="bold")
        ax.text(0, 1.085, f"{tasks} tasks, {domains} domains", transform=ax.transAxes, fontsize=6)
        if ax is not axes[0]:
            ax.tick_params(labelleft=False)
        assert np.allclose(plot_curves["learned_adapter_seed_mean"], np.mean(list(seeded.values()), axis=0))
    axes[0].set_ylabel("Fraction solved", fontsize=6.5, labelpad=3)
    ax = axes[3]
    n = int(observed.sum())
    edges = np.arange(6) * 20
    ax.bar(edges[:-1], observed / n, width=20, align="edge", color="#D55E00",
           alpha=.8, edgecolor="white", linewidth=.4)
    ax.stairs(uniform / n, edges, color="#777777", linestyle="--", linewidth=1.2)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, .6)
    ax.set_xticks((0, 50, 100), ("0", "50", "100"))
    ax.get_xticklabels()[-1].set_horizontalalignment("right")
    ax.set_yticks((0, .2, .4, .6), ("0", ".2", ".4", ".6"))
    ax.set_xlabel("h_add rank percentile", fontsize=6, labelpad=3)
    ax.set_ylabel("Fraction of choices", fontsize=6.5, labelpad=3)
    ax.text(0, 1.205, "d  Learned picks", transform=ax.transAxes, fontsize=7, weight="bold")
    ax.text(0, 1.085, "Held-out 1 + 2", transform=ax.transAxes, fontsize=6)
    for ax in axes:
        ax.tick_params(axis="both", labelsize=6, length=2, width=.6, pad=2)
        ax.spines[["top", "right"]].set_visible(False)
        for side in ("bottom", "left"):
            ax.spines[side].set_linewidth(.6)
    handles, labels = axes[0].get_legend_handles_labels()
    handles.append(Line2D([], [], color="#777777", linestyle="--", linewidth=1.2))
    labels.append("Uniform on same menus")
    # Two rows, with the reference and its three corruption rungs on the first.
    order = (0, 4, 1, 5, 2, 6, 3, 7)
    legend = fig.legend([handles[i] for i in order], [labels[i] for i in order],
                        ncol=4, loc="upper center", bbox_to_anchor=(.515, 1.01),
                        frameon=False, fontsize=6, columnspacing=1, handlelength=1.8,
                        handletextpad=.4, labelspacing=.4, borderaxespad=.4)
    panel_bounds = ((0, .03, .277, .83), (.277, .03, .506, .83),
                    (.506, .03, .737, .83), (.737, .03, 1, .83))
    geometry(fig, axes, panel_bounds)
    for extension in ("pdf", "svg", "png"):
        fig.savefig(HERE / f"fig_node_choice.{extension}", dpi=300)
    assert "<text" in (HERE / "fig_node_choice.svg").read_text()
    with Image.open(HERE / "fig_node_choice.png") as image:
        assert image.size == (1650, 615)
    print("EXPORT PASS: editable SVG text; PDF/SVG/PNG; PNG 1650 x 615 pixels")
    plt.close(fig)


def main():
    curves = evidence_curves()
    # Exact populations and random seed multiplicities from the same metric inputs.
    held = load_json(BASE + "v4/panels/metrics/all-episode-metrics.json")
    rows_by_panel = {"p135": load_json(BASE + "v2/metrics/all-episode-metrics.json")["records"],
                     "p2": held["p2"], "p2u": held["p2u"]}
    for panel, _, tasks, domains in PANELS:
        rows = rows_by_panel[panel]
        assert len({r["task"] for r in rows}) == tasks
        assert len({r["task"].split("/")[-1].split("-expanded-")[0] for r in rows}) == domains
        random = [r for r in rows if r["arm"] == "random_valid"]
        assert len({r["seed"] for r in random}) == 5
        assert set(Counter((r["task"], r["algorithm"]) for r in random).values()) == {5}
    observed, uniform, stats = held_out_preferences()
    draw(curves, observed, uniform)
    print("EVIDENCE PASS: reused budget/AUC/seed-17 assertions; 5 random seeds; all held-out menu h_add "
          "available; priority equations; all episode heap-head/chance metrics match")
    print("CURVES " + json.dumps({p: {"curves": c, "training_seeds": s} for p, (c, s) in curves.items()}))
    print("PREFERENCES " + json.dumps(stats))


if __name__ == "__main__":
    main()
