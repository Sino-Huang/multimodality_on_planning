from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.best_first_curriculum import (
    CURRICULA,
    curriculum_metadata,
    load_best_first_issue67,
    paired_bootstrap_interval,
    replacement_setting_summary,
    select_issue67_coverage,
)
from scripts.run_best_first_issue65 import _run_children

ROOT = Path(__file__).resolve().parents[2]


def test_child_log_multiplexer_tolerates_malformed_terminal_bytes(capsys) -> None:
    command = (
        sys.executable,
        "-c",
        "import os; os.write(1, b'\\xe2\\n')",
    )

    assert _run_children((command,), prefixes=("terminal",)) == 0
    assert "[terminal]" in capsys.readouterr().out


def test_issue67_contract_uses_the_greedy_representative_cell() -> None:
    experiment = load_best_first_issue67(ROOT)

    assert experiment.contract_id == "issue-67-best-first-curriculum-comparison-v1"
    assert {task.algorithm for task in experiment.tasks} == {"best_first_add_greedy"}
    assert {task.source_issue for task in experiment.tasks} == {67}
    assert len(experiment.tasks) == 23
    assert experiment.training_counts == {"dev": 6_696, "train": 8_342}
    assert experiment.preflight()["physical_model_conditions"] == 4


def test_issue67_released_curricula_have_identical_content_and_distinct_orders() -> None:
    experiment = load_best_first_issue67(ROOT)
    rows = {control: curriculum_metadata(experiment, control)["train"] for control in CURRICULA}
    keys = {control: [(row["pair_id"], row["record_index"]) for row in records] for control, records in rows.items()}

    assert set(keys["staged"]) == set(keys["shuffled"]) == set(keys["mixed_order"])
    assert keys["staged"] != keys["shuffled"]
    assert keys["staged"] != keys["mixed_order"]
    assert [row["stage_index"] for row in rows["staged"]] == sorted(row["stage_index"] for row in rows["staged"])


def test_issue67_qualification_uses_the_preregistered_domain_fallback() -> None:
    experiment = load_best_first_issue67(ROOT)

    qualification = select_issue67_coverage(
        experiment.tasks,
        model_load_seconds=65.0,
        throughput_samples=(0.37,),
        runtime_seconds_per_call=0.0,
        rollout_shard_count=2,
    )
    stopped = select_issue67_coverage(
        experiment.tasks,
        model_load_seconds=65.0,
        throughput_samples=(0.01,),
        runtime_seconds_per_call=0.0,
        rollout_shard_count=2,
    )

    assert qualification["coverage"]["outcome"] == "PASS"
    assert qualification["coverage"]["mode"] == "cheapest_complete_task_per_domain"
    assert len(qualification["coverage"]["task_ids"]) == 12
    assert qualification["coverage"]["maximum_scheduled_calls"] == 9_472
    assert stopped["coverage"]["outcome"] == "VALID_STOP"
    assert stopped["coverage"]["task_ids"] == []


def test_issue67_statistics_use_whole_instance_pairs() -> None:
    interval = paired_bootstrap_interval(
        {"a": 1.0, "b": 0.5, "c": 1.0},
        {"a": 0.0, "b": 0.5, "c": 0.0},
        resamples=1_000,
        seed=1729,
        confidence=0.95,
    )

    assert interval["point"] == 2 / 3
    assert interval["lower"] >= 0.0
    assert interval["upper"] <= 1.0


def test_issue67_replacement_summary_does_not_claim_a_heuristic_contrast() -> None:
    experiment = load_best_first_issue67(ROOT)
    result = replacement_setting_summary(experiment)

    assert result["algorithm_difference"] == "priority_and_reopening_rule"
    assert result["learned_success_difference_greedy_minus_w3"] == 0.0
    assert result["conclusion"] == "no_material_model_decision_advantage"
    assert result["greedy_relative_decision_reduction"]["point"] == 1 - 6_696 / 7_095
    assert result["totals"]["best_first_add_w3"]["decision_count"] == 7_095
    assert result["totals"]["best_first_add_greedy"]["decision_count"] == 6_696


def test_issue67_complete_dry_run_exposes_parallel_ports_and_progress_plan() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_best_first_issue67.py"), "all", "--dry-run"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["dry_run"] is True
    assert result["writes"] == 0
    cells = result["plans"]["training"]["cells"]
    assert [cell["curriculum"] for cell in cells] == list(CURRICULA)
    assert [cell["master_port"] for cell in cells] == [29670, 29671, 29672]
    assert [cell["device"] for cell in cells] == ["0", "1", "0"]
    assert all(cell["plan"]["estimated_optimizer_steps"] == 522 for cell in cells)


def test_issue67_qualification_stop_writes_a_gated_not_run_receipt(tmp_path: Path) -> None:
    qualification = tmp_path / "qualification" / "qualification.json"
    qualification.parent.mkdir(parents=True)
    qualification.write_text(
        json.dumps({"coverage": {"outcome": "VALID_STOP", "task_ids": []}}),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_best_first_issue67.py"),
            "adjudicate",
            "--output-root",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads((tmp_path / "adjudication" / "report.json").read_text(encoding="utf-8"))
    receipt = json.loads((tmp_path / "adjudication" / "gated-not-run-receipt.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "VALID_STOP"
    assert report["scientific_completion"] is False
    assert receipt["receipt_type"] == "gated_not_run"
    assert receipt["start_permitted"] is False
