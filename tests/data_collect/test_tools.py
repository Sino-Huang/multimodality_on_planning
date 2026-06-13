from __future__ import annotations

import json
from importlib import metadata as importlib_metadata
from pathlib import Path

import pytest

from src.data_collect import cli
from src.data_collect.config import DEFAULT_CURRICULUM_CONFIG_PATH, DEFAULT_GENERATOR_DEPENDENCIES_PATH
from src.data_collect.tools import inspect_tools


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_temp_config(tmp_path: Path) -> tuple[Path, Path]:
    config_payload = _load_json(DEFAULT_CURRICULUM_CONFIG_PATH)
    dependency_payload = _load_json(DEFAULT_GENERATOR_DEPENDENCIES_PATH)

    config_payload["workspace_root"] = str(REPO_ROOT)

    config_path = tmp_path / "curriculum.yaml"
    dependency_path = tmp_path / "generator_dependencies.yaml"
    config_payload["dependency_config"] = str(dependency_path)

    _write_json(config_path, config_payload)
    _write_json(dependency_path, dependency_payload)
    return config_path, dependency_path


def test_inspect_tools_cli_reports_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    result = cli.main(["inspect-tools", "--config", str(DEFAULT_CURRICULUM_CONFIG_PATH)])
    captured = capsys.readouterr()

    payload = json.loads(captured.out)

    assert result == 0
    assert payload["python"]["available"] is True
    assert "commands" in payload
    assert "downward_root" in payload
    assert "rendering_ready" in payload
    assert "adapter_matrix" in payload
    assert len(payload["adapter_matrix"]) == 15
    assert all(adapter_payload["adapter_configured"] is True for adapter_payload in payload["adapter_matrix"])


def test_inspect_tools_reports_missing_generator_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path, _ = _build_temp_config(tmp_path)
    config_payload = _load_json(config_path)
    config_payload["generator_root"] = "missing-generator-root"
    _write_json(config_path, config_payload)

    monkeypatch.setattr(importlib_metadata, "version", lambda name: (_ for _ in ()).throw(importlib_metadata.PackageNotFoundError(name)))

    report = inspect_tools(config_path)

    assert report.generator_root_exists is False
    assert report.ready is False
    assert any("generator_root missing" in issue for issue in report.issues)
    assert len(report.adapter_matrix) == 15


def test_inspect_tools_emits_uv_install_guidance_for_missing_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path, dependency_path = _build_temp_config(tmp_path)
    dependency_payload = _load_json(dependency_path)
    dependency_payload["dependency_groups"]["npuzzle"]["python_packages"] = ["installed-pkg", "missing-pkg"]
    _write_json(dependency_path, dependency_payload)

    def fake_version(name: str) -> str:
        if name == "installed-pkg":
            return "1.2.3"
        raise importlib_metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib_metadata, "version", fake_version)

    report = inspect_tools(config_path)

    npuzzle = next(group for group in report.dependency_groups if group.group_id == "npuzzle")
    assert [package.name for package in npuzzle.python_packages] == ["installed-pkg", "missing-pkg"]
    assert npuzzle.missing_python_packages == ("missing-pkg",)
    assert npuzzle.uv_install_command == "uv pip install missing-pkg"
    assert all(adapter.adapter_configured is True for adapter in report.adapter_matrix)


def test_inspect_tools_fails_when_render_profile_missing_and_rendering_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path, _ = _build_temp_config(tmp_path)
    config_payload = _load_json(config_path)
    config_payload["domains"][0]["render_profile_path"] = "data/pddl_instances/15puzzle/missing-render.pddl"
    _write_json(config_path, config_payload)

    monkeypatch.setattr(importlib_metadata, "version", lambda name: (_ for _ in ()).throw(importlib_metadata.PackageNotFoundError(name)))

    report = inspect_tools(config_path)

    assert report.require_rendering is True
    assert report.rendering_ready is False
    assert report.ready is False
    assert any("render profile missing for domain: 15puzzle" in issue for issue in report.issues)
    assert len(report.adapter_matrix) == 15
