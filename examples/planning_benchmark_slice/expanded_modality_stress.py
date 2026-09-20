"""Frozen modality-stress bindings, corruption and resumable episodes (#126).


The membership comes from the frozen admission artifact (admission.json), never
re-derived from the panel pool. Corruption is applied inside StressTaskViews.observe
after page assembly and before the model call, deterministically in the clean
observation and the frozen seed rule, so independent replay recomputes identical
input tokens. Episodes reuse the expanded baseline episode engine semantics with
the v2 deltas (per-binding seeds, hard one-call cap on the pretrained_base arm).
Clean-observation comparators are reused replay-verified baseline episodes.
"""

from __future__ import annotations

import hashlib
import random
import re
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .expanded_baseline import _commit_pending, _restore_events
from .expanded_generalization_eval import V2VisualSession
from .expanded_views import ExpandedTaskViews
from .modality_view_preparation import write_json
from .scene_assets import read_json
from .visual_episode import replay_visual_episode

PROTOCOL = Path("configs/experiments/expanded-study/modality-stress-protocol.json")
ADMISSION = Path("outputs/expanded-study/v1/modality-stress/admission.json")
EVALUATION_INPUTS_SCHEMA = "expanded_modality_stress_evaluation_inputs_v1"
EVALUATION_SCHEMA = "expanded_modality_stress_evaluation_v1"
ANALYSIS_SCHEMA = "expanded_modality_stress_analysis_v1"
WORKER_SCHEMA = "expanded_modality_stress_evaluation_worker_v1"
EPISODE_SCHEMA = "expanded_modality_stress_episode_v1"
WORKERS = 2
MODEL_KIND = "models"
CONTROL_KIND = "controls"
GPU_CONDITIONS = ("learned_adapter", "pretrained_base")
CPU_CONDITIONS = ("random_valid",)
MODEL_CALL_CONDITIONS = {"pretrained_base", "learned_adapter"}
ENGINE_ARM = {
    "learned_adapter": "process_sft",
    "pretrained_base": "pretrained_base",
    "random_valid": "random_valid",
    "exact_reference": "exact_reference",
}
BASE_MODEL_CALL_CAP = 1
FAMILY_ORDER = ("visual-blank", "visual-degraded", "text-shuffled", "text-masked")
MASK_CHARACTER = "▮"
MASK_PATTERN = re.compile(r"[A-Za-z0-9]+")
CONTEXT_TOKENS = 32768
OUTPUT_TOKENS = 384


def load_protocol(root: Path) -> dict[str, Any]:
    return read_json(root / PROTOCOL)


def load_admission(root: Path, protocol: dict[str, Any]) -> dict[str, Any]:
    admission = read_json(root / ADMISSION)
    if (
        admission.get("schema_version") != protocol["admission"]["schema_version"]
        or admission.get("protocol_id") != protocol["protocol_id"]
        or admission.get("decision") != "PASS"
        or admission.get("membership_sha256") != protocol["membership_rule"]["membership_sha256"]
        or sorted(admission.get("membership", [])) != sorted(protocol["membership_rule"]["membership"])
    ):
        raise ValueError("modality-stress admission artifact differs from the frozen protocol")
    return admission


def load_panel_tasks(root: Path, protocol: dict[str, Any]) -> list[dict[str, Any]]:
    panel = read_json(root / protocol["panel"])
    views = read_json(root / protocol["panel_view_report"])
    tasks = {task["row"]["task_id"]: task for task in views["tasks"]}
    if (
        panel.get("panel_id") != protocol["panel_id"]
        or len(panel.get("tasks", [])) != 24
        or len(tasks) != 24
        or any("native_views" not in task for task in tasks.values())
    ):
        raise ValueError("modality-stress panel differs from the frozen qualified panel")
    reference_by_id = {task["row"]["task_id"]: task for task in panel["tasks"]}
    return [
        {
            **tasks[task_id],
            "reference_paths": reference_by_id[task_id]["reference_paths"],
            "task_index": index,
        }
        for index, task_id in enumerate(protocol["membership_rule"]["membership"])
    ]


def family_arms(protocol: dict[str, Any], family: str) -> list[str]:
    return list(protocol["corruption_families"][family]["applicable_modalities"])


def bindings(tasks: list[dict[str, Any]], protocol: dict[str, Any]) -> list[dict[str, Any]]:
    new_control_seeds = [seed for seed in protocol["evaluation"]["random_valid_rollout_seeds"] if seed != 17]
    base_seed = int(protocol["training_seed"])
    rows = []
    index = 0
    for task in tasks:
        for family in FAMILY_ORDER:
            for modality in family_arms(protocol, family):
                for algorithm in protocol["learned_algorithms"]:
                    for condition in GPU_CONDITIONS:
                        rows.append(
                            {
                                "index": index,
                                "worker": index % WORKERS,
                                "kind": MODEL_KIND,
                                "task_index": task["task_index"],
                                "task_id": task["row"]["task_id"],
                                "family": family,
                                "modality": modality,
                                "algorithm": algorithm,
                                "condition": condition,
                                "seed": base_seed,
                            }
                        )
                        index += 1
    for task in tasks:
        for algorithm in protocol["learned_algorithms"]:
            for seed in new_control_seeds:
                rows.append(
                    {
                        "index": index,
                        "worker": index % WORKERS,
                        "kind": CONTROL_KIND,
                        "task_index": task["task_index"],
                        "task_id": task["row"]["task_id"],
                        "family": None,
                        "modality": "text-state",
                        "algorithm": algorithm,
                        "condition": "random_valid",
                        "seed": seed,
                    }
                )
                index += 1
    expected = len(tasks) * (
        len(FAMILY_ORDER) * 2 * len(protocol["learned_algorithms"]) * len(GPU_CONDITIONS)
        + len(protocol["learned_algorithms"]) * len(new_control_seeds)
    )
    if len(rows) != expected or len({tuple(sorted(row.items())) for row in rows}) != len(rows):
        raise ValueError("modality-stress binding enumeration is incomplete or duplicated")
    return rows


def assigned_bindings(rows: list[dict[str, Any]], worker: int, kind: str) -> list[dict[str, Any]]:
    if worker not in range(WORKERS) or kind not in {MODEL_KIND, CONTROL_KIND}:
        raise ValueError("unknown modality-stress worker or execution kind")
    return [row for row in rows if row["worker"] == worker and row["kind"] == kind]


def binding_paths(root: Path, protocol: dict[str, Any], binding: dict[str, Any]) -> tuple[Path, Path, Path]:
    task_name = binding["task_id"].replace("/", "__")
    if binding["kind"] == MODEL_KIND:
        episode = (
            root
            / protocol["output_root"]
            / "episodes"
            / binding["modality"]
            / task_name
            / f"{binding['algorithm']}-{binding['family']}-{binding['condition']}.json.gz"
        )
        view_output = (
            root
            / protocol["output_root"]
            / "views"
            / binding["modality"]
            / task_name
            / f"{binding['algorithm']}-{binding['family']}-{binding['condition']}"
        )
    else:
        episode = (
            root
            / protocol["output_root"]
            / "episodes"
            / "control"
            / task_name
            / f"{binding['algorithm']}-{binding['condition']}-seed{binding['seed']}.json.gz"
        )
        view_output = (
            root
            / protocol["output_root"]
            / "views"
            / "control"
            / task_name
            / f"{binding['algorithm']}-{binding['condition']}-seed{binding['seed']}"
        )
    partial = episode.with_name(episode.name.removesuffix(".json.gz") + ".partial.json.gz")
    return episode, partial, view_output


def adapter_bank(protocol: dict[str, Any], modality: str) -> dict[str, str]:
    return {
        row["algorithm"]: row["checkpoint"]
        for row in protocol["fixed_adapters"]
        if row["modality"] == modality
    }


def _shuffle_text(text: str, master_seed: int) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()
    seed = int.from_bytes(
        hashlib.sha256(f"{master_seed}|text-shuffled|{digest}".encode()).digest()[:8], "big"
    )
    tokens = text.split()
    random.Random(seed).shuffle(tokens)
    return " ".join(tokens)


def _mask_text(text: str) -> str:
    return MASK_PATTERN.sub(MASK_CHARACTER, text)


def _corrupt_image(image: Any, family: str) -> Any:
    if not isinstance(image, Image.Image):
        return image
    if family == "visual-blank":
        corrupted = Image.new(image.mode, image.size, (128, 128, 128))
    elif family == "visual-degraded":
        corrupted = image.resize((16, 16), Image.BILINEAR).resize(image.size, Image.NEAREST)
    else:
        raise ValueError(f"unknown visual corruption family: {family}")
    image.close()
    return corrupted


def corrupt_example(example: dict[str, Any], family: str, master_seed: int) -> None:
    """Apply the frozen deterministic corruption to one observe() result in place."""

    content = example["messages"][-1]["content"]
    if family in ("text-shuffled", "text-masked"):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                part["text"] = (
                    _shuffle_text(part["text"], master_seed)
                    if family == "text-shuffled"
                    else _mask_text(part["text"])
                )
    elif family in ("visual-blank", "visual-degraded"):
        replaced: dict[int, Any] = {}
        example["images"] = [
            replaced.setdefault(id(image), _corrupt_image(image, family)) for image in example["images"]
        ]
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image" and id(part.get("image")) in replaced:
                part["image"] = replaced[id(part["image"])]
    else:
        raise ValueError(f"unknown corruption family: {family}")


class StressTaskViews(ExpandedTaskViews):
    """ExpandedTaskViews plus the frozen deterministic observation corruption."""

    def __init__(self, *args: Any, corruption: str | None = None, master_seed: int = 42613, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._corruption = corruption
        self._master_seed = master_seed

    def observe(self, raw, algorithm, *, modality="visual-state", pixels=True):
        example = super().observe(raw, algorithm, modality=modality, pixels=pixels)
        if self._corruption is None:
            return example
        corrupt_example(example, self._corruption, self._master_seed)
        count = self.page_processor.count(example["messages"], image_sizes=example["image_sizes"])
        if count + OUTPUT_TOKENS > CONTEXT_TOKENS:
            raise RuntimeError("VALID_STOP: corrupted live input exceeds the approved 32K context")
        example["binding"]["input_tokens"] = count
        return example


def _identity(
    protocol: dict[str, Any],
    binding: dict[str, Any],
    episode: Path,
    view_output: Path,
    checkpoint: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": EPISODE_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "panel_id": protocol["panel_id"],
        "binding_index": binding["index"],
        "worker": binding["worker"],
        "family": binding["family"],
        "task_id": binding["task_id"],
        "modality": binding["modality"],
        "algorithm": binding["algorithm"],
        "arm": binding["condition"],
        "seed": binding["seed"],
        "output": str(episode.relative_to(Path(protocol["root"]))),
        "view_output": str(view_output.relative_to(Path(protocol["root"]))),
        "checkpoint": checkpoint,
        "model_id": protocol["model_id"],
        "model_revision": protocol["model_revision"],
        "oracle_assisted_valid_operation_control": binding["condition"] == "random_valid",
    }


def run_binding(
    root: Path,
    protocol: dict[str, Any],
    task: dict[str, Any],
    binding: dict[str, Any],
    checkpoint: str | None,
    endpoint: str,
    generate: Callable[[dict[str, Any]], tuple[str, int | None]] | None,
) -> tuple[dict[str, Any], bool]:
    """Run one stress episode; modeled on expanded_baseline.run_binding with v2 seeds/caps."""

    episode, partial_path, view_output = binding_paths(root, protocol, binding)
    expected = _identity(protocol, binding, episode, view_output, checkpoint)
    corruption = binding["family"] if binding["kind"] == MODEL_KIND else None
    master_seed = int(protocol["corruption_master_seed"])
    if episode.exists():
        if partial_path.exists():
            raise ValueError("completed episode retains a conflicting partial journal")
        report = read_json(episode)
        if any(report.get(key) != value for key, value in expected.items()):
            raise ValueError("retained episode binding differs")
        independently_replay(root, protocol, task, report, endpoint)
        return report, True

    views = StressTaskViews(
        root, task, view_output, endpoint, corruption=corruption, master_seed=master_seed
    )
    session = V2VisualSession(
        root,
        task["row"],
        binding["algorithm"],
        ENGINE_ARM[binding["condition"]],
        binding["seed"],
        episode,
        protocol["protocol_id"],
        views=views,
        model_call_cap=BASE_MODEL_CALL_CAP if binding["condition"] == "pretrained_base" else None,
    )
    saved = (
        read_json(partial_path)
        if partial_path.exists()
        else {
            **expected,
            "events": [],
            "call_measurements": [],
            "pending": None,
            "started": time.time(),
            "active_wall_seconds": 0.0,
        }
    )
    if any(saved.get(key) != value for key, value in expected.items()):
        raise ValueError("partial episode binding differs")
    attempt_started = time.monotonic()
    _restore_events(session, views, saved)
    _commit_pending(session, views, saved)
    saved["active_wall_seconds"] += time.monotonic() - attempt_started
    write_json(partial_path, saved)
    checkpoint_started = time.monotonic()
    while (request := session.next_request()) is not None:
        raw = dict(request.model_input)
        example = views.observe(raw, binding["algorithm"], modality=binding["modality"] or "text-state")
        call_started = time.monotonic()
        try:
            if generate is None:
                generated, generated_tokens = session.reference_output(), None
            else:
                generated, generated_tokens = generate(example)
        finally:
            for image in example["images"]:
                if isinstance(image, Image.Image):
                    image.close()
        measurement = {
            "event_index": len(session.events),
            "model_call": binding["condition"] in MODEL_CALL_CONDITIONS,
            "input_tokens": example["binding"]["input_tokens"],
            "generated_sequence_tokens": generated_tokens,
            "call_wall_seconds": time.monotonic() - call_started,
        }
        saved["pending"] = {
            "input": raw,
            "binding": example["binding"],
            "raw_output": generated,
            "measurement": measurement,
        }
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write_json(partial_path, saved)
        checkpoint_started = time.monotonic()
        _commit_pending(session, views, saved)
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write_json(partial_path, saved)
        checkpoint_started = time.monotonic()
    report = {
        **expected,
        "outcome": "RECORDED",
        "events": saved["events"],
        "result": session.result(),
        "call_measurements": saved["call_measurements"],
        "started": saved["started"],
        "finished": time.time(),
        "active_wall_seconds": saved["active_wall_seconds"] + time.monotonic() - checkpoint_started,
        "raw_invalid_outputs_preserved": sum(not event["accepted"] for event in saved["events"]),
    }
    views.save()
    write_json(episode, report)
    partial_path.unlink()
    return report, False


def independently_replay(
    root: Path, protocol: dict[str, Any], task: dict[str, Any], report: dict[str, Any], endpoint: str
) -> dict[str, Any]:
    """Replay one stress episode with the corruption spec and the recorded call cap enforced."""

    corruption = report["family"] if report.get("family") else None
    master_seed = int(protocol["corruption_master_seed"])
    views = StressTaskViews(
        root, task, root / report["view_output"], endpoint, read_only=True, corruption=corruption,
        master_seed=master_seed,
    )
    replay_report = dict(report, arm=ENGINE_ARM[report["arm"]], contract_id=report["protocol_id"])
    return replay_visual_episode(
        root,
        task["row"],
        replay_report,
        views,
        session_class=lambda *args, **kwargs: V2VisualSession(
            *args, model_call_cap=int(report["result"]["model_call_limit"]), **kwargs
        ),
    )


def verify_comparator(
    root: Path,
    protocol: dict[str, Any],
    task: dict[str, Any],
    modality: str,
    algorithm: str,
    condition: str,
    endpoint: str,
) -> dict[str, Any]:
    """Bind and independently replay one reused clean-observation baseline episode."""

    audit = protocol["comparator_audit"]
    baseline_protocol = read_json(root / audit["baseline_protocol"])
    path = (
        root
        / audit["baseline_episodes_root"]
        / modality
        / task["row"]["task_id"].replace("/", "__")
        / f"{algorithm}-{condition}.json.gz"
    )
    report = read_json(path)
    view_output = root / report["view_output"]
    views = ExpandedTaskViews(root, task, view_output, endpoint, read_only=True)
    replay_report = dict(report, contract_id=report.get("contract_id", report.get("protocol_id")))
    replay_visual_episode(root, task["row"], replay_report, views)
    if (
        report.get("task_id") != task["row"]["task_id"]
        or report.get("modality") != modality
        or report.get("algorithm") != algorithm
        or report.get("arm") != condition
        or report.get("seed") != 17
        or report.get("protocol_id") != baseline_protocol["protocol_id"]
        or report.get("model_id") != baseline_protocol["model_id"]
        or report.get("model_revision") != baseline_protocol["model_revision"]
    ):
        raise ValueError("reused modality-stress comparator differs from its panel binding")
    return {
        **report,
        "comparator_source": str(path.relative_to(root)),
        "comparator_contract": report.get("protocol_id"),
    }


def comparator_bindings(protocol: dict[str, Any], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enumerate the reused clean-observation comparator episodes (frozen join)."""

    rows = []
    arms = ("text-state", "visual-state", "multimodal-state")
    for task in tasks:
        for modality in arms:
            for algorithm in protocol["learned_algorithms"]:
                for condition in ("process_sft", "pretrained_base"):
                    rows.append(
                        {
                            "task_id": task["row"]["task_id"],
                            "modality": modality,
                            "algorithm": algorithm,
                            "condition": condition,
                        }
                    )
        for algorithm in protocol["learned_algorithms"]:
            for condition in ("random_valid", "exact_reference"):
                rows.append(
                    {
                        "task_id": task["row"]["task_id"],
                        "modality": "text-state",
                        "algorithm": algorithm,
                        "condition": condition,
                    }
                )
    return rows


def summarize_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate recorded stress episodes by condition, family, and modality."""

    def bucket(key: Callable[[dict[str, Any]], str]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for report in reports:
            grouped.setdefault(key(report), []).append(report)
        return {
            name: {
                "episodes": len(rows),
                "invariant_valid_success": sum(bool(row["result"]["invariant_valid_success"]) for row in rows),
                "decisions": sum(int(row["result"]["decision_count"]) for row in rows),
                "expansions": sum(int(row["result"]["expansion_count"]) for row in rows),
                "invalid_operations": sum(int(row["result"]["invalid_operation_count"]) for row in rows),
            }
            for name, rows in sorted(grouped.items())
        }

    return {
        "episodes": len(reports),
        "by_condition": bucket(lambda row: row["arm"]),
        "by_family": bucket(lambda row: str(row.get("family"))),
        "by_modality": bucket(lambda row: str(row.get("modality"))),
    }
