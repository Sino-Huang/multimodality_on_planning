"""Figure 2: a typed search loop and the first two valid ferry steps under three algorithms.

Evidence: outputs/expanded-study/v1/baseline/episodes/text-state/
expanded-final__ferry-compact-915000/{bfs,best_first_width,
best_first_add_greedy,best_first_add_w3}-exact_reference.json.gz;
outputs/expanded-study/v1/baseline/episodes/visual-state/
expanded-final__ferry-compact-915000/best_first_add_greedy-process_sft.json.gz;
outputs/expanded-study/v1/panel-v2/views/ferry-compact-915000/
unlabelled/state-000000.png.
Run from this directory: python fig_contracts.py [EVIDENCE_ROOT].
"""

import gzip
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from PIL import Image

from _style import EVIDENCE_ROOT

HERE = Path(__file__).resolve().parent
TASK = "expanded-final__ferry-compact-915000"
BASE = Path("outputs/expanded-study/v1/baseline/episodes")
SCENE = Path("outputs/expanded-study/v1/panel-v2/views/ferry-compact-915000/unlabelled/state-000000.png")
ALGO_STYLE = {"bfs": "#0072B2", "best_first_width": "#009E73",
              "best_first_add_greedy": "#D55E00"}
INK = "#213548"
COPIED = "#596775"
DERIVED = "#D55E00"
W, H = 5.5, 2.35


def episode(modality, algorithm, arm):
    path = BASE / modality / TASK / f"{algorithm}-{arm}.json.gz"
    with gzip.open(EVIDENCE_ROOT / path, "rt") as stream:
        data = json.load(stream)
    assert data["task_id"] == "expanded-final/ferry-compact-915000"
    assert data["model_id"] == "Qwen/Qwen3-VL-8B-Instruct"
    if arm == "process_sft":
        assert data["checkpoint"] == (
            "outputs/matched_modalities/v5/training/visual-state/best_first_add_greedy/final")
    assert data["result"]["algorithm_invariants_hold"]
    assert all(event["accepted"] for event in data["events"][:2])
    return data["events"][:2]


def action_name(action):
    return f"{action['name']}({','.join(action['args'])})"


def verify_evidence():
    visual = episode("visual-state", "best_first_add_greedy", "process_sft")
    assert visual[0]["raw_output"] == ('{"action":{"args":["l1","l0"],"name":"sail"},'
                                         '"source_state_id":"s0"}')
    assert visual[0]["view"]["state_representation"] == "scene-only-128-unlabelled-v1"
    assert ["current-state", 0, 0] in visual[0]["view"]["input_pages"]

    bfs = episode("text-state", "bfs", "exact_reference")
    first_head = bfs[0]["input"]["search_memory"]["frontier_head"]
    for i, event in enumerate(bfs):
        memory = event["input"]["search_memory"]
        candidates = memory["successor_candidates"]
        operation = json.loads(event["raw_output"])["typed_operation"]
        assert memory["frontier_size"] == 1
        assert [action_name(row["grounded_action"]) for row in candidates] == [
            "sail(l1,l0)", "sail(l1,l2)"]
        assert [row["visited"] for row in candidates] == ([False, False] if i == 0
                                                              else [True, False])
        assert operation["action"] == candidates[i]["grounded_action"]
        assert operation["source_state_id"] == first_head
        assert operation["frontier_intent"] == {
            "retire_source": i == 0, "target_position": i}
        assert operation["frontier_intent"]["target_position"] == (
            memory["frontier_size"] - int(operation["frontier_intent"]["retire_source"]))
        assert operation["visit_target"] is True
        assert operation["evaluate_target"] is False

    bfws = episode("text-state", "best_first_width", "exact_reference")
    objects = bfws[0]["input"]["task_context"]["objects"]
    assert objects == ["c0", "l0", "l1", "l2"]
    for i, event in enumerate(bfws):
        candidates = event["input"]["observation"]["candidates"]
        operation = json.loads(event["raw_output"])["typed_operation"]
        assert len(candidates) == 2
        assert candidates[0]["action"] == {"name": "sail", "args": [2, 1]}
        assert candidates[0]["dup"] == (i == 1)
        assert (candidates[0]["eval"] is None) == (i == 1)
        chosen = candidates[i]
        assert chosen["dup"] is False
        assert chosen["eval"]["novelty"] == 1
        assert chosen["eval"]["partition"] == 1
        assert chosen["eval"]["frontier"] == {
            "retire_source": i == 0, "target_position": i}
        assert operation["frontier_intent"] == chosen["eval"]["frontier"]
        assert operation["action"] == {
            "name": chosen["action"]["name"],
            "args": [objects[index] for index in chosen["action"]["args"]]}
        assert operation["source_state_id"] == event["input"]["observation"]["state"]["state_id"] == "$"
        assert operation["visit_target"] is True
        assert operation["evaluate_target"] is True

    additive = episode("text-state", "best_first_add_greedy", "exact_reference")
    first = additive[0]["input"]["successor_candidates"]
    columns = first["columns"]
    selected = [{name: value for name, value in zip(columns, row)} for row in first["rows"]]
    assert len(selected) == 2
    assert [(row["action"], row["g"], row["h"], row["priority"], row["target_state_id"])
            for row in selected] == [(["sail", "l1", "l0"], 1, 4, 4, "s1"),
                                    (["sail", "l1", "l2"], 1, 3, 3, "s2")]
    assert additive[1]["input"]["successor_candidates"]["rows"] == first["rows"][1:]
    for i, event in enumerate(additive):
        operation = json.loads(event["raw_output"])
        assert set(operation) == {"action", "source_state_id"}
        assert operation["action"] == {"name": selected[i]["action"][0],
                                       "args": selected[i]["action"][1:]}
        assert operation["source_state_id"] == event["input"]["current"]["state_id"] == "s0"
    weighted = episode("text-state", "best_first_add_w3", "exact_reference")
    weighted_first = weighted[0]["input"]["successor_candidates"]
    assert weighted_first["columns"] == columns
    weighted_rows = [dict(zip(columns, row)) for row in weighted_first["rows"]]
    assert [(row["action"], row["g"], row["h"], row["target_state_id"])
            for row in weighted_rows] == [(row["action"], row["g"], row["h"],
                                           row["target_state_id"]) for row in selected]
    assert all(row["priority"] == row["g"] + 3 * row["h"] for row in weighted_rows)
    assert [event["raw_output"] for event in weighted] == [event["raw_output"] for event in additive]
    assert weighted[1]["input"]["successor_candidates"]["rows"] == weighted_first["rows"][1:]
    assert visual[0]["raw_output"] == additive[0]["raw_output"]
    return visual


def text(ax, x, y, value, *, color=INK, size=6.15, bold=False):
    ax.text(x, y, value, ha="left", va="center", color=color, fontsize=size,
            weight="bold" if bold else "normal")


def card(ax, x, y, w, h, lines, *, heading_lines=1):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=.015,rounding_size=.035",
                                facecolor="#F5F8FA", edgecolor="#CFDBE3", lw=.65))
    for offset, line in enumerate(lines):
        ax.text(x + w / 2, y + h / 2 + (len(lines) - 1) * .043 - .086 * offset,
                line, color=INK, ha="center", va="center", fontsize=6,
                weight="bold" if offset < heading_lines else "normal")


def arrow(ax, start, end, *, color=COPIED):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=7,
                                 lw=.8, color=color))


def column(ax, x, title, algorithm):
    width = 1.76
    ax.add_patch(FancyBboxPatch((x, .048), width, 1.625,
                                boxstyle="round,pad=.005,rounding_size=.035",
                                facecolor="#F8FAFC", edgecolor="#D5E0E7", lw=.7))
    text(ax, x + .08, 1.57, title, color=ALGO_STYLE[algorithm], size=7.1, bold=True)
    text(ax, x + .08, 1.46, "observation supplies", size=6, bold=True)
    text(ax, x + .08, .91 if algorithm == "best_first_width" else .99,
         "policy emits", size=6, bold=True)
    return x + .09


def main():
    verify_evidence()
    with Image.open(EVIDENCE_ROOT / SCENE) as image:
        assert image.size == (128, 128)
        scene = image.copy()

    fig = plt.figure(figsize=(W, H), facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, W), ylim=(0, H))
    ax.axis("off")

    image_ax = fig.add_axes((.05 / W, 1.94 / H, .40 / W, .40 / H))
    image_ax.imshow(scene, interpolation="nearest")
    image_ax.axis("off")
    image_ax.add_patch(Rectangle((0, 0), 1, 1, transform=image_ax.transAxes,
                                 edgecolor="#C8D6DF", facecolor="none", lw=.7))
    card(ax, .51, 1.95, .74, .37, ["Observation", "text / visual /", "multimodal"])
    card(ax, 1.36, 1.95, .84, .37,
         ["Search Process", "Policy", "Qwen3-VL-8B", "+ LoRA"], heading_lines=2)
    card(ax, 2.31, 1.95, .84, .37,
         ["Typed Search", "Operation", "sail(l1,l0)", "from s0"], heading_lines=2)
    card(ax, 3.26, 1.95, 1.14, .37,
         ["Trusted Search", "Runtime", "check → apply, or", "reject and end episode"], heading_lines=2)
    card(ax, 4.51, 1.95, .90, .37, ["Search Memory", "frontier · visited", "novelty tables"])
    for end, start in [(.51, .45), (1.36, 1.25), (2.31, 2.20), (3.26, 3.15), (4.51, 4.40)]:
        arrow(ax, (start, 2.135), (end, 2.135))
    text(ax, .08, 1.84, "candidate rows stay text in every observation type", size=6, color=COPIED)
    ax.plot([5.11, 5.11, .80], [1.975, 1.75, 1.75], color=COPIED, lw=.75)
    arrow(ax, (.80, 1.75), (.80, 1.975))
    ax.plot([.05, 5.45], [1.715, 1.715], color="#D5E0E7", lw=.7)

    b = column(ax, .05, "BFS", "bfs")
    text(ax, b, 1.35, "frontier_size: 1 → 1", color=COPIED)
    text(ax, b, 1.24, "sail(l1,l0): new → visited", color=COPIED)
    text(ax, b, 1.13, "sail(l1,l2): new → new", color=COPIED)
    text(ax, b, .85, "1 action: sail(l1,l0) · source: head", color=COPIED, size=6)
    text(ax, b, .73, "retire: true · position: 0", color=DERIVED)
    text(ax, b, .61, "both: visit true · evaluate false")
    text(ax, b, .49, "2 action: sail(l1,l2) · source: s0", color=COPIED, size=6)
    text(ax, b, .37, "retire: false · position: 1", color=DERIVED)
    text(ax, b, .195, "Queue fields derived from frontier size", size=6)
    text(ax, b, .095, "and step's place in the expansion.", size=6)

    f = column(ax, 1.87, "BFWS", "best_first_width")
    text(ax, f, 1.35, "sail [2,1] · dup: false", color=COPIED)
    text(ax, f, 1.24, "novelty: 1 · goals left: 1", color=COPIED)
    text(ax, f, 1.13, "eval.frontier: {true, 0}", color=COPIED)
    text(ax, f, 1.02, "step 2 [2,1]: dup:true · eval:null", color=COPIED, size=6)
    text(ax, f, .80, "1 action: sail", color=COPIED)
    text(ax, f + .67, .80, "(l1,l0)", color=DERIVED)
    text(ax, f + 1.08, .80, "· source: $", color=COPIED, size=6)
    text(ax, f, .69, "both: visit/evaluate true")
    text(ax, f, .58, "frontier_intent: {true, 0}", color=COPIED)
    text(ax, f, .47, "2 action: sail", color=COPIED)
    text(ax, f + .67, .47, "(l1,l2)", color=DERIVED)
    text(ax, f + 1.08, .47, "· source: $", color=COPIED, size=6)
    text(ax, f, .36, "frontier_intent: {false, 1}", color=COPIED)
    text(ax, f, .195, "Position supplied in candidate eval;", size=6)
    text(ax, f, .095, "copied, not derived by the policy.", size=6)

    a = column(ax, 3.69, "Additive · greedy best-first", "best_first_add_greedy")
    text(ax, a, 1.35, "sail(l1,l0)  g:1 h:4 p:4 → s1", color=COPIED, size=6)
    text(ax, a, 1.24, "sail(l1,l2)  g:1 h:3 p:3 → s2", color=COPIED, size=6)
    text(ax, a, .85, "1 action: sail(l1,l0)", color=COPIED)
    text(ax, a, .73, "source_state_id: s0", color=COPIED)
    text(ax, a, .61, "2 action: sail(l1,l2)", color=COPIED)
    text(ax, a, .49, "source_state_id: s0", color=COPIED)
    text(ax, a, .32, "Runtime computes g, h and priority.", size=6)
    text(ax, a, .195, "Runtime keeps the priority heap;", size=6)
    text(ax, a, .095, "weighted A*: priority g + 3h.", size=6)

    for ext in ("pdf", "svg"):
        fig.savefig(HERE / f"fig_contracts.{ext}")
    fig.savefig(HERE / "fig_contracts.png", dpi=300)
    plt.close(fig)
    print("fig_contracts: main-grid visual process_sft + four text exact-reference episodes; "
          "BFS derived queue fields, BFWS copied frontier, additive runtime values verified")


if __name__ == "__main__":
    main()
