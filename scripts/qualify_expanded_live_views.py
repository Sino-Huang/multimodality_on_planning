#!/usr/bin/env python
"""Exercise unseen accepted-state rendering and read-only restoration on every task."""

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.expanded_views import ExpandedTaskViews
from examples.planning_benchmark_slice.source_goal import evaluate_goal
from PIL import Image


def main():
    output = ROOT / "outputs/expanded-study/v1/panel-v2/live-view-qualification"
    if len(sys.argv) > 1 and sys.argv[1] == "audit":
        terminal = read(os.environ["EXPANDED_TERMINAL_PATH"])
        if terminal["status"] != "succeeded":
            raise RuntimeError(f"live-view qualification failed: {terminal['directory']}/worker.log")
        report = read(output / "report.json")
        assert len(report["tasks"]) == 24
        assert all(t["outcome"] == "PASS" for t in report["tasks"])
        write(ROOT / "docs/experiments/expanded-study/panel-live-views.json", report)
        print("PASS: all 24 tasks exercised off-reference rendering/restoration or verified reference closure")
        return
    tasks = read(ROOT / "outputs/expanded-study/v1/panel-v2/reference-views.json")["tasks"]
    reports = []
    for number, task in enumerate(tasks):
        folder = output / task["row"]["task_id"].replace("/", "__")
        views = ExpandedTaskViews(ROOT, task, folder, "http://127.0.0.1:18092")
        selected = None
        for entry in views.catalog["states"]:
            source = views.authority.canonical_state(tuple(entry["atoms"]), tuple(entry["fluents"]))
            for action in views.authority.applicable_actions(source):
                target = views.authority.apply(source, action).target_state
                if views.key(target.atoms, target.fluents) not in {
                    views.key(s["atoms"], s["fluents"]) for s in views.catalog["states"]
                }:
                    selected = (source, action, target)
                    break
            if selected:
                break
        result = dict(task_id=task["row"]["task_id"], outcome="PASS", reference_closure=selected is None)
        if selected:
            source, action, target = selected
            if views.key(target.atoms, target.fluents) not in views.indices:
                assert len(views.scene_views.tasks[views.row["task_id"]]["scenes"]) == views.original_count
            index = views.register(source, dict(name=action.name, args=list(action.args)))
            assert index >= views.original_count
            views.save()
            restored = ExpandedTaskViews(ROOT, task, folder, "http://127.0.0.1:18092", read_only=True)
            native = restored.scene_views.tasks[restored.row["task_id"]]
            assert (
                native["scene_bindings"][str(index)]
                == views.scene_views.tasks[views.row["task_id"]]["scene_bindings"][str(index)]
            )
            with Image.open(ROOT / native["scenes"][str(index)]) as image:
                assert image.size == (128, 128)
            assert evaluate_goal(
                restored.manifest["source"]["source_goal"],
                set(target.atoms) | set(restored.authority.static_initial_facts),
                restored.manifest["source"],
            ) == restored.authority.is_goal(target)
            result.update(
                state=index,
                source_state=views.indices[views.key(source.atoms, source.fluents)],
                action=action.serialize(),
                native_scene=native["scenes"][str(index)],
                native_binding=native["scene_bindings"][str(index)],
                restored_read_only=True,
            )
        reports.append(result)
        write(os.environ["EXPANDED_PROGRESS_PATH"], dict(completed=number + 1))
        print(result, flush=True)
    write(output / "report.json", dict(tasks=reports, model_calls=0, outcome="PASS"))


if __name__ == "__main__":
    main()
