"""Figure 1: a real search trace, unmatched development data costs, and channel corruption.

Run from figures/: python fig_teaser.py [EVIDENCE_ROOT]. All drawn values are
checked against the read-only episode, baseline, development, and stress files.
"""
import csv
import gzip
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch
from PIL import Image

from _style import EVIDENCE_ROOT, assert_3dp, load_json

HERE = Path(__file__).resolve().parent
FERRY = Path("outputs/expanded-study/v1/panel-v2/views/ferry-compact-915000")
BASE = Path("outputs/expanded-study/v1/baseline/episodes")
ALGO_STYLE = {"bfs": "#0072B2", "best_first_width": "#009E73",
              "best_first_add_w3": "#E69F00", "best_first_add_greedy": "#D55E00"}
INK, MUTED, PALE = "#213548", "#596775", "#DFE5E9"


def gz_json(path):
    with gzip.open(EVIDENCE_ROOT / path, "rt") as stream:
        return json.load(stream)


def episode_assertions():
    ep = gz_json(BASE / "text-state/expanded-final__ferry-compact-915000/best_first_add_greedy-exact_reference.json.gz")
    manifest = load_json(FERRY / "manifest.json")
    catalog = gz_json(FERRY / "scenes/catalog.json.gz")
    events = ep["events"]
    assert manifest["split"] == "test" and ep["task_id"] == manifest["task_id"]
    assert ep["result"]["goal_reached"] and (ep["result"]["decision_count"], ep["result"]["expansion_count"]) == (11, 4)
    assert manifest["reference_costs"]["best_first_add_greedy"] == {"decisions": 11, "expansions": 4}
    assert manifest["task_context"]["canonical_goal"] == ["atom", "at", ["c0", "l1"]]
    assert len(events) == 11 and all(event["accepted"] for event in events)
    assert [event["input"]["current"]["state_id"] for event in events] == ["s0", "s0", "s2", "s2", "s2", "s3", "s3", "s3", "s5", "s5", "s5"]
    assert [events[i]["input"]["current"]["h"] for i in (0, 2, 5, 8)] == [3, 3, 2, 1]
    assert events[0]["view"]["state_representation"] == "scene-only-128-unlabelled-v1"
    assert ["current-state", 0, 0] in events[0]["view"]["input_pages"]
    # Reconstruct state edges from the emitted action matched to the supplied row;
    # successor_state is a scene-catalog index, NOT an episode state ID.
    edges = []
    for event in events:
        emission = json.loads(event["raw_output"])
        source = event["input"]["current"]["state_id"]
        assert emission["source_state_id"] == source
        rows = event["input"]["successor_candidates"]
        match = [dict(zip(rows["columns"], row)) for row in rows["rows"]
                 if row[rows["columns"].index("action")] == [emission["action"]["name"], *emission["action"]["args"]]]
        assert len(match) == 1
        if event["index"] == 8:
            assert (match[0]["h"], match[0]["target_state_id"]) == (0, "s6")
        edges.append((source, match[0]["target_state_id"], emission["action"]))
    goal_id = edges[8][1]
    assert edges[8][2] == {"name": "debark", "args": ["c0", "l1"]}
    # A duplicate target can arise from an alternative stub; take the first edge
    # along the four on-path source states, rather than silently treating IDs as images.
    plan_sources = ["s0", "s2", "s3", "s5"]
    path = []
    target = goal_id
    for source in reversed(plan_sources):
        choices = [(idx, action) for idx, (src, dst, action) in enumerate(edges) if src == source and dst == target]
        assert len(choices) == 1, (source, target, choices)
        index, action = choices[0]
        path.append((index, action))
        target = source
    path.reverse()
    assert target == "s0" and [i for i, _ in path] == [1, 2, 7, 8]
    supplied = catalog["path_bindings"][1]["supplied_actions"]
    assert [f"({action['name']} {' '.join(action['args'])})" for _, action in path] == supplied
    assert [events[i]["input"]["current"]["h"] for i, _ in path] == [3, 3, 2, 1]
    with Image.open(EVIDENCE_ROOT / FERRY / "unlabelled/state-000000.png") as cached:
        assert cached.size == (128, 128)
        image = cached.convert("RGB").copy()
    # The scene's three purple pier spans, not a labelled catalog frame.
    purple = (179, 165, 218)
    locations = [x for x in range(128) if image.getpixel((x, 96)) == purple]
    spans = []
    for x in locations:
        if not spans or x != spans[-1][-1] + 1:
            spans.append([x])
        else:
            spans[-1].append(x)
    assert [(span[0], span[-1]) for span in spans] == [(4, 40), (45, 81), (86, 122)]
    return image, spans, events, edges


def grid_and_development():
    algos = list(ALGO_STYLE)
    modalities = ["text-state", "visual-state", "multimodal-state"]
    arms = ["pretrained_base", "process_sft", "random_valid", "exact_reference"]
    with (EVIDENCE_ROOT / "docs/experiments/expanded-study/synthesis-v1/baseline-summary.csv").open(newline="") as stream:
        rows = {(row["modality"], row["algorithm"], row["arm"]): row for row in csv.DictReader(stream)}
    assert len(rows) == 48 and set(rows) == {(m, a, arm) for m in modalities for a in algos for arm in arms}
    for modality in modalities:
        version = "v3" if modality == "text-state" else "v5"
        for algo in algos:
            report = load_json(f"outputs/matched_modalities/{version}/training/{modality}/{algo}/report.json")
            assert (report["algorithm"], report["train_records"], report["seed"], report["steps"]) == (
                algo, 512, 17, 16)
    expected = {"bfs": (0, 0, 0, 15), "best_first_width": (0, 0, 0, 17),
                "best_first_add_w3": (20, 18, 22, 24),
                "best_first_add_greedy": (22, 22, 21, 24)}
    grid = {}
    for algo in algos:
        values = expected[algo]
        for modality, success in zip(modalities, values[:3]):
            for arm, count in (("pretrained_base", 0), ("process_sft", success),
                               ("random_valid", values[3]), ("exact_reference", 24)):
                row = rows[(modality, algo, arm)]
                assert (int(row["episodes"]), int(row["successes"])) == (24, count)
                assert_3dp(row["success_rate"], count / 24)
            grid[(algo, modality)] = success / 24
        obs = [int(rows[(m, algo, "process_sft")]["successes"]) for m in modalities]
        assert_3dp((sum(obs) / 72, min(obs) / 24, max(obs) / 24, values[3] / 24), {
            "bfs": (0, 0, 0, .625), "best_first_width": (0, 0, 0, 17 / 24),
            "best_first_add_w3": (60 / 72, .75, 22 / 24, 1),
            "best_first_add_greedy": (65 / 72, 21 / 24, 22 / 24, 1)}[algo])
    prior = load_json("docs/experiments/deadline-study/prior-evidence.json")
    bfs = next(stage for stage in prior["historical_bfs_stages"] if stage["stage"] == "v8")
    bfws = load_json("data/bfws_phase_v1/issue59-distributed-terminal/adjudication-report.json")
    visual = prior["issue75"]
    training = load_json("outputs/visual_development/issue75-32k-v5/attempt-001/training.json")
    trains = {r["algorithm"]: r for r in training["training_runs"]}
    assert (bfs["selected_tasks"], len(bfs["selected_task_ids"])) == (15, 15)
    assert len(bfws["coverage"]["task_ids"]) == 15 and bfws["outcome"] == "PASS"
    assert len(trains) == 4 and len(visual["evaluation_seeds"]) == 5
    assert visual["evaluation_seeds"] == [17, 29, 43, 71, 101]
    completion = (EVIDENCE_ROOT / "docs/experiments/issue75/v5-completion.md").read_text()
    for expected_line in ("BFS | 100% (75/75) | 70.7% (53/75)",
                          "BFWS | 66.7% (50/75) | 52.0% (39/75)",
                          "Additive w3 | 100% (60/60) | 100% (60/60)",
                          "Additive greedy | 100% (60/60) | 100% (60/60)"):
        assert expected_line in completion
    assert 75 // len(visual["evaluation_seeds"]) == 15
    bmetrics = bfs["metrics"]
    dev = [("bfs", "text", load_json("data/bfs_pilot_v6/ms-swift-process/manifest.json")["counts"]["train"],
            bmetrics["process_sft_invariant_valid_success"], bmetrics["random_valid_invariant_valid_success"]),
           ("best_first_width", "text", load_json("data/bfws_phase_v1/corpus-release/training/manifest.json")["counts"]["train"],
            bfws["process_sft_invariant_valid_success"], bfws["random_valid_invariant_valid_success"])]
    for algo, issue, doc in (("best_first_add_w3", 65, "issue-65-best-first-add-w3-development.md"),
                             ("best_first_add_greedy", 66, "issue-66-best-first-add-greedy-development.md")):
        folder = f"data/best_first_paired_phase_v3/issue{issue}-{'w3' if issue == 65 else 'greedy'}-sft/manifest.json"
        manifest = load_json(folder)
        report = load_json(f"outputs/best_first_phase/issue{issue}-v1/adjudication/report.json")
        assert manifest["algorithm"] == algo and report["outcome"] == "PASS"
        assert "process SFT: 115/115 successes" in (EVIDENCE_ROOT / "docs" / doc).read_text()
        assert_3dp(report["metrics"]["process_sft_invariant_valid_success"], 115 / 115)
        dev.append((algo, "text", manifest["counts"]["train"],
                    report["metrics"]["process_sft_invariant_valid_success"],
                    report["metrics"]["random_valid_invariant_valid_success"]))
    for algo in algos:
        vals = visual["metrics"][algo]["invariant_valid_success"]
        dev.append((algo, "visual", trains[algo]["train_records"], vals["process_sft"], vals["random_valid"]))
    expected_dev = [("bfs", "text", 12994, 1, 1), ("best_first_width", "text", 47780, 14 / 15, 7 / 15),
                    ("best_first_add_w3", "text", 9398, 1, 1),
                    ("best_first_add_greedy", "text", 8342, 1, 1),
                    ("bfs", "visual", 11911, 1, 53 / 75),
                    ("best_first_width", "visual", 14225, 50 / 75, 39 / 75),
                    ("best_first_add_w3", "visual", 9398, 1, 1),
                    ("best_first_add_greedy", "visual", 8342, 1, 1)]
    for row, want in zip(dev, expected_dev):
        assert row[:3] == want[:3]
        assert_3dp(row[3:], want[3:])
    assert len(dev) == 8 and min(item[2] for item in dev) / 512 > 10
    # Multimodal lacks a large-corpus partner; second-backbone points are omitted.
    return grid, dev


def corruption():
    analysis = load_json("outputs/expanded-study/v1/modality-stress/analysis.json")
    groups = {row["group"]: row for row in analysis["contrasts"]["degradation_by_family_modality"]}
    plotted = ["text-shuffled__text-state", "text-shuffled__multimodal-state",
               "visual-blank__visual-state", "visual-blank__multimodal-state"]
    expected = [(-17 / 18, -1, -15 / 18), (-13 / 18, -16 / 18, -9 / 18),
                (-1 / 18, -3 / 18, 0), (-2 / 18, -5 / 18, 0)]
    for key, want in zip(plotted, expected):
        row = groups[key]
        assert (row["tasks"], row["cells"], row["descriptive_only"]) == (9, 18, False)
        lohi = row["degradation_interval_95"]
        assert_3dp((row["mean_degradation"], lohi["low"], lohi["high"]), want)
    for modality in ("visual-state", "multimodal-state"):
        blank = groups[f"visual-blank__{modality}"]
        degraded = groups[f"visual-degraded__{modality}"]
        for field in ("mean_degradation", "degradation_interval_95"):
            assert blank[field] == degraded[field]
        paired = {}
        for cell in analysis["cells"]:
            if cell["modality"] == modality and cell["family"] in ("visual-blank", "visual-degraded"):
                paired.setdefault((cell["task_id"], cell["algorithm"]), {})[cell["family"]] = cell["learned_corrupted"]
        assert len(paired) == 18 and all(len(pair) == 2 and pair["visual-blank"] == pair["visual-degraded"] for pair in paired.values())
        assert blank["degradation_interval_95"]["high"] == 0
    assert_3dp(max(abs(groups[key]["mean_degradation"]) for key in plotted[2:]), .111)
    assert_3dp(abs(groups[plotted[0]]["mean_degradation"]), .944)
    # Text masking breaks output format; the channel claim rests on shuffling.
    return [groups["text-shuffled__multimodal-state"], groups["visual-blank__multimodal-state"]]


def draw():
    image, spans, events, edges = episode_assertions()
    grid, dev = grid_and_development()
    contrast = corruption()
    fig = plt.figure(figsize=(5.5, 1.85), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1]); ax.set(xlim=(0, 5.5), ylim=(0, 1.85)); ax.axis("off")
    def txt(x, y, text, fs=6.2, color=INK, **kw):
        return ax.text(x, y, text, fontsize=fs, color=color, **kw)
    txt(.04, 1.81, "a  The trace, not the plan", fs=7.5, weight="bold", va="top")
    txt(.04, 1.65, "one operation per model call", color=MUTED)
    ax.imshow(image, extent=(.04, .45, .95, 1.36), interpolation="nearest", aspect="auto")
    for label, span in zip(("l0", "l1", "l2"), spans):
        txt(.04 + .41 * (span[0] + span[-1]) / 256, .90, label, ha="center", fs=6)
    txt(.04, .76, "goal:\nat(c0,l1)", fs=6, va="top", linespacing=1)
    txt(.62, 1.56, "state : h_add", fs=6, color=MUTED)
    row_y = lambda i: 1.45 - i * .099
    groups = [("s0", 3, 0), ("s2", 3, 2), ("s3", 2, 5), ("s5", 1, 8)]
    for (name, h, index), (_, _, next_index) in zip(groups, groups[1:]):
        ax.add_patch(FancyArrowPatch((.58, row_y(index) - .05), (.58, row_y(next_index) + .05),
                                     arrowstyle="-|>", mutation_scale=6, lw=1.2, color=INK))
    for name, h, index in groups:
        ax.add_patch(Circle((.58, row_y(index)), .045, facecolor="white", edgecolor=INK, lw=.8))
        txt(.66, row_y(index), f"{name}:{h}", fs=6, va="center")
    txt(.60, .26, "goal:0", fs=6, weight="bold")
    for index, event in enumerate(events):
        y = row_y(index)
        action = json.loads(event["raw_output"])["action"]
        on_path = index in (1, 2, 7, 8)
        color = INK if on_path else MUTED
        ax.plot([.85, .91], [y, y], lw=1.2 if on_path else .7, color=color)
        ax.add_patch(Circle((.97, y), .066 if index >= 9 else .047,
                            facecolor=color if on_path else "white", edgecolor=color, lw=.8))
        txt(.97, y, str(index + 1), fs=6, color="white" if on_path else MUTED,
            weight="bold" if on_path else "normal", ha="center", va="center")
        txt(1.06, y, f"{action['name']}({','.join(action['args'])})", fs=6, color=color,
            weight="bold" if on_path else "normal", va="center")
    txt(.04, .12, "bold: actual plan · numbered: reasoning trace", fs=6)

    txt(1.96, 1.81, "b  An order of magnitude apart", fs=7.5, weight="bold", va="top")
    txt(1.96, 1.65, "success rate · solid text · dashed visual", fs=6, color=MUTED)
    for x, label, algo in ((2.14, "BFS", "bfs"), (2.59, "BFWS", "best_first_width"),
                           (3.14, "WA*", "best_first_add_w3"), (3.68, "GBF", "best_first_add_greedy")):
        ax.plot([x, x + .11], [1.49, 1.49], color=ALGO_STYLE[algo], lw=1.4)
        txt(x + .14, 1.49, label, fs=6, color=ALGO_STYLE[algo], va="center", weight="bold")
    xlog = lambda n: 2.14 + 2.28 * (math.log(n) - math.log(512)) / (math.log(50000) - math.log(512))
    yscale = lambda v: .42 + .91 * v
    for value in (0, .5, 1):
        y = yscale(value)
        ax.plot([2.14, 4.42], [y, y], color=PALE, lw=.55)
        txt(2.07, y, f"{value:g}", fs=6, ha="right", va="center", color=MUTED)
    for records, label in ((512, "512"), (2000, "2k"), (10000, "10k"), (50000, "50k")):
        x = xlog(records)
        ax.plot([x, x], [.39, .42], color=MUTED, lw=.6)
        txt(x, .29, label, fs=6, color=MUTED, ha="center")
    for algo, modality, records, rate, _ in dev:
        color = ALGO_STYLE[algo]
        line = "-" if modality == "text" else (0, (3, 2))
        main_rate = grid[(algo, f"{modality}-state")]
        xs, ys = [xlog(512), xlog(records)], [yscale(main_rate), yscale(rate)]
        ax.plot(xs, ys, color=color, lw=1.15, linestyle=line,
                marker="s" if modality == "text" else "^", markersize=4.2,
                markerfacecolor="white" if modality == "text" else color,
                markeredgecolor=color, markeredgewidth=1.0, zorder=3 if modality == "visual" else 2)
    txt(3.22, .11, "training records (log scale)", fs=6, color=MUTED, ha="center")

    txt(4.45, 1.81, "c  Channel: text", fs=7.5, weight="bold", va="top")
    txt(4.46, 1.64, "multimodal adapters\n95% CI", fs=6, color=MUTED,
        va="top", linespacing=1.1)
    ydelta = lambda v: .47 + .86 * (v + 1)
    txt(4.47, .90, "Δ success", fs=6, color=MUTED, va="center", ha="center", rotation=90)
    for value, label in ((-1, "−1"), (-.5, "−.5"), (0, "0")):
        y = ydelta(value)
        txt(4.69, y, label, fs=6, color=MUTED, ha="right", va="center")
        ax.plot([4.73, 5.44], [y, y], color=PALE if value != 0 else MUTED,
                ls="-" if value != 0 else "--", lw=.55 if value != 0 else .7)
    for row, x, label in zip(contrast, (4.98, 5.30), ("shuffle\ntext", "blank\nimages")):
        ci = row["degradation_interval_95"]
        ax.plot([x, x], [ydelta(ci["low"]), ydelta(ci["high"])], color=INK, lw=1.35)
        for end in ("low", "high"):
            yy = ydelta(ci[end])
            ax.plot([x - .035, x + .035], [yy, yy], color=INK, lw=.8)
        y = ydelta(row["mean_degradation"])
        ax.plot(x, y, marker="o", ms=4.4, color=INK)
        txt(x + .075 if x < 5 else x - .075, y,
            f"{row['mean_degradation']:.2f}".replace("-", "−"),
            fs=6, ha="left" if x < 5 else "right", va="center")
        txt(x, .36, label, fs=6, ha="center", va="top", linespacing=1.08)
    for extension in ("pdf", "svg", "png"):
        fig.savefig(HERE / f"fig_teaser.{extension}", dpi=300 if extension == "png" else None)
    plt.close(fig)
    print("fig_teaser: 11-step trace / 48 grid rows / eight evidenced dev endpoints / two plotted multimodal corruption groups asserted")


if __name__ == "__main__":
    draw()
