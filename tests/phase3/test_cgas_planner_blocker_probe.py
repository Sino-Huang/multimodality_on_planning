from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_probe_records_repeated_native_searches_without_authoritative_fields() -> None:
    # Given: two unique, caller-selected diagnostic targets below the repository tmp boundary.
    first = _probe_path(f"pytest-first-{uuid4().hex}")
    second = _probe_path(f"pytest-second-{uuid4().hex}")

    # When: the frozen characterization profile is probed twice.
    first_run = _run_probe(first)
    second_run = _run_probe(second)

    # Then: the normalized scientific record is byte-identical and timing is retained separately.
    assert first.read_bytes() == second.read_bytes()
    assert first_run.stdout == second_run.stdout == ""
    record = json.loads(first.read_text(encoding="utf-8"))
    assert record["diagnostic_only"] is True
    assert record["non_authoritative"] is True
    assert record["repeat_count"] == 2
    assert record["authoritative_hashes"]["before"] == record["authoritative_hashes"]["after"]
    assert record["bundle"]["sha256"] == "942d7be93ad0eb0ec6580bfe380fb8f09141662140ffc3d3c98e7f09a10ddaf4"
    assert record["bundle"]["run_fingerprint"] == "0856e76571643362abb70551ff9d4e02e2d585f7384fc3ac0adb64df240d893a"
    assert [(row["instance_id"], row["bfs"]["expansion_count"], row["iw_width_1"]["expansion_count"]) for row in record["representatives"]] == [
        ("blocksworld-dev-hard-0000", 10001, 73),
        ("blocksworld-test-hard-0014", 10001, 71),
        ("blocksworld-train-hard-0000", 10001, 90),
    ]
    assert all(row["sas_plan"]["replay"]["goal_satisfied"] is True for row in record["representatives"])
    assert all(len(row["bfs"]["implementation_sha256"]) == 64 for row in record["representatives"])
    assert all(len(row["iw_width_1"]["implementation_sha256"]) == 64 for row in record["representatives"])
    assert all(row["bfs"]["replay"]["goal_satisfied"] is False for row in record["representatives"])
    assert all(row["iw_width_1"]["replay"]["goal_satisfied"] is False for row in record["representatives"])
    assert all(row["iw_width_1"]["recovery_absent"] is True for row in record["representatives"])
    assert all(row["runs_match"] is True for row in record["representatives"])
    assert (first.parent / "timings.jsonl").is_file()
    assert (second.parent / "timings.jsonl").is_file()
    assert not _contains_forbidden_field(record)


@pytest.mark.parametrize(
    "path",
    (
        REPOSITORY_ROOT / "tmp" / ".cgas-characterization" / "probe.json",
        REPOSITORY_ROOT / ".omo" / "evidence" / "cgas-partition-characterization" / "probe.json",
        REPOSITORY_ROOT / "data" / "planning_cgas_v1" / "probe.json",
        REPOSITORY_ROOT / "tmp" / "cgas-planner-blocker-investigation-safe-token" / ".." / "probe.json",
        Path("/tmp/cgas-planner-blocker-investigation-outside/probe.json"),
    ),
)
def test_probe_rejects_unsafe_output_paths_before_planning(path: Path) -> None:
    # Given: a path outside the one-run repository tmp evidence boundary.

    # When: the diagnostic CLI validates the explicit caller target.
    result = _run_probe(path)

    # Then: the planner is never reached.
    assert result.returncode != 0
    assert "unsafe_output_path" in result.stderr


def test_probe_rejects_existing_or_symlinked_target_before_planning(tmp_path: Path) -> None:
    # Given: an occupied target and a parent redirected through a symlink.
    occupied = _probe_path(f"pytest-occupied-{uuid4().hex}")
    occupied.parent.mkdir(mode=0o700)
    occupied.write_text("occupied\n", encoding="utf-8")
    linked_parent = REPOSITORY_ROOT / "tmp" / f"cgas-planner-blocker-investigation-pytest-linked-{uuid4().hex}"
    linked_parent.symlink_to(tmp_path, target_is_directory=True)

    # When: either target is supplied to the diagnostic CLI.
    occupied_result = _run_probe(occupied)
    linked_result = _run_probe(linked_parent / "probe.json")

    # Then: neither target is adopted or overwritten.
    assert occupied_result.returncode != 0
    assert "output_target_exists" in occupied_result.stderr
    assert linked_result.returncode != 0
    assert "unsafe_output_path" in linked_result.stderr
    assert occupied.read_text(encoding="utf-8") == "occupied\n"
    assert linked_parent.is_symlink()


def test_probe_rejects_source_traversal_before_opening_the_file() -> None:
    # Given: a lexical traversal that resolves to a repository file.
    code = """
from scripts.phase3.cgas_planner_blocker_probe import REPOSITORY_ROOT, _repository_file
_repository_file('../multimodality_on_planning/AGENTS.md')
"""

    # When: the source boundary resolves a run-contract path.
    result = _run_python(code)

    # Then: traversal is rejected even though the final path is inside the repository.
    assert result.returncode != 0
    assert "source_path_outside_repository" in result.stderr


def test_probe_rejects_symlinked_source_parent_component() -> None:
    # Given: a repository-local source path redirected through a symlinked component.
    link = REPOSITORY_ROOT / "tmp" / f"cgas-planner-blocker-investigation-source-link-{uuid4().hex}"
    link.symlink_to(REPOSITORY_ROOT / "data", target_is_directory=True)
    code = f"""
from scripts.phase3.cgas_planner_blocker_probe import _repository_file
_repository_file({str(link.relative_to(REPOSITORY_ROOT) / 'curriculum_pddl/accepted_manifest.jsonl')!r})
"""

    # When: the run-contract source is opened.
    result = _run_python(code)

    # Then: the source boundary rejects the redirected parent before reading bytes.
    assert result.returncode != 0
    assert "source_path_unavailable" in result.stderr


def test_probe_publishes_through_created_directory_descriptor_after_parent_replacement(tmp_path: Path) -> None:
    # Given: a newly created evidence directory that an attacker replaces with a symlink.
    name = f"cgas-planner-blocker-investigation-pytest-race-{uuid4().hex}"
    code = f"""
import os
from pathlib import Path
from scripts.phase3 import cgas_planner_blocker_probe as probe
paths = probe._prepare_output(Path('tmp/{name}/probe.json'))
published = paths.output.parent
moved = published.with_name('{name}-moved')
os.rename(published, moved)
published.symlink_to(Path({str(tmp_path)!r}), target_is_directory=True)
probe._write_new(paths.directory_descriptor, 'probe.json', b'anchored')
paths.close()
assert (moved / 'probe.json').read_bytes() == b'anchored'
assert not (Path({str(tmp_path)!r}) / 'probe.json').exists()
"""

    # When: publication uses the prepared output after replacement.
    result = _run_python(code)

    # Then: bytes reach the originally opened directory, not the replacement path.
    assert result.returncode == 0, result.stderr


def test_probe_rejects_preexisting_sigalrm_timer_without_replacing_handler() -> None:
    # Given: a compositional caller that already owns SIGALRM.
    code = """
import signal
from scripts.phase3 import cgas_planner_blocker_probe as probe
def existing_handler(_number, _frame):
    return None
signal.signal(signal.SIGALRM, existing_handler)
signal.setitimer(signal.ITIMER_REAL, 30)
try:
    with probe._time_limit():
        raise AssertionError('unexpected timer admission')
except probe.PlannerBlockerProbeError as error:
    assert str(error) == 'existing_sigalrm_timer'
else:
    raise AssertionError('missing timer rejection')
assert signal.getsignal(signal.SIGALRM) is existing_handler
assert signal.getitimer(signal.ITIMER_REAL)[0] > 0
signal.setitimer(signal.ITIMER_REAL, 0)
"""

    # When: the probe attempts to install its fresh-process deadline.
    result = _run_python(code)

    # Then: the caller's timer and handler remain intact.
    assert result.returncode == 0, result.stderr


def test_probe_restores_fresh_process_sigalrm_handler() -> None:
    # Given: a caller-owned handler without an active timer.
    code = """
import signal
from scripts.phase3 import cgas_planner_blocker_probe as probe
def existing_handler(_number, _frame):
    return None
signal.signal(signal.SIGALRM, existing_handler)
with probe._time_limit():
    pass
assert signal.getsignal(signal.SIGALRM) is existing_handler
"""

    # When: one fresh-process planning deadline exits normally.
    result = _run_python(code)

    # Then: the original handler is restored.
    assert result.returncode == 0, result.stderr


def _probe_path(suffix: str) -> Path:
    return REPOSITORY_ROOT / "tmp" / f"cgas-planner-blocker-investigation-{suffix}" / "probe.json"


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


def _run_probe(output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.phase3.cgas_planner_blocker_probe", "--output", str(output)],
        capture_output=True,
        check=False,
        cwd=REPOSITORY_ROOT,
        text=True,
        timeout=120,
    )


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        check=False,
        cwd=REPOSITORY_ROOT,
        text=True,
        timeout=30,
    )
