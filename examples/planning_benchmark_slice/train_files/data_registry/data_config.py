"""Planning benchmark smoke dataset registry for Blocksworld JSONL artifacts."""

from dataclasses import dataclass
from typing import Any

from starVLA.dataloader.gr00t_lerobot.embodiment_tags import EmbodimentTag

_OPTIONAL_REGISTRY_IMPORT_DEPENDENCIES = frozenset(
    {
        "accelerate",
        "numpy",
        "pandas",
        "pydantic",
        "torch",
        "tqdm",
    }
)

try:
    from starVLA.dataloader.gr00t_lerobot.datasets import ModalityConfig as _StarVLAModalityConfig
    from starVLA.dataloader.gr00t_lerobot.transform.base import (
        ComposedModalityTransform as _StarVLAComposedModalityTransform,
    )
except ModuleNotFoundError as exc:
    if exc.name not in _OPTIONAL_REGISTRY_IMPORT_DEPENDENCIES:
        raise
    _StarVLAModalityConfig = None
    _StarVLAComposedModalityTransform = None


PLANNING_BLOCKSWORLD_ROBOT_TYPE = "planning_blocksworld"
PLANNING_BLOCKSWORLD_DEV_SMOKE_MIXTURE = "planning_blocksworld_dev_smoke"
PLANNING_DATASET_SMOKE_DIR = "outputs/planning_artifacts/dataset_smoke"
PLANNING_PHASE3_JSONL_ROBOT_TYPE = "planning_phase3_supervised_jsonl"
PLANNING_PHASE3_JSONL_MIXTURE = "planning_phase3_supervised_all"
PLANNING_PHASE3_JSONL_DIR = "data/phase3_supervised_planning"


@dataclass(frozen=True)
class PlanningModalityConfig:
    delta_indices: list[int]
    modality_keys: list[str]


class PlanningNoOpTransform:
    def __init__(self) -> None:
        self.transforms: list[Any] = []

    def __call__(self, data: dict[str, Any]) -> dict[str, Any]:
        return data

    def apply(self, data: dict[str, Any]) -> dict[str, Any]:
        return data


class PlanningBlocksworldSmokeDataConfig:
    """Minimal smoke DataConfig for Task 9 serialized planning JSONL records.

    The registered artifacts are modality JSONL files, not full continuous-action
    LeRobot training datasets. Keys mirror the stable fields in each JSONL record
    so registry discovery can validate the planning names without forcing a VLA
    action tensor conversion.
    """

    embodiment_tag = EmbodimentTag.NEW_EMBODIMENT
    video_keys = ["model_facing.visual_observation"]
    state_keys = ["evaluation_metadata.state_atoms"]
    action_keys = ["supervised_target.next_action", "supervised_target.internal_state_update"]
    language_keys = ["model_facing.language_context", "model_facing.planner", "model_facing.response_format"]
    observation_indices = [0]
    state_indices = [0]
    action_indices = [0]

    def modality_config(self):
        return {
            "video": _modality_config(delta_indices=self.observation_indices, modality_keys=self.video_keys),
            "state": _modality_config(delta_indices=self.state_indices, modality_keys=self.state_keys),
            "action": _modality_config(delta_indices=self.action_indices, modality_keys=self.action_keys),
            "language": _modality_config(delta_indices=self.observation_indices, modality_keys=self.language_keys),
        }

    def transform(self):
        if _StarVLAComposedModalityTransform is not None:
            return _StarVLAComposedModalityTransform(transforms=[])
        return PlanningNoOpTransform()


class PlanningPhase3SupervisedJsonlDataConfig(PlanningBlocksworldSmokeDataConfig):
    """Registry surface for complete Phase 3 supervised planning JSONL files.

    These files are training-ready JSONL records with symbolic action targets.
    They are not a StarVLA/LeRobot tensor conversion and do not claim continuous
    robot action support.
    """

    video_keys = ["model_facing.vision.frame_paths"]
    state_keys = ["evaluation_metadata.final_state_atoms"]
    action_keys = ["supervised_target.plan"]
    language_keys = ["model_facing.task", "model_facing.domain", "model_facing.planner"]


def _modality_config(*, delta_indices: list[int], modality_keys: list[str]):
    if _StarVLAModalityConfig is not None:
        return _StarVLAModalityConfig(delta_indices=delta_indices, modality_keys=modality_keys)
    return PlanningModalityConfig(delta_indices=delta_indices, modality_keys=modality_keys)


ROBOT_TYPE_CONFIG_MAP = {
    PLANNING_BLOCKSWORLD_ROBOT_TYPE: PlanningBlocksworldSmokeDataConfig(),
    PLANNING_PHASE3_JSONL_ROBOT_TYPE: PlanningPhase3SupervisedJsonlDataConfig(),
}


ROBOT_TYPE_TO_EMBODIMENT_TAG = {}


DATASET_NAMED_MIXTURES = {
    PLANNING_BLOCKSWORLD_DEV_SMOKE_MIXTURE: [
        (f"{PLANNING_DATASET_SMOKE_DIR}/language.jsonl", 1.0, PLANNING_BLOCKSWORLD_ROBOT_TYPE),
        (f"{PLANNING_DATASET_SMOKE_DIR}/vision.jsonl", 1.0, PLANNING_BLOCKSWORLD_ROBOT_TYPE),
        (f"{PLANNING_DATASET_SMOKE_DIR}/vision_language.jsonl", 1.0, PLANNING_BLOCKSWORLD_ROBOT_TYPE),
        (f"{PLANNING_DATASET_SMOKE_DIR}/vision_language_tool.jsonl", 1.0, PLANNING_BLOCKSWORLD_ROBOT_TYPE),
    ],
    PLANNING_PHASE3_JSONL_MIXTURE: [
        (f"{PLANNING_PHASE3_JSONL_DIR}/train.jsonl", 1.0, PLANNING_PHASE3_JSONL_ROBOT_TYPE),
        (f"{PLANNING_PHASE3_JSONL_DIR}/dev.jsonl", 1.0, PLANNING_PHASE3_JSONL_ROBOT_TYPE),
        (f"{PLANNING_PHASE3_JSONL_DIR}/test.jsonl", 1.0, PLANNING_PHASE3_JSONL_ROBOT_TYPE),
    ],
}
