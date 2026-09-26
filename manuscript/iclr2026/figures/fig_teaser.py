"""Figure 1: BFS/BFWS execution, image-based node choice, and FOLIO transfer.

Run: source ~/cd_vlaplan && python /absolute/path/fig_teaser.py [EVIDENCE_ROOT].
Every observation is checked against read-only evidence before rendering.
"""
import csv
import gzip
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.transforms import Bbox
from PIL import Image

from _style import EVIDENCE_ROOT, assert_3dp, load_json

HERE = Path(__file__).resolve().parent
FERRY = Path("outputs/expanded-study/v1/panel-v2/views/ferry-compact-915000")
BASE = Path("outputs/expanded-study/v1/baseline/episodes")
ALGO_STYLE = {"bfs": "#0072B2", "best_first_width": "#009E73"}
OBS_STYLE = {"text": "s", "visual": "^", "multimodal": "o"}
INK, MUTED, PALE = "#213548", "#596775", "#DFE5E9"


def gz_json(path):
    with gzip.open(EVIDENCE_ROOT / path, "rt") as stream:
        return json.load(stream)


def episode_assertions():
    ep = gz_json(BASE / "text-state/expanded-final__ferry-compact-915000/bfs-exact_reference.json.gz")
    manifest = load_json(FERRY / "manifest.json")
    catalog = gz_json(FERRY / "scenes/catalog.json.gz")
    events = ep["events"]
    assert manifest["split"] == "test" and ep["task_id"] == manifest["task_id"] == "expanded-final/ferry-compact-915000"
    assert ep["algorithm"] == "bfs" and ep["result"]["goal_reached"]
    assert (ep["result"]["decision_count"], ep["result"]["expansion_count"]) == (10, 7)
    assert manifest["reference_costs"]["bfs"] == {"decisions": 10, "expansions": 7}
    assert manifest["task_context"]["canonical_goal"] == ["atom", "at", ["c0", "l1"]]
    assert len(events) == 10 and all(event["accepted"] for event in events)
    operations = [json.loads(event["raw_output"])["typed_operation"] for event in events]
    parents, sources, goal_ids = {}, set(), set()
    retired = []
    for index, (event, operation) in enumerate(zip(events, operations)):
        observation = event["input"]["observation"]
        source = observation["state_id"]
        sources.add(source)
        if operation.get("operation_type") == "retire_frontier":
            assert operation["state_id"] == source
            retired.append(index)
            continue
        assert operation["source_state_id"] == source
        candidates = event["input"]["search_memory"]["successor_candidates"]
        matches = [row for row in candidates if row["grounded_action"] == operation["action"]]
        assert len(matches) == 1 and not matches[0]["visited"]
        target = matches[0]["target_state_id"]
        assert target not in parents
        parents[target] = (source, index)
        if set(event["input"]["goal_atoms"]).issubset(json.loads(target)):
            goal_ids.add(target)
    assert retired == [2] and len(sources) == 7 and len(goal_ids) == 1
    assert ep["result"]["expansion_count"] == len(sources)
    initial = events[0]["input"]["observation"]["state_id"]
    target = goal_ids.pop()
    path = []
    while target != initial:
        target, index = parents[target]
        path.append(index)
    path.reverse()
    assert path == [1, 3, 5, 7]
    plan = [operations[index]["action"] for index in path]
    assert [f"({action['name']} {' '.join(action['args'])})" for action in plan] == catalog["path_bindings"][1]["supplied_actions"]
    assert len(plan) == 4
    assert json.loads(initial) == ["at(c0,l2)", "at-ferry(l1)", "empty-ferry"]
    with Image.open(EVIDENCE_ROOT / FERRY / "unlabelled/state-000000.png") as cached:
        assert cached.size == (128, 128)
        image = cached.convert("RGB").copy()
    locations = [x for x in range(128) if image.getpixel((x, 96)) == (179, 165, 218)]
    spans = []
    for x in locations:
        if not spans or x != spans[-1][-1] + 1:
            spans.append([x])
        else:
            spans[-1].append(x)
    assert [(span[0], span[-1]) for span in spans] == [(4, 40), (45, 81), (86, 122)]
    return image, spans, operations, path


def grid_and_development():
    with (EVIDENCE_ROOT / "docs/experiments/expanded-study/synthesis-v1/baseline-summary.csv").open(newline="") as stream:
        rows = {(row["modality"], row["algorithm"]): row for row in csv.DictReader(stream)
                if row["algorithm"] in ALGO_STYLE and row["arm"] == "process_sft"}
    assert len(rows) == 6
    grid = {}
    for algo in ALGO_STYLE:
        for modality in OBS_STYLE:
            name = f"{modality}-state"
            row = rows[(name, algo)]
            assert (int(row["episodes"]), int(row["successes"])) == (24, 0)
            assert_3dp(row["success_rate"], 0)
            version = "v3" if modality == "text" else "v5"
            report = load_json(f"outputs/matched_modalities/{version}/training/{name}/{algo}/report.json")
            assert (report["algorithm"], report["train_records"]) == (algo, 512)
            grid[(algo, modality)] = (report["train_records"], float(row["success_rate"]))
    prior = load_json("docs/experiments/deadline-study/prior-evidence.json")
    bfs = next(stage for stage in prior["historical_bfs_stages"] if stage["stage"] == "v8")
    bfws = load_json("data/bfws_phase_v1/issue59-distributed-terminal/adjudication-report.json")
    visual = prior["issue75"]
    training = load_json("outputs/visual_development/issue75-32k-v5/attempt-001/training.json")
    trains = {row["algorithm"]: row for row in training["training_runs"] if row["algorithm"] in ALGO_STYLE}
    assert bfs["selected_tasks"] == len(bfs["selected_task_ids"]) == 15
    assert len(bfws["coverage"]["task_ids"]) == 15 and bfws["outcome"] == "PASS"
    assert visual["evaluation_seeds"] == [17, 29, 43, 71, 101]
    completion = (EVIDENCE_ROOT / "docs/experiments/issue75/v5-completion.md").read_text()
    assert "BFS | 100% (75/75) | 70.7% (53/75)" in completion
    assert "BFWS | 66.7% (50/75) | 52.0% (39/75)" in completion
    dev = [("bfs", "text", load_json("data/bfs_pilot_v6/ms-swift-process/manifest.json")["counts"]["train"],
            bfs["metrics"]["process_sft_invariant_valid_success"]),
           ("best_first_width", "text", load_json("data/bfws_phase_v1/corpus-release/training/manifest.json")["counts"]["train"],
            bfws["process_sft_invariant_valid_success"])]
    for algo in ALGO_STYLE:
        dev.append((algo, "visual", trains[algo]["train_records"],
                    visual["metrics"][algo]["invariant_valid_success"]["process_sft"]))
    expected = [("bfs", "text", 12994, 1), ("best_first_width", "text", 47780, 14 / 15),
                ("bfs", "visual", 11911, 1), ("best_first_width", "visual", 14225, 50 / 75)]
    assert len(dev) == len(expected) == 4
    for row, want in zip(dev, expected):
        assert row[:3] == want[:3]
        assert_3dp(row[3], want[3])
    return grid, dev


def search_control():
    analysis = load_json("outputs/choice-frontier/v4/panels/metrics/analysis.json")
    expected = {"p2": (11, (.636, .545, .682), .621, .036),
                "p2u": (12, (.333, .208, .292), .278, .017)}
    panels = []
    for panel, (tasks, seed_rates, mean, random) in expected.items():
        arms = analysis["arms"][panel]
        seeds = analysis["training_seeds"][panel]
        assert seeds == [17, 29, 71]
        assert len(arms["learned_adapter_seed_mean"]["per_task"]) == tasks
        primary = analysis["heldout_p2" if panel == "p2" else "unscreened_p2u"]["primary"]
        assert primary["tasks"] == tasks and primary["seeds"] == seeds
        rates = [arms[f"learned_adapter_s{seed}"]["solved_at_2"] for seed in seeds]
        assert_3dp(rates, seed_rates)
        average = sum(rates) / len(rates)
        assert_3dp(average, mean)
        assert_3dp(arms["random_valid"]["solved_at_2"], random)
        assert arms["exact_reference"]["solved_at_2"] == 1
        panels.append((average, min(rates), max(rates), arms["random_valid"]["solved_at_2"]))
    return panels


def folio_transfer():
    cells = {"base", *(f"{algorithm}_{modality}" for algorithm in ("bfs", "iw") for modality in OBS_STYLE)}
    with (EVIDENCE_ROOT / "docs/experiments/expanded-study/synthesis-v1/transfer-accuracy.csv").open(newline="") as stream:
        rows = {row["cell"]: row for row in csv.DictReader(stream)
                if row["benchmark"] == "folio" and row["cell"] in cells}
    assert set(rows) == cells
    expected = {"base": 120, "bfs_text": 120, "bfs_visual": 121, "bfs_multimodal": 121,
                "iw_text": 132, "iw_visual": 129, "iw_multimodal": 129}
    values = {}
    for cell, count in expected.items():
        row = rows[cell]
        assert (int(row["examples"]), int(row["correct"]), int(row["malformed"])) == (200, count, 0)
        assert_3dp(row["accuracy"], count / 200)
        values[cell] = float(row["accuracy"])
    return values


def draw():
    image, spans, operations, path = episode_assertions()
    grid, dev = grid_and_development()
    heldout, folio = search_control(), folio_transfer()
    width, height = 5.5, 2.0
    fig = plt.figure(figsize=(width, height), dpi=300, facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set(xlim=(0, width), ylim=(0, height))
    ax.axis("off")
    panels = {"a": (0, 1.51), "b": (1.55, 2.91), "c": (2.95, 4.22), "d": (4.26, 5.5)}
    ownership = {}
    panel = "a"

    def txt(x, y, text, fs=6, color=INK, **kw):
        artist = ax.text(x, y, text, fontsize=fs, color=color, **kw)
        ownership[artist] = panel
        return artist

    txt(.03, 1.96, "a  The trace,\n    not the plan", fs=7, weight="bold", va="top", linespacing=1.1)
    txt(.03, 1.56, "BFS: 10 operations", color=MUTED)
    ax.imshow(image, extent=(.03, .40, .93, 1.30), interpolation="nearest", aspect="auto")
    for label, span in zip(("l0", "l1", "l2"), spans):
        txt(.03 + .37 * (span[0] + span[-1]) / 256, .84, label, ha="center")
    txt(.03, .70, "goal:\nc0 at l1", va="top", linespacing=1.15)
    for index, operation in enumerate(operations):
        y = 1.42 - index * .116
        on_path = index in path
        color = INK if on_path else MUTED
        txt(.51, y, str(index + 1), ha="right", va="center", color=color,
            weight="bold" if on_path else "normal")
        action = operation.get("action")
        label = f"{action['name']}({','.join(action['args'])})" if action else "retire"
        txt(.56, y, label, color=color, va="center", weight="bold" if on_path else "normal")
    txt(.03, .19, "7 expansions", color=MUTED)
    txt(.03, .05, "bold: four-operator plan", color=MUTED)

    panel = "b"
    txt(1.57, 1.96, "b  Executing BFS\n    and BFWS", fs=7, weight="bold", va="top", linespacing=1.1)
    for x, label, algo in ((1.64, "BFS", "bfs"), (2.20, "BFWS", "best_first_width")):
        ax.plot([x, x + .09], [1.56, 1.56], color=ALGO_STYLE[algo], lw=1.5)
        txt(x + .13, 1.56, label, va="center", color=ALGO_STYLE[algo], weight="bold")
    for x, modality, label in ((1.62, "text", "text"), (2.03, "visual", "visual"), (2.53, "multimodal", "multi.")):
        ax.plot(x, 1.39, marker=OBS_STYLE[modality], ms=3.5, mfc="white", color=INK, mew=.8)
        txt(x + .065, 1.39, label, va="center", color=MUTED)
    txt(1.57, 1.21, "success", color=MUTED)
    xlog = lambda n: 1.81 + .99 * (math.log(n) - math.log(512)) / (math.log(50000) - math.log(512))
    yscale = lambda v: .63 + .48 * v
    for value in (0, .5, 1):
        y = yscale(value)
        ax.plot([1.81, 2.80], [y, y], color=PALE, lw=.55)
        txt(1.67, y, f"{value:g}".replace("0.5", ".5"), ha="right", va="center", color=MUTED)
    for records, label in ((512, "512"), (10000, "10k"), (50000, "50k")):
        x = xlog(records)
        ax.plot([x, x], [.60, .63], color=MUTED, lw=.6)
        txt(x, .48, label, color=MUTED, ha="center")
    # All six small-corpus observations coincide. Nested shapes show modality;
    # two-colour halves show the two algorithms without jittering either axis.
    for modality, size in (("multimodal", 10), ("visual", 7), ("text", 3.5)):
        assert grid[("bfs", modality)] == grid[("best_first_width", modality)]
        records, rate = grid[("bfs", modality)]
        ax.plot(xlog(records), yscale(rate), marker=OBS_STYLE[modality], ms=size,
                fillstyle="left", mfc=ALGO_STYLE["bfs"], mfcalt=ALGO_STYLE["best_first_width"],
                mec="white", mew=.45, zorder=4)
    # Independent development panels are isolated hollow points, never curves.
    # The near-coincident BFS endpoints use different nested marker sizes.
    for algo, modality, records, rate in dev:
        ax.plot(xlog(records), yscale(rate), marker=OBS_STYLE[modality],
                ms=6.5 if modality == "visual" else 3.5, mfc="none",
                mec=ALGO_STYLE[algo], mew=1, zorder=3)
    txt(2.23, .34, "training records (log)", color=MUTED, ha="center")
    txt(1.57, .18, "hollow: separate", color=MUTED)
    txt(1.57, .05, "development panels", color=MUTED)

    panel = "c"
    txt(2.97, 1.96, "c  Choosing the\n    next node", fs=7, weight="bold", va="top", linespacing=1.1)
    txt(2.97, 1.56, "GBFS, WA* · image menus", color=MUTED)
    txt(2.97, 1.39, "success ≤2× ref. expansions", color=MUTED)
    ysuccess = lambda v: .63 + .56 * v
    for value in (0, .5, 1):
        y = ysuccess(value)
        txt(3.12, y, f"{value:g}".replace("0.5", ".5"), color=MUTED, ha="right", va="center")
        ax.plot([3.17, 4.18], [y, y], color=MUTED if value == 1 else PALE,
                ls="--" if value == 1 else "-", lw=.7 if value == 1 else .55)
    txt(3.69, 1.24, "exact reference", color=MUTED, ha="center")
    for (mean, low, high, random), x, label in zip(heldout, (3.43, 3.96), ("held-out 1", "held-out 2")):
        ax.plot([x - .04, x - .04], [ysuccess(low), ysuccess(high)], color=INK, lw=1.2)
        for value in (low, high):
            ax.plot([x - .07, x - .01], [ysuccess(value), ysuccess(value)], color=INK, lw=.8)
        ax.plot(x - .04, ysuccess(mean), marker="s", ms=3.8, color=INK)
        ax.plot(x + .05, ysuccess(random), marker="o", ms=3.8, mfc="white", color=MUTED)
        txt(x - .04, ysuccess(high) + .07, f"{mean:.2f}", ha="center")
        txt(x, .48, label, ha="center")
    ax.plot(3.02, .32, marker="s", ms=3.8, color=INK)
    txt(3.11, .32, "learned: mean", va="center")
    txt(3.11, .19, "and 3-seed range", va="center", color=MUTED)
    ax.plot(3.02, .06, marker="o", ms=3.8, mfc="white", color=MUTED)
    txt(3.11, .06, "random valid", color=MUTED, va="center")

    panel = "d"
    txt(4.28, 1.96, "d  Beyond planning:\n    FOLIO", fs=7, weight="bold", va="top", linespacing=1.1)
    txt(4.28, 1.56, "accuracy", color=MUTED)
    yfolio = lambda v: .64 + .68 * (v - .59) / .08
    for value in (.60, .63, .66):
        y = yfolio(value)
        txt(4.55, y, f"{value:.2f}".lstrip("0"), color=MUTED, ha="right", va="center")
        ax.plot([4.60, 5.46], [y, y], color=PALE, lw=.55)
    ax.plot([4.60, 5.46], [yfolio(folio["base"])] * 2, color=MUTED, ls="--", lw=.8)
    for x, modality, label in ((4.70, "text", "text"), (5.02, "visual", "visual"), (5.34, "multimodal", "multi.")):
        for prefix, algo, offset in (("bfs", "bfs", -.035), ("iw", "best_first_width", .035)):
            ax.plot(x + offset, yfolio(folio[f"{prefix}_{modality}"]), marker=OBS_STYLE[modality],
                    ms=4, mfc="white", color=ALGO_STYLE[algo], mew=1)
        txt(x, .48, label, ha="center", color=MUTED)
    txt(4.28, .34, f"dashed: base {folio['base']:.2f}", color=MUTED)
    for x, label, algo in ((4.35, "BFS", "bfs"), (4.91, "BFWS", "best_first_width")):
        ax.plot([x, x + .09], [.18, .18], color=ALGO_STYLE[algo], lw=1.5)
        txt(x + .13, .18, label, va="center", color=ALGO_STYLE[algo], weight="bold")
    txt(4.28, .05, "adapters", color=MUTED)

    # Check glyph extents at the final physical size, including every tick/legend.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    issues, extents = [], []
    for artist, owner in ownership.items():
        assert artist.get_fontsize() >= 6
        extent = artist.get_window_extent(renderer)
        left, right = panels[owner]
        box = Bbox.from_extents(left, 0, right, height).transformed(ax.transData)
        for name, bounds in (("canvas", fig.bbox), (f"panel {owner}", box)):
            if not (bounds.contains(extent.x0, extent.y0) and bounds.contains(extent.x1, extent.y1)):
                issues.append((name, artist.get_text()))
        for other, previous in extents:
            if extent.overlaps(previous):
                issues.append(("text overlap", artist.get_text(), other.get_text()))
        extents.append((artist, extent))
    assert not issues, issues
    assert width == 5.5 and height == 2.0
    for extension in ("pdf", "svg", "png"):
        fig.savefig(HERE / f"fig_teaser.{extension}", dpi=300)
    plt.close(fig)
    print(f"fig_teaser: BFS trace and reconstructed four-operator plan / six baseline cells / four development endpoints / held-out seed rates / seven FOLIO cells asserted; {len(ownership)} labels inside canvas and panel boxes, no text overlap; {width} x {height} in")


if __name__ == "__main__":
    draw()
