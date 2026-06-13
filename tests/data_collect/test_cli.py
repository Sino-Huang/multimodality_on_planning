from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from src.data_collect import cli


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "src.data_collect", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


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
        "--require-rendering",
        "--dry-run",
        "--force",
        "--json",
    ):
        assert flag in result.stdout
    assert "accepted final manifests require rendering" in result.stdout.lower()


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

    def fake_orchestrate_generation(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return SimpleNamespace(
            accepted_manifest_path=Path("/tmp/out/accepted_manifest.jsonl"),
            output_root=Path("/tmp/out"),
            rejections_path=Path("/tmp/out/rejections.jsonl"),
            summary_path=Path("/tmp/out/summary.json"),
            summary=SimpleNamespace(
                accepted_total=2,
                rejected_total=0,
                to_dict=lambda: {"accepted_total": 2, "rejected_total": 0},
            ),
        )

    monkeypatch.setattr(cli, "orchestrate_generation", fake_orchestrate_generation)

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
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert calls["kwargs"]["renderer"] == "planimation-renderer"
    assert calls["kwargs"]["domains"] == ("blocksworld", "gripper")
    assert calls["kwargs"]["splits"] == ("train",)
    assert calls["kwargs"]["quotas_by_split"] == {"train": {"easy": 1, "medium": 1, "hard": 1}}
    assert calls["kwargs"]["max_attempts_per_bucket"] == 10
    assert calls["kwargs"]["seed"] == 123
    assert payload["output_root"] == "/tmp/out"
    assert payload["summary"]["accepted_total"] == 2


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
