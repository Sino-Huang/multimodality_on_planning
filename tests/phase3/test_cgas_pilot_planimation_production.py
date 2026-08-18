from __future__ import annotations

import json
import os
import stat
import subprocess
import types
from pathlib import Path
from typing import Any

import pytest


# Frozen Phase 3 wire fields retained only for this production compatibility seam.
BACKEND_PIN = "94d82afb5ee122ce579dd11ca1953b7c85ca5824"
REQUEST_SHA256 = "13db7cba5fb1cf885bd203ff657e5c7714bda6f832c5970dbfe5a9dee36d0585"
INDEX_SHA256 = "46d1e7c1c0a6a133372782e691888840a74f3d3732dd625b5e2d8611fdf5d390"
MAPPING_SHA256 = "3d6ff222e3662319d9429e18e3bd0d33a7ea1aee67a07e6d9b1a25c506ad7de3"
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


class _Connection:
    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        del exc_type, exc, traceback
        return False


def _prepare_repository(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repository"
    output_root = root / "outputs" / "production"
    paths = (
        ".slim/clonedeps/repos/planimation__backend/server/manage.py",
        ".slim/clonedeps/.venv-planimation-v0.1.7/bin/python",
        "modules/downward/fast-downward.py",
        "tmp/cgas-phase3-pilot-expansion-index-v1/missing-render-request.jsonl",
        "tmp/cgas-phase3-pilot-expansion-index-v1/pilot-expansion-index.jsonl",
        "tmp/cgas-phase3-pilot-representative-mapping-v1/representative-source-mapping.jsonl",
        "modules/pddl-generators/blocksworld/4ops/domain.pddl",
        "data/pddl_instances/blocksworld/blocksworld_AP.pddl",
    )
    for relative_path in paths:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="ascii")
    interpreter = root / ".slim/clonedeps/.venv-planimation-v0.1.7/bin/python"
    interpreter.chmod(interpreter.stat().st_mode | stat.S_IXUSR)
    fast_downward = root / "modules/downward/fast-downward.py"
    fast_downward.chmod(fast_downward.stat().st_mode | stat.S_IXUSR)
    return root, output_root


def _write_receipt(root: Path, output_root: Path, port: int, **overrides: object) -> Path:
    receipt = {
        "schema_version": "cgas_phase3_pilot_planimation_production_authorization_v4",
        "issue": 8,
        "authorized": True,
        "backend_commit": BACKEND_PIN,
        "output_root": str(output_root.resolve()),
        "port": port,
        "base_url": f"http://127.0.0.1:{port}",
        "request_sha256": REQUEST_SHA256,
        "request_count": 16_822,
        "index_sha256": INDEX_SHA256,
        "index_count": 31_171,
        "mapping_sha256": MAPPING_SHA256,
        "mapping_count": 16_822,
        "hosted_requests": 0,
        "fallback_allowed": False,
        "fast_downward_revision": FAST_DOWNWARD_REVISION,
        "planner_alias": "lama-first",
        "planner_time_limit_seconds": 120,
        "solver_url": f"http://127.0.0.1:{port}/forbidden-solver",
    }
    receipt.update(overrides)
    path = root / "authorization.json"
    path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="ascii")
    return path


def _arguments(root: Path, output_root: Path, receipt: Path, port: int) -> list[str]:
    return [
        "--authorization-path",
        str(receipt),
        "--repository-root",
        str(root),
        "--output-root",
        str(output_root),
        "--port",
        str(port),
    ]


def _adapter_result(
    output_root: Path,
    counts: dict[str, int],
    manifest_rows: list[dict[str, object]] | None = None,
    resume_command: str | None = None,
) -> types.SimpleNamespace:
    report_path = output_root / "reports" / "render-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "schema_version": "cgas_phase3_pilot_planimation_adapter_v4",
                "status": "complete",
                "counts": counts,
                **({"resume_command": resume_command} if resume_command is not None else {}),
            }
        )
        + "\n",
        encoding="ascii",
    )
    manifest_path = output_root / "diagnostics" / "state_render_manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in (manifest_rows or [])), encoding="ascii"
    )
    return types.SimpleNamespace(manifest_path=manifest_path, report_path=report_path, counts=counts)


def _resume_root(output_root: Path, checkpoint: bytes = b'{"status":"failed"}\n') -> None:
    (output_root / "candidate_problems").mkdir(parents=True)
    (output_root / "state_cache").mkdir()
    diagnostics = output_root / "diagnostics"
    diagnostics.mkdir()
    (diagnostics / "run-contract.json").write_text("{}\n", encoding="ascii")
    (diagnostics / "render-checkpoint.jsonl").write_bytes(checkpoint)
    (output_root / "reports").mkdir()
    (output_root / "backend.log").write_bytes(b"")


def _prior_report(output_root: Path, receipt: Path, authorization: dict[str, object]) -> None:
    report = {
        "adapter": None,
        "authorization": authorization,
        "authorization_receipt_path": str(receipt.resolve()),
        "backend": {
            "clone_path": "clone",
            "commit": BACKEND_PIN,
            "exited_cleanly": True,
            "returncode": 0,
            "server_log": "backend.log",
            "started": True,
        },
        "backend_commit": BACKEND_PIN,
        "hosted_requests": 0,
        "network": {
            "all_loopback": True,
            "call_count": 0,
            "hosted_requests": 0,
            "limitation": "project client only",
            "recorded_post_urls": [],
        },
        "schema_version": "cgas_phase3_pilot_planimation_production_v3",
        "status": "hard_stop",
    }
    (output_root / "reports" / "planimation-production-report.json").write_text(
        json.dumps(report, sort_keys=True) + "\n", encoding="ascii"
    )


def _patch_server(monkeypatch: pytest.MonkeyPatch, production: Any) -> tuple[list[list[str]], _Process]:
    commands: list[list[str]] = []
    process = _Process()

    def popen(command: list[str], **kwargs: object) -> _Process:
        commands.append(command)
        assert kwargs["env"] is not None
        assert kwargs["cwd"] is not None
        return process

    monkeypatch.setattr(production.subprocess, "Popen", popen)
    def git_revision(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        revision = FAST_DOWNWARD_REVISION if "modules/downward" in str(command) else BACKEND_PIN
        return subprocess.CompletedProcess(command, 0, revision + "\n", "")

    monkeypatch.setattr(production.subprocess, "run", git_revision)
    monkeypatch.setattr(production.socket, "create_connection", lambda *args, **kwargs: _Connection())
    return commands, process


def test_authorization_validation_precedes_backend_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18101, authorized=False)
    starts: list[object] = []
    monkeypatch.setattr(production.subprocess, "Popen", lambda *args, **kwargs: starts.append(args))

    assert production.main(_arguments(root, output_root, receipt, 18101)) == 1
    assert starts == []


def test_cli_passes_exact_frozen_bindings_to_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18102)
    commands, _ = _patch_server(monkeypatch, production)
    received: list[Any] = []
    counts = {"requested": 16_822, "processed": 0, "succeeded": 16_822, "failed": 0, "remaining": 0}

    def render(request: Any, *, renderer: Any) -> types.SimpleNamespace:
        received.extend((request, renderer))
        return _adapter_result(output_root, counts)

    monkeypatch.setattr(production, "render_missing_states", render)

    assert production.main(_arguments(root, output_root, receipt, 18102)) == 0
    request, renderer = received
    assert request.request_path == root / "tmp/cgas-phase3-pilot-expansion-index-v1/missing-render-request.jsonl"
    assert request.expansion_index_path == root / "tmp/cgas-phase3-pilot-expansion-index-v1/pilot-expansion-index.jsonl"
    assert request.representative_mapping_path == root / "tmp/cgas-phase3-pilot-representative-mapping-v1/representative-source-mapping.jsonl"
    assert request.domain_path == root / "modules/pddl-generators/blocksworld/4ops/domain.pddl"
    assert request.profile_path == root / "data/pddl_instances/blocksworld/blocksworld_AP.pddl"
    assert request.expected_request_sha256 == REQUEST_SHA256
    assert request.expected_request_count == 16_822
    assert request.expected_index_sha256 == INDEX_SHA256
    assert request.expected_index_count == 31_171
    assert request.expected_mapping_sha256 == MAPPING_SHA256
    assert request.expected_mapping_count == 16_822
    assert request.config == production.RenderConfig("http://127.0.0.1:18102", 120, 0, 1, None, "http://127.0.0.1:18102/forbidden-solver")
    assert isinstance(renderer, production.LocalLamaFirstRenderer)
    assert renderer.revision == FAST_DOWNWARD_REVISION
    assert commands == [
        [
            str(root / ".slim/clonedeps/.venv-planimation-v0.1.7/bin/python"),
            "manage.py",
            "runserver",
            "127.0.0.1:18102",
            "--noreload",
        ]
    ]


def test_production_adapter_resume_command_reenters_production_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18114)
    _patch_server(monkeypatch, production)
    counts = {"requested": 1, "processed": 0, "succeeded": 1, "failed": 0, "remaining": 0}

    def render(request: Any, *, renderer: Any) -> types.SimpleNamespace:
        del renderer
        return _adapter_result(output_root, counts, resume_command=request.resume_command)

    monkeypatch.setattr(production, "render_missing_states", render)

    assert production.main(_arguments(root, output_root, receipt, 18114)) == 0
    report = json.loads((output_root / "reports" / "planimation-production-report.json").read_text(encoding="ascii"))
    command = report["adapter"]["resume_command"]
    assert "scripts.phase3.cgas_pilot_planimation_production" in command
    assert "scripts.phase3.cgas_pilot_planimation_adapter" not in command
    assert str(receipt) in command
    assert str(output_root) in command
    assert "18114" in command


def test_cli_rejects_non_loopback_receipt_before_backend_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18103, base_url="http://example.invalid:18103")
    starts: list[object] = []
    monkeypatch.setattr(production.subprocess, "Popen", lambda *args, **kwargs: starts.append(args))

    assert production.main(_arguments(root, output_root, receipt, 18103)) == 1
    assert starts == []


def test_cli_records_project_client_posts_and_restores_recorder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.planimation_phase1_client as client_module
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18104)
    _patch_server(monkeypatch, production)
    calls: list[str] = []

    def original_post(url: str, *args: object, **kwargs: object) -> object:
        del args, kwargs
        calls.append(url)
        return object()

    monkeypatch.setattr(client_module.requests, "post", original_post)
    counts = {"requested": 1, "processed": 1, "succeeded": 1, "failed": 0, "remaining": 0}

    def render(request: Any, *, renderer: Any) -> types.SimpleNamespace:
        del renderer
        client_module.requests.post(
            request.config.base_url + "/upload/pddl",
            files={
                "plan": (None, "(pickup b1)"),
                "url": (None, request.config.solver_url),
            },
        )
        return _adapter_result(output_root, counts)

    monkeypatch.setattr(production, "render_missing_states", render)

    assert production.main(_arguments(root, output_root, receipt, 18104)) == 0
    saved = json.loads((output_root / "reports" / "planimation-production-report.json").read_text(encoding="ascii"))
    assert calls == ["http://127.0.0.1:18104/upload/pddl"]
    assert client_module.requests.post is original_post
    assert saved["network"]["call_count"] == 1
    assert saved["network"]["recorded_post_urls"] == calls
    assert saved["network"]["hosted_requests"] == 0


def test_report_preserves_complete_terminal_failure_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18105)
    _patch_server(monkeypatch, production)
    counts = {"requested": 2, "processed": 2, "succeeded": 0, "failed": 2, "remaining": 0}
    monkeypatch.setattr(
        production,
        "render_missing_states",
        lambda request, *, renderer: _adapter_result(output_root, counts),
    )

    assert production.main(_arguments(root, output_root, receipt, 18105)) == 1
    saved = json.loads((output_root / "reports" / "planimation-production-report.json").read_text(encoding="ascii"))
    assert saved["status"] == "complete_with_failures"
    assert saved["coverage_status"] == "complete"
    assert saved["adapter"]["status"] == "complete_with_failures"
    assert saved["adapter"]["counts"] == counts
    assert saved["backend"]["exited_cleanly"] is True


def test_resume_accepts_exact_residue_and_preserves_adapter_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18106)
    _resume_root(output_root)
    _patch_server(monkeypatch, production)
    received: list[Any] = []
    counts = {"requested": 1, "processed": 0, "succeeded": 1, "failed": 0, "remaining": 0}

    def render(request: Any, *, renderer: Any) -> types.SimpleNamespace:
        received.extend((request, renderer))
        return _adapter_result(output_root, counts)

    monkeypatch.setattr(production, "render_missing_states", render)

    assert production.main(_arguments(root, output_root, receipt, 18106)) == 0
    request, renderer = received
    assert request.output_root == output_root
    assert request.request_path == root / "tmp/cgas-phase3-pilot-expansion-index-v1/missing-render-request.jsonl"
    assert request.expansion_index_path == root / "tmp/cgas-phase3-pilot-expansion-index-v1/pilot-expansion-index.jsonl"
    assert request.representative_mapping_path == root / "tmp/cgas-phase3-pilot-representative-mapping-v1/representative-source-mapping.jsonl"
    assert request.config == production.RenderConfig("http://127.0.0.1:18106", 120, 0, 1, None, "http://127.0.0.1:18106/forbidden-solver")
    assert isinstance(renderer, production.LocalLamaFirstRenderer)


def test_fresh_v3_interruption_then_resume_uses_same_root_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18113)
    _, process = _patch_server(monkeypatch, production)
    calls: list[Any] = []
    counts = {"requested": 1, "processed": 0, "succeeded": 1, "failed": 0, "remaining": 0}

    def interrupted(request: Any, *, renderer: Any) -> types.SimpleNamespace:
        del renderer
        calls.append(request)
        (output_root / "candidate_problems").mkdir()
        (output_root / "state_cache").mkdir()
        diagnostics = output_root / "diagnostics"
        diagnostics.mkdir()
        (diagnostics / "run-contract.json").write_text("{}\n", encoding="ascii")
        (diagnostics / "render-checkpoint.jsonl").write_text('{"status":"failed"}\n', encoding="ascii")
        raise production.LamaFirstHardStop("planning_launch_failed")

    monkeypatch.setattr(production, "render_missing_states", interrupted)
    assert production.main(_arguments(root, output_root, receipt, 18113)) == 1
    process.returncode = None

    def resumed(request: Any, *, renderer: Any) -> types.SimpleNamespace:
        calls.append((request, renderer))
        return _adapter_result(output_root, counts)

    monkeypatch.setattr(production, "render_missing_states", resumed)
    assert production.main(_arguments(root, output_root, receipt, 18113)) == 0
    resumed_request, resumed_renderer = calls[1]
    assert resumed_request.output_root == output_root
    assert resumed_request.config.base_url == "http://127.0.0.1:18113"
    assert resumed_request.config.solver_url == "http://127.0.0.1:18113/forbidden-solver"
    assert isinstance(resumed_renderer, production.LocalLamaFirstRenderer)


def test_nonempty_residue_without_contract_or_checkpoint_stops_before_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18107)
    (output_root / "candidate_problems").mkdir(parents=True)
    starts: list[object] = []
    monkeypatch.setattr(production, "_backend_commit", lambda clone: BACKEND_PIN)
    monkeypatch.setattr(production, "_start_server", lambda *args, **kwargs: starts.append(args))

    assert production.main(_arguments(root, output_root, receipt, 18107)) == 1
    assert starts == []
    assert not (output_root / "reports" / "planimation-production-report.json").exists()


def test_mismatched_prior_report_authorization_stops_before_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18108)
    _resume_root(output_root)
    _prior_report(output_root, receipt, {"authorized": False})
    starts: list[object] = []
    monkeypatch.setattr(production.subprocess, "Popen", lambda *args, **kwargs: starts.append(args))

    assert production.main(_arguments(root, output_root, receipt, 18108)) == 1
    assert starts == []


def test_corrupt_resume_checkpoint_records_zero_posts_without_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.planimation_phase1_client as client_module
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18109)
    checkpoint = b"not-json\n"
    _resume_root(output_root, checkpoint)
    _patch_server(monkeypatch, production)
    calls: list[str] = []

    def original_post(url: str, *args: object, **kwargs: object) -> object:
        del args, kwargs
        calls.append(url)
        return object()

    def reject_corrupt_checkpoint(request: Any, *, renderer: Any) -> types.SimpleNamespace:
        del request, renderer
        raise production.ProductionRenderError("checkpoint_corrupt")

    monkeypatch.setattr(client_module.requests, "post", original_post)
    monkeypatch.setattr(production, "render_missing_states", reject_corrupt_checkpoint)

    assert production.main(_arguments(root, output_root, receipt, 18109)) == 1
    saved = json.loads((output_root / "reports" / "planimation-production-report.json").read_text(encoding="ascii"))
    assert calls == []
    assert client_module.requests.post is original_post
    assert (output_root / "diagnostics" / "render-checkpoint.jsonl").read_bytes() == checkpoint
    assert saved["status"] == "hard_stop"
    assert saved["reason"] == "checkpoint_corrupt"
    assert saved["network"]["call_count"] == 0


def test_attempt_001_root_is_rejected_before_backend_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, _ = _prepare_repository(tmp_path)
    output_root = root / "outputs" / "cgas-phase3-pilot-production-attempt-001"
    receipt = _write_receipt(root, output_root, 18110)
    starts: list[object] = []
    monkeypatch.setattr(production, "_start_server", lambda *args, **kwargs: starts.append(args))

    assert production.main(_arguments(root, output_root, receipt, 18110)) == 1
    assert starts == []


def test_report_accounts_for_planning_failures_submitted_plans_and_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18111)
    _patch_server(monkeypatch, production)
    counts = {"requested": 2, "processed": 2, "succeeded": 1, "failed": 1, "remaining": 0}
    rows = [
        {"planning_status": "planning_submitted", "planimation_request_count": 1},
        {"planning_status": "planning_unsolvable", "planimation_request_count": 0},
    ]
    monkeypatch.setattr(
        production,
        "render_missing_states",
        lambda request, *, renderer: _adapter_result(output_root, counts, rows),
    )

    assert production.main(_arguments(root, output_root, receipt, 18111)) == 1
    saved = json.loads((output_root / "reports" / "planimation-production-report.json").read_text(encoding="ascii"))
    assert saved["adapter"]["planning"] == {
        "planning_failures": 1,
        "planimation_calls": 1,
        "submitted_plans": 1,
    }


@pytest.mark.parametrize(
    ("url_suffix", "files"),
    [
        ("/upload/pddl", {"url": (None, "http://127.0.0.1:18112/forbidden-solver")}),
        ("/upload/pddl", {"plan": (None, "(pickup b1)"), "url": (None, "http://127.0.0.1:9/forbidden-solver")}),
        ("/upload/other", {"plan": (None, "(pickup b1)"), "url": (None, "http://127.0.0.1:18112/forbidden-solver")}),
    ],
)
def test_recorder_rejects_nonlocal_or_incomplete_upload_before_forwarding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, url_suffix: str, files: dict[str, tuple[None, str]]
) -> None:
    import scripts.planimation_phase1_client as client_module
    import scripts.phase3.cgas_pilot_planimation_production as production

    root, output_root = _prepare_repository(tmp_path)
    receipt = _write_receipt(root, output_root, 18112)
    _patch_server(monkeypatch, production)
    calls: list[str] = []

    def original_post(url: str, *args: object, **kwargs: object) -> object:
        del args, kwargs
        calls.append(url)
        return object()

    def render(request: Any, *, renderer: Any) -> types.SimpleNamespace:
        del renderer
        client_module.requests.post(request.config.base_url + url_suffix, files=files)
        raise AssertionError("recorder forwarded an invalid upload")

    monkeypatch.setattr(client_module.requests, "post", original_post)
    monkeypatch.setattr(production, "render_missing_states", render)

    assert production.main(_arguments(root, output_root, receipt, 18112)) == 1
    assert calls == []
