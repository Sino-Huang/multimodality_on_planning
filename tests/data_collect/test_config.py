from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.data_collect.config import (
    DEFAULT_CURRICULUM_CONFIG_PATH,
    DEFAULT_GENERATOR_DEPENDENCIES_PATH,
    EXPECTED_DOMAIN_TO_GENERATOR,
    EXPECTED_SPLIT_BUCKETS,
    load_curriculum_config,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def read_yaml(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_temp_config(tmp_path: Path) -> tuple[dict, dict, Path, Path]:
    config_payload = deepcopy(read_yaml(DEFAULT_CURRICULUM_CONFIG_PATH))
    dependency_payload = deepcopy(read_yaml(DEFAULT_GENERATOR_DEPENDENCIES_PATH))

    config_payload["workspace_root"] = str(REPO_ROOT)

    config_path = tmp_path / "curriculum.yaml"
    dependency_path = tmp_path / "generator_dependencies.yaml"
    config_payload["dependency_config"] = str(dependency_path)

    write_yaml(config_path, config_payload)
    write_yaml(dependency_path, dependency_payload)
    return config_payload, dependency_payload, config_path, dependency_path


def test_default_curriculum_config_validates() -> None:
    config = load_curriculum_config(DEFAULT_CURRICULUM_CONFIG_PATH)

    assert config.domain_count == 15
    assert config.target_accepted_total == 3600
    assert config.domain_to_generator_id == EXPECTED_DOMAIN_TO_GENERATOR
    assert config.require_rendering is True
    assert config.candidate_multiplier == 2
    assert config.dependency_config_path == DEFAULT_GENERATOR_DEPENDENCIES_PATH.resolve()

    for split_name, expected_buckets in EXPECTED_SPLIT_BUCKETS.items():
        split = config.splits[split_name]
        assert split.total == sum(expected_buckets.values())
        assert split.buckets == expected_buckets

    for domain in config.domains:
        assert domain.generator_dir.exists()
        assert domain.render_profile_path.exists()
        dependency_group = config.dependencies[domain.dependency_group]
        assert dependency_group.python_runtime == "python3"
        assert isinstance(dependency_group.python_packages, tuple)
        assert isinstance(dependency_group.system_tools, tuple)


def test_invalid_bucket_quota_fails_validation(tmp_path: Path) -> None:
    config_payload, _, config_path, _ = build_temp_config(tmp_path)
    config_payload["splits"]["train"]["buckets"]["hard"] = 49
    write_yaml(config_path, config_payload)

    with pytest.raises(ValueError, match=r"splits\.train\.buckets"):
        load_curriculum_config(config_path)


def test_missing_render_profile_mapping_fails_validation(tmp_path: Path) -> None:
    config_payload, _, config_path, _ = build_temp_config(tmp_path)
    config_payload["domains"][0]["render_profile_path"] = None
    write_yaml(config_path, config_payload)

    with pytest.raises(ValueError, match=r"render_profile_path"):
        load_curriculum_config(config_path)


def test_missing_dependency_group_fails_validation(tmp_path: Path) -> None:
    config_payload, dependency_payload, config_path, dependency_path = build_temp_config(tmp_path)
    dependency_payload["dependency_groups"].pop("npuzzle")
    write_yaml(config_path, config_payload)
    write_yaml(dependency_path, dependency_payload)

    with pytest.raises(ValueError, match=r"unknown dependency group 'npuzzle'"):
        load_curriculum_config(config_path)
