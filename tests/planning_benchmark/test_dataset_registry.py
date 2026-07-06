from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from starVLA.dataloader.gr00t_lerobot.registry import (
    DATASET_NAMED_MIXTURES,
    OPTIONAL_REGISTRY_IMPORT_DEPENDENCIES,
    ROBOT_TYPE_CONFIG_MAP,
    _load_module_from_path,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PLANNING_ROBOT_TYPE = "planning_blocksworld"
PLANNING_MIXTURE = "planning_blocksworld_dev_smoke"
DATASET_SMOKE_DIR = REPO_ROOT / "outputs" / "planning_artifacts" / "dataset_smoke"
EXPECTED_SMOKE_FILES = {
    "language.jsonl",
    "vision.jsonl",
    "vision_language.jsonl",
    "vision_language_tool.jsonl",
}


def test_planning_registry_auto_discovers_smoke_names() -> None:
    assert PLANNING_MIXTURE in DATASET_NAMED_MIXTURES
    assert PLANNING_ROBOT_TYPE in ROBOT_TYPE_CONFIG_MAP


def test_planning_registry_mixture_points_to_task9_smoke_jsonl() -> None:
    mixture = DATASET_NAMED_MIXTURES[PLANNING_MIXTURE]

    assert len(mixture) == len(EXPECTED_SMOKE_FILES)
    assert {Path(dataset).name for dataset, _weight, _robot_type in mixture} == EXPECTED_SMOKE_FILES
    assert {robot_type for _dataset, _weight, robot_type in mixture} == {PLANNING_ROBOT_TYPE}
    assert all(weight == 1.0 for _dataset, weight, _robot_type in mixture)
    for dataset, _weight, _robot_type in mixture:
        dataset_path = REPO_ROOT / dataset
        assert dataset_path.parent == DATASET_SMOKE_DIR
        assert dataset_path.exists(), f"missing smoke JSONL: {dataset_path}"


def test_planning_registry_data_config_shape_is_minimal_smoke_config() -> None:
    data_config = ROBOT_TYPE_CONFIG_MAP[PLANNING_ROBOT_TYPE]
    modality_config = data_config.modality_config()

    assert set(modality_config) == {"video", "state", "action", "language"}
    assert data_config.transform().transforms == []
    assert data_config.action_keys == ["supervised_target.next_action", "supervised_target.internal_state_update"]


def test_planning_registry_names_are_unique() -> None:
    robot_type_sources: dict[str, list[str]] = {}
    mixture_sources: dict[str, list[str]] = {}

    for config_path in sorted((REPO_ROOT / "examples").glob("*/train_files/data_registry/data_config.py")):
        module = _load_data_config(config_path)
        if module is None:
            continue
        source = str(config_path.relative_to(REPO_ROOT))
        for robot_type in getattr(module, "ROBOT_TYPE_CONFIG_MAP", {}):
            robot_type_sources.setdefault(robot_type, []).append(source)
        for mixture_name in getattr(module, "DATASET_NAMED_MIXTURES", {}):
            mixture_sources.setdefault(mixture_name, []).append(source)

    assert robot_type_sources[PLANNING_ROBOT_TYPE] == [
        "examples/planning_benchmark_slice/train_files/data_registry/data_config.py"
    ]
    assert mixture_sources[PLANNING_MIXTURE] == [
        "examples/planning_benchmark_slice/train_files/data_registry/data_config.py"
    ]
    assert _duplicates(robot_type_sources) == {}
    assert _duplicates(mixture_sources) == {}


def test_registry_loader_reraises_internal_missing_imports(tmp_path: Path) -> None:
    bad_config = tmp_path / "bad_data_config.py"
    bad_config.write_text("import definitely_missing_internal_project_module_for_f2\n", encoding="utf-8")

    with pytest.raises(ModuleNotFoundError) as exc_info:
        _load_module_from_path("_bad_registry_config_for_f2", bad_config)

    assert exc_info.value.name == "definitely_missing_internal_project_module_for_f2"


def test_collision_helper_reraises_internal_missing_imports(tmp_path: Path) -> None:
    bad_config = tmp_path / "bad_data_config.py"
    bad_config.write_text("import definitely_missing_internal_project_module_for_collision_f2\n", encoding="utf-8")

    with pytest.raises(ModuleNotFoundError) as exc_info:
        _load_data_config(bad_config)

    assert exc_info.value.name == "definitely_missing_internal_project_module_for_collision_f2"


def _load_data_config(config_path: Path):
    module_name = "_planning_registry_collision_check_" + "_".join(config_path.parts[-5:-1])
    spec = importlib.util.spec_from_file_location(module_name, config_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        if exc.name not in OPTIONAL_REGISTRY_IMPORT_DEPENDENCIES:
            raise
        return None
    return module


def _duplicates(sources_by_name: dict[str, list[str]]) -> dict[str, list[str]]:
    return {name: sources for name, sources in sources_by_name.items() if len(sources) > 1}
