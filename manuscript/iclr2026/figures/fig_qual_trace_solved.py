"""Illustrative issue-145 five-block search trace; run: python fig_qual_trace_solved.py.

Evidence: outputs/expanded-study/v1/baseline/episodes/{text,visual}-state/
expanded-final__blocksworld-expanded-911101/best_first_add_greedy-
{process_sft,exact_reference}.json.gz events[].{input,raw_output,view}, result;
outputs/expanded-study/v1/panel-v2/views/blocksworld-expanded-911101/
scenes/catalog.json.gz states[].{atoms,scene_path}. Policy images are cached,
not re-rendered; only nearest-neighbour enlargement is applied.
"""
import gzip
import json
from pathlib import Path

import matplotlib.pyplot as plt
from PIL import Image

from _style import EVIDENCE_ROOT, ARM_STYLE

HERE = Path(__file__).resolve().parent
TASK = "expanded-final__blocksworld-expanded-911101"
BASE = f"outputs/expanded-study/v1/baseline/episodes"
CATALOG = "outputs/expanded-study/v1/panel-v2/views/blocksworld-expanded-911101/scenes/catalog.json.gz"
INK = "#253746"
MUTED = "#596a76"
ORANGE = ARM_STYLE["first_adapter"]["color"]


def gz(rel):
    with gzip.open(EVIDENCE_ROOT / rel, "rt") as stream:
        return json.load(stream)


def episode(observation, algorithm, arm):
    path = f"{BASE}/{observation}/{TASK}/{algorithm}-{arm}.json.gz"
    data = gz(path)
    assert data["output"] == path and data["modality"] == observation
    return data


def atoms_in_event(event):
    observation = event["input"].get("observation")
    if observation is not None and "state_atoms" in observation:
        return set(observation["state_atoms"])
    facts = event["input"]["current"]["state_facts"]
    args = facts["arguments"]
    atoms = set(facts["zero_arity"])
    for group in facts["unary_groups"]:
        for argument in group["arguments"]:
            for predicate in group["predicates"]:
                atoms.add(f"{predicate}({args[argument]})")
    for predicate, by_first in facts["binary_by_first"].items():
        for first, seconds in by_first:
            for second in seconds:
                atoms.add(f"{predicate}({args[first]},{args[second]})")
    for predicate, rows in facts["nary"].items():
        for row in rows:
            atoms.add(f"{predicate}({','.join(args[i] for i in row)})")
    return atoms


def scene(catalog, index, event=None):
    if event is not None:
        assert event["view"]["state_representation"] == "scene-only-128-unlabelled-v1"
        assert ["current-state", index, 0] in event["view"]["input_pages"]
        assert event["view"]["state"] == index
        assert set(catalog["states"][index]["atoms"]) == atoms_in_event(event)
    # The cached, unlabelled 128-pixel policy input is the evidence image.
    path = f"outputs/expanded-study/v1/panel-v2/views/blocksworld-expanded-911101/unlabelled/state-{index:06d}.png"
    assert catalog["states"][index]["scene_path"].endswith(f"/frames/state-{index:06d}.png")
    with Image.open(EVIDENCE_ROOT / path) as image:
        assert image.size == (128, 128)
        return image.copy()


def save(fig, name):
    assert fig.get_size_inches().tolist() == {"fig_qual_trace_solved": [5.5, 2.6],
                                               "fig_qual_trace_failures": [5.5, 2.4],
                                               "fig_qual_trace_corruption": [5.5, 1.4]}[name]
    for ext in ("pdf", "svg", "png"):
        fig.savefig(HERE / f"{name}.{ext}", dpi=300 if ext == "png" else None)
    plt.close(fig)


def text(fig, x, y, label, *, size=6.3, color=INK, weight="normal", **kwargs):
    assert size >= 6
    fig.text(x, y, label, fontsize=size, color=color, weight=weight, **kwargs)


def main():
    catalog = gz(CATALOG)
    assert catalog["task_context"]["objects_by_type"]["object"] == ["b1", "b2", "b3", "b4", "b5"]
    assert catalog["canonical_goal"] == ["and", [
        ["atom", "on", ["b2", "b4"]], ["atom", "on", ["b3", "b5"]],
        ["atom", "on", ["b4", "b3"]]]]
    visual = episode("visual-state", "best_first_add_greedy", "process_sft")
    reference = episode("visual-state", "best_first_add_greedy", "exact_reference")
    text_adapter = episode("text-state", "best_first_add_greedy", "process_sft")
    text_reference = episode("text-state", "best_first_add_greedy", "exact_reference")
    for adapter, exact in ((visual, reference), (text_adapter, text_reference)):
        result = adapter["result"]
        assert (result["termination_reason"], result["decision_count"], result["expansion_count"]) == ("goal_reached", 18, 6)
        assert [event["raw_output"] for event in adapter["events"]] == [event["raw_output"] for event in exact["events"]]
    events = visual["events"]
    expanded = []
    for event in events:
        if not expanded or expanded[-1][0] != event["input"]["current"]["state_id"]:
            expanded.append((event["input"]["current"]["state_id"], event))
    assert [(state, event["input"]["current"]["h"]) for state, event in expanded] == [
        ("s0", 8), ("s1", 8), ("s3", 5), ("s6", 5), ("s9", 2), ("s11", 1)]
    final = events[17]
    goal_row = dict(zip(final["input"]["successor_candidates"]["columns"], final["input"]["successor_candidates"]["rows"][0]))
    assert (goal_row["target_state_id"], goal_row["h"], final["successor_state"]) == ("s13", 0, 77)
    assert set(catalog["states"][77]["atoms"]) >= {"on(b2,b4)", "on(b3,b5)", "on(b4,b3)"}
    assert ["current-state", 8, 0] in events[8]["view"]["input_pages"]
    # At s6 the first unpruned equal-priority pair occurs in this episode.
    for event in events[:8]:
        block = event["input"]["successor_candidates"]
        earlier = [dict(zip(block["columns"], row)) for row in block["rows"]]
        priorities = [r["priority"] for r in earlier if not r["pruned"]]
        assert len(priorities) == len(set(priorities))
    assert events[12]["input"]["current"]["state_id"] == "s9"
    rows = [dict(zip(events[8]["input"]["successor_candidates"]["columns"], row)) for row in events[8]["input"]["successor_candidates"]["rows"]]
    assert [(r["action"], r["g"], r["h"], r["priority"], r["closed"], r["pruned"], r["target_state_id"]) for r in rows] == [
        (["putdown", "b4"], 4, 4, 4, False, False, "s7"),
        (["stack", "b4", "b1"], 4, 4, 4, False, False, "s8"),
        (["stack", "b4", "b2"], 4, 5, 5, True, True, "s3"),
        (["stack", "b4", "b3"], 4, 2, 2, False, False, "s9")]
    assert [json.loads(e["raw_output"])["action"]["name"] for e in events[8:12]] == ["putdown", "stack", "stack", "stack"]
    fig = plt.figure(figsize=(5.5, 2.6), facecolor="white")
    text(fig, .025, .952, "A trained greedy best-first search trace", size=7.5, weight="bold")
    text(fig, .025, .892, "Expanded states (cached policy views; $h_{add}$ alongside)", size=6.2, color=MUTED)
    # Evidence: events[].input.current.{state_id,h}, view.input_pages, catalog.states[].atoms/scene_path.
    for j, (state, event) in enumerate(expanded + [("s13", None)]):
        x = .024 + j * .14
        index = event["view"]["state"] if event else 77
        image = scene(catalog, index, event)
        ax = fig.add_axes([x, .65, .104, .212])
        ax.imshow(image, interpolation="nearest")
        ax.axis("off")
        h = event["input"]["current"]["h"] if event else goal_row["h"]
        text(fig, x+.052, .619, f"{state}  h={h}", size=6.2, ha="center")
        if j < 6:
            text(fig, x+.119, .75, "→", size=7, ha="center", color=MUTED)
    text(fig, .025, .565, "One expansion: s6, h_add=5", size=7, weight="bold")
    text(fig, .437, .565, "Runtime heap expands s9 (h_add=2) next", size=6.2, weight="bold")
    # Evidence: events[8] is the s6 cached policy view; candidate rows are runtime-computed values.
    ax = fig.add_axes([.027, .118, .18, .37]); ax.imshow(scene(catalog, 8, events[8]), interpolation="nearest"); ax.axis("off")
    text(fig, .023, .08, "s6 · catalog state 8", size=6, color=MUTED)
    text(fig, .245, .484, "Textual successor rows", size=6.7, weight="bold")
    text(fig, .245, .425, "action", size=6, color=MUTED)
    text(fig, .438, .425, "g", size=6, color=MUTED)
    text(fig, .476, .425, "h", size=6, color=MUTED)
    text(fig, .512, .425, "prio", size=6, color=MUTED)
    text(fig, .565, .425, "state", size=6, color=MUTED)
    for j, row in enumerate(rows):
        y = .35 - j*.079
        action = f"{row['action'][0]}({','.join(row['action'][1:])})" + ("*" if row["pruned"] else "")
        text(fig, .245, y, action, size=6, color=MUTED if row["pruned"] else INK)
        text(fig, .438, y, str(row["g"]), size=6)
        text(fig, .476, y, str(row["h"]), size=6)
        text(fig, .512, y, str(row["priority"]), size=6, color=MUTED if row["pruned"] else INK)
        text(fig, .565, y, row["target_state_id"], size=6)
    text(fig, .245, .035, "* closed/pruned by runtime", size=6, color=MUTED)
    text(fig, .61, .518, "Adapter emits (verbatim)", size=6.7, weight="bold", color=ORANGE)
    # Evidence: visual process_sft events[8:12].raw_output, reference events[8:12].raw_output.
    # The three segments concatenate exactly to the original raw JSON string.
    for j, event in enumerate(events[8:12]):
        raw = event["raw_output"]
        p = raw.index('"name":')
        q = raw.index('"source_state_id":')
        assert raw[p-1] == ',' and raw[q-1] == ','
        for k, segment in enumerate((raw[:p], raw[p:q], raw[q:])):
            text(fig, .61, .468 - (j*3 + k)*.039, segment, size=6.0, family="DejaVu Sans Mono")
    save(fig, "fig_qual_trace_solved")
    print("Q1: 18 decisions, six expanded, identical visual and text reference outputs; seven cached scenes")


if __name__ == "__main__":
    main()
