"""Figure 2: BFS/BFWS execution and image-based GBFS/WA* node choice.

The upper panel retains one BFS ferry step. The lower panel contrasts the
two levels, using execution traces and a recorded, shuffled image menu.
Run: source ~/cd_vlaplan && python fig_contracts.py [EVIDENCE_ROOT]
"""

import gzip
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from PIL import Image

from _style import EVIDENCE_ROOT

HERE = Path(__file__).resolve().parent
BASE = Path("outputs/expanded-study/v1/baseline/episodes/text-state")
TASK = "expanded-final__ferry-compact-915000"
SCENE = Path("outputs/expanded-study/v1/panel-v2/views/ferry-compact-915000/unlabelled/state-000000.png")
CHOICE_BASE = Path("outputs/choice-frontier/v1/evaluation")
CHOICE_EPISODE = CHOICE_BASE / "episodes" / TASK / "best_first_add_greedy-exact_reference-17.json.gz"
CHOICE_PROTOCOL = Path("configs/experiments/choice-frontier/choice-frontier-protocol-v1.json")
# Same algorithm colours, ink, and sans-serif font as fig_teaser.py / _style.py.
ALGORITHMS = (
    ("bfs", "BFS", "#0072B2", r"$\kappa_{\mathcal{A}}=\langle\sigma\rangle$  (FIFO)"),
    ("best_first_width", "BFWS", "#009E73", r"$\kappa_{\mathcal{A}}=\langle w,\mathrm{\#}g,g,\sigma\rangle$"),
)
INK, MUTED, LINE = "#213548", "#596775", "#CED8DF"
W, H = 5.5, 2.8


def action_name(action):
    return f"{action['name']}({','.join(action['args'])})"


def evidence():
    """Assert both execution operations and the recorded image-choice menu."""
    first, operations = {}, {}
    for algorithm, _, _, _ in ALGORITHMS:
        with gzip.open(EVIDENCE_ROOT / BASE / TASK / f"{algorithm}-exact_reference.json.gz", "rt") as stream:
            episode = json.load(stream)
        assert episode["task_id"] == "expanded-final/ferry-compact-915000"
        assert episode["result"]["algorithm_invariants_hold"]
        event = episode["events"][0]
        assert event["index"] == 0 and event["accepted"]
        assert event["view"]["state"] == 0
        assert ["current-state", 0, 0] in event["view"]["input_pages"]
        first[algorithm] = event["input"]
        raw = json.loads(event["raw_output"])
        operations[algorithm] = raw["typed_operation"] if "typed_operation" in raw else raw
        assert operations[algorithm]["action"] == {"name": "sail", "args": ["l1", "l0"]}

    bfs = first["bfs"]
    memory = bfs["search_memory"]
    candidates = memory["successor_candidates"]
    assert [action_name(row["grounded_action"]) for row in candidates] == ["sail(l1,l0)", "sail(l1,l2)"]
    assert [row["visited"] for row in candidates] == [False, False]
    assert bfs["goal_atoms"] == ["at(c0,l1)"]
    assert bfs["observation"]["state_atoms"] == ["at(c0,l2)", "at-ferry(l1)", "empty-ferry"]
    op = operations["bfs"]
    assert op["source_state_id"] == memory["frontier_head"] == bfs["observation"]["state_id"]
    assert memory["frontier_size"] == 1
    assert op["frontier_intent"] == {"retire_source": True, "target_position": 0}
    assert op["frontier_intent"]["target_position"] == memory["frontier_size"] - int(op["frontier_intent"]["retire_source"])
    assert op["visit_target"] and not op["evaluate_target"]

    bfws = first["best_first_width"]
    objects = bfws["task_context"]["objects"]
    assert objects == ["c0", "l0", "l1", "l2"]
    rows = bfws["observation"]["candidates"]
    decoded = [{"name": row["action"]["name"], "args": [objects[i] for i in row["action"]["args"]]} for row in rows]
    assert decoded == [row["grounded_action"] for row in candidates]
    assert all(not row["dup"] for row in rows)
    op = operations["best_first_width"]
    assert op["source_state_id"] == bfws["observation"]["state"]["state_id"] == bfws["search_memory"]["head"] == "$"
    assert op["action"] == decoded[0]
    assert op["frontier_intent"] == rows[0]["eval"]["frontier"] == {"retire_source": True, "target_position": 0}
    assert op["visit_target"] and op["evaluate_target"]
    assert rows[0]["eval"]["priority"] == [1, 1, 1, 1]
    assert rows[0]["eval"]["novelty"] == rows[0]["eval"]["partition"] == 1


    with Image.open(EVIDENCE_ROOT / SCENE) as image:
        assert image.size == (128, 128)
        scene = image.convert("RGB").copy()
    menu, reference = choice_evidence()
    return candidates, bfs["goal_atoms"][0], bfs["observation"]["state_atoms"], operations, scene, menu, reference


def choice_evidence():
    """Resolve the recorded menu through its original view store, without scores."""
    with gzip.open(EVIDENCE_ROOT / CHOICE_EPISODE, "rt") as stream:
        episode = json.load(stream)
    assert episode["task_id"] == "expanded-final/ferry-compact-915000"
    assert episode["algorithm"] == "best_first_add_greedy"
    assert episode["condition"] == "exact_reference"
    assert episode["result"]["algorithm_invariants_hold"]
    event = episode["events"][2]
    assert event["decision_index"] == 2
    assert event["menu"] == [
        {"choice": "c0", "state_ref": "s3"},
        {"choice": "c1", "state_ref": "s1"},
    ]
    assert event["input"]["frontier_menu"] == {"choices": ["c0", "c1"]}
    assert set(event["input"]) == {"algorithm", "frontier_menu", "representation", "schema_version"}
    assert event["view"]["menu_size"] == 2
    pages = event["view"]["input_pages"]
    assert pages == [["task-context", None, 0], ["initial-state", 0, 0],
                     ["frontier-choice", 3, 0], ["frontier-choice", 1, 0], ["goal", None, 0]]
    reference = json.loads(event["raw_output"])["expand_choice"]
    assert reference == "c0"
    runtime = event["trusted_runtime_result"]
    assert runtime["accepted"] and runtime["status"] == "expanded"
    assert runtime["expanded_state_id"] == "s3"
    assert episode["events"][1]["trusted_runtime_result"]["frontier_after"]["head"]["state_id"] == "s3"
    admissions = [a["trusted_runtime_result"] for e in episode["events"][:2]
                  for a in e["trusted_runtime_result"]["admissions"]]
    enqueued = {a["target_state_id"]: a for a in admissions if a["status"] == "enqueued"}
    assert enqueued["s3"]["h"] == enqueued["s3"]["priority"] == 2
    assert enqueued["s1"]["h"] == enqueued["s1"]["priority"] == 4
    assert min(event["menu"], key=lambda row: enqueued[row["state_ref"]]["priority"])["choice"] == reference
    assert any(a["trusted_runtime_result"]["status"] == "enqueued" for a in runtime["admissions"])

    protocol = json.loads((EVIDENCE_ROOT / CHOICE_PROTOCOL).read_text())
    report_path = protocol["evaluation"]["panel_view_report"]
    assert report_path == "outputs/expanded-study/v1/panel-v2/reference-views.json"
    report = json.loads((EVIDENCE_ROOT / report_path).read_text())
    task = next(row for row in report["tasks"] if row["row"]["task_id"] == episode["task_id"])
    native = task["native_views"]
    assert native["recipe_id"] == "scene-only-128-unlabelled-v1"
    with gzip.open(EVIDENCE_ROOT / episode["view_output"] / "views.json.gz", "rt") as stream:
        retained = json.load(stream)
    assert retained["source_manifest"] == native["source_manifest"]
    assert not retained["states"] and not retained["scene_only_paths"]
    manifest = json.loads((EVIDENCE_ROOT / native["source_manifest"]).read_text())
    with gzip.open(EVIDENCE_ROOT / manifest["scene_catalog"], "rt") as stream:
        catalog = json.load(stream)
    assert catalog["states"][3]["atoms"] == ["at-ferry(l2)", "on(c0)"]
    assert catalog["states"][1]["atoms"] == ["at(c0,l2)", "at-ferry(l0)", "empty-ferry"]
    for path in native["static_pages"] + native["goal_pages"] + [native["scenes"]["0"]]:
        assert (EVIDENCE_ROOT / path).is_file()
    menu = []
    for row, page in zip(event["menu"], pages[2:4]):
        index = page[1]
        path = native["scenes"][str(index)]
        assert path == str(SCENE.parent / f"state-{index:06d}.png")
        with Image.open(EVIDENCE_ROOT / path) as image:
            assert image.size == (128, 128)
            menu.append((row["choice"], image.convert("RGB").copy()))
    # The same search-control records verify the weight in the WA* key.
    weighted_path = CHOICE_EPISODE.with_name("best_first_add_w3-exact_reference-17.json.gz")
    with gzip.open(EVIDENCE_ROOT / weighted_path, "rt") as stream:
        weighted = json.load(stream)
    assert weighted["algorithm"] == "best_first_add_w3"
    for event in weighted["events"]:
        for admission in event["trusted_runtime_result"].get("admissions", []):
            values = admission["trusted_runtime_result"]
            assert values["priority"] == values["g"] + 3 * values["h"]
    return menu, reference


def main():
    candidates, goal, facts, operations, scene, menu, reference = evidence()
    fig = plt.figure(figsize=(W, H), dpi=300, facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, W), ylim=(-.05, H - .05))
    ax.axis("off")
    boxes, arrows, ownership = {}, {}, {}

    def text(x, y, label, size=6.5, color=INK, inside=(), on_arrow=(), **kwargs):
        artist = ax.text(x, y, label, fontsize=size, color=color, va="center", **kwargs)
        ownership[artist] = (inside, on_arrow)
        return artist

    def box(name, x, y, width, height, face="#F6F8FA", edge=LINE):
        patch = FancyBboxPatch((x, y), width, height,
                              boxstyle="round,pad=0.012,rounding_size=0.025",
                              facecolor=face, edgecolor=edge, linewidth=.65)
        ax.add_patch(patch)
        boxes[name] = patch

    def arrow(name, start, end):
        patch = FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=7,
                                linewidth=.85, color=MUTED)
        ax.add_patch(patch)
        arrows[name] = patch

    def route(name, xs, ys):
        arrows[name], = ax.plot(xs, ys, color=MUTED, lw=.85)

    text(.06, 2.66, "a  One step at inference", size=8, weight="bold")
    text(5.40, 2.66, r"Training: $(o_t,a_t^*)$ from reference trace $\tau^*$", ha="right", color=MUTED)

    # Generic queue at expansion start; blank chips are not a ferry snapshot.
    text(.08, 2.47, r"search state $M_t$", weight="bold")
    text(.08, 2.335, r"open list ordered by $\kappa_{\mathcal{A}}$")
    for i in range(4):
        box(f"node{i}", .09 + .265 * i, 2.065, .22, .18,
            face="#DCEAF4" if i == 0 else "#F6F8FA",
            edge="#0072B2" if i == 0 else LINE)
    text(.20, 2.155, r"$n_t$", ha="center", weight="bold", inside=("node0",))
    text(.60, 1.995, r"head = $n_t$", ha="center", color=MUTED)
    box("closed", .16, 1.765, .91, .16)
    text(.615, 1.845, "closed / visited", ha="center", color=MUTED, inside=("closed",))

    box("observation", 1.23, 1.605, 3.15, .835, face="white")
    text(1.39, 2.51, r"observation $o_t$", weight="bold")
    ax.imshow(scene, extent=(1.41, 2.09, 1.75, 2.43),
              interpolation="nearest", aspect="equal", zorder=2)
    text(1.75, 1.67, "current state (image)", ha="center", inside=("observation",))
    box("facts", 2.19, 1.74, 1.01, .66)
    text(2.24, 2.305, "state facts (text)", weight="bold", inside=("facts", "observation"))
    for y, fact in zip((2.18, 2.055, 1.93), facts):
        text(2.24, y, fact, inside=("facts", "observation"))
    text(2.24, 1.815, f"goal: {goal}", inside=("facts", "observation"))
    box("candidates", 3.34, 1.81, .97, .59)
    text(3.39, 2.305, r"candidates $C_t$", weight="bold", inside=("candidates", "observation"))
    text(3.39, 2.17, "always text", color=MUTED, inside=("candidates", "observation"))
    for y, row in zip((2.04, 1.91), candidates):
        text(3.39, y, action_name(row["grounded_action"]), inside=("candidates", "observation"))
    # Deliberately outside the observation group, with a visible lower gutter.
    text(1.45, 1.505, "text: facts as text · visual: facts as images · multimodal: both", color=MUTED)
    arrow("observe", (1.14, 2.15), (1.215, 2.15))

    box("vlm", 4.64, 1.975, .69, .435, face="#EAF1F6", edge="#9AAFBF")
    text(4.985, 2.275, "VLM", size=8, weight="bold", ha="center", inside=("vlm",))
    text(4.985, 2.09, r"$p_\theta$", size=9, ha="center", inside=("vlm",))
    arrow("model_input", (4.395, 2.18), (4.62, 2.18))
    text(4.985, 1.86, "one per step", color=MUTED, ha="center")

    route("output", [5.40, 5.40, 1.42], [2.18, 1.36, 1.36])
    arrow("output_start", (5.345, 2.18), (5.40, 2.18))
    arrow("output_end", (1.60, 1.36), (1.34, 1.36))
    intent = operations["bfs"]["frontier_intent"]
    action = action_name(operations["bfs"]["action"])
    emitted = (r"BFS: $a_t=\langle src,\mathrm{" + action + r"},"
               + rf"r=\mathrm{{{str(intent['retire_source']).lower()}}},p={intent['target_position']}\rangle$")
    text(3.40, 1.36, emitted, size=7, ha="center", on_arrow=("output",),
         bbox={"facecolor": "white", "edgecolor": "none", "pad": 2})

    box("runtime", .10, 1.215, 1.22, .37)
    text(.71, 1.495, "runtime", weight="bold", ha="center", inside=("runtime",))
    text(.71, 1.325, r"$a_t\in V_{\mathcal{A}}(M_t)$?", size=8, ha="center", inside=("runtime",))
    route("update", [.10, .035, .035, .09], [1.40, 1.40, 2.155, 2.155])
    arrow("update_end", (.035, 2.155), (.09, 2.155))
    text(.08, 1.675, r"✓ $M_{t+1}=T_{\mathcal{A}}(M_t,a_t)$", size=6.5)
    arrow("reject", (1.10, 1.20), (1.43, 1.16))
    text(1.49, 1.16, "× episode ends", color=MUTED)
    text(3.40, 1.205, r"$n_t$: node under expansion; $src=n_t$", color=MUTED, ha="center")
    ax.plot([.06, 5.43], [1.10, 1.10], color=LINE, lw=.65)

    text(.06, .995, "b  Execution (BFS, BFWS)", size=8, weight="bold")
    text(.08, .86, r"Ferry, first step: $src=n_t$, " + f"$o$ = {action}")
    for index, (algorithm, title, color, key) in enumerate(ALGORITHMS):
        x, width = .07 + 1.30 * index, 1.24
        name = f"algorithm{index}"
        patch = Rectangle((x, .10), width, .67, facecolor="#F8FAFC", edgecolor="none")
        ax.add_patch(patch)
        boxes[name] = patch
        ax.plot([x, x + width], [.77, .77], color=color, lw=2.2, solid_capstyle="butt")
        text(x + .045, .68, title, size=7, weight="bold", inside=(name,))
        text(x + .045, .55, key, inside=(name,))
        text(x + .045, .425, r"write $\langle src,o,r,p\rangle$", inside=(name,))
        intent = operations[algorithm]["frontier_intent"]
        values = rf"$r=\mathrm{{{str(intent['retire_source']).lower()}}},\ p={intent['target_position']}$"
        text(x + .045, .30, ("derive " if index == 0 else "copy ") + values, weight="bold", inside=(name,))
        text(x + .045, .18, r"$p=|\mathrm{open}|-r$" if index == 0 else "from candidate", color=MUTED, inside=(name,))
    text(.08, .015, "runtime selects head; retire ends expansion", color=MUTED)

    text(2.72, .995, "Search control (GBFS, WA*)", size=8, weight="bold")
    text(2.72, .85, r"$\kappa_{\mathcal{A}}$: GBFS $h_{\mathrm{add}}$; WA* $g+3h_{\mathrm{add}}$")
    text(2.72, .74, "shuffled menu · no scores", color=MUTED)
    for index, (label, image) in enumerate(menu):
        x, size = 2.77 + .56 * index, .42
        ax.imshow(image, extent=(x, x + size, .24, .24 + size),
                  interpolation="nearest", aspect="equal", zorder=2)
        if label == reference:
            patch = Rectangle((x - .015, .225), size + .03, size + .03,
                              facecolor="none", edgecolor="#D55E00", linewidth=1.1)
            ax.add_patch(patch)
            boxes["reference_choice"] = patch
        text(x + size / 2, .165, label + (" (ref.)" if label == reference else ""),
             ha="center", weight="bold" if label == reference else "normal")
    text(2.72, .015, "+ initial and goal pages", color=MUTED)
    arrow("choice_input", (3.82, .53), (4.01, .53))
    text(4.12, .67, "VLM writes", weight="bold")
    text(4.12, .51, r"$\langle\mathrm{expand},c\rangle$", size=7)
    text(4.05, .335, r"runtime expands $c$")
    text(4.05, .195, "and inserts successors")
    text(4.05, .015, r"ref.: smallest $\kappa_{\mathcal{A}}$", color=MUTED)

    # Geometry is checked on the final 300-dpi rendering, not guessed widths.
    def intersects_stroke(path, bounds):
        # CLOSEPOLY has a dummy vertex (often 0,0), not a drawn segment to it.
        # Flatten curves and test real segments so arrowheads do not create
        # spurious diagonals across the entire figure.
        start = previous = None
        for vertices, code in path.iter_segments(curves=False):
            if code == path.MOVETO:
                start = previous = vertices[-2:]
            else:
                current = start if code == path.CLOSEPOLY else vertices[-2:]
                if type(path)([previous, current]).intersects_bbox(bounds, filled=False):
                    return True
                previous = current
        return False

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    padding = 2 * fig.dpi / 72
    issues = []
    for label, (containers, owned_arrows) in ownership.items():
        assert label.get_fontsize() >= 6.5
        extent = label.get_window_extent(renderer)
        if not (fig.bbox.contains(extent.x0, extent.y0) and fig.bbox.contains(extent.x1, extent.y1)):
            issues.append(("canvas", label.get_text()))
        for name in containers:
            inner = boxes[name].get_window_extent(renderer).padded(-padding)
            if not (inner.contains(extent.x0, extent.y0) and inner.contains(extent.x1, extent.y1)):
                issues.append(("box padding", name, label.get_text()))
            if name.startswith("algorithm"):
                right = boxes[name].get_window_extent(renderer).x1 - extent.x1
                if right < .04 * fig.dpi:
                    issues.append(("card right padding", name, label.get_text()))
        for name, patch in boxes.items():
            border = patch.get_path().transformed(patch.get_transform())
            stroke = patch.get_linewidth() * fig.dpi / 144
            if intersects_stroke(border, extent.padded(stroke)):
                issues.append(("box border", name, label.get_text()))
        for name, artist in arrows.items():
            if name not in owned_arrows:
                path = artist.get_path().transformed(artist.get_transform())
                stroke = artist.get_linewidth() * fig.dpi / 144
                if intersects_stroke(path, extent.padded(stroke)):
                    issues.append(("arrow collision", name, label.get_text()))
        for image in ax.images:
            if extent.overlaps(image.get_window_extent(renderer)):
                issues.append(("image collision", label.get_text()))
    labels = list(ownership)
    for index, label in enumerate(labels):
        extent = label.get_window_extent(renderer)
        for other in labels[index + 1:]:
            if extent.overlaps(other.get_window_extent(renderer)):
                issues.append(("text collision", label.get_text(), other.get_text()))
    assert W <= 5.5 and H <= 2.8
    assert not issues, "\n".join(map(str, issues))
    for extension in ("pdf", "svg"):
        fig.savefig(HERE / f"fig_contracts.{extension}")
    fig.savefig(HERE / "fig_contracts.png", dpi=300)
    plt.close(fig)
    print(f"fig_contracts: evidence, {len(ownership)} text bounds, 2-pt box padding, "
          f"card right padding, text/image, and box-border/arrow collisions passed; {W} x {H} in")


if __name__ == "__main__":
    main()
