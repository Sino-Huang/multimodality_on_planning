"""Production-only local LAMA-first Planimation renderer."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast
from urllib.parse import urlsplit

from .cgas_pilot_planimation_adapter import _planimation_compat_problem_path
from .cgas_planimation_evidence import EvidenceMalformedError, extract_vfg_action_sequence
from .pddl import PDDLError, normalize_action_string
from .planimation_pairing_contracts import RenderConfig, RendererResult
from .planimation_pairing_rendering import render_state_with_planimation
from .traversal_state_types import JSONValue


FAST_DOWNWARD_REVISION: Final = "b9fba250f5269a20cb0e950375720281621fb030"
LAMA_FIRST_ALIAS: Final = "lama-first"
PLAN_FILENAME: Final = "sas_plan"
_ACTION_LINE: Final = re.compile(r"^\s*(\([^()\r\n]+\))\s*$")
_COST_FOOTER: Final = re.compile(r"^\s*;\s*cost\s*=\s*(\d+(?:\.\d+)?)\s*\((?:unit|general)\s+cost\)\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class LamaFirstHardStop(Exception):
    rule: str

    def __str__(self) -> str:
        return self.rule


@dataclass(frozen=True, slots=True)
class PlannerExecution:
    returncode: int | None
    external_timeout: bool = False
    launch_error: str | None = None


@dataclass(frozen=True, slots=True)
class LocalLamaFirstRenderer:
    repository_root: Path
    fast_downward_path: Path
    revision: str
    time_limit_seconds: int
    watchdog_seconds: float
    solver_url: str

    @property
    def renderer_id(self) -> str:
        return f"local_lama_first:{self.revision}:{self.time_limit_seconds}"

    def run_contract_metadata(self) -> dict[str, JSONValue]:
        return {
            "source": "local_lama_first",
            "alias": LAMA_FIRST_ALIAS,
            "planner_path": str(self.fast_downward_path),
            "planner_revision": self.revision,
            "time_limit_seconds": self.time_limit_seconds,
            "watchdog_seconds": self.watchdog_seconds,
            "solver_url": self.solver_url,
        }

    def __call__(
        self, domain_path: Path, problem_path: Path, profile_path: Path, cache_dir: Path, config: RenderConfig
    ) -> RendererResult:
        if config.plan is not None:
            raise LamaFirstHardStop("planning_prepopulated_plan")
        if config.solver_url not in {None, self.solver_url}:
            raise LamaFirstHardStop("planning_solver_url_mismatch")
        if self.revision != FAST_DOWNWARD_REVISION or self.time_limit_seconds < 1 or self.watchdog_seconds <= self.time_limit_seconds:
            raise LamaFirstHardStop("planning_configuration_invalid")
        _assert_forbidden_solver_url(self.solver_url)
        compat_path = _planimation_compat_problem_path(domain_path, problem_path, cache_dir)
        planner_root = cache_dir / "local-lama-first"
        planner_root.mkdir(parents=True, exist_ok=True)
        plan_path = planner_root / PLAN_FILENAME
        command = [
            str(self.fast_downward_path),
            "--alias",
            LAMA_FIRST_ALIAS,
            "--overall-time-limit",
            f"{self.time_limit_seconds}s",
            "--plan-file",
            str(plan_path),
            str(domain_path),
            str(compat_path),
        ]
        if tuple(planner_root.glob(PLAN_FILENAME + "*")):
            return _planning_failure(
                self._metadata(command, plan_path, PlannerExecution(None, launch_error="preexisting_sas_plan_residue")),
                "planning_plan_residue",
            )
        execution = _run_process(command, self.repository_root, self.watchdog_seconds)
        metadata = self._metadata(command, plan_path, execution)
        if execution.launch_error is not None:
            return _planning_failure(metadata, "planning_launch_failed")
        if execution.external_timeout:
            return _planning_failure(metadata, "planning_timeout")
        if execution.returncode is None:
            return _planning_failure(metadata, "planning_returncode_missing")
        files = tuple(sorted(planner_root.glob(PLAN_FILENAME + "*")))
        if len(files) > 1:
            return _planning_failure(metadata, "planning_plan_multiple")
        returncode = execution.returncode
        if returncode in {10, 11}:
            return _planning_failure(metadata, "planning_unsolvable")
        if returncode == 12:
            return _planning_failure(metadata, "planning_unsolved_incomplete")
        if 20 <= returncode <= 24:
            return _planning_failure(metadata, "planning_resource_limit")
        if 1 <= returncode <= 3:
            return _planning_failure(metadata, "planning_nonclean_resource_failure")
        if returncode < 0 or 30 <= returncode <= 39 or returncode != 0:
            return _planning_failure(metadata, "planning_returncode_unexpected")
        if len(files) != 1:
            return _planning_failure(metadata, "planning_plan_missing")
        try:
            actions, cost = _parse_plan(files[0])
        except LamaFirstHardStop as error:
            return _planning_failure(metadata, error.rule)
        metadata.update({"actions": list(actions), "action_count": len(actions), "cost": cost})
        if not actions:
            return _planning_failure(metadata, "planning_zero_step_unsupported")
        plan = "\n".join(actions)
        submitted_metadata = {**metadata, "planning_status": "planning_submitted", "planimation_request_count": 1}
        render_config = RenderConfig(
            config.base_url,
            config.timeout_seconds,
            config.request_delay_seconds,
            config.max_attempts,
            plan,
            self.solver_url,
        )
        result: dict[str, Any] = dict(render_state_with_planimation(domain_path, compat_path, profile_path, cache_dir, render_config))
        result["planner_metadata"] = submitted_metadata
        result["planning_status"] = "planning_submitted"
        result["planimation_request_count"] = 1
        if result.get("status") != "success":
            return cast(RendererResult, result)
        try:
            trace_path = Path(str(result["trace_path"]))
            if not trace_path.is_absolute():
                trace_path = self.repository_root / trace_path
            vfg_actions = extract_vfg_action_sequence(json.loads(trace_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, EvidenceMalformedError, KeyError, TypeError) as error:
            result.update({"status": "failed", "message": "render_vfg_action_invalid"})
            result["planner_metadata"] = {**submitted_metadata, "vfg_error": str(error)}
            return cast(RendererResult, result)
        if vfg_actions != actions:
            result.update({"status": "failed", "message": "render_vfg_action_mismatch"})
            result["planner_metadata"] = {**submitted_metadata, "vfg_actions": list(vfg_actions)}
        return cast(RendererResult, result)

    def _metadata(self, command: list[str], plan_path: Path, execution: PlannerExecution) -> dict[str, JSONValue]:
        return {
            "source": "local_lama_first",
            "alias": LAMA_FIRST_ALIAS,
            "command": cast(list[JSONValue], command),
            "planner_path": str(self.fast_downward_path),
            "planner_revision": self.revision,
            "return_code": execution.returncode,
            "launch_error": execution.launch_error,
            "external_timeout": execution.external_timeout,
            "timeout_policy": {
                "internal_seconds": self.time_limit_seconds,
                "watchdog_seconds": self.watchdog_seconds,
                "mode": "process_group",
            },
            "plan_path": str(plan_path),
            "cost": None,
            "action_count": 0,
            "planning_status": "planning_started",
            "planimation_request_count": 0,
        }


def _assert_forbidden_solver_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname != "127.0.0.1" or parts.path != "/forbidden-solver":
        raise LamaFirstHardStop("planning_solver_url_invalid")


def _planning_failure(metadata: dict[str, JSONValue], status: str) -> RendererResult:
    return {
        "status": "failed",
        "attempts": 0,
        "message": status,
        "planning_status": status,
        "planimation_request_count": 0,
        "planner_metadata": {**metadata, "planning_status": status},
    }


def _parse_plan(path: Path) -> tuple[tuple[str, ...], int | float]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise LamaFirstHardStop("planning_plan_unreadable") from error
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise LamaFirstHardStop("planning_plan_malformed")
    cost_match = _COST_FOOTER.fullmatch(lines.pop())
    if cost_match is None:
        raise LamaFirstHardStop("planning_plan_malformed")
    actions: list[str] = []
    for line in lines:
        match = _ACTION_LINE.fullmatch(line)
        if match is None:
            raise LamaFirstHardStop("planning_plan_malformed")
        try:
            actions.append(normalize_action_string(match.group(1)))
        except PDDLError as error:
            raise LamaFirstHardStop("planning_plan_malformed") from error
    cost_text = cost_match.group(1)
    return tuple(actions), float(cost_text) if "." in cost_text else int(cost_text)


def _run_process(command: list[str], cwd: Path, watchdog_seconds: float) -> PlannerExecution:
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as error:
        return PlannerExecution(None, launch_error=str(error))
    try:
        process.communicate(timeout=watchdog_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.communicate()
        return PlannerExecution(process.returncode, external_timeout=True)
    return PlannerExecution(process.returncode)
