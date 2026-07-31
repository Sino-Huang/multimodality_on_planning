from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROBE_SOURCE = REPOSITORY_ROOT / "scripts/phase3/cgas_planner_alternative_profile_probe.py"
FINAL_RETAINED_PROBE = REPOSITORY_ROOT / "tmp/cgas-planner-alternative-profile-final-20260730t120000/probe.json"


def test_alternative_profiles_are_deterministic_and_non_authoritative() -> None:
    # Given: two write-once alternative-profile evidence targets.
    first = _output_path(uuid4().hex)
    second = _output_path(uuid4().hex)

    # When: the four approved profiles run twice each.
    first_run = _run_probe(first)
    second_run = _run_probe(second)

    # Then: normalized scientific records are identical and timing remains separate.
    assert first_run.returncode == second_run.returncode == 0
    assert first.read_bytes() == second.read_bytes()
    record = json.loads(first.read_text(encoding="utf-8"))
    assert record["diagnostic_only"] is True
    assert record["non_authoritative"] is True
    assert record["profile_changed"] is True
    assert record["repeat_count"] == 2
    assert record["authoritative_hashes"]["before"] == record["authoritative_hashes"]["after"]
    assert record["probe_implementation_sha256"] == hashlib.sha256(PROBE_SOURCE.read_bytes()).hexdigest()
    assert [profile["profile_id"] for profile in record["profiles"]] == ["bfs_30000", "bfs_100000", "iw_2", "iw_3"]
    assert [profile["limits"] for profile in record["profiles"]] == _effective_limits()
    assert all(len(profile["instances"]) == 3 for profile in record["profiles"])
    assert _planner_outcomes(record) == [
        ("bfs_30000", "blocksworld-dev-hard-0000", 30_001, "skipped_resource_limit", 0),
        ("bfs_30000", "blocksworld-test-hard-0014", 30_001, "skipped_resource_limit", 0),
        ("bfs_30000", "blocksworld-train-hard-0000", 30_001, "skipped_resource_limit", 0),
        ("bfs_100000", "blocksworld-dev-hard-0000", 100_001, "skipped_resource_limit", 0),
        ("bfs_100000", "blocksworld-test-hard-0014", 100_001, "skipped_resource_limit", 0),
        ("bfs_100000", "blocksworld-train-hard-0000", 100_001, "skipped_resource_limit", 0),
        ("iw_2", "blocksworld-dev-hard-0000", 8_188, "failed_no_plan_extracted", 0),
        ("iw_2", "blocksworld-test-hard-0014", 8_019, "failed_no_plan_extracted", 0),
        ("iw_2", "blocksworld-train-hard-0000", 8_725, "failed_no_plan_extracted", 0),
        ("iw_3", "blocksworld-dev-hard-0000", 10_001, "skipped_resource_limit", 0),
        ("iw_3", "blocksworld-test-hard-0014", 10_001, "skipped_resource_limit", 0),
        ("iw_3", "blocksworld-train-hard-0000", 10_001, "skipped_resource_limit", 0),
    ]
    assert all(instance["planner"]["replay"]["goal_satisfied"] is False for profile in record["profiles"] for instance in profile["instances"])
    assert all(instance["planner"]["recovery_absent"] is True for profile in record["profiles"] for instance in profile["instances"])
    assert all(instance["runs_match"] is True for profile in record["profiles"] for instance in profile["instances"])
    assert (first.parent / "timings.jsonl").is_file()
    assert not _contains_forbidden_field(record)


def test_final_retained_probe_matches_current_cli_semantics() -> None:
    # Given: the final write-once retained probe from the current implementation contract.
    retained = json.loads(FINAL_RETAINED_PROBE.read_text(encoding="utf-8"))
    output = _output_path(uuid4().hex)

    # When: the CLI writes a new equivalent diagnostic record.
    result = _run_probe(output)
    current = json.loads(output.read_text(encoding="utf-8"))

    # Then: semantic evidence excluding independent output/timing location matches exactly.
    assert result.returncode == 0
    assert retained == current


def test_alternative_probe_rejects_current_probe_output_namespace() -> None:
    # Given: a path under the current-profile diagnostic namespace.
    path = REPOSITORY_ROOT / "tmp" / f"cgas-planner-blocker-investigation-{uuid4().hex}" / "probe.json"

    # When: the alternative CLI validates its evidence destination.
    result = _run_probe(path)

    # Then: it fails before computation.
    assert result.returncode != 0
    assert "unsafe_output_path" in result.stderr


def _output_path(token: str) -> Path:
    return REPOSITORY_ROOT / "tmp" / f"cgas-planner-alternative-profile-{token}" / "probe.json"


def _run_probe(output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.phase3.cgas_planner_alternative_profile_probe", "--output", str(output)],
        capture_output=True,
        check=False,
        cwd=REPOSITORY_ROOT,
        text=True,
        timeout=1200,
    )


def _planner_outcomes(record: dict[str, object]) -> list[tuple[str, str, int, str, int]]:
    profiles = record["profiles"]
    assert isinstance(profiles, list)
    outcomes: list[tuple[str, str, int, str, int]] = []
    for profile in profiles:
        assert isinstance(profile, dict)
        profile_id = profile["profile_id"]
        instances = profile["instances"]
        assert isinstance(profile_id, str)
        assert isinstance(instances, list)
        for instance in instances:
            assert isinstance(instance, dict)
            planner = instance["planner"]
            assert isinstance(planner, dict)
            outcomes.append((profile_id, instance["instance_id"], planner["expansion_count"], planner["status"], planner["plan_length"]))
    return outcomes


def _effective_limits() -> list[dict[str, int]]:
    baseline = {
        "gbfs_max_depth": 128,
        "gbfs_max_expansions": 10_000,
        "local_iw_max_width": 1,
        "local_iw_novelty_max_expansions": 10_000,
        "local_iw_recovery": 0,
        "local_iw_width": 1,
        "local_max_applicable_actions": 2_000,
        "max_expansions": 10_000,
        "max_grounded_actions": 100_000,
        "max_grounded_atoms": 100_000,
        "max_plan_length": 128,
        "max_trace_steps": 0,
    }
    return [
        {**baseline, "max_expansions": 30_000},
        {**baseline, "max_expansions": 100_000},
        {**baseline, "local_iw_max_width": 2, "local_iw_width": 2},
        {**baseline, "local_iw_max_width": 3, "local_iw_width": 3},
    ]


def _contains_forbidden_field(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            field in {"eligibility", "approval", "role", "promotion", "publication"}
            or _contains_forbidden_field(nested)
            for field, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_field(item) for item in value)
    return False
