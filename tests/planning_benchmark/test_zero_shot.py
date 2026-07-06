from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from examples.planning_benchmark_slice.zero_shot import ALGORITHMS, MODALITIES, build_prompt_packages, leakage_errors_for_packages, score_model_output_payload


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "planning"
NONTRIVIAL_FIXTURE = FIXTURE_DIR / "blocksworld_nontrivial.json"
ZERO_SHOT_FIXTURE_DIR = FIXTURE_DIR / "zero_shot"


def _run_build(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice.zero_shot_build", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def _run_diagnostic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "examples.planning_benchmark_slice.zero_shot_diagnostic", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def _fixture(name: str) -> Path:
    return ZERO_SHOT_FIXTURE_DIR / name


def test_build_prompt_packages_covers_algorithm_modality_matrix_and_separates_gold() -> None:
    packages = build_prompt_packages(fixture_path=NONTRIVIAL_FIXTURE, algorithms=ALGORITHMS, modalities=MODALITIES)

    assert len(packages) == 16
    assert sorted((package["algorithm"], package["modality"]) for package in packages) == sorted(
        (algorithm, modality) for algorithm in ALGORITHMS for modality in MODALITIES
    )
    assert leakage_errors_for_packages(packages) == []

    vision = next(package for package in packages if package["algorithm"] == "bfs" and package["modality"] == "vision")
    language = next(package for package in packages if package["algorithm"] == "bfs" and package["modality"] == "language")

    assert "gold_scoring_metadata" in vision
    assert "model_facing" in vision
    vision_prompt = json.dumps(vision["model_facing"], sort_keys=True).lower()
    assert "on(a,b)" not in vision_prompt
    assert "current_state_atoms" not in vision_prompt
    assert "state_id" not in vision_prompt
    assert "goal_atoms" not in vision_prompt
    assert "current_state_atoms" in language["model_facing"]["language_input"]
    assert "render_paths" not in json.dumps(language["model_facing"], sort_keys=True)
    assert "image" not in json.dumps(language["model_facing"], sort_keys=True).lower()


def test_zero_shot_build_cli_writes_deterministic_json_packages(tmp_path: Path) -> None:
    output = tmp_path / "zero_shot"
    result = _run_build(
        "--fixture",
        str(NONTRIVIAL_FIXTURE),
        "--algorithms",
        "bfs",
        "fast_forward",
        "iterated_width",
        "graphplan",
        "--modalities",
        "vision",
        "language",
        "vision_language",
        "vision_language_tool",
        "--output",
        str(output),
        "--json",
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["valid"] is True
    assert payload["package_count"] == 16
    assert payload["leakage_errors"] == []
    assert len(list(output.glob("*.json"))) == 16
    assert (output / "blocksworld-dev-fixture-0000__bfs__vision.json").exists()


def test_validate_schema_accepts_valid_fixture_and_rejects_parse_error() -> None:
    valid = _run_diagnostic("validate-schema", "--input", str(_fixture("bfs_valid_output.json")), "--json")
    invalid = _run_diagnostic("validate-schema", "--input", str(_fixture("bfs_parse_error.json")), "--json")

    valid_payload = json.loads(valid.stdout)
    invalid_payload = json.loads(invalid.stdout)

    assert valid.returncode == 0
    assert valid.stderr == ""
    assert valid_payload["valid"] is True
    assert valid_payload["syntactic_validity"] is True
    assert invalid.returncode != 0
    assert invalid_payload["valid"] is False
    assert invalid_payload["error"]["code"] == "json_parse_error"
    assert "schema invalid" in invalid.stderr


def test_score_model_output_labels_all_proposal_outcomes() -> None:
    cases = {
        "bfs_valid_output.json": ("Pass", True, True, True),
        "bfs_algorithm_error.json": ("Algorithmic Error", True, False, True),
        "bfs_illegal_action.json": ("Action Error", True, True, False),
        "bfs_parse_error.json": ("Parse Error", False, False, False),
    }

    for filename, expected in cases.items():
        label, syntactic_validity, algorithmic_fidelity, action_validity = expected
        payload = json.loads(_fixture(filename).read_text(encoding="utf-8"))
        result = score_model_output_payload(payload)
        assert result["score_label"] == label
        assert result["syntactic_validity"] is syntactic_validity
        assert result["algorithmic_fidelity"] is algorithmic_fidelity
        assert result["action_validity"] is action_validity


def test_zero_shot_score_cli_reports_action_error_fixture() -> None:
    result = _run_diagnostic("score", "--input", str(_fixture("bfs_illegal_action.json")), "--json")

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["score_label"] == "Action Error"
    assert payload["syntactic_validity"] is True
    assert payload["action_validity"] is False
