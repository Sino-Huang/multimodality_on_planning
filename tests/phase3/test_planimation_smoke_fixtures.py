from __future__ import annotations

import hashlib
import importlib.util
import json
import types
from pathlib import Path

import pytest

from scripts.phase3.cgas_candidate_accounting import PlannerInput, planner_input_record
from scripts.phase3.cgas_candidate_space import build_candidate
from scripts.phase3.cgas_pilot_expansion_index import state_sha256

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = (
    REPOSITORY_ROOT
    / ".claude"
    / "evidence"
    / "cgas-phase3-pilot-rendering"
    / "local_planimation_adapter_integration.py"
)


def _load_harness() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("local_planimation_adapter_integration", HARNESS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_smoke_fixture(root: Path, selector: str, fixture: dict[str, object]) -> None:
    fixture_path = root / "configs/cgas/planimation_smoke" / f"{selector}.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")


def test_loads_validated_eight_object_smoke_fixture() -> None:
    harness = _load_harness()

    fixture = harness.load_smoke_fixture(REPOSITORY_ROOT, "8-object")

    assert fixture["problem_identity"] == {
        "candidate_id": "0322c69e499f0e2ba7161d25787a1260a275bd22382438a7f48e51e9da3737c4",
        "object_count": 8,
        "planner": "bfs",
        "raw_rank": 93,
        "role": "train",
        "row_id": "cgas-pilot-expansion-20b7ac18577176c1fa927b68",
        "source_record_sha256": "37d284f8b8b34c5a9b351092734ed663169e8191408044a6337d645a33e66198",
        "state_sha256": "00014e0bdfd513580c65f03b94e5c0a1487c34c7be37bd1fadf92bf9643e5f7f",
    }
    assert fixture["expected_actions"] == [
        "(unstack b5 b6)",
        "(stack b5 b4)",
        "(pickup b6)",
        "(stack b6 b5)",
    ]
    assert fixture["semantic_expectations"] == {
        "minimum_covered_object_count": 8,
        "expected_action_count": 4,
        "expected_visual_stage_count": 5,
    }
    assert fixture["resource_expectations"] == {
        "backend_startup_timeout_seconds": 180,
        "adapter_request_timeout_seconds": 90,
        "max_attempts": 1,
        "request_delay_seconds": 0,
    }


def test_loads_validated_twelve_object_smoke_fixture() -> None:
    harness = _load_harness()

    fixture = harness.load_smoke_fixture(REPOSITORY_ROOT, "12-object")

    assert fixture["problem_identity"] == {
        "candidate_id": "ca6fb5aa595c065744e0172f1b50d4e237bd4c851d094de684127a240cd3e85d",
        "object_count": 12,
        "planner": "bfs",
        "raw_rank": 9,
        "role": "held_out_calibration",
        "row_id": "cgas-pilot-expansion-347abc61e3ddea26d65eed27",
        "source_record_sha256": "eb8d5b84e65bf9d8be846d0144583f65f289b38719df673489e5c117e8ce7073",
        "state_sha256": "0002870c7b4fc6cd2c137f636c641655ec1f9addf7679404671df53f7d02ea51",
    }
    assert fixture["expected_actions"] == ["(stack b10 b9)"]
    assert fixture["semantic_expectations"] == {
        "minimum_covered_object_count": 12,
        "expected_action_count": 1,
        "expected_visual_stage_count": 2,
    }


@pytest.mark.parametrize(
    ("source_selector", "identity_updates"),
    (
        ("12-object", {}),
        ("8-object", {"role": "held_out_calibration"}),
        ("8-object", {"planner": "iw"}),
        ("8-object", {"row_id": "wrong-row"}),
    ),
)
def test_fixture_selector_is_bound_to_expected_identity(
    tmp_path: Path,
    source_selector: str,
    identity_updates: dict[str, str],
) -> None:
    harness = _load_harness()
    fixture = json.loads(
        (REPOSITORY_ROOT / f"configs/cgas/planimation_smoke/{source_selector}.json").read_text(encoding="utf-8")
    )
    fixture["fixture_id"] = "8-object"
    fixture["problem_identity"].update(identity_updates)
    _write_smoke_fixture(tmp_path, "8-object", fixture)

    with pytest.raises(harness.ProofError) as excinfo:
        harness.load_smoke_fixture(tmp_path, "8-object")

    assert excinfo.value.reason == "smoke_fixture_selector_identity_mismatch"


def test_fixture_rejects_coordinated_candidate_identity_drift(tmp_path: Path) -> None:
    harness = _load_harness()
    fixture = json.loads(
        (REPOSITORY_ROOT / "configs/cgas/planimation_smoke/8-object.json").read_text(encoding="utf-8")
    )
    candidate = build_candidate(8, 0)
    source = planner_input_record(PlannerInput(8, 0, "emitted", candidate.candidate_id, 0, candidate))
    source_digest = hashlib.sha256(
        (json.dumps(source, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()
    ).hexdigest()
    state_atoms = sorted(f"({' '.join(atom)})" for atom in candidate.init_atoms)
    fixture["problem_identity"].update(
        {
            "raw_rank": 0,
            "candidate_id": candidate.candidate_id,
            "source_record_sha256": source_digest,
            "state_sha256": state_sha256(state_atoms),
        }
    )
    fixture["state_atoms"] = state_atoms
    _write_smoke_fixture(tmp_path, "8-object", fixture)

    with pytest.raises(harness.ProofError) as excinfo:
        harness.load_smoke_fixture(tmp_path, "8-object")

    assert excinfo.value.reason == "smoke_fixture_selector_identity_mismatch"


def test_fixture_rejects_coordinated_state_identity_drift(tmp_path: Path) -> None:
    harness = _load_harness()
    fixture = json.loads(
        (REPOSITORY_ROOT / "configs/cgas/planimation_smoke/8-object.json").read_text(encoding="utf-8")
    )
    state_atoms = sorted([*fixture["state_atoms"], "(clear b00)"])
    fixture["state_atoms"] = state_atoms
    fixture["problem_identity"]["state_sha256"] = state_sha256(state_atoms)
    _write_smoke_fixture(tmp_path, "8-object", fixture)

    with pytest.raises(harness.ProofError) as excinfo:
        harness.load_smoke_fixture(tmp_path, "8-object")

    assert excinfo.value.reason == "smoke_fixture_selector_identity_mismatch"


def test_fixture_plan_must_match_independent_expected_actions(tmp_path: Path) -> None:
    harness = _load_harness()
    fixture = json.loads(
        (REPOSITORY_ROOT / "configs/cgas/planimation_smoke/8-object.json").read_text(encoding="utf-8")
    )
    fixture["supplied_plan"] = "(pickup b1)"
    _write_smoke_fixture(tmp_path, "8-object", fixture)

    with pytest.raises(harness.ProofError) as excinfo:
        harness.load_smoke_fixture(tmp_path, "8-object")

    assert excinfo.value.reason == "smoke_fixture_action_sequence_mismatch"


def test_fixture_resource_bounds_must_be_safe_and_fixed(tmp_path: Path) -> None:
    harness = _load_harness()
    fixture = json.loads(
        (REPOSITORY_ROOT / "configs/cgas/planimation_smoke/8-object.json").read_text(encoding="utf-8")
    )
    fixture["resource_expectations"]["backend_startup_timeout_seconds"] = -1
    _write_smoke_fixture(tmp_path, "8-object", fixture)

    with pytest.raises(harness.ProofError) as excinfo:
        harness.load_smoke_fixture(tmp_path, "8-object")

    assert excinfo.value.reason == "smoke_fixture_resource_expectations_invalid"


def test_fixture_semantic_counts_must_match_identity_and_plan(tmp_path: Path) -> None:
    harness = _load_harness()
    fixture = json.loads(
        (REPOSITORY_ROOT / "configs/cgas/planimation_smoke/8-object.json").read_text(encoding="utf-8")
    )
    fixture["semantic_expectations"]["expected_action_count"] = 2
    fixture["semantic_expectations"]["expected_visual_stage_count"] = 3
    _write_smoke_fixture(tmp_path, "8-object", fixture)

    with pytest.raises(harness.ProofError) as excinfo:
        harness.load_smoke_fixture(tmp_path, "8-object")

    assert excinfo.value.reason == "smoke_fixture_semantic_expectations_invalid"


def test_materializes_fixture_for_shared_adapter_path_without_backend(tmp_path: Path) -> None:
    harness = _load_harness()
    fixture = harness.load_smoke_fixture(REPOSITORY_ROOT, "8-object")

    materialized = harness.materialize_smoke_fixture(fixture, tmp_path)

    index_row = json.loads(Path(materialized["index_path"]).read_text(encoding="utf-8"))
    request_row = json.loads(Path(materialized["request_path"]).read_text(encoding="utf-8"))
    identity = fixture["problem_identity"]
    assert {
        key: index_row[key]
        for key in (
            "candidate_id",
            "object_count",
            "planner",
            "raw_rank",
            "role",
            "row_id",
            "source_record_sha256",
            "state_sha256",
        )
    } == identity
    assert index_row["instance_id"] == identity["candidate_id"]
    assert index_row["state_atoms"] == fixture["state_atoms"]
    assert index_row["supplied_plan"] == fixture["supplied_plan"]
    assert request_row == {
        "partitions": ["train|8|bfs"],
        "state_atoms": fixture["state_atoms"],
        "state_sha256": identity["state_sha256"],
    }
    assert materialized["schema_version"] == "cgas_phase3_planimation_smoke_fixture_v1"
    assert materialized["supplied_plan_text"] == fixture["supplied_plan"]
    assert materialized["expected_actions"] == fixture["expected_actions"]
