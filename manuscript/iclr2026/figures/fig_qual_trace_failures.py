"""512-record BFS and BFWS failure mechanisms across 24 tasks × 3 modalities.

Evidence: outputs/expanded-study/v1/baseline/episodes/{text,visual,multimodal}-state/
expanded-final__*/{bfs,best_first_width}-{process_sft,exact_reference,random_valid}.json.gz
(events[].{input,raw_output,accepted,view}, result); failure-mechanism-tables/
failures-by-cell.csv; cached policy scenes from panel-v2/views/blocksworld-expanded-911101.
The task was nominated in issue #145; selection is illustrative, not pre-registered.
"""
import csv
import io
import json

import matplotlib.pyplot as plt

from _style import EVIDENCE_ROOT, ARM_STYLE
from fig_qual_trace_solved import BASE, CATALOG, TASK, ORANGE, INK, MUTED, episode, gz, scene, save, text

OBS = ("text-state", "visual-state", "multimodal-state")


def aggregate():
    # Evidence: all 72 baseline episodes/algorithm; CSV strata include 27 BFS
    # process_sft episodes/modality, while the present main grid has 24.
    table = list(csv.DictReader(io.StringIO((EVIDENCE_ROOT / "docs/experiments/expanded-study/failure-mechanism-tables/failures-by-cell.csv").read_text())))
    for obs in OBS:
        for alg, expected in (("bfs", {"other_invariant_violation": 26 if obs != "visual-state" else 24,
                                               "invalid_frontier_operation": 1 if obs != "visual-state" else 2}),
                              ("best_first_width", {"malformed_output": 24})):
            rows = [r for r in table if r["algorithm_family"] == alg and r["modality"] == obs and r["arm"] == "process_sft"]
            assert {r["failure_kind"]: int(r["failures"]) for r in rows} == expected
            assert {int(r["stratum_episodes"]) for r in rows} == {27 if alg == "bfs" else 24}
    # The extra 3 BFS episodes/observation type are outside this main-grid
    # count; their identification as DAgger original_process_sft is unverified.
    tasks = sorted((EVIDENCE_ROOT / BASE / "text-state").glob("expanded-final__*"))
    assert len(tasks) == 24
    bfs = {"bookkeeping": 0, "unvisited": 0, "visited": 0, "retire": 0}
    bfws = {"unparseable": 0, "invented_schema": 0, "reference_action": 0}
    expected_keys = {"action", "evaluate_target", "frontier_intent", "source_state_id", "visit_target"}
    for obs in OBS:
        assert {p.name for p in (EVIDENCE_ROOT / BASE / obs).glob("expanded-final__*")} == {p.name for p in tasks}
        for task in tasks:
            for algorithm in ("bfs", "best_first_width"):
                root = f"{BASE}/{obs}/{task.name}/{algorithm}"
                learned, reference = gz(root + "-process_sft.json.gz"), gz(root + "-exact_reference.json.gz")
                assert learned["result"]["termination_reason"] == "deterministic_invalid_operation"
                failed = learned["events"][-1]
                assert failed["accepted"] is False and all(e["accepted"] for e in learned["events"][:-1])
                if algorithm == "best_first_width":
                    assert len(learned["events"]) == learned["result"]["decision_count"] == 1
                    try:
                        output = json.loads(failed["raw_output"])
                    except json.JSONDecodeError:
                        bfws["unparseable"] += 1
                        continue
                    typed = output["typed_operation"]
                    assert isinstance(typed, dict) and set(typed) != expected_keys
                    bfws["invented_schema"] += 1
                    ref_op = json.loads(reference["events"][0]["raw_output"])["typed_operation"]
                    bfws["reference_action"] += typed.get("action") == ref_op["action"]
                    continue
                operation = json.loads(failed["raw_output"])["typed_operation"]
                if operation.get("operation_type") == "retire_frontier":
                    bfs["retire"] += 1
                    continue
                assert set(operation) == expected_keys
                head = failed["input"]["observation"]["state_id"]
                matches = [event for event in reference["events"]
                           if event["input"]["observation"]["state_id"] == head
                           and json.loads(event["raw_output"])["typed_operation"].get("action") == operation["action"]]
                assert matches, (obs, task.name, operation)
                prior = [e for e in learned["events"][:-1]
                         if e["input"]["observation"]["state_id"] == head
                         and json.loads(e["raw_output"])["typed_operation"].get("action") == operation["action"]]
                bfs["visited" if prior else "unvisited"] += 1
                ref_op = json.loads(reference["events"][failed["index"]]["raw_output"])["typed_operation"]
                assert operation["frontier_intent"] != ref_op["frontier_intent"]
                bfs["bookkeeping"] += 1
    assert bfs == {"bookkeeping": 68, "unvisited": 67, "visited": 1, "retire": 4}, bfs
    assert bfws == {"unparseable": 32, "invented_schema": 40, "reference_action": 17}, bfws
    return bfs, bfws


def main():
    counts = aggregate()
    catalog = gz(CATALOG)
    bfs = [episode(obs, "bfs", "process_sft") for obs in OBS]
    bfs_ref = episode("text-state", "bfs", "exact_reference")
    bfs_random = episode("text-state", "bfs", "random_valid")
    assert (bfs_ref["result"]["termination_reason"], bfs_ref["result"]["decision_count"]) == ("goal_reached", 143)
    assert (bfs_random["result"]["termination_reason"], bfs_random["result"]["decision_count"]) == ("expansion_budget_exhausted", 145)
    assert all(d["result"]["termination_reason"] == "deterministic_invalid_operation" and d["result"]["decision_count"] == 3 and len(d["events"]) == 3 and all(e["accepted"] for e in d["events"][:2]) for d in bfs)
    assert len({d["events"][2]["raw_output"] for d in bfs}) == 1
    bfws = [episode(obs, "best_first_width", "process_sft") for obs in OBS]
    bfws_ref = [episode(obs, "best_first_width", "exact_reference") for obs in OBS]
    # Evidence: checkpoint-matched reports under outputs/matched_modalities/v3
    # and v5/training/{observation}/{algorithm}/report.json.
    for report in bfs + bfws:
        checkpoint = report["checkpoint"]
        training = json.loads((EVIDENCE_ROOT / checkpoint).parent.joinpath("report.json").read_text())
        assert training["final_checkpoint"] == checkpoint and training["train_records"] == 512
        assert len(training["training_record_ids"]) == 512
    assert all(d["result"]["termination_reason"] == "deterministic_invalid_operation" and d["result"]["decision_count"] == 1 and len(d["events"]) == 1 and not d["events"][0]["accepted"] for d in bfws)
    left = json.loads(bfs[0]["events"][2]["raw_output"])["typed_operation"]
    right = json.loads(bfs_ref["events"][2]["raw_output"])["typed_operation"]
    assert left["action"] == right["action"] == {"name": "putdown", "args": ["b1"]}
    assert left["frontier_intent"] == {"retire_source": False, "target_position": 2}
    assert right["frontier_intent"] == {"retire_source": True, "target_position": 1}
    assert all(d["events"][2]["input"]["observation"]["frontier_size"] == 2 for d in bfs)
    assert set(bfs[0]["events"][2]["input"]["observation"]["state_atoms"]) == set(catalog["states"][1]["atoms"])
    # Candidate list follows the exact BFS continuation: the third operation
    # revisits the initial state. Runtime's first two successors are unvisited.
    assert [json.loads(e["raw_output"])["typed_operation"]["action"] for e in bfs_ref["events"][2:4]] == [
        {"name": "putdown", "args": ["b1"]}, {"name": "stack", "args": ["b1", "b3"]}]
    assert all(e["accepted"] for e in bfs_ref["events"][2:4])
    visited = {frozenset(catalog["states"][i]["atoms"]) for i in (0, 1, 2)}
    assert all(frozenset(catalog["states"][e["successor_state"]]["atoms"]) not in visited
               for e in bfs_ref["events"][2:4])
    head_atoms = set(bfs[0]["events"][2]["input"]["observation"]["state_atoms"])
    assert {"holding(b1)", "clear(b4)"} <= head_atoms
    assert head_atoms - {"holding(b1)", "clear(b4)"} | {
        "arm-empty", "clear(b1)", "on(b1,b4)"} == set(catalog["states"][0]["atoms"])
    assert ["current-state", 1, 0] in bfs[1]["events"][2]["view"]["input_pages"]
    for learned, reference in zip(bfws, bfws_ref):
        ref = json.loads(reference["events"][0]["raw_output"])["typed_operation"]
        assert ref == {"action": {"args": ["b1", "b4"], "name": "unstack"}, "evaluate_target": True,
                       "frontier_intent": {"retire_source": True, "target_position": 0}, "source_state_id": "$", "visit_target": True}
        candidate = reference["events"][0]["input"]["observation"]["candidates"][0]
        objects = reference["events"][0]["input"]["task_context"]["objects"]
        assert candidate["eval"]["frontier"] == ref["frontier_intent"]
        assert (candidate["action"]["name"], [objects[i] for i in candidate["action"]["args"]]) == ("unstack", ["b1", "b4"])
    typed = [json.loads(d["events"][0]["raw_output"])["typed_operation"] for d in bfws[:2]]
    assert set(typed[0]) == {"action", "evaluate_target", "frontier_exhausted", "exact_bfws_goal_count_priority_successor", "exact_bfws_successor", "retire_source", "source_state_id"}
    assert set(typed[1]) == {"action", "frontier_target_state_id", "retire_source_state"}
    runaway = bfws[2]["events"][0]["raw_output"]
    assert len(runaway) == 1712 and '"action":{"args":["b1","b4"],"name":"unstack"}' in runaway
    assert '"exact_bfws_goal_count_priority_successor"' in runaway
    try:
        json.loads(runaway)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("multimodal runaway unexpectedly became valid JSON")
    assert all(op["action"] == {"args": ["b1", "b4"], "name": "unstack"} for op in typed)
    fig = plt.figure(figsize=(5.5, 2.4), facecolor="white")
    text(fig, .023, .939, "Why the 512-record BFS and BFWS adapters fail", size=7.5, weight="bold")
    text(fig, .023, .88, "BFS · queue fields", size=7.2, weight="bold", color="#0072B2")
    text(fig, .52, .88, "BFWS · operation schema", size=7.2, weight="bold", color="#009E73")
    # Evidence: BFS events[2] and exact events[2], plus the unlabelled
    # state-000001.png seen by the visual policy at its rejected operation.
    ax = fig.add_axes([.025, .39, .205, .44]);ax.imshow(scene(catalog, 1, bfs[1]["events"][2]), interpolation="nearest");ax.axis("off")
    text(fig, .025, .345, "Head: b1 held", size=6.1)
    text(fig, .025, .295, "frontier size 2", size=6.1)
    text(fig, .025, .245, "putdown(b1) · unvisited", size=6.1)
    text(fig, .025, .195, "stack(b1,b3) · unvisited", size=6.1)
    text(fig, .025, .145, "stack(b1,b4) · visited", size=6.1)
    text(fig, .235, .77, "Adapter", size=6.3, weight="bold")
    text(fig, .235, .69, "putdown(b1)", size=6.1)
    text(fig, .235, .61, "retire_source: false", size=6.1, color=ORANGE)
    text(fig, .235, .53, "target_position: 2", size=6.1, color=ORANGE)
    text(fig, .235, .44, "Reference", size=6.3, weight="bold")
    text(fig, .235, .36, "putdown(b1)", size=6.1)
    text(fig, .235, .28, "retire_source: true", size=6.1, color=ORANGE)
    text(fig, .235, .20, "target_position: 1", size=6.1, color=ORANGE)
    text(fig, .025, .086, "Exact: goal in 143; random-valid: cap at 145", size=6.1)
    # Evidence: BFWS first candidate.eval.frontier, all three process_sft
    # first raw operations, and exact_reference first typed operation.
    text(fig, .52, .787, "Candidate eval.frontier: {true, 0}", size=6.2)
    text(fig, .52, .707, "Reference: unstack(b1,b4); visit/evaluate", size=6.1)
    text(fig, .52, .647, "source '$'; frontier_intent {true, 0}", size=6.1)
    text(fig, .52, .554, "Text: missing frontier_intent, visit_target", size=6.1, color=ORANGE)
    text(fig, .52, .482, "invented: frontier_exhausted, exact_bfws_*", size=6.1)
    text(fig, .52, .391, "Visual: frontier_target_state_id,", size=6.1, color=ORANGE)
    text(fig, .52, .327, "retire_source_state (invented keys)", size=6.1)
    text(fig, .52, .237, "Multimodal: invented-key runaway", size=6.1, color=ORANGE)
    text(fig, .52, .17, f"{bfws[2]['events'][0]['raw_output'][:38]}…", size=6.0, family="DejaVu Sans Mono")
    text(fig, .52, .09, "1,712 characters; rejected at decision 1", size=6.1)
    save(fig, "fig_qual_trace_failures")
    print("Q2: BFS", counts[0], "BFWS", counts[1])


if __name__ == "__main__":
    main()
