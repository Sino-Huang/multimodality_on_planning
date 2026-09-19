"""Frozen v2 evaluation bindings and resumable episodes for generalization-robustness-v2 (#124).

The membership comes from the frozen admission artifact (admission-v2.json), never
re-derived from the candidate pool. Episodes reuse the expanded baseline episode
engine semantics (expanded_baseline.run_binding) with two v2 deltas: per-binding
seeds (random_valid runs the five frozen rollout seeds) and a hard one-call cap on
the pretrained_base arm per the frozen v2 estimand.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .expanded_baseline import _commit_pending, _restore_events
from .expanded_views import ExpandedTaskViews
from .modality_view_preparation import write_json
from .scene_assets import read_json
from .visual_episode import VisualSession, replay_visual_episode

PROTOCOL_V2 = Path("configs/experiments/expanded-study/generalization-robustness-protocol-v2.json")
ADMISSION_V2 = Path("outputs/expanded-study/v1/generalization-robustness/admission-v2.json")
CANDIDATES_ROOT = ADMISSION_V2.parent / "candidates"
EVALUATION_INPUTS_SCHEMA = "expanded_generalization_evaluation_inputs_v1"
EVALUATION_SCHEMA = "expanded_generalization_evaluation_v1"
WORKER_SCHEMA = "expanded_generalization_evaluation_worker_v1"
EPISODE_SCHEMA = "expanded_baseline_episode_v1"
WORKERS = 2
MODEL_KIND = "models"
CONTROL_KIND = "controls"
GPU_CONDITIONS = ("learned_adapter", "pretrained_base")
CPU_CONDITIONS = ("random_valid", "exact_reference")
MODEL_CALL_CONDITIONS = {"pretrained_base", "learned_adapter"}
ENGINE_ARM = {
    "learned_adapter": "process_sft",
    "pretrained_base": "pretrained_base",
    "random_valid": "random_valid",
    "exact_reference": "exact_reference",
}
BASE_MODEL_CALL_CAP = 1


def load_protocol_v2(root: Path) -> dict[str, Any]:
    return read_json(root / PROTOCOL_V2)


def load_admission(root: Path, protocol: dict[str, Any]) -> dict[str, Any]:
    admission = read_json(root / ADMISSION_V2)
    if (
        admission.get("schema_version") != "expanded_generalization_admission_v2"
        or admission.get("protocol_id") != protocol["protocol_id"]
        or admission.get("decision") != "PASS"
        or admission.get("membership_sha256") != protocol["membership_rule"]["membership_sha256"]
    ):
        raise ValueError("generalization v2 admission evidence differs from the frozen protocol")
    return admission


def candidate_dir(root: Path, family: str, variant_id: str) -> Path:
    # Candidate assets are anchored to the frozen admission artifact location, not
    # to the (possibly redirected) episode output_root.
    return root / CANDIDATES_ROOT / family / variant_id


def load_tasks(
    root: Path,
    protocol: dict[str, Any],
    admission: dict[str, Any],
    *,
    only: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Load the materialized candidate assets for the admitted membership only."""

    tasks = []
    for family, variant_ids in admission["membership"].items():
        for variant_id in variant_ids:
            if only is not None and variant_id not in only:
                continue
            folder = candidate_dir(root, family, variant_id)
            task = read_json(folder / "task-with-views.json")
            if task["variant_id"] != variant_id:
                raise ValueError("candidate asset variant identity differs from the admission membership")
            reference_costs = task["row"]["reference_costs"]
            if any(algorithm not in reference_costs for algorithm in protocol["learned_algorithms"]):
                raise ValueError("candidate reference costs do not cover the frozen learned algorithms")
            tasks.append({"family": family, "task_index": len(tasks), **task})
    if only is not None and len(tasks) != len(only):
        raise ValueError("--only variant list does not match the admission membership")
    return tasks


def bindings(tasks: list[dict[str, Any]], protocol: dict[str, Any]) -> list[dict[str, Any]]:
    rollout_seeds = list(protocol["evaluation"]["random_valid_rollout_seeds"])
    base_seed = int(protocol["training_seed"])
    rows = []
    index = 0
    for task in tasks:
        for modality in protocol["modalities"]:
            for algorithm in protocol["learned_algorithms"]:
                for condition in (*GPU_CONDITIONS, *CPU_CONDITIONS):
                    seeds = rollout_seeds if condition == "random_valid" else [base_seed]
                    for seed in seeds:
                        rows.append(
                            {
                                "index": index,
                                "worker": index % WORKERS,
                                "task_index": task["task_index"],
                                "variant_id": task["variant_id"],
                                "family": task["family"],
                                "modality": modality,
                                "algorithm": algorithm,
                                "condition": condition,
                                "seed": seed,
                            }
                        )
                        index += 1
    expected = len(tasks) * len(protocol["modalities"]) * len(protocol["learned_algorithms"]) * (
        len(GPU_CONDITIONS) + len(rollout_seeds) + 1
    )
    if len(rows) != expected or len({tuple(sorted(row.items())) for row in rows}) != len(rows):
        raise ValueError("generalization v2 binding enumeration is incomplete or duplicated")
    return rows


def assigned_bindings(rows: list[dict[str, Any]], worker: int, kind: str) -> list[dict[str, Any]]:
    if worker not in range(WORKERS) or kind not in {MODEL_KIND, CONTROL_KIND}:
        raise ValueError("unknown generalization v2 worker or execution kind")
    conditions = set(GPU_CONDITIONS if kind == MODEL_KIND else CPU_CONDITIONS)
    return [row for row in rows if row["worker"] == worker and row["condition"] in conditions]


def binding_paths(root: Path, protocol: dict[str, Any], binding: dict[str, Any]) -> tuple[Path, Path, Path]:
    condition = binding["condition"]
    if condition == "random_valid":
        condition = f"random_valid-seed{binding['seed']}"
    episode = (
        root
        / protocol["output_root"]
        / "episodes"
        / binding["modality"]
        / binding["variant_id"]
        / f"{binding['algorithm']}-{condition}.json.gz"
    )
    partial = episode.with_name(episode.name.removesuffix(".json.gz") + ".partial.json.gz")
    view_output = (
        root
        / protocol["output_root"]
        / "views"
        / binding["modality"]
        / binding["variant_id"]
        / f"{binding['algorithm']}-{condition}"
    )
    return episode, partial, view_output


def adapter_bank(protocol: dict[str, Any], modality: str) -> dict[str, str]:
    return {
        row["algorithm"]: row["checkpoint"]
        for row in protocol["fixed_adapters"]
        if row["modality"] == modality
    }


class V2VisualSession(VisualSession):
    """VisualSession plus the v2 hard model-call cap (pretrained_base arm: one call)."""

    def __init__(self, *args: Any, model_call_cap: int | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._model_call_cap = model_call_cap

    def next_request(self):
        request = super().next_request()
        if (
            request is not None
            and self._model_call_cap is not None
            and len(self.events) >= self._model_call_cap
        ):
            self.session.termination_reason = "model_call_limit"
            self.pending = None
            return None
        return request

    def result(self):
        result = super().result()
        if self._model_call_cap is not None:
            result["model_call_limit"] = self._model_call_cap
        return result


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
        "task_id": binding["variant_id"],
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
    """Run one v2 episode; modeled on expanded_baseline.run_binding with v2 seeds/caps."""

    episode, partial_path, view_output = binding_paths(root, protocol, binding)
    expected = _identity(protocol, binding, episode, view_output, checkpoint)
    if episode.exists():
        if partial_path.exists():
            raise ValueError("completed episode retains a conflicting partial journal")
        report = read_json(episode)
        if any(report.get(key) != value for key, value in expected.items()):
            raise ValueError("retained episode binding differs")
        views = ExpandedTaskViews(root, task, view_output, endpoint, read_only=True)
        replay_visual_episode(root, task["row"], report, views)
        return report, True

    views = ExpandedTaskViews(root, task, view_output, endpoint)
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
        example = views.observe(raw, binding["algorithm"], modality=binding["modality"])
        call_started = time.monotonic()
        try:
            if generate is None:
                generated, generated_tokens = session.reference_output(), None
            else:
                generated, generated_tokens = generate(example)
        finally:
            for image in example["images"]:
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


def independently_replay(root: Path, task: dict[str, Any], report: dict[str, Any], endpoint: str) -> dict[str, Any]:
    """Replay one v2 episode with the engine arm mapped and the recorded call cap enforced."""

    views = ExpandedTaskViews(root, task, root / report["view_output"], endpoint, read_only=True)
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


def summarize_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate recorded episodes by condition, family, and modality."""

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
        "by_family": bucket(lambda row: row["family"]),
        "by_modality": bucket(lambda row: row["modality"]),
    }
