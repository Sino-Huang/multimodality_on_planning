"""Twelve unlabelled domains and one held-out image-menu decision.

The gallery uses the alphabetically first task per domain in panel-v2/views.
For the seed-17 adapter, select the first solved Held-out 1 task alphabetically,
excluding ferry and blocksworld, then its earliest 5--8-option decision with
a unique minimum reference key and an agreeing adapter pick. Relax to 4--10
options if necessary, then repeat on Held-out 2. Across solved algorithms,
earliest decision index wins, with algorithm name resolving an index tie.
Run: source ~/cd_vlaplan && python /absolute/path/fig_domains.py [EVIDENCE_ROOT]
"""

import gzip
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.transforms import Bbox
from PIL import Image

from _style import ARM_STYLE, EVIDENCE_ROOT

HERE = Path(__file__).resolve().parent
W, H = 5.5, 2.4
INK, MUTED, LINE = "#213548", "#596775", "#CED8DF"
MAIN_VIEWS = Path("outputs/expanded-study/v1/panel-v2/views")
PANELS = (("p2", "Held-out 1"), ("p2u", "Held-out 2"))
RECIPE = "scene-only-128-unlabelled-v1"
DOMAINS = (
    ("15puzzle", "15-puzzle"), ("blocksworld", "Blocksworld"),
    ("depot", "Depot"), ("driverlog", "Driverlog"),
    ("elevators", "Elevators"), ("ferry", "Ferry"),
    ("grid", "Grid"), ("gripper", "Gripper"), ("logistics", "Logistics"),
    ("storage", "Storage"), ("towers_of_hanoi", "Towers of Hanoi"),
    ("visitall", "Visitall"),
)


def load(path):
    path = EVIDENCE_ROOT / path
    with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as stream:
        return json.load(stream)


def image(path):
    """Read original pixels: no conversion, crop, relabelling, or retouching."""
    with Image.open(EVIDENCE_ROOT / path) as source:
        assert source.size == (128, 128), path
        return source.copy()


def initial_state(manifest, task_id):
    catalog = load(manifest["scene_catalog"])
    assert manifest["task_id"] == catalog["task_id"] == task_id
    state = catalog["states"][0]
    assert state["index"] == 0 and state["parent"] is None
    assert state["atoms"] == catalog["task_context"]["initial_dynamic_atoms"]
    assert state["fluents"] == catalog["task_context"]["initial_dynamic_fluents"]
    return catalog


def assert_binding(native, catalog, index):
    """Check native scene identity against the retained Planimation path."""
    binding = native["scene_bindings"][str(index)]
    path = next(row for row in catalog["path_bindings"] if row["vfg"] == binding["vfg"])
    assert path["state_indices"][binding["stage"]] == index
    assert path["semantic_validation"] == "supplied_actions_and_PDDL_state_sequence_match"
    assert (EVIDENCE_ROOT / binding["vfg"]).is_file()
    return native["scenes"][str(index)]


def gallery_evidence():
    gallery = []
    for domain, name in DOMAINS:
        tasks = sorted(path for path in (EVIDENCE_ROOT / MAIN_VIEWS).iterdir()
                       if path.is_dir() and path.name.startswith(domain + "-"))
        task = tasks[0]
        native_path = task.relative_to(EVIDENCE_ROOT) / "unlabelled/task.json"
        native = load(native_path)
        task_id = "expanded-final/" + task.name
        assert native["recipe_id"] == RECIPE and native["task_id"] == task_id
        manifest = load(native["source_manifest"])
        catalog = initial_state(manifest, task_id)
        path = assert_binding(native, catalog, 0)
        assert path == str(task.relative_to(EVIDENCE_ROOT) / "unlabelled/state-000000.png")
        gallery.append((name, image(path), path))
        print(f"GALLERY {name}: task={task_id}; image={path}; evidence={native_path} -> "
              f"{native['source_manifest']} -> {manifest['scene_catalog']}")
    assert len(gallery) == 12
    return gallery


def select_decision():
    """Apply the prespecified task, menu-size, uniqueness and agreement rule."""
    for directory, panel_name in PANELS:
        base = Path("outputs/choice-frontier/v4/panels") / directory
        cells = load(base / "evaluation/cells.json")["cells"]
        solved = sorted(key for key, result in cells.items()
                        if key.endswith("|learned_adapter|s17")
                        and not any(domain + "-" in key for domain in ("ferry", "blocksworld"))
                        and result["invariant_valid_success"])
        first_task = solved[0].split("|")[0]
        episodes = []
        for key in solved:
            task_id, algorithm, _, _ = key.split("|")
            if task_id != first_task:
                continue
            path = (base / "evaluation/episodes" / task_id.replace("/", "__")
                    / f"{algorithm}-learned_adapter-s17-17.json.gz")
            episode = load(path)
            assert episode["result"] == cells[key]
            episodes.append((algorithm, path, episode))
        for low, high in ((5, 8), (4, 10)):
            matches = []
            for algorithm, path, episode in episodes:
                admissions = {}
                for index, event in enumerate(episode["events"]):
                    assert event["decision_index"] == index
                    if low <= len(event["menu"]) <= high:
                        keys = [admissions[row["state_ref"]]["priority"] for row in event["menu"]]
                        best = min(keys)
                        reference = event["menu"][keys.index(best)]["choice"]
                        pick = json.loads(event["raw_output"]).get("expand_choice")
                        if keys.count(best) == 1 and pick == reference:
                            matches.append((index, algorithm, path, episode, event, admissions.copy()))
                            break
                    for admission in event["trusted_runtime_result"].get("admissions", []):
                        runtime = admission["trusted_runtime_result"]
                        if runtime["status"] == "enqueued":
                            admissions[runtime["target_state_id"]] = runtime
            if matches:
                chosen = min(matches, key=lambda row: (row[0], row[1]))
                print(f"SELECTION panel={panel_name}; task={first_task}; menu_range={low}..{high}")
                return base, panel_name, chosen
    raise AssertionError("No decision satisfies the prespecified selection rule")


def decision_evidence():
    base, panel_name, chosen = select_decision()
    index, algorithm, episode_path, episode, event, admissions = chosen
    task_id = episode["task_id"]
    assert panel_name == "Held-out 1" and task_id == "choice-frontier-v4/depot-expanded-955042"
    assert algorithm == episode["algorithm"] == "best_first_add_w3"
    assert episode["training_seed"] == 17 and episode["condition"] == "learned_adapter"
    assert episode["checkpoint"] == "outputs/choice-frontier/v3/training/best_first_add_w3/seed-17/final"
    assert episode["result"]["goal_reached"] and episode["result"]["algorithm_invariants_hold"]
    assert episode["result"]["expansion_count"] <= episode["decision_cap"]
    assert index == 3
    assert event["menu"] == [{"choice": f"c{i}", "state_ref": state}
                             for i, state in enumerate(("s5", "s1", "s7", "s4", "s8", "s3"))]
    labels = [row["choice"] for row in event["menu"]]
    assert labels == event["input"]["frontier_menu"]["choices"]
    assert set(event["input"]) == {"algorithm", "frontier_menu", "representation", "schema_version"}
    assert len(labels) == len(set(labels)) == event["view"]["menu_size"] == 6
    pick = json.loads(event["raw_output"])["expand_choice"]
    assert pick == "c2" and event["trusted_runtime_result"]["accepted"]
    assert event["trusted_runtime_result"]["expanded_state_id"] == "s7"
    scores = [admissions[row["state_ref"]] for row in event["menu"]]
    assert all(score["priority"] == score["g"] + 3 * score["h"] for score in scores)
    keys = [score["priority"] for score in scores]
    assert keys == [38, 34, 30, 38, 36, 31] and keys.count(min(keys)) == 1
    head = episode["events"][index - 1]["trusted_runtime_result"]["frontier_after"]["head"]
    reference = next(row["choice"] for row in event["menu"] if row["state_ref"] == head["state_id"])
    assert reference == pick and head["priority"] == min(keys) == 30
    report = load(base / "reference-views.json")
    task = next(row for row in report["tasks"] if row["row"]["task_id"] == task_id)
    native = task["native_views"]
    assert native["recipe_id"] == RECIPE
    retained = load(Path(episode["view_output"]) / "views.json.gz")
    assert retained["task_id"] == task_id and retained["source_manifest"] == native["source_manifest"]
    catalog = initial_state(load(native["source_manifest"]), task_id)
    pages = [page for page in event["view"]["input_pages"] if page[0] == "frontier-choice"]
    assert pages == [["frontier-choice", n, 0] for n in (5, 1, 28, 26, 29, 3)]
    assert [score["h"] for score in scores] == [12, 11, 9, 12, 11, 10]
    action_paths = {"s0": []}
    for previous in episode["events"][:index]:
        runtime = previous["trusted_runtime_result"]
        for admission in runtime["admissions"]:
            result = admission["trusted_runtime_result"]
            if result["status"] == "enqueued":
                action = admission["action"]
                name = "(" + " ".join([action["name"], *action["args"]]) + ")"
                action_paths[result["target_state_id"]] = action_paths[runtime["expanded_state_id"]] + [name]
    menu = []
    for row, page, score in zip(event["menu"], pages, scores):
        scene_index = page[1]
        if str(scene_index) in native["scenes"]:
            path = assert_binding(native, catalog, scene_index)
        else:
            state = next(state for state in retained["states"] if state["index"] == scene_index)
            path = state["scene_path"]
            assert path == str(Path(episode["view_output"]) / f"state-{scene_index:06d}.png")
            assert state["supplied_actions"] == action_paths[row["state_ref"]]
            assert state["parent"]["action"] == state["supplied_actions"][-1]
            assert (EVIDENCE_ROOT / state["vfg"]).is_file()
        menu.append((row["choice"], image(path), score["h"], row["choice"] == pick,
                     row["choice"] == reference))
        print(f"MENU {row['choice']}: runtime={row['state_ref']}; catalog={scene_index}; "
              f"h_add={score['h']}; g={score['g']}; key={score['priority']}; image={path}")
    print(f"DECISION source={episode_path}; index={index}; size={len(menu)}; adapter={pick}; "
          f"reference={reference}; unique minimum key=30")
    return menu, f"{panel_name} · Depot · WA*"


def main():
    gallery = gallery_evidence()
    menu, subtitle = decision_evidence()
    fig = plt.figure(figsize=(W, H), dpi=300, facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, W), ylim=(0, H))
    ax.axis("off")
    texts, images = [], []
    panels = {"a": (0.02, 0.925, 5.48, 2.38), "b": (0.02, 0.02, 5.48, 0.90)}

    def text(panel, x, y, value, size=6, **kwargs):
        artist = ax.text(x, y, value, fontsize=size, color=INK, va="center", **kwargs)
        texts.append((artist, panel))

    def scene(panel, pixels, x, y, side):
        extent = (x, x + side, y, y + side)
        ax.imshow(pixels, extent=extent, interpolation="nearest", aspect="equal", zorder=2)
        ax.add_patch(Rectangle((x, y), side, side, fill=False, edgecolor=LINE, lw=.45, zorder=3))
        images.append((Bbox.from_extents(x, y, x + side, y + side), panel))

    text("a", .06, 2.285, "a  What the VLM sees", size=8, weight="bold")
    text("b", .06, .835, "b  One held-out decision", size=8, weight="bold")
    text("b", 5.42, .835, subtitle, size=6.5, ha="right")
    ax.plot([.06, 5.42], [.92, .92], color=LINE, lw=.65)
    for i, (name, pixels, _) in enumerate(gallery):
        row, column = divmod(i, 6)
        center = .47 + .91 * column
        bottom = 1.69 - .64 * row
        scene("a", pixels, center - .25, bottom, .50)
        text("a", center, bottom - .075, name, ha="center")
    for i, (label, pixels, h, picked, reference) in enumerate(menu):
        center = .47 + .91 * i
        x, y, side = center - .235, .255, .47
        scene("b", pixels, x, y, side)
        if picked:
            ax.add_patch(Rectangle((x - .012, y - .012), side + .024, side + .024,
                                   fill=False, lw=1.5, edgecolor=ARM_STYLE["learned_adapter_seed_mean"]["color"],
                                   zorder=4))
        if reference:
            ax.plot(x - .065, y + side / 2, "o", color=INK, ms=3.6, zorder=4)
        text("b", center, y - .075, f"{label} · h_add {h}", size=6, ha="center")
    text("b", .06, .065, "Orange frame + dark dot: adapter = reference", size=6)
    text("b", 5.42, .065, "h_add shown for the reader only", size=6, ha="right")

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    text_boxes = []
    panel_boxes = {name: ax.transData.transform_bbox(Bbox.from_extents(*bounds))
                   for name, bounds in panels.items()}
    image_boxes = [(ax.transData.transform_bbox(box), panel) for box, panel in images]

    def contained(outer, inner):
        return (outer.x0 <= inner.x0 and outer.y0 <= inner.y0
                and outer.x1 >= inner.x1 and outer.y1 >= inner.y1)

    for artist, panel in texts:
        box = artist.get_window_extent(renderer)
        assert artist.get_fontsize() >= 6
        assert contained(canvas, box), artist.get_text()
        assert contained(panel_boxes[panel], box), artist.get_text()
        text_boxes.append((box, artist.get_text()))
    for i, (box, value) in enumerate(text_boxes):
        for other, other_value in text_boxes[i + 1:]:
            assert not box.overlaps(other), (value, other_value)
        for image_box, _ in image_boxes:
            assert not box.overlaps(image_box), ("text/image", value)
    for i, (box, panel) in enumerate(image_boxes):
        assert contained(panel_boxes[panel], box)
        for other, _ in image_boxes[i + 1:]:
            assert not box.overlaps(other), "image/image"
    assert tuple(fig.get_size_inches()) == (5.5, 2.4)
    for suffix in ("pdf", "svg", "png"):
        fig.savefig(HERE / f"fig_domains.{suffix}", dpi=300, facecolor="white")
    plt.close(fig)
    assert "<text" in (HERE / "fig_domains.svg").read_text()
    with Image.open(HERE / "fig_domains.png") as preview:
        assert preview.size == (1650, 720)
    print(f"PASS: 12 initial scenes, 6 menu scenes, source/task/state/binding/score/pick assertions; "
          f"{len(texts)} text boxes; canvas/panel containment, text/text, text/image, image/image "
          "checks; minimum 6 pt; 5.5 x 2.4 in; PDF/SVG/PNG exported; SVG text editable")


if __name__ == "__main__":
    main()
