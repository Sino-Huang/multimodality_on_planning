from __future__ import annotations

import json
from pathlib import Path

from scripts.phase3.output_layout_contracts import DEFAULT_OUTPUT_LAYOUT, PILOT_SOURCE_ROOT


def repository(tmp_path: Path) -> Path:
    result = (tmp_path / "synthetic-repository").resolve()
    (result / "outputs/deprecated/phase3").mkdir(parents=True)
    for index, relocation in enumerate(DEFAULT_OUTPUT_LAYOUT.relocations):
        source = result / relocation.source.value
        source.mkdir(parents=True)
        (source / f"payload-{index}.txt").write_text(f"payload-{index}\n", encoding="utf-8")
    pilot = result / PILOT_SOURCE_ROOT
    for family in ("full_reasoning", "step_vlm", "search_traversal"):
        for split in ("train", "dev", "test"):
            (pilot / f"{family}_{split}.jsonl").write_text(json.dumps({"family": family, "split": split}) + "\n", encoding="utf-8")
    return result
