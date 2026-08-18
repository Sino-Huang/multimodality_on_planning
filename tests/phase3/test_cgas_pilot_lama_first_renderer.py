from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


FAST_DOWNWARD_REVISION = "b9fba250f5269a20cb0e950375720281621fb030"

DOMAIN = """(define (domain blocksworld-4ops)
(:requirements :strips)
(:predicates (clear ?x) (on-table ?x) (arm-empty) (holding ?x) (on ?x ?y))
)"""

PROBLEM = """(define (problem fixture)
(:domain blocksworld-4ops)
(:objects b00)
(:init (arm-empty) (clear b00) (on-table b00))
(:goal (and (holding b00)))
)"""


def _renderer(tmp_path: Path) -> tuple[Any, Path, Path, Path, Path]:
    from scripts.phase3.cgas_pilot_lama_first_renderer import LocalLamaFirstRenderer

    root = tmp_path / "repository"
    planner = root / "modules/downward/fast-downward.py"
    planner.parent.mkdir(parents=True)
    planner.write_text("#!/bin/sh\n", encoding="ascii")
    domain = root / "domain.pddl"
    problem = root / "problem.pddl"
    profile = root / "profile.pddl"
    cache = root / "cache"
    for path, contents in ((domain, DOMAIN), (problem, PROBLEM), (profile, "profile")):
        path.write_text(contents, encoding="ascii")
    return (
        LocalLamaFirstRenderer(root, planner, FAST_DOWNWARD_REVISION, 30, 31.0, "http://127.0.0.1:18082/forbidden-solver"),
        domain,
        problem,
        profile,
        cache,
    )


def _write_plan(command: list[str], contents: str) -> Path:
    plan_path = Path(command[command.index("--plan-file") + 1])
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(contents, encoding="ascii")
    return plan_path


def _vfg(actions: list[str]) -> str:
    return json.dumps(
        {
            "visualStages": [
                {"stageName": "Initial Stage", "visualSprites": []},
                *({"stageName": action, "visualSprites": []} for action in actions),
            ]
        }
    )


def test_valid_local_plan_uses_shared_compat_problem_and_submits_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_lama_first_renderer as lama
    from scripts.phase3.planimation_pairing_contracts import RenderConfig

    renderer, domain, problem, profile, cache = _renderer(tmp_path)
    commands: list[list[str]] = []
    uploads: list[tuple[Path, RenderConfig]] = []

    def execute(command: list[str], _cwd: Path, _watchdog: float) -> lama.PlannerExecution:
        commands.append(command)
        _write_plan(command, "(pickup b1)\n; cost = 1 (unit cost)\n")
        return lama.PlannerExecution(0)

    def render(_domain: Path, compat: Path, _profile: Path, cache_dir: Path, config: RenderConfig) -> dict[str, object]:
        uploads.append((compat, config))
        trace = cache_dir / "trace.vfg.json"
        trace.write_text(_vfg(["(pickup b1)"]), encoding="ascii")
        return {"status": "success", "attempts": 1, "frame_path": "frame.png", "trace_path": str(trace)}

    monkeypatch.setattr(lama, "_run_process", execute)
    monkeypatch.setattr(lama, "render_state_with_planimation", render)

    result = renderer(domain, problem, profile, cache, RenderConfig(base_url="http://127.0.0.1:18082", max_attempts=1))

    assert result["status"] == "success"
    assert len(commands) == 1
    assert commands[0][1:5] == ["--alias", "lama-first", "--overall-time-limit", "30s"]
    assert commands[0][-2] == str(domain)
    assert len(uploads) == 1
    compat, config = uploads[0]
    assert compat == Path(commands[0][-1])
    assert "b00" not in compat.read_text(encoding="ascii")
    assert "(:objects b1 )" in compat.read_text(encoding="ascii")
    assert config.plan == "(pickup b1)"
    assert config.solver_url == "http://127.0.0.1:18082/forbidden-solver"
    assert result["planner_metadata"]["source"] == "local_lama_first"
    assert result["planner_metadata"]["actions"] == ["(pickup b1)"]
    assert result["planimation_request_count"] == 1


@pytest.mark.parametrize(
    ("returncode", "expected"),
    [
        (10, "planning_unsolvable"),
        (11, "planning_unsolvable"),
        (12, "planning_unsolved_incomplete"),
        (20, "planning_resource_limit"),
        (21, "planning_resource_limit"),
        (22, "planning_resource_limit"),
        (23, "planning_resource_limit"),
        (24, "planning_resource_limit"),
        (1, "planning_nonclean_resource_failure"),
        (2, "planning_nonclean_resource_failure"),
        (3, "planning_nonclean_resource_failure"),
    ],
)
def test_terminal_planning_exit_codes_never_submit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, returncode: int, expected: str
) -> None:
    import scripts.phase3.cgas_pilot_lama_first_renderer as lama
    from scripts.phase3.planimation_pairing_contracts import RenderConfig

    renderer, domain, problem, profile, cache = _renderer(tmp_path)
    uploads: list[object] = []

    def execute(command: list[str], _cwd: Path, _watchdog: float) -> lama.PlannerExecution:
        if returncode in {1, 2, 3}:
            _write_plan(command, "(pickup b1)\n; cost = 1 (unit cost)\n")
        return lama.PlannerExecution(returncode)

    monkeypatch.setattr(lama, "_run_process", execute)
    monkeypatch.setattr(lama, "render_state_with_planimation", lambda *args: uploads.append(args))

    result = renderer(domain, problem, profile, cache, RenderConfig())

    assert result["status"] == "failed"
    assert result["planning_status"] == expected
    assert result["planimation_request_count"] == 0
    assert uploads == []


def test_timeout_and_zero_step_plan_are_terminal_without_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.phase3.cgas_pilot_lama_first_renderer as lama
    from scripts.phase3.planimation_pairing_contracts import RenderConfig

    renderer, domain, problem, profile, cache = _renderer(tmp_path)
    uploads: list[object] = []
    monkeypatch.setattr(lama, "render_state_with_planimation", lambda *args: uploads.append(args))
    monkeypatch.setattr(lama, "_run_process", lambda *args: lama.PlannerExecution(None, external_timeout=True))

    timeout = renderer(domain, problem, profile, cache, RenderConfig())
    assert timeout["planning_status"] == "planning_timeout"
    assert timeout["planimation_request_count"] == 0

    def zero(command: list[str], _cwd: Path, _watchdog: float) -> lama.PlannerExecution:
        _write_plan(command, "; cost = 0 (unit cost)\n")
        return lama.PlannerExecution(0)

    monkeypatch.setattr(lama, "_run_process", zero)
    zero_step = renderer(domain, problem, profile, cache / "zero", RenderConfig())
    assert zero_step["planning_status"] == "planning_zero_step_unsupported"
    assert zero_step["planimation_request_count"] == 0
    assert uploads == []


@pytest.mark.parametrize("returncode", [30, 31, 39, -9, 99])
def test_unexpected_planner_contracts_are_terminal_without_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, returncode: int
) -> None:
    import scripts.phase3.cgas_pilot_lama_first_renderer as lama
    from scripts.phase3.planimation_pairing_contracts import RenderConfig

    renderer, domain, problem, profile, cache = _renderer(tmp_path)
    uploads: list[object] = []
    monkeypatch.setattr(lama, "_run_process", lambda *args: lama.PlannerExecution(returncode))
    monkeypatch.setattr(lama, "render_state_with_planimation", lambda *args: uploads.append(args))

    result = renderer(domain, problem, profile, cache, RenderConfig())
    assert result["status"] == "failed"
    assert result["planning_status"] == "planning_returncode_unexpected"
    assert result["planimation_request_count"] == 0
    assert uploads == []


def test_missing_or_malformed_success_plan_hard_stops_without_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_lama_first_renderer as lama
    from scripts.phase3.planimation_pairing_contracts import RenderConfig

    renderer, domain, problem, profile, cache = _renderer(tmp_path)
    uploads: list[object] = []
    monkeypatch.setattr(lama, "render_state_with_planimation", lambda *args: uploads.append(args))
    monkeypatch.setattr(lama, "_run_process", lambda *args: lama.PlannerExecution(0))
    missing = renderer(domain, problem, profile, cache, RenderConfig())
    assert missing["planning_status"] == "planning_plan_missing"

    def malformed(command: list[str], _cwd: Path, _watchdog: float) -> lama.PlannerExecution:
        _write_plan(command, "pickup b1\n; cost = 1 (unit cost)\n")
        return lama.PlannerExecution(0)

    monkeypatch.setattr(lama, "_run_process", malformed)
    malformed_result = renderer(domain, problem, profile, cache / "malformed", RenderConfig())
    assert malformed_result["planning_status"] == "planning_plan_malformed"
    assert uploads == []


@pytest.mark.parametrize(
    ("execution", "expected"),
    [
        ("launch", "planning_launch_failed"),
        ("missing_returncode", "planning_returncode_missing"),
    ],
)
def test_planner_launch_and_missing_returncode_are_terminal_zero_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, execution: str, expected: str
) -> None:
    import scripts.phase3.cgas_pilot_lama_first_renderer as lama
    from scripts.phase3.planimation_pairing_contracts import RenderConfig

    renderer, domain, problem, profile, cache = _renderer(tmp_path)
    if execution == "launch":
        outcome = lama.PlannerExecution(None, launch_error="cannot execute")
    else:
        outcome = lama.PlannerExecution(None)
    monkeypatch.setattr(lama, "_run_process", lambda *args: outcome)
    monkeypatch.setattr(lama, "render_state_with_planimation", lambda *args: pytest.fail("unexpected HTTP renderer call"))

    result = renderer(domain, problem, profile, cache, RenderConfig())
    assert result["status"] == "failed"
    assert result["planning_status"] == expected
    assert result["attempts"] == 0
    assert result["planimation_request_count"] == 0


def test_planner_residue_is_terminal_and_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.phase3.cgas_pilot_lama_first_renderer as lama
    from scripts.phase3.planimation_pairing_contracts import RenderConfig

    renderer, domain, problem, profile, cache = _renderer(tmp_path)
    residue = cache / "local-lama-first"
    residue.mkdir(parents=True)
    plan = residue / "sas_plan.1"
    plan.write_text("stale\n", encoding="ascii")
    monkeypatch.setattr(lama, "_run_process", lambda *args: pytest.fail("residue must not launch planner"))

    result = renderer(domain, problem, profile, cache, RenderConfig())
    assert result["planning_status"] == "planning_plan_residue"
    assert result["planimation_request_count"] == 0
    assert plan.read_text(encoding="ascii") == "stale\n"


def test_vfg_action_mismatch_is_explicit_render_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.phase3.cgas_pilot_lama_first_renderer as lama
    from scripts.phase3.planimation_pairing_contracts import RenderConfig

    renderer, domain, problem, profile, cache = _renderer(tmp_path)

    def execute(command: list[str], _cwd: Path, _watchdog: float) -> lama.PlannerExecution:
        _write_plan(command, "(pickup b1)\n; cost = 1 (unit cost)\n")
        return lama.PlannerExecution(0)

    def render(_domain: Path, _problem: Path, _profile: Path, cache_dir: Path, _config: RenderConfig) -> dict[str, object]:
        trace = cache_dir / "trace.vfg.json"
        trace.write_text(_vfg(["(putdown b1)"]), encoding="ascii")
        return {"status": "success", "attempts": 1, "frame_path": "frame.png", "trace_path": str(trace)}

    monkeypatch.setattr(lama, "_run_process", execute)
    monkeypatch.setattr(lama, "render_state_with_planimation", render)

    result = renderer(domain, problem, profile, cache, RenderConfig())
    assert result["status"] == "failed"
    assert result["message"] == "render_vfg_action_mismatch"
    assert result["planimation_request_count"] == 1
