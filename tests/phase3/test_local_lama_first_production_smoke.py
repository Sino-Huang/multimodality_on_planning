from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import types
from pathlib import Path
from typing import Any

import pytest


HARNESS_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "evidence"
    / "cgas-phase3-pilot-rendering"
    / "local_lama_first_production_smoke.py"
)
BACKEND_COMMIT = "94d82afb5ee122ce579dd11ca1953b7c85ca5824"
FAST_DOWNWARD_REVISION = "b9fba250f5269a20cb0e950375720281621fb030"


class _Process:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return 0 if self.returncode is None else self.returncode

    def kill(self) -> None:
        self.returncode = -9


def _load_harness() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("local_lama_first_production_smoke", HARNESS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _prepare_repository(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repository"
    output = root / "outputs" / "cgas-lama-first-production-smoke-20260817-attempt-001"
    paths = (
        ".slim/clonedeps/repos/planimation__backend/server/manage.py",
        ".slim/clonedeps/.venv-planimation-v0.1.7/bin/python",
        "modules/downward/fast-downward.py",
        "modules/pddl-generators/blocksworld/4ops/domain.pddl",
        "data/pddl_instances/blocksworld/blocksworld_AP.pddl",
    )
    for relative in paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="ascii")
    for relative in (".slim/clonedeps/.venv-planimation-v0.1.7/bin/python", "modules/downward/fast-downward.py"):
        path = root / relative
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return root, output


def _receipt(root: Path, output: Path, port: int, **overrides: object) -> Path:
    value = {
        "schema_version": "cgas_lama_first_production_smoke_authorization_v1",
        "issue": 8,
        "authorized": True,
        "output_root": str(output.resolve()),
        "port": port,
        "base_url": f"http://127.0.0.1:{port}",
        "solver_url": f"http://127.0.0.1:{port}/forbidden-solver",
        "backend_commit": BACKEND_COMMIT,
        "fast_downward_revision": FAST_DOWNWARD_REVISION,
        "planner_alias": "lama-first",
        "planner_time_limit_seconds": 120,
        "hosted_requests": 0,
        "fallback_allowed": False,
        "case_ids": ["8-object-raw-rank-93", "12-object-raw-rank-9"],
    }
    value.update(overrides)
    path = root / "authorization.json"
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="ascii")
    return path


def _arguments(receipt: Path, output: Path, port: int) -> list[str]:
    return ["--authorization-path", str(receipt), "--output-root", str(output), "--port", str(port)]


def _patch_preflight(monkeypatch: pytest.MonkeyPatch, harness: types.ModuleType, root: Path, output: Path) -> _Process:
    process = _Process()
    monkeypatch.setattr(harness, "_repository_root", lambda: root)
    monkeypatch.setattr(harness, "AUTHORIZED_OUTPUT_ROOT", output)
    monkeypatch.setattr(harness, "_backend_commit", lambda path: BACKEND_COMMIT)
    monkeypatch.setattr(harness, "_fast_downward_revision", lambda path: FAST_DOWNWARD_REVISION)
    monkeypatch.setattr(harness, "_start_server", lambda *args: (process, open(output.parent / "backend-test.log", "wb")))
    monkeypatch.setattr(harness, "_wait_for_loopback", lambda *args: None)
    return process


def _success_renderer(recorder: dict[str, Any], captured: list[Any]) -> type[object]:
    class Renderer:
        def __init__(self, *args: Any) -> None:
            captured.append(args)

        def __call__(self, _domain: Path, _problem: Path, _profile: Path, cache: Path, config: Any) -> dict[str, object]:
            recorder["calls"].append(config.base_url + "/upload/pddl")
            frame = cache / "frame.png"
            trace = cache / "trace.vfg.json"
            cache.mkdir(parents=True, exist_ok=True)
            frame.write_bytes(b"frame")
            trace.write_text("{}", encoding="ascii")
            return {
                "status": "success",
                "attempts": 1,
                "frame_path": str(frame),
                "trace_path": str(trace),
                "planning_status": "planning_submitted",
                "planimation_request_count": 1,
                "planner_metadata": {
                    "source": "local_lama_first",
                    "planning_status": "planning_submitted",
                    "planimation_request_count": 1,
                    "actions": ["(pickup b1)"],
                    "action_count": 1,
                },
            }

    return Renderer


def test_authorization_is_checked_before_server_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = _load_harness()
    root, output = _prepare_repository(tmp_path)
    receipt = _receipt(root, output, 18083, authorized=False)
    starts: list[object] = []
    monkeypatch.setattr(harness, "_repository_root", lambda: root)
    monkeypatch.setattr(harness, "AUTHORIZED_OUTPUT_ROOT", output)
    monkeypatch.setattr(harness, "_start_server", lambda *args: starts.append(args))

    assert harness.main(_arguments(receipt, output, 18083)) == 1
    assert starts == []


def test_nonfresh_root_stops_before_server_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = _load_harness()
    root, output = _prepare_repository(tmp_path)
    receipt = _receipt(root, output, 18083)
    output.mkdir(parents=True)
    starts: list[object] = []
    monkeypatch.setattr(harness, "_repository_root", lambda: root)
    monkeypatch.setattr(harness, "AUTHORIZED_OUTPUT_ROOT", output)
    monkeypatch.setattr(harness, "_start_server", lambda *args: starts.append(args))

    assert harness.main(_arguments(receipt, output, 18083)) == 1
    assert starts == []


def test_two_fixed_cases_use_exact_config_and_certify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = _load_harness()
    root, output = _prepare_repository(tmp_path)
    receipt = _receipt(root, output, 18083)
    process = _patch_preflight(monkeypatch, harness, root, output)
    recorder: dict[str, Any] = {"calls": [], "restore": lambda: None}
    captured: list[Any] = []
    monkeypatch.setattr(harness, "_install_post_recorder", lambda base_url: recorder)
    monkeypatch.setattr(harness, "LocalLamaFirstRenderer", _success_renderer(recorder, captured))
    monkeypatch.setattr(harness, "validate_render_artifacts", lambda *args: types.SimpleNamespace(status="success"))

    assert harness.main(_arguments(receipt, output, 18083)) == 0
    report = json.loads((output / "proof-report.json").read_text(encoding="ascii"))
    assert report["certified"] is True
    assert [case["candidate_id"] for case in report["cases"]] == [
        "0322c69e499f0e2ba7161d25787a1260a275bd22382438a7f48e51e9da3737c4",
        "ca6fb5aa595c065744e0172f1b50d4e237bd4c851d094de684127a240cd3e85d",
    ]
    assert report["network"]["call_count"] == 2
    assert len(captured) == 1
    assert captured[0][2] == FAST_DOWNWARD_REVISION
    assert process.terminated is True


def test_failure_writes_hard_stop_report_and_cleans_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = _load_harness()
    root, output = _prepare_repository(tmp_path)
    receipt = _receipt(root, output, 18083)
    process = _patch_preflight(monkeypatch, harness, root, output)
    monkeypatch.setattr(harness, "_install_post_recorder", lambda base_url: {"calls": [], "restore": lambda: None})

    class FailingRenderer:
        def __init__(self, *args: Any) -> None:
            pass

        def __call__(self, *args: Any) -> dict[str, object]:
            return {"status": "failed", "planning_status": "planning_unsolvable", "planimation_request_count": 0}

    monkeypatch.setattr(harness, "LocalLamaFirstRenderer", FailingRenderer)

    assert harness.main(_arguments(receipt, output, 18083)) == 1
    report = json.loads((output / "proof-report.json").read_text(encoding="ascii"))
    assert report["status"] == "hard_stop"
    assert report["certified"] is False
    assert process.terminated is True


def test_hosted_post_is_not_forwarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.planimation_phase1_client as client_module

    harness = _load_harness()
    root, output = _prepare_repository(tmp_path)
    receipt = _receipt(root, output, 18083)
    _patch_preflight(monkeypatch, harness, root, output)
    forwarded: list[str] = []

    def original_post(url: str, *args: object, **kwargs: object) -> object:
        del args, kwargs
        forwarded.append(url)
        return object()

    class HostedRenderer:
        def __init__(self, *args: Any) -> None:
            pass

        def __call__(self, *args: Any) -> dict[str, object]:
            client_module.requests.post("https://planimation.planning.domains/upload/pddl", files={})
            raise AssertionError("hosted post was forwarded")

    monkeypatch.setattr(client_module.requests, "post", original_post)
    monkeypatch.setattr(harness, "LocalLamaFirstRenderer", HostedRenderer)

    assert harness.main(_arguments(receipt, output, 18083)) == 1
    assert forwarded == []
