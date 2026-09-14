#!/usr/bin/env python
"""Independent source, profile, split, replay and view checks for the selected panel."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.expanded_views import reference_catalog
from examples.planning_benchmark_slice.modality_pages import fact_blocks, paginate
from examples.planning_benchmark_slice.modality_view_preparation import _state_goal_checks
from examples.planning_benchmark_slice.pddl_state import PDDLStateAuthority, GroundedAction
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.scene_only_preparation import check_task
from examples.planning_benchmark_slice.source_goal import source_task
from examples.planning_benchmark_slice.task_isomorphism import same_instance, context_shape


def main():
    path = ROOT / "outputs/expanded-study/v1/panel-v2/independent-audit.json"
    if len(sys.argv) > 1 and sys.argv[1] == "hook":
        terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
        if terminal["status"] != "succeeded":
            raise RuntimeError(f"panel audit failed: {terminal['directory']}/worker.log")
        r = read(path)
        assert r["outcome"] == "PASS" and len(r["tasks"]) == 24
        write(ROOT / "docs/experiments/expanded-study/panel-independent-audit.json", r)
        print("PASS: independently audited 24 source/profile/split/replay/view bindings")
        return
    protocol = read(ROOT / "configs/experiments/expanded-study/panel-protocol-v2.json")
    selection = read(ROOT / protocol["output_root"] / "structural-selection.json")
    report = read(ROOT / protocol["output_root"] / "reference-views.json")
    scope = read(ROOT / protocol["domain_scope"])
    assert selection["protocol"] == report["protocol"] == protocol
    assert len(report["tasks"]) == scope["target_problems"] == 24
    assert {t["row"]["domain"] for t in report["tasks"]} == set(scope["domains"])
    selected = {g["selected"]["row"]["task_id"]: g for g in selection["strata"]}
    historical = read(ROOT / protocol["historical_inventory"])
    from collections import defaultdict

    index = defaultdict(list)
    for raw in historical["task_semantics"]:
        context = json.loads(raw)
        index[context_shape(context)].append(context)
    contexts = []
    results = []
    for task in report["tasks"]:
        row = task["row"]
        group = selected[row["task_id"]]
        assert row == group["selected"]["row"] and row["split"] == "test"
        profile = next(
            p for p in protocol["strata"] if (p["domain"], p["stratum"]) == (row["domain"], row["difficulty"])
        )
        assert group["selected"]["seed"] in profile["seeds"]
        source = read(ROOT / row["task_path"])
        authority = PDDLStateAuthority.from_pddl(source["domain_pddl"], source["problem_pddl"])
        context = authority.task_context()
        assert not any(same_instance(context, old) for old in index[context_shape(context)])
        assert not any(same_instance(context, old) for old in contexts)
        contexts.append(context)
        if source.get("initial_walk"):
            walk = source["initial_walk"]
            initial = PDDLStateAuthority.from_pddl(source["domain_pddl"], walk["origin_problem_pddl"])
            state = initial.initial_state
            assert len(walk["actions"]) == profile["walk_steps"]
            for action in walk["actions"]:
                words = action.strip("()").split()
                state = initial.apply(state, GroundedAction(words[0], tuple(words[1:]))).target_state
            assert state.atoms == authority.initial_state.atoms and state.fluents == authority.initial_state.fluents
            assert source_task(source["domain_pddl"], walk["origin_problem_pddl"]) == source_task(
                source["domain_pddl"], source["problem_pddl"]
            )
        native = task["native_views"]
        manifest = read_json(ROOT / native["source_manifest"])
        catalog = read_json(ROOT / manifest["scene_catalog"])
        assert manifest["source"] == source_task(source["domain_pddl"], source["problem_pddl"])
        _state_goal_checks(authority, catalog, manifest["source"])
        check_task(ROOT, native, set(range(len(catalog["states"]))))
        expected = [
            p.to_dict()
            for p in paginate(
                "goal", fact_blocks(catalog["task_context"], catalog["states"][0], manifest["source"])["goal"]
            )
        ]
        assert manifest["reusable_recipes"]["goal"] == json.loads(json.dumps(expected))
        replay = reference_catalog(ROOT, row, task["reference_paths"], protocol["study_id"])
        assert replay["decisions"] == catalog["decisions"]
        assert all(
            {k: s[k] for k in ("index", "atoms", "fluents", "parent")} == r
            for s, r in zip(catalog["states"], replay["states"], strict=True)
        )
        assert len(task["measurements"]) == len(replay["decisions"])
        snapshot = ROOT / "configs/experiments/expanded-study/tasks" / f"{row['domain']}-{row['difficulty']}.json"
        write(snapshot, source)
        results.append(
            dict(
                task_id=row["task_id"],
                domain=row["domain"],
                stratum=row["difficulty"],
                seed=group["selected"]["seed"],
                source_snapshot=str(snapshot.relative_to(ROOT)),
                states=len(catalog["states"]),
                reference_decisions=len(replay["decisions"]),
                split_isolation=True,
                source_goal_and_walk_replayed=True,
                reference_replay=True,
                native_view_bindings=True,
            )
        )
        write(os.environ["EXPANDED_PROGRESS_PATH"], dict(completed=len(results)))
        print(results[-1], flush=True)
    write(
        path,
        dict(
            outcome="PASS",
            tasks=results,
            historical_contexts=len(historical["task_semantics"]),
            gpu_qualification_separate=True,
        ),
    )


if __name__ == "__main__":
    main()
