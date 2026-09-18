"""Second-backbone interface specifications for the #101-#103 replication branch.

The frozen primary contract (Qwen3-VL-8B) stays the default everywhere; these specs
only take effect where a caller explicitly passes a backbone. Selection evidence and
the frozen processor-compaction disclosure live in
docs/experiments/expanded-study/second-backbone-selection.*.
"""

from __future__ import annotations

BACKBONES = {
    "internvl3_5-8b": {
        "key": "internvl3_5-8b",
        "model_id": "OpenGVLab/InternVL3_5-8B-HF",
        "model_revision": "741a7d03020411e666c6109218ab71e08151ef86",
        "processor_class": "InternVLProcessor",
        "model_class": "transformers.InternVLForConditionalGeneration",
        # The processor's real call path forces crop_to_patches=True
        # (InternVLProcessorKwargs images default): images are dynamically tiled
        # at 448x448 (min_patches=1, max_patches=12, plus a thumbnail tile when
        # tiled) and encoded as <img> + 256 x <IMG_CONTEXT> per tile + </img>.
        "processor_overrides": {},
        "image_wrapper_tokens": 2,
        "lora_exclude_modules": r".*(vision_tower|multi_modal_projector).*",
        "license": "apache-2.0",
    }
}


def backbone_spec(key: str) -> dict:
    if key not in BACKBONES:
        raise ValueError(f"unknown second backbone: {key}")
    return BACKBONES[key]


def model_class(path: str):
    import importlib

    module, name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module), name)
