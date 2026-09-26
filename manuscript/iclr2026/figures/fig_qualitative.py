"""Illustrative qualitative scenes and traces; selections fixed BEFORE inspecting episodes.

Q1: Among validation-panel (task, algorithm) pairs, select the largest
    three-seed-mean adapter-minus-random-valid M1 (AUC), ties by task and
    algorithm lexicographically. Select the adapter training seed with the
    highest M1 on that pair, ties by smallest seed. Compare that episode to
    its exact-reference and seed-17 random-valid zoo episodes.
Q2: In the selected Q1 adapter episode, choose the event with the largest
    frontier menu; ties go to the earliest decision. Show every menu entry.
Q3: Among held-out-panel (task, algorithm) pairs whose exact reference
    reaches the goal and whose every adapter seed exhausts its decision cap,
    choose the largest cap; ties by task and algorithm lexicographically.
    Illustrate training seed 17 (the first of the fixed seeds), not a
    post-hoc favorable example.

Source keys: outputs/choice-frontier/v4/seeds/metrics/all-episode-metrics.json
records.{task,algorithm,arm,training_seed,auc,decision_cap,termination,
teacher_agreements,teacher_chance_sum,teacher_decisions}; v2/metrics/
all-episode-metrics.json records.{task,algorithm,arm,auc}; v4/panels/metrics/
all-episode-metrics.json.p2[].{task,algorithm,arm,decision_cap,termination};
selected episodes episodes[].events[].{menu,chosen_label,selected_state_id};
selected views states[].{scene_path,...}; state scenes/*.vfg.json.gz.
Printed quantitative values must be asserted at three decimals (half-up).
"""

from collections import defaultdict
from functools import lru_cache
import gzip
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageChops

from _style import ARM_STYLE, EVIDENCE_ROOT, assert_3dp, f3, load_json


HERE = Path(__file__).resolve().parent
V2 = "outputs/choice-frontier/v2"
V3 = "outputs/choice-frontier/v3"
V4 = "outputs/choice-frontier/v4"
SIZE = 256  # Re-render the identical cached VFG; policy input was 128 pixels.
METRICS = load_json(f"{V4}/seeds/metrics/all-episode-metrics.json")["records"]
ZOO = load_json(f"{V2}/metrics/all-episode-metrics.json")["records"]
P2 = load_json(f"{V4}/panels/metrics/all-episode-metrics.json")["p2"]


def read_gz(relative):
    with gzip.open(EVIDENCE_ROOT / relative, "rt") as stream:
        return json.load(stream)


def selected_cases():
    adapter = defaultdict(list)
    random = defaultdict(list)
    for record in METRICS:
        adapter[(record["task"], record["algorithm"])].append(record)
    for record in ZOO:
        if record["arm"] == "random_valid":
            random[(record["task"], record["algorithm"])].append(record)
    ranked = sorted(
        ((sum(r["auc"] for r in rows) / len(rows)
          - sum(r["auc"] for r in random[key]) / len(random[key]), key)
         for key, rows in adapter.items()),
        key=lambda pair: (-pair[0], pair[1]),
    )
    gain, key = ranked[0]
    assert key == ("choice-frontier-v2/grid-expanded-935016", "best_first_add_w3")
    assert_3dp(gain, 0.717)
    assert_3dp(sum(r["auc"] for r in adapter[key]) / len(adapter[key]), 0.792)
    assert_3dp(sum(r["auc"] for r in random[key]) / len(random[key]), 0.075)
    assert len(adapter[key]) == 3 and len(random[key]) == 5
    seed = sorted(adapter[key], key=lambda r: (-r["auc"], r["training_seed"]))[0]["training_seed"]
    assert seed == 17

    held = defaultdict(dict)
    for record in P2:
        if record["arm"] in ("exact_reference", "learned_adapter"):
            held[(record["task"], record["algorithm"])][
                (record["arm"], record.get("training_seed"))
            ] = record
    qualifying = []
    for task, rows in held.items():
        exact = rows[("exact_reference", None)]
        seeds = [r for (arm, _), r in rows.items() if arm == "learned_adapter"]
        if (exact["termination"] == "goal_reached" and len(seeds) == 3
                and all(r["termination"] == "decision_budget_exhausted"
                        and r["decision_cap"] == exact["decision_cap"]
                        and r["decisions"] == r["decision_cap"] for r in seeds)):
            qualifying.append((exact["decision_cap"], task))
    cap, failure = sorted(qualifying, key=lambda item: (-item[0], item[1]))[0]
    assert failure == ("choice-frontier-v4/15puzzle-expanded-955075", "best_first_add_greedy")
    assert cap == 92
    return key, seed, failure, cap


def episode(task, algorithm, arm, seed=17):
    name = task.replace("/", "__")
    if task.startswith("choice-frontier-v2"):
        if arm == "learned_adapter":
            version = V3 if seed == 17 else f"{V4}/seeds"
            path = f"{version}/evaluation/episodes/{name}/{algorithm}-learned_adapter-s{seed}-17.json.gz"
        else:
            path = f"{V2}/zoo/episodes/{name}/{algorithm}-{arm}-m2-17.json.gz"
    elif arm == "learned_adapter":
        path = f"{V4}/panels/p2/evaluation/episodes/{name}/{algorithm}-learned_adapter-s{seed}-17.json.gz"
    else:
        path = f"{V4}/panels/p2/zoo/episodes/{name}/{algorithm}-{arm}-m2-17.json.gz"
    return read_gz(path)


def scene_catalog(task):
    task_name = task.split("/")[-1]
    prefix = f"{V2}/views" if task.startswith("choice-frontier-v2") else f"{V4}/panels/views"
    catalog = read_gz(f"{prefix}/{task_name}/scenes/catalog.json.gz")
    assert catalog["stored_scene_size"] == [128, 128]
    return catalog


def additional_scenes(task, algorithm, seed):
    name = task.replace("/", "__")
    if task.startswith("choice-frontier-v2"):
        version = V3 if seed == 17 else f"{V4}/seeds"
    else:
        version = f"{V4}/panels/p2"
    base = f"{version}/evaluation/views/{name}/{algorithm}-learned_adapter-s{seed}-17"
    return read_gz(f"{base}/views.json.gz")["states"]


def h_trajectory(ep):
    """Recover h_add only from trusted enqueued-successor and head records."""
    known = {}
    trace = []
    for event in ep["events"]:
        runtime = event["trusted_runtime_result"]
        sid = runtime["expanded_state_id"]
        trace.append((event["decision_index"] + 1, known.get(sid)))
        for admission in runtime.get("admissions", []):
            result = admission["trusted_runtime_result"]
            if result.get("status") == "enqueued":
                target = result["target_state_id"]
                known[target] = result["h"]
    assert len(trace) == ep["result"]["decision_count"]
    return trace


def grid_atoms(ep, initial):
    """Match zoo successor states to *existing* VFG by their trusted action trace.

    The grid domain modifies at-robot, key possession, and the locked door;
    catalogue states that share these resulting atoms already have cached VFG.
    No new scene, pixels, or state content is synthesized or retouched here.
    """
    atoms = {"s0": frozenset(initial["atoms"])}
    for event in ep["events"]:
        source = atoms[event["trusted_runtime_result"]["expanded_state_id"]]
        for admission in event["trusted_runtime_result"].get("admissions", []):
            result = admission["trusted_runtime_result"]
            target = result.get("target_state_id")
            if result.get("status") != "enqueued" or target in atoms:
                continue
            changed = set(source)
            verb = admission["action"]["name"]
            args = admission["action"]["args"]
            if verb == "move":
                changed.remove(f"at-robot({args[0]})")
                changed.add(f"at-robot({args[1]})")
            elif verb == "pickup":
                changed.remove("arm-empty")
                changed.remove(f"at({args[1]},{args[0]})")
                changed.add(f"holding({args[1]})")
            elif verb == "putdown":
                changed.remove(f"holding({args[1]})")
                changed.add("arm-empty")
                changed.add(f"at({args[1]},{args[0]})")
            elif verb == "unlock":
                changed.remove(f"locked({args[1]})")
                changed.add(f"open({args[1]})")
            else:
                raise ValueError(f"Unknown grid action {verb}")
            atoms[target] = frozenset(changed)
    return atoms


def scenes(task, algorithm, seed, ep):
    catalog = scene_catalog(task)
    base = catalog["states"]
    more = additional_scenes(task, algorithm, seed)
    by_atoms = {frozenset(row["atoms"]): row for row in [*base, *more]}
    if ep.get("condition") != "learned_adapter" and task.startswith("choice-frontier-v2"):
        # Zoo episodes store no own VFG. Match their trusted successor atoms to
        # the same task's already cached, unlabelled adapter-run VFGs.
        for other_algorithm in ("best_first_add_greedy", "best_first_add_w3"):
            for other_seed in (17, 29, 71):
                for state in additional_scenes(task, other_algorithm, other_seed):
                    by_atoms[frozenset(state["atoms"])] = state
    if ep.get("condition") == "learned_adapter":
        # Episode-local state IDs and the episode-local views share indices.
        return {f"s{row['index']}": row for row in [*base, *more]}
    if task.startswith("choice-frontier-v2"):
        reconstructed = grid_atoms(ep, base[0])
        return {state: by_atoms[atoms] for state, atoms in reconstructed.items() if atoms in by_atoms}
    return {f"s{row['index']}": row for row in base}


@lru_cache(maxsize=None)
def rendered_scene(task, vfg, stage, cached):
    """Verify policy-visible pixels before a label-free high-resolution re-render."""
    from scripts.planimation_phase1_frames import render_vfg_to_local_png_frames
    from tempfile import TemporaryDirectory

    catalog = scene_catalog(task)
    objects = frozenset(name for names in catalog["task_context"]["objects_by_type"].values()
                        for name in names)
    # v2 catalog frames predate the named-object tint; later episode views use it.
    # Select the arguments of the actual cached policy-visible frame, then prove identity.
    if cached.startswith(f"{V2}/views/"):
        objects = frozenset()
    raw = gzip.decompress((EVIDENCE_ROOT / vfg).read_bytes())
    with TemporaryDirectory() as tmp:
        output = Path(tmp)
        assert render_vfg_to_local_png_frames(raw, output, stage, stage,
                                               canvas_size=128, draw_labels=False,
                                               object_names=objects) == 1
        with Image.open(output / "frame_000.png") as check, Image.open(EVIDENCE_ROOT / cached) as old:
            assert old.size == (128, 128)
            assert ImageChops.difference(check.convert("RGB"), old.convert("RGB")).getbbox() is None, (vfg, stage, cached)
        assert render_vfg_to_local_png_frames(raw, output, stage, stage,
                                               canvas_size=SIZE, draw_labels=False,
                                               object_names=objects) == 1
        with Image.open(output / "frame_000.png") as image:
            assert image.size == (SIZE, SIZE)
            return image.convert("RGB").copy()


def image_for(task, row, catalog):
    if task.startswith("choice-frontier-v4/"):
        # Some base-catalog PNGs omit tile glyphs present in their VFG;
        # show the exact cached policy-visible pixels, including later glyphs.
        with Image.open(EVIDENCE_ROOT / row["scene_path"]) as image:
            assert image.size == (128, 128)
            return image.convert("RGB").copy()
    if "vfg" in row:
        path = row["vfg"]
        # Per-state VFG holds the entire action path, so its final stage is the state.
        with gzip.open(EVIDENCE_ROOT / path, "rt") as stream:
            stage = len(json.load(stream)["visualStages"]) - 1
    else:
        index = row["index"]
        binding = next(b for b in catalog["path_bindings"] if index in b["state_indices"])
        path, stage = binding["vfg"], binding["state_indices"].index(index)
    return rendered_scene(task, path, stage, row["scene_path"])


def show_scene(ax, task, row, catalog, edge="#DADFE5"):
    ax.imshow(image_for(task, row, catalog), interpolation="nearest", aspect="equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(1.7 if edge != "#DADFE5" else 0.55)
        spine.set_edgecolor(edge)


def save(fig, stem):
    for suffix in ("pdf", "svg", "png"):
        fig.savefig(HERE / f"{stem}.{suffix}", dpi=300, facecolor="white")
    plt.close(fig)


def success_plot(task, algorithm, seed, eps):
    arms = [("exact_reference", eps[0], "Exact reference"),
            ("learned_adapter_seed_mean", eps[1], f"Adapter s{seed}"),
            ("random_valid", eps[2], "Random-valid s17")]
    assert [e["result"]["decision_count"] for _, e, _ in arms] == [10, 10, 18]
    assert [e["result"]["goal_reached"] for _, e, _ in arms] == [True, True, False]
    assert eps[2]["result"]["termination_reason"] == "decision_budget_exhausted"
    assert [e["decision_cap"] for _, e, _ in arms] == [18, 18, 18]
    comparisons = [
        event["trusted_runtime_result"]["expanded_state_id"]
        == previous["trusted_runtime_result"]["frontier_after"]["head"]["state_id"]
        for previous, event in zip(eps[1]["events"], eps[1]["events"][1:])
    ]
    record = next(r for r in METRICS if r["task"] == task
                  and r["algorithm"] == algorithm and r["training_seed"] == seed)
    assert sum(comparisons) == record["teacher_agreements"] == 7
    assert len(comparisons) == record["teacher_decisions"] == 9
    fig = plt.figure(figsize=(6.85, 4.05))
    grid = fig.add_gridspec(4, 7, left=.16, right=.98, top=.88, bottom=.12,
                            height_ratios=[1, 1, 1, 1.3], hspace=.33, wspace=.09)
    fig.text(.015, .975, "a   Same task, different expansion choices", fontsize=8, weight="bold", va="top")
    fig.text(.16, .907, "Five evenly spaced decisions", fontsize=7, color="#555555")
    fig.text(.85, .907, "Final expansion", fontsize=7, color="#555555", ha="center")
    for row_index, (arm, ep, name) in enumerate(arms):
        catalog = scene_catalog(task)
        lookup = scenes(task, algorithm, seed, ep)
        count = len(ep["events"])
        positions = [round(i * (count - 2) / 4) for i in range(5)] + [count - 1]
        assert len(set(positions)) == 6 and positions[-1] == count - 1
        assert [i + 1 for i in positions] == ([1, 3, 5, 7, 9, 10] if count == 10
                                              else [1, 5, 9, 13, 17, 18])
        for col, event_index in enumerate(positions):
            event = ep["events"][event_index]
            sid = event["trusted_runtime_result"]["expanded_state_id"]
            assert sid in lookup, f"No cached VFG for {name} expanded {sid}"
            ax = fig.add_subplot(grid[row_index, col + (1 if col < 5 else 1)])
            show_scene(ax, task, lookup[sid], catalog,
                       edge=ARM_STYLE[arm]["color"] if col == 5 else "#DADFE5")
            ax.set_xlabel(f"d{event_index + 1}", fontsize=7, labelpad=1)
        fig.text(.015, .79 - .18 * row_index, name, color=ARM_STYLE[arm]["color"], fontsize=7.1)
    ax = fig.add_subplot(grid[3, 1:])
    for arm, ep, name in arms:
        trace = [(step, h) for step, h in h_trajectory(ep) if h is not None]
        ax.plot([step for step, _ in trace], [h for _, h in trace],
                label=name, color=ARM_STYLE[arm]["color"],
                marker=ARM_STYLE[arm]["marker"], markersize=3, linewidth=1.25)
    ax.set(xlabel="Expansion decision", ylabel=r"Expanded state $h_{add}$")
    ax.set_xlim(1, 18)
    ax.grid(axis="y", alpha=.2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=7, frameon=False, ncol=3, loc="upper center")
    save(fig, "fig_qualitative_success")


def rank_histogram():
    observed = np.zeros(5, dtype=int)
    uniform = np.zeros(5, dtype=float)
    for metric in METRICS:
        ep = episode(metric["task"], metric["algorithm"], "learned_adapter", metric["training_seed"])
        heuristic = {}
        for event in ep["events"]:
            menu = event["menu"]
            choice = json.loads(event["raw_output"])["expand_choice"]
            assert any(c["choice"] == choice for c in menu)
            if len(menu) == 1:
                rank = 0
            else:
                ordered = sorted(menu, key=lambda c: (heuristic[c["state_ref"]], c["choice"]))
                rank = next(i for i, c in enumerate(ordered) if c["choice"] == choice)
            bin_index = min(4, (5 * rank) // len(menu))
            observed[bin_index] += 1
            for position in range(len(menu)):
                uniform[min(4, (5 * position) // len(menu))] += 1 / len(menu)
            for admission in event["trusted_runtime_result"].get("admissions", []):
                result = admission["trusted_runtime_result"]
                if result.get("status") == "enqueued":
                    heuristic[result["target_state_id"]] = result["h"]
    assert int(observed.sum()) == 2231
    assert_3dp(uniform.sum(), 2231)
    assert observed.tolist() == [1041, 392, 295, 279, 224]
    assert_3dp(uniform.tolist(), [650.023, 420.860, 431.063, 420.860, 308.195])
    return observed, uniform


def decision_plot(task, algorithm, seed, ep):
    event = max(ep["events"], key=lambda ev: len(ev["menu"]))
    assert event["decision_index"] == 9 and len(event["menu"]) == 12
    earlier = ep["events"][event["decision_index"] - 1]
    reference_id = earlier["trusted_runtime_result"]["frontier_after"]["head"]["state_id"]
    adapter_id = event["trusted_runtime_result"]["expanded_state_id"]
    assert reference_id == adapter_id == "s20"
    known = {}
    for previous in ep["events"][:event["decision_index"]]:
        for admission in previous["trusted_runtime_result"].get("admissions", []):
            result = admission["trusted_runtime_result"]
            if result.get("status") == "enqueued":
                known[result["target_state_id"]] = result["h"]
    assert [known[c["state_ref"]] for c in event["menu"]] == [6, 10, 2, 4, 2, 10, 2, 5, 2, 3, 8, 0]
    lookup, catalog = scenes(task, algorithm, seed, ep), scene_catalog(task)
    obs, uniform = rank_histogram()
    fig = plt.figure(figsize=(6.85, 3.05))
    grid = fig.add_gridspec(2, 8, left=.035, right=.975, top=.85, bottom=.21,
                            width_ratios=[1, 1, 1, 1, 1, 1, .7, 2.2], hspace=.35, wspace=.12)
    fig.text(.035, .975, "b   The entire largest menu (expansion decision 10)",
             weight="bold", fontsize=8, va="top")
    fig.text(.035, .91, "Labels are the policy's opaque choices; h_add is privileged (not shown to policy).",
             fontsize=7, color="#555555")
    for index, option in enumerate(event["menu"]):
        ax = fig.add_subplot(grid[index // 6, index % 6])
        state = option["state_ref"]
        assert state in lookup and state in known
        show_scene(ax, task, lookup[state], catalog,
                   edge=ARM_STYLE["learned_adapter_seed_mean"]["color"] if state == adapter_id else "#DADFE5")
        if state == reference_id:
            ax.add_patch(plt.Rectangle((5, 5), SIZE - 10, SIZE - 10, fill=False,
                                       edgecolor=ARM_STYLE["exact_reference"]["color"],
                                       lw=1.1, linestyle="--"))
        ax.set_xlabel(f"{option['choice']}  h={known[state]}", fontsize=7, labelpad=1)
    ax = fig.add_subplot(grid[:, 7])
    indexes = np.arange(5)
    ax.bar(indexes - .17, obs, width=.33, color=ARM_STYLE["learned_adapter_seed_mean"]["color"], label="Adapter")
    ax.bar(indexes + .17, uniform, width=.33, facecolor="white", edgecolor="#777777", label="Uniform")
    ax.set_xticks(indexes, ["0–20", "20–40", "40–60", "60–80", "80–100"], rotation=35, fontsize=6.7)
    ax.set_title("Decision count", fontsize=7)
    ax.set_xlabel("Rank percentile, lower h first", fontsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper right", fontsize=6.7, frameon=False)
    agreements = sum(m["teacher_agreements"] for m in METRICS)
    eligible = sum(m["teacher_decisions"] for m in METRICS)
    chance = sum(m["teacher_chance_sum"] for m in METRICS)
    assert agreements == 429 and eligible == 2117
    assert_3dp(chance, 269.711)
    assert_3dp(100 * agreements / eligible, 20.265)
    assert_3dp(100 * chance / eligible, 12.740)
    fig.text(.74, .94, f"Exact agreement {agreements}/{eligible} vs chance {f3(chance)} expected",
             ha="center", fontsize=6.1)
    save(fig, "fig_qualitative_decision")


def failure_plot(task, algorithm, cap, exact, adapter):
    assert exact["result"]["goal_reached"] and not adapter["result"]["goal_reached"]
    assert len(exact["events"]) == 47 and len(adapter["events"]) == cap == 92
    a_trace = h_trajectory(adapter)
    e_trace = h_trajectory(exact)
    best_at = min((i for i, h in a_trace if h is not None), key=lambda i: (a_trace[i - 1][1], i))
    assert best_at == 40 and a_trace[-1][1] == 35 and a_trace[best_at - 1][1] == 9
    fig = plt.figure(figsize=(6.85, 2.35))
    grid = fig.add_gridspec(1, 4, left=.085, right=.98, top=.78, bottom=.22,
                            width_ratios=[3.1, 1, 1, 1], wspace=.18)
    fig.text(.035, .975, "c   Held-out failure: no sustained heuristic descent", weight="bold", fontsize=8, va="top")
    fig.text(.035, .88, "Adapter seed 17 exhausts its cap; the exact reference reaches the goal.",
             fontsize=7, color="#555555")
    ax = fig.add_subplot(grid[0, 0])
    for trace, arm, label in [(e_trace, "exact_reference", "Exact reference"),
                              (a_trace, "learned_adapter_seed_mean", "Adapter s17")]:
        values = [(x, y) for x, y in trace if y is not None]
        ax.plot([x for x, _ in values], [y for _, y in values], label=label,
                color=ARM_STYLE[arm]["color"], lw=1.1, marker=ARM_STYLE[arm]["marker"], markersize=2)
    running_best = np.minimum.accumulate([h for _, h in a_trace if h is not None])
    assert int(running_best[-1]) == 9
    ax.plot([i for i, h in a_trace if h is not None], running_best,
            color=ARM_STYLE["learned_adapter_seed_mean"]["color"], linestyle="--",
            lw=1.6, label="Adapter best so far")
    ax.set(xlabel="Expansion decision", ylabel=r"Expanded state $h_{add}$")
    ax.set_xlim(1, cap)
    ax.grid(axis="y", alpha=.2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=6.8, loc="upper left")
    lookup, catalog = scenes(task, algorithm, 17, adapter), scene_catalog(task)
    for col, step in enumerate((1, best_at, cap), start=1):
        event = adapter["events"][step - 1]
        sid = event["trusted_runtime_result"]["expanded_state_id"]
        ax = fig.add_subplot(grid[0, col])
        show_scene(ax, task, lookup[sid], catalog,
                   edge=ARM_STYLE["learned_adapter_seed_mean"]["color"] if step == cap else "#DADFE5")
        ax.set_xlabel(f"d{step}  h={'—' if a_trace[step-1][1] is None else a_trace[step-1][1]}",
                      fontsize=7, labelpad=3)
    save(fig, "fig_qualitative_failure")


def prepare_renderer():
    """Import the original VFG renderer from the selected evidence repository."""
    sys.path.insert(0, str(EVIDENCE_ROOT))


def main():
    prepare_renderer()
    key, seed, failure, cap = selected_cases()
    exact = episode(*key, "exact_reference")
    adapter = episode(*key, "learned_adapter", seed)
    random = episode(*key, "random_valid")
    success_plot(*key, seed, (exact, adapter, random))
    decision_plot(*key, seed, adapter)
    failure_plot(*failure, cap, episode(*failure, "exact_reference"),
                 episode(*failure, "learned_adapter", 17))
    print(f"Q1 {key} seed{seed}; Q2 menu "
          f"{max(len(event['menu']) for event in adapter['events'])}; "
          f"Q3 {failure} cap {cap}; PDF/SVG/PNG exported")


if __name__ == "__main__":
    main()
