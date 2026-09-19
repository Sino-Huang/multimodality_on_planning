from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import Path
from typing import cast

import pytest

from src.data_collect import cli
from src.data_collect.generate import GenerationRunReceipt
from src.data_collect.governance import (
    AuthorizationReceipt,
    GateReceipt,
    ReceiptBinding,
    RunReceipt,
    StopOutcome,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "src.data_collect", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def _write_governance_inputs(
    tmp_path: Path,
    output_root: Path,
    *,
    include_structural_profiles: bool = True,
) -> list[str]:
    binding = ReceiptBinding("contract-v1", "attempt-cli-001", str(output_root.resolve()))
    gate = GateReceipt(binding=binding, outcome=StopOutcome.PASS)
    authorization = AuthorizationReceipt(binding, gate.receipt_id)
    gate_path = tmp_path / "gate.json"
    authorization_path = tmp_path / "authorization.json"
    policy_path = tmp_path / "policy.json"
    profiles_path = tmp_path / "profiles.json"
    gate_path.write_text(gate.canonical_json(), encoding="utf-8")
    authorization_path.write_text(authorization.canonical_json(), encoding="utf-8")
    policy_path.write_text(
        json.dumps(
            {
                "version": "fixture-v1",
                "horizon_ranges": [{"name": "short", "minimum": 0, "maximum": 3}],
                "branching_ranges": [{"name": "narrow", "minimum": 0, "maximum": 3}],
                "object_count_ranges": [{"name": "small", "minimum": 0, "maximum": 3}],
                "required_cells": [
                    {
                        "split": "train",
                        "cell": {"horizon": "short", "branching": "narrow", "object_count": "small"},
                        "minimum_count": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    profiles_path.write_text(
        json.dumps(
            [
                {
                    "instance_id": "tiny-train-easy-0000",
                    "split": "train",
                    "horizon": 1,
                    "branching_factor": 1,
                    "object_count": 1,
                }
            ]
        ),
        encoding="utf-8",
    )
    inputs = [
        "--gate-receipt", str(gate_path),
        "--authorization-receipt", str(authorization_path),
        "--receipt-root", str((tmp_path / "receipts").resolve()),
        "--split-ledger", str(tmp_path / "split-ledger.jsonl"),
        "--structural-policy", str(policy_path),
    ]
    if include_structural_profiles:
        inputs.extend(["--structural-profiles", str(profiles_path)])
    return inputs


def test_help_lists_expected_subcommands() -> None:
    result = run_module("--help")

    assert result.returncode == 0
    assert "generate" in result.stdout
    assert "inspect-tools" in result.stdout
    assert "merge-shards" in result.stdout


def test_generate_help_lists_expected_options_and_rendering_contract() -> None:
    result = run_module("generate", "--help")

    assert result.returncode == 0
    for flag in (
        "--config",
        "--output",
        "--domains",
        "--splits",
        "--quota",
        "--seed",
        "--max-attempts-per-bucket",
        "--candidate-multiplier",
        "--require-rendering",
        "--dry-run",
        "--force",
        "--json",
        "--gate-receipt",
        "--authorization-receipt",
        "--receipt-root",
        "--split-ledger",
        "--structural-policy",
        "--structural-profiles",
    ):
        assert flag in result.stdout
    assert "accepted final manifests require rendering" in result.stdout.lower()


def test_generate_requires_governance_inputs_before_output_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "out"

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["generate", "--output", str(output_root), "--seed", "123"])

    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert "--gate-receipt" in captured.err
    assert "--receipt-root" in captured.err
    assert "--split-ledger" in captured.err
    assert "--structural-policy" in captured.err
    assert not output_root.exists()


def test_merge_shards_cli_calls_merger_and_emits_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: dict[str, object] = {}

    def fake_merge_shards(*, shards_root, output_root, force, resume):
        calls["shards_root"] = shards_root
        calls["output_root"] = output_root
        calls["force"] = force
        calls["resume"] = resume
        return SimpleNamespace(
            accepted_manifest_path=Path("/tmp/merged/accepted_manifest.jsonl"),
            output_root=Path("/tmp/merged"),
            rejections_path=Path("/tmp/merged/rejections.jsonl"),
            summary_path=Path("/tmp/merged/summary.json"),
            summary=SimpleNamespace(
                accepted_total=2,
                rejected_total=1,
                to_dict=lambda: {"accepted_total": 2, "rejected_total": 1},
            ),
        )

    monkeypatch.setattr(cli, "merge_shards", fake_merge_shards)

    result = cli.main(
        [
            "merge-shards",
            "--shards-root",
            str(tmp_path / "shards"),
            "--output",
            str(tmp_path / "merged"),
            "--resume",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert calls["shards_root"] == tmp_path / "shards"
    assert calls["output_root"] == tmp_path / "merged"
    assert calls["force"] is False
    assert calls["resume"] is True
    assert payload["summary"] == {"accepted_total": 2, "rejected_total": 1}


def test_merge_shards_cli_rejects_force_with_resume(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            [
                "merge-shards",
                "--shards-root",
                str(tmp_path / "shards"),
                "--output",
                str(tmp_path / "merged"),
                "--force",
                "--resume",
            ]
        )

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert "cannot be combined" in captured.err


def test_invalid_quota_override_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            [
                "generate",
                "--config",
                str(Path("src/data_collect/configs/curriculum_15_domains.yaml")),
                "--output",
                str(tmp_path / "out"),
                "--seed",
                "123",
                "--quota",
                "easy=1,medium=oops,hard=1",
            ]
        )

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert "invalid quota override" in captured.err


def test_invalid_candidate_multiplier_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            [
                "generate",
                "--config",
                str(Path("src/data_collect/configs/curriculum_15_domains.yaml")),
                "--output",
                str(tmp_path / "out"),
                "--seed",
                "123",
                "--candidate-multiplier",
                "0",
                "--dry-run",
                *_write_governance_inputs(tmp_path, tmp_path / "out"),
            ]
        )

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert "--candidate-multiplier must be positive" in captured.err


def test_require_rendering_cannot_be_combined_with_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            [
                "generate",
                "--config",
                str(Path("src/data_collect/configs/curriculum_15_domains.yaml")),
                "--output",
                str(tmp_path / "out"),
                "--seed",
                "123",
                "--dry-run",
                "--require-rendering",
                *_write_governance_inputs(tmp_path, tmp_path / "out"),
            ]
        )

    captured = capsys.readouterr()

    assert excinfo.value.code == 2
    assert "cannot be combined with --dry-run" in captured.err


def test_generate_parses_smoke_override_and_emits_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_config = SimpleNamespace(
        require_rendering=True,
        selected_domain_ids=("blocksworld", "gripper"),
        splits={"train": object()},
    )
    calls: dict[str, object] = {}

    monkeypatch.setattr(cli, "load_curriculum_config", lambda _: fake_config)
    monkeypatch.setattr(cli, "PlanimationRenderer", lambda: "planimation-renderer")

    def fake_run_governed_generation(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        request = args[0]
        authorization = RunReceipt(
            binding=request.binding,
            outcome=StopOutcome.PASS,
            run_state="authorized-to-start",
            start_permitted=True,
            scientific_completion=False,
            gate_receipt_id="a" * 64,
            authorization_receipt_id="b" * 64,
        )
        return GenerationRunReceipt(
            outcome=StopOutcome.PASS,
            status="completed",
            binding=request.binding,
            scientific_completion=True,
            receipt_path=Path("/tmp/receipt.json"),
            authorization_receipt=authorization,
            execution_result={"output_root": "/tmp/out", "accepted_count": 2},
        )

    monkeypatch.setattr(cli, "run_governed_generation", fake_run_governed_generation)

    result = cli.main(
        [
            "generate",
            "--config",
            str(Path("src/data_collect/configs/curriculum_15_domains.yaml")),
            "--output",
            str(tmp_path / "out"),
            "--domains",
            "blocksworld,gripper",
            "--splits",
            "train",
            "--quota",
            "easy=1,medium=1,hard=1",
            "--seed",
            "123",
            "--max-attempts-per-bucket",
            "10",
            "--candidate-multiplier",
            "1",
            "--json",
            *_write_governance_inputs(
                tmp_path,
                tmp_path / "out",
                include_structural_profiles=False,
            ),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    kwargs = cast(dict[str, object], calls["kwargs"])
    assert kwargs["renderer"] == "planimation-renderer"
    assert kwargs["domains"] == ("blocksworld", "gripper")
    assert kwargs["splits"] == ("train",)
    assert kwargs["quotas_by_split"] == {"train": {"easy": 1, "medium": 1, "hard": 1}}
    assert kwargs["max_attempts_per_bucket"] == 10
    assert kwargs["candidate_multiplier"] == 1
    assert kwargs["seed"] == 123
    assert kwargs["structural_profiles"] is None
    assert payload["outcome"] == "PASS"
    assert payload["execution_result"]["accepted_count"] == 2


def test_require_rendering_flag_reaches_governed_curriculum_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @dataclass(frozen=True)
    class FakeCurriculumConfig:
        require_rendering: bool
        selected_domain_ids: tuple[str, ...]
        splits: dict[str, object]
        candidate_multiplier: int

    fake_config = FakeCurriculumConfig(
        require_rendering=False,
        selected_domain_ids=("blocksworld",),
        splits={"train": object()},
        candidate_multiplier=1,
    )
    observed: dict[str, object] = {}
    monkeypatch.setattr(cli, "load_curriculum_config", lambda _: fake_config)
    monkeypatch.setattr(cli, "PlanimationRenderer", lambda: "planimation-renderer")

    def fake_run_governed_generation(*args, **kwargs):
        request = args[0]
        observed["curriculum_config"] = args[1]
        observed["renderer"] = kwargs["renderer"]
        authorization = RunReceipt(
            binding=request.binding,
            outcome=StopOutcome.PASS,
            run_state="authorized-to-start",
            start_permitted=True,
            scientific_completion=False,
            gate_receipt_id="a" * 64,
            authorization_receipt_id="b" * 64,
        )
        return GenerationRunReceipt(
            outcome=StopOutcome.PASS,
            status="completed",
            binding=request.binding,
            scientific_completion=True,
            receipt_path=Path("/tmp/receipt.json"),
            authorization_receipt=authorization,
            execution_result={"output_root": "/tmp/out", "accepted_count": 1},
        )

    monkeypatch.setattr(cli, "run_governed_generation", fake_run_governed_generation)

    result = cli.main(
        [
            "generate",
            "--output",
            str(tmp_path / "out"),
            "--seed",
            "123",
            "--require-rendering",
            "--json",
            *_write_governance_inputs(
                tmp_path,
                tmp_path / "out",
                include_structural_profiles=False,
            ),
        ]
    )

    governed_config = cast(FakeCurriculumConfig, observed["curriculum_config"])
    assert result == 0
    assert fake_config.require_rendering is False
    assert governed_config.require_rendering is True
    assert observed["renderer"] == "planimation-renderer"


def test_generate_exits_cleanly_when_renderer_dependencies_are_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_config = SimpleNamespace(
        require_rendering=True,
        selected_domain_ids=("blocksworld", "gripper"),
        splits={"train": object()},
    )

    monkeypatch.setattr(cli, "load_curriculum_config", lambda _: fake_config)

    def fail_renderer() -> None:
        raise RuntimeError(
            "Planimation renderer dependencies unavailable: missing Python package 'requests' required by scripts.planimation_phase1"
        )

    monkeypatch.setattr(cli, "PlanimationRenderer", fail_renderer)

    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            [
                "generate",
                "--config",
                str(Path("src/data_collect/configs/curriculum_15_domains.yaml")),
                "--output",
                str(tmp_path / "out"),
                "--domains",
                "blocksworld,gripper",
                "--splits",
                "train",
                "--quota",
                "easy=1,medium=1,hard=1",
                "--seed",
                "123",
                "--max-attempts-per-bucket",
                "10",
                "--require-rendering",
                *_write_governance_inputs(tmp_path, tmp_path / "out"),
            ]
        )

    captured = capsys.readouterr()

    assert excinfo.value.code == 1
    assert "Planimation renderer dependencies unavailable" in captured.err
    assert "requests" in captured.err


def test_invalid_subcommand_exits_nonzero_with_argparse_error() -> None:
    result = run_module("no-such-command")

    assert result.returncode != 0
    assert "invalid choice" in result.stderr
