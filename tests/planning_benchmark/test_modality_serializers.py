from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.generate_experts import generate_experts
from examples.planning_benchmark_slice.modality_serializers import (
    build_modality_records,
    leakage_errors_for_record,
    serialize_modalities,
)
from examples.planning_benchmark_slice.zero_shot import ALGORITHMS, MODALITIES


REPO_ROOT = Path(__file__).resolve().parents[2]
NONTRIVIAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "planning" / "blocksworld_nontrivial.json"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _generate_all_experts(output: Path) -> None:
    generate_experts(
        fixture_path=NONTRIVIAL_FIXTURE,
        algorithms=ALGORITHMS,
        output_dir=output,
    )


def _run_serializer(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice.serialize_modalities", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_serialize_modalities_writes_four_jsonl_files_and_summary(tmp_path: Path) -> None:
    expert_dir = tmp_path / "experts"
    dataset_dir = tmp_path / "dataset"
    _generate_all_experts(expert_dir)

    summary = serialize_modalities(input_path=expert_dir, output_dir=dataset_dir, modalities=MODALITIES)

    assert summary["valid"] is True
    assert summary["leakage_errors"] == []
    assert summary["counts_by_modality"] == {modality: 8 for modality in MODALITIES}
    assert summary["counts_by_algorithm"] == {algorithm: {modality: 2 for modality in MODALITIES} for algorithm in ALGORITHMS}
    assert set(summary["output_paths"]) == set(MODALITIES)
    assert {path.name for path in dataset_dir.glob("*.jsonl")} == {f"{modality}.jsonl" for modality in MODALITIES}
    assert len(_read_jsonl(dataset_dir / "vision.jsonl")) == 8
    assert summary["vision_skip_reasons"]
    assert {reason["code"] for reason in summary["vision_skip_reasons"]} == {"no_render_artifacts"}


def test_serializer_cli_emits_json_and_deterministic_modality_files(tmp_path: Path) -> None:
    expert_dir = tmp_path / "experts"
    dataset_dir = tmp_path / "dataset"
    _generate_all_experts(expert_dir)

    result = _run_serializer(
        "--input",
        str(expert_dir),
        "--output",
        str(dataset_dir),
        "--modalities",
        "vision",
        "language",
        "vision_language",
        "vision_language_tool",
        "--json",
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["valid"] is True
    assert payload["record_count"] == 32
    assert payload["leakage_errors"] == []
    assert set(payload["output_paths"]) == set(MODALITIES)
    first_language = _read_jsonl(dataset_dir / "language.jsonl")[0]
    assert first_language["schema_version"] == "planning_modality_record_v1"
    assert first_language["modality_boundary_note"].startswith("Only model_facing")


def test_vision_only_has_no_symbolic_state_ids_or_pddl(tmp_path: Path) -> None:
    expert_dir = tmp_path / "experts"
    _generate_all_experts(expert_dir)

    records = build_modality_records(input_path=expert_dir, modalities=("vision",))

    assert records
    assert all(leakage_errors_for_record(record) == [] for record in records)
    for record in records:
        model_facing = record["model_facing"]
        flattened = json.dumps(model_facing, sort_keys=True).lower()
        field_paths = json.dumps(sorted(_field_paths(model_facing))).lower()
        assert "pddl" not in flattened
        assert "state_atoms" not in field_paths
        assert "goal_atoms" not in field_paths
        assert "state_id" not in field_paths
        assert "legal_actions" not in field_paths
        assert "selected_action" not in field_paths
        assert "on(a,b)" not in flattened
        assert "arm-empty" not in flattened
        assert re.search(r"\b[0-9a-f]{64}\b", flattened) is None
        assert record["supervised_target"]["next_action"] in {"pickup(a)", "stack(a,b)"}
        assert record["evaluation_metadata"]["state_id"]


def test_language_only_has_symbolic_text_but_no_render_or_image_paths(tmp_path: Path) -> None:
    expert_dir = tmp_path / "experts"
    _generate_all_experts(expert_dir)

    records = build_modality_records(input_path=expert_dir, modalities=("language",))

    assert records
    assert all(leakage_errors_for_record(record) == [] for record in records)
    first = records[0]["model_facing"]
    flattened = json.dumps(first, sort_keys=True).lower()
    assert "current_state_atoms" in flattened
    assert "goal_atoms" in flattened
    assert "on(a,b)" in flattened
    assert "render" not in flattened
    assert "image" not in flattened
    assert "frame" not in flattened
    assert "selected_action" not in flattened


def test_vision_language_tool_includes_algorithm_scratchpads_and_targets(tmp_path: Path) -> None:
    expert_dir = tmp_path / "experts"
    _generate_all_experts(expert_dir)

    records = build_modality_records(input_path=expert_dir, modalities=("vision_language_tool",))
    by_algorithm = {algorithm: next(record for record in records if record["algorithm"] == algorithm) for algorithm in ALGORITHMS}

    assert {"frontier_before", "frontier_after", "visited_before", "visited_after"} <= set(
        by_algorithm["bfs"]["model_facing"]["tool_state"]["scratchpad"]
    )
    assert {"heuristic_value", "successor_heuristics", "selected_successor_id", "tie_break_rule"} <= set(
        by_algorithm["fast_forward"]["model_facing"]["tool_state"]["scratchpad"]
    )
    assert {"width", "novelty_table_before", "novelty_table_after", "decision"} <= set(
        by_algorithm["iterated_width"]["model_facing"]["tool_state"]["scratchpad"]
    )
    assert {"proposition_layers", "action_layers", "mutex_pairs", "extraction"} <= set(
        by_algorithm["graphplan"]["model_facing"]["tool_state"]["scratchpad"]
    )
    for record in records:
        assert record["model_facing"]["tool_state"]["update_target_field"] == "internal_state_update"
        assert record["supervised_target"]["next_action"] in {"pickup(a)", "stack(a,b)"}
        assert record["supervised_target"]["internal_state_update"]
        assert "selected_action" not in json.dumps(record["model_facing"], sort_keys=True)


def test_leakage_helpers_report_forbidden_vision_and_language_fields() -> None:
    vision_record = {
        "modality": "vision",
        "record_id": "bad_vision",
        "model_facing": {"state_id": "a" * 64, "visual_observation": {"render_paths": []}},
    }
    language_record = {
        "modality": "language",
        "record_id": "bad_language",
        "model_facing": {"language_context": {"render_paths": ["frame_000.png"]}},
    }

    vision_errors = leakage_errors_for_record(vision_record)
    language_errors = leakage_errors_for_record(language_record)

    assert {error.code for error in vision_errors} >= {"vision_symbolic_field_leak", "vision_symbolic_text_leak"}
    assert {error.code for error in language_errors} >= {"language_visual_field_leak", "language_visual_text_leak"}


def _field_paths(value: object, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.append(path)
            paths.extend(_field_paths(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            paths.extend(_field_paths(nested, f"{prefix}[{index}]"))
    return paths
