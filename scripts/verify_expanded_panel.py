#!/usr/bin/env python
"""Read-only final binding verification for the frozen Goal-2 panel."""

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.planning_benchmark_slice.expanded_scheduler import ROOT, read, alive


def main():
    final = read(ROOT / "configs/experiments/expanded-study/final-panel.json")
    views = read(ROOT / final["view_report"])
    selection = read(ROOT / "outputs/expanded-study/v1/panel-v2/structural-selection.json")
    scope = read(ROOT / "configs/experiments/expanded-study/panel-domain-scope.json")
    audit = read(ROOT / "docs/experiments/expanded-study/panel-independent-audit.json")
    memory = read(ROOT / "docs/experiments/expanded-study/panel-common-memory.json")
    live = read(ROOT / "docs/experiments/expanded-study/panel-live-views.json")
    gpu = read(ROOT / "docs/experiments/expanded-study/panel-gpu-qualification.json")
    ledger = read(ROOT / "outputs/expanded-study/v1/budget.json")
    assert selection["selected_count"] == len(final["tasks"]) == len(views["tasks"]) == 24
    assert not selection["missing_strata"]
    assert len({t["row"]["task_id"] for t in final["tasks"]}) == 24
    assert Counter(t["row"]["domain"] for t in final["tasks"]) == {d: 2 for d in scope["domains"]}
    assert {(t["row"]["domain"], t["row"]["difficulty"]) for t in final["tasks"]} == {
        (d, s) for d in scope["domains"] for s in ("compact", "expanded")
    }
    assert len(final["algorithms"]) == 4 and len(final["modalities"]) == 3 and len(final["conditions"]) == 4
    assert final["logical_bindings"] == 24 * 4 * 3 * 4 and final["model_episodes"] == 24 * 4 * 3 * 2
    by_id = {t["row"]["task_id"]: t for t in views["tasks"]}
    for task in final["tasks"]:
        raw = by_id[task["row"]["task_id"]]
        assert task["row"] == raw["row"] and task["reference_paths"] == raw["reference_paths"]
        assert set(task["reference_paths"]) == set(final["algorithms"])
        assert all((ROOT / p).is_file() for p in task["reference_paths"].values())
        assert read(ROOT / task["source_snapshot"]) == read(ROOT / task["row"]["task_path"])
        assert task["row"]["split"] == "test"
    assert audit["outcome"] == memory["outcome"] == live["outcome"] == "PASS"
    assert len(audit["tasks"]) == len(live["tasks"]) == 24
    assert (
        memory["decisions"] == 4310
        and memory["maximum_common_input_bytes"] <= 32768
        and memory["maximum_accepted_deltas"] <= 16
    )
    assert gpu["hardware_capacity_passed"] and gpu["final_panel_frozen"]
    assert gpu["outcome"] == "QUALIFIED_WITH_CONDITIONAL_COST_ADMISSION"
    assert not gpu["reference_allowance_proxy_fits"]
    assert gpu["spent_gpu_hours"] + gpu["historical_consumption_proxy_gpu_hours"] <= 56
    assert not final["completion_within_budget_guaranteed"] and not final["episode_runner_implemented_by_goal2"]
    ports = []
    for worker in gpu["workers"]:
        recorded = worker["attempt"]
        current = next(
            a for a in ledger["attempts"] if a["job_id"] == recorded["job_id"] and a["attempt"] == recorded["attempt"]
        )
        assert current == recorded and current["status"] == "succeeded" and not alive(current.get("worker"))
        assert read(Path(current["directory"]) / "hook-result.json")["returncode"] == 0
        ports.append(current["master_port"])
        for modality in worker["qualification"]["modalities"]:
            cases = {c["name"]: c for c in modality["cases"]}
            assert len(cases) == 4 and len(modality["adapters"]) == 4
            assert cases["single_limit"]["input_tokens"] == [32384]
            assert cases["batch_limit"]["input_tokens"] == [12000, 12000]
            assert all(c["generated_tokens"] == 384 and not c["scored"] for c in cases.values())
    assert len(set(ports)) == 2
    assert ledger["schedule"] == read(ROOT / "docs/experiments/expanded-study/schedule.json")
    assert not final["new_training"]
    print(
        "PASS: 24 tasks / 12 domains, 1152 logical bindings, all audits and both GPU probes; conditional cost admission explicitly retained"
    )


if __name__ == "__main__":
    main()
