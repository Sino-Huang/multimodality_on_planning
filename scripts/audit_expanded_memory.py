#!/usr/bin/env python
"""Check all projected common inputs and accepted-delta bounds across modalities."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, write
from examples.planning_benchmark_slice.scene_assets import read_json
from examples.planning_benchmark_slice.modality_pages import project_messages, LEGEND
from examples.planning_benchmark_slice.scene_only_views import SCENE_LEGEND


def main():
    path = ROOT / "docs/experiments/expanded-study/panel-common-memory.json"
    if len(sys.argv) > 1 and sys.argv[1] == "audit":
        t = read(os.environ["EXPANDED_TERMINAL_PATH"])
        if t["status"] != "succeeded":
            raise RuntimeError(f"common memory audit failed: {t['directory']}/worker.log")
        report = read(path)
        assert report["outcome"] == "PASS" and report["decisions"] == 4310
        print("PASS: full common-input equality across all three modalities")
        return
    report = read(ROOT / "outputs/expanded-study/v1/panel-v2/reference-views.json")
    count = 0
    max_bytes = 0
    max_deltas = 0
    for task in report["tasks"]:
        for algorithm, path_ref in task["reference_paths"].items():
            for event in read_json(ROOT / path_ref)["events"]:
                raw = event["input"]
                original = json.dumps(raw, sort_keys=True)
                common = []
                for modality in ("text-state", "visual-state", "multimodal-state"):
                    messages = project_messages(
                        raw, algorithm, modality, {}, [], legend=LEGEND if modality == "text-state" else SCENE_LEGEND
                    )
                    payload = json.loads(messages[-1]["content"][0]["text"])
                    for key in ("semantic_blocks", "representation", "view_legend"):
                        payload.pop(key, None)
                    common.append(payload)
                assert common[0] == common[1] == common[2]
                assert json.dumps(raw, sort_keys=True) == original
                if algorithm.startswith("best_first_add"):
                    deltas = raw["accepted_deltas"]["rows"]
                else:
                    deltas = raw["search_memory"]["accepted_deltas" if algorithm == "bfs" else "deltas"]
                assert len(deltas) <= 16
                max_deltas = max(max_deltas, len(deltas))
                size = len(json.dumps(common[0], sort_keys=True, separators=(",", ":")).encode())
                max_bytes = max(max_bytes, size)
                assert size <= 32768
                count += 1
        write(os.environ["EXPANDED_PROGRESS_PATH"], dict(completed=count))
    write(
        path,
        dict(
            outcome="PASS",
            decisions=count,
            modalities=3,
            maximum_common_input_bytes=max_bytes,
            maximum_accepted_deltas=max_deltas,
            scientific_inputs_mutated=False,
            scope="all retained exact-reference decisions; live complete-input token cap remains separately enforced",
        ),
    )
    print(read(path))


if __name__ == "__main__":
    main()
