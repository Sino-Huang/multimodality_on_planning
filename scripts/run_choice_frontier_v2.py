#!/usr/bin/env python
"""Choice-frontier v2 (#135) adapter re-evaluation runner on the frozen fresh panel.

Copy of ``scripts/run_choice_frontier.py`` (#132) reduced to the model-evaluation
stages. Changed: panel/membership (``configs/experiments/choice-frontier-v2``),
output root ``outputs/choice-frontier/v2`` and ledger/schedule paths. Everything
else is the frozen #132 protocol: model, inference settings, seed 17, the #132
adapters under ``outputs/choice-frontier/v1/training`` (no retraining) and the
#132 smoke gate under ``outputs/choice-frontier/v1/smoke``.

Stages (docs/experiments/choice-frontier/issue-135-protocol.md):

- ``prepare-views`` — native reference traces + planimation scene-only views for
  the frozen panel tasks (the ``scripts/prepare_expanded_views.py`` recipe; CPU).
- ``evaluate-inputs`` / ``evaluate-worker --worker {0,1} --kind models``.
- ``finalize`` — independent replay of every episode + evaluation.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.choice_frontier import (  # noqa: E402
    CHOICE_ARM,
    ChoiceFrontierModelSession,
    ChoiceFrontierTask,
)
from examples.planning_benchmark_slice.choice_frontier_views import ChoiceFrontierTaskViews  # noqa: E402
from examples.planning_benchmark_slice.modality_view_preparation import write_json  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402

PROTOCOL_PATH = Path("configs/experiments/choice-frontier/choice-frontier-protocol-v1.json")
MEMBERSHIP_PATH = Path("configs/experiments/choice-frontier-v2/membership.json")
SCHEDULE_PATH = Path("docs/experiments/choice-frontier/schedule-v2.json")
LEDGER_PATH = ROOT / "outputs/choice-frontier/v2/budget.json"
V2_OUTPUT_ROOT = "outputs/choice-frontier/v2"
V1_ROOT = ROOT / "outputs/choice-frontier/v1"
VIEW_REPORT = ROOT / V2_OUTPUT_ROOT / "reference-views.json"
# Only the two evaluated additive cells: native bfs exceeds the expanded-study
# 128-expansion reference ceiling on the fresh C* >= 8 panel, and the reference
# traces only seed the state catalog (unseen states are rendered live).
VIEW_ALGORITHMS = ("best_first_add_w3", "best_first_add_greedy")
VIEW_ENDPOINT_INDEX = 0  # prepare_task renders at 18092 + index % 4; only 18092 is required
BASE_MODEL_CALL_CAP = 1
EPISODE_SCHEMA = "choice_frontier_episode_v1"
ENGINE_ARM = {
    "learned_adapter": "process_sft",
    "pretrained_base": "pretrained_base",
    "random_valid": "random_valid",
    "exact_reference": "exact_reference",
}


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, payload) -> None:
    write_json(path, payload)


def load_protocol() -> dict:
    """Frozen #132 protocol with only the v2 identity and output root replaced."""

    protocol = read_json(ROOT / PROTOCOL_PATH)
    protocol["root"] = str(ROOT)
    protocol["protocol_id"] = "choice-frontier-v2"
    protocol["output_root"] = V2_OUTPUT_ROOT
    protocol["ledger"] = str(LEDGER_PATH.relative_to(ROOT))
    protocol["schedule"] = str(SCHEDULE_PATH)
    return protocol


def output_root(protocol: dict) -> Path:
    return ROOT / protocol["output_root"]


def progress_writer():
    path = Path(os.environ.get("EXPANDED_PROGRESS_PATH", "/tmp/choice-frontier-progress.json"))

    def progress(stage: str, **fields):
        write(path, {"stage": stage, "updated": time.time(), **fields})

    return progress


def membership() -> dict:
    return read_json(ROOT / MEMBERSHIP_PATH)


def load_tasks(protocol: dict) -> list[dict]:
    frozen = membership()
    views = {task["row"]["task_id"]: task for task in read_json(VIEW_REPORT)["tasks"]}
    tasks = []
    for index, panel in enumerate(frozen["tasks"]):
        task_id = panel["row"]["task_id"]
        view = views[task_id]
        if view["outcome"] != "REFERENCE_VIEWS_PASS" or view["row"]["task_path"] != panel["row"]["task_path"]:
            raise ValueError(f"v2 native views differ from the frozen panel task: {task_id}")
        # Choice-contract reference costs (R) come from the frozen membership row.
        tasks.append({**view, "row": panel["row"], "task_index": index})
    if [task["row"]["task_id"] for task in tasks] != frozen["task_ids"]:
        raise ValueError("choice-frontier v2 task loading differs from the frozen membership")
    return tasks


def reference_expansions(task: dict, algorithm: str) -> int:
    return int(task["row"]["reference_costs"][algorithm]["expansions"])


# --------------------------------------------------------------------------- #
# prepare-views: native reference traces + scene-only views (CPU, render backend)
# --------------------------------------------------------------------------- #


def _view_task(item: tuple[dict, dict]) -> dict:
    from examples.planning_benchmark_slice.matched_tasks import exact_reference
    from scripts.prepare_expanded_views import prepare_task

    protocol, panel_row = item
    name = panel_row["task_id"].split("/", 1)[1]
    domain, _stratum, seed = name.rsplit("-", 2)
    candidate = ROOT / protocol["output_root"] / "candidates" / name
    # Native exact references under the expanded-study screening ceilings, then
    # re-bound to the resulting per-instance budgets (expanded_candidates.screen);
    # the views renderer replays them to seed the reference state catalog.
    ceiling = {**panel_row, "reference_costs": {a: {"decisions": 256, "expansions": 128} for a in VIEW_ALGORITHMS}}
    study = {"output_root": protocol["output_root"], "study_id": protocol["study_id"],
             "final": {"max_exact_decisions_per_algorithm": 256}}
    native = {}
    for algorithm in VIEW_ALGORITHMS:
        result = exact_reference(ROOT, ceiling, algorithm, study)["result"]
        native[algorithm] = {"decisions": result["decision_count"], "expansions": result["expansion_count"]}
    for algorithm in ("best_first_add_greedy", "best_first_add_w3"):
        if native[algorithm]["expansions"] != panel_row["reference_costs"][algorithm]["expansions"]:
            raise ValueError(f"native exact expansions differ from choice-contract R: {name} {algorithm}")
    row = {**panel_row, "reference_costs": native}
    for algorithm in VIEW_ALGORITHMS:
        path = candidate / f"reference-{algorithm}.json.gz"
        if not path.exists():
            write(path, exact_reference(ROOT, row, algorithm, study))
    group = {"domain": domain, "stratum": "expanded", "selected": {"seed": int(seed), "row": row}}
    return prepare_task(protocol, group, VIEW_ENDPOINT_INDEX)


def prepare_views_stage(workers: int = 4) -> dict:
    from concurrent.futures import ProcessPoolExecutor

    protocol = {
        "study_id": "choice-frontier-v2-views",
        "output_root": V2_OUTPUT_ROOT,
        "reference": {"algorithms": list(VIEW_ALGORITHMS)},
        "membership_sha256": membership()["membership_sha256"],
    }
    rows = [task["row"] for task in membership()["tasks"]]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        tasks = list(pool.map(_view_task, [(protocol, row) for row in rows]))
    write(VIEW_REPORT, {"protocol": protocol, "tasks": tasks, "complete_live_input_bounds": False,
                        "hardware_qualified": False})
    return {"tasks": len(tasks), "outcomes": sorted({t["outcome"] for t in tasks})}


# --------------------------------------------------------------------------- #
# episodes: identity, runner, replay
# --------------------------------------------------------------------------- #


def _identity(protocol: dict, binding: dict, episode: Path, view_output: Path, checkpoint) -> dict:
    return {
        "schema_version": EPISODE_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "binding_index": binding["index"],
        "worker": binding["worker"],
        "kind": binding["kind"],
        "arm": CHOICE_ARM,
        "task_id": binding["task_id"],
        "algorithm": binding["algorithm"],
        "condition": binding["condition"],
        "seed": binding["seed"],
        "output": str(episode.relative_to(ROOT)),
        "view_output": str(view_output.relative_to(ROOT)),
        "checkpoint": checkpoint,
        "model_id": protocol["model_id"],
        "model_revision": protocol["model_revision"],
        "oracle_assisted_valid_operation_control": binding["condition"] == "random_valid",
    }


def episode_paths(protocol: dict, binding: dict, *, smoke: bool = False) -> tuple[Path, Path, Path]:
    base = output_root(protocol) / ("smoke" if smoke else "evaluation")
    task_name = binding["task_id"].replace("/", "__")
    name = f"{binding['algorithm']}-{binding['condition']}-{binding['seed']}"
    episode = base / "episodes" / task_name / f"{name}.json.gz"
    view_output = base / "views" / task_name / name
    partial = episode.with_name(episode.name + ".partial.json.gz")
    return episode, partial, view_output


def _session_for(protocol: dict, task: dict, binding: dict, views: ChoiceFrontierTaskViews, checkpoint):
    algorithm = binding["algorithm"]
    choice_task = ChoiceFrontierTask(
        instance_id=task["row"]["task_id"],
        pair_id=task["row"]["task_id"],
        domain=task["row"]["domain"],
        algorithm=algorithm,
        exact_expansions=reference_expansions(task, algorithm),
    )
    decision_cap = BASE_MODEL_CALL_CAP if binding["condition"] == "pretrained_base" else None
    return ChoiceFrontierModelSession(
        authority=views.authority,
        task=choice_task,
        arm=ENGINE_ARM[binding["condition"]],
        seed=int(binding["seed"]),
        adapter_id=checkpoint,
        decision_cap=decision_cap,
    )


def _register_admissions(session, views, event) -> None:
    result = event["trusted_runtime_result"]
    if result.get("status") != "expanded":
        return
    expanded_state = session.controller._states_by_ref[result["expanded_state_id"]]
    for admission in result["admissions"]:
        views.register(expanded_state, admission["action"])


def _restore_events(session, views, saved) -> None:
    for event in saved["events"]:
        request = session.next_request()
        if request is None or dict(request.model_input) != event["input"]:
            raise ValueError("partial choice-frontier episode replay input differs")
        if [dict(entry) for entry in request.menu_binding] != event["menu"]:
            raise ValueError("partial choice-frontier episode replay menu differs")
        binding = views.observe_choices(
            dict(request.model_input), session.menu_states(request), pixels=False
        )["binding"]
        if binding != event["view"]:
            raise ValueError("partial choice-frontier episode replay page binding differs")
        session.submit_output(event["raw_output"])
        committed = session.events[-1]
        if committed["trusted_runtime_result"] != event["trusted_runtime_result"]:
            raise ValueError("partial choice-frontier episode replay runtime result differs")
        committed["view"] = binding
        _register_admissions(session, views, committed)


def _commit_pending(session, views, saved) -> None:
    pending = saved.get("pending")
    if pending is None:
        return
    request = session.next_request()
    if request is None or dict(request.model_input) != pending["input"]:
        raise ValueError("persisted pending choice-frontier output no longer matches the request")
    observed = views.observe_choices(dict(request.model_input), session.menu_states(request), pixels=False)[
        "binding"
    ]
    if observed != pending["binding"]:
        raise ValueError("persisted pending choice-frontier output has a different view binding")
    session.submit_output(pending["raw_output"])
    committed = session.events[-1]
    committed["view"] = observed
    _register_admissions(session, views, committed)
    saved["events"].append(committed)
    saved["call_measurements"].append(pending["measurement"])
    saved["pending"] = None
    views.save()


def run_binding(root, protocol, task, binding, checkpoint, endpoint, generate, *, smoke=False):
    from PIL import Image

    episode, partial_path, view_output = episode_paths(protocol, binding, smoke=smoke)
    expected = _identity(protocol, binding, episode, view_output, checkpoint)
    if episode.exists():
        if partial_path.exists():
            raise ValueError("completed choice-frontier episode retains a conflicting partial journal")
        report = read_json(episode)
        if any(report.get(key) != value for key, value in expected.items()):
            raise ValueError("retained choice-frontier episode binding differs")
        independently_replay(root, protocol, task, report, endpoint, smoke=smoke)
        return report, True
    views = ChoiceFrontierTaskViews(root, task, view_output, endpoint)
    session = _session_for(protocol, task, binding, views, checkpoint)
    saved = (
        read_json(partial_path)
        if partial_path.exists()
        else {
            **expected,
            "decision_cap": session.decision_cap,
            "events": [],
            "call_measurements": [],
            "pending": None,
            "started": time.time(),
            "active_wall_seconds": 0.0,
        }
    )
    if any(saved.get(key) != value for key, value in expected.items()):
        raise ValueError("partial choice-frontier episode binding differs")
    attempt_started = time.monotonic()
    _restore_events(session, views, saved)
    _commit_pending(session, views, saved)
    saved["active_wall_seconds"] += time.monotonic() - attempt_started
    write(partial_path, saved)
    checkpoint_started = time.monotonic()

    while (request := session.next_request()) is not None:
        raw = dict(request.model_input)
        example = views.observe_choices(raw, session.menu_states(request), pixels=generate is not None)
        call_started = time.monotonic()
        try:
            if generate is None:
                generated = session.reference_output()
                generated_tokens = None
            else:
                generated, generated_tokens = generate(example)
        finally:
            for image in example["images"]:
                if isinstance(image, Image.Image):
                    image.close()
        measurement = {
            "event_index": len(session.events),
            "model_call": binding["condition"] in {"learned_adapter", "pretrained_base"},
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
        write(partial_path, saved)
        checkpoint_started = time.monotonic()
        _commit_pending(session, views, saved)
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write(partial_path, saved)
        checkpoint_started = time.monotonic()
    report = {
        **expected,
        "decision_cap": session.decision_cap,
        "outcome": "RECORDED",
        "events": saved["events"],
        "result": session.result(),
        "call_measurements": saved["call_measurements"],
        "started": saved["started"],
        "finished": time.time(),
        "active_wall_seconds": saved["active_wall_seconds"] + time.monotonic() - checkpoint_started,
        "raw_invalid_outputs_preserved": sum(
            1 for event in saved["events"] if event["trusted_runtime_result"].get("status") == "rejected"
        ),
    }
    views.save()
    write(episode, report)
    partial_path.unlink()
    return report, False


def independently_replay(root, protocol, task, report, endpoint, *, smoke=False) -> dict:
    _episode, _partial, view_output = episode_paths(
        protocol,
        {
            "index": report["binding_index"],
            "worker": report["worker"],
            "kind": report["kind"],
            "task_id": report["task_id"],
            "algorithm": report["algorithm"],
            "condition": report["condition"],
            "seed": report["seed"],
        },
        smoke=smoke,
    )
    views = ChoiceFrontierTaskViews(root, task, view_output, endpoint, read_only=True)
    binding = {
        "condition": report["condition"],
        "algorithm": report["algorithm"],
        "seed": report["seed"],
    }
    session = _session_for(protocol, task, binding, views, report.get("checkpoint"))
    if session.decision_cap != int(report["decision_cap"]):
        raise ValueError("choice-frontier replay decision cap differs")
    for event in report["events"]:
        request = session.next_request()
        if request is None:
            raise ValueError("choice-frontier replay ended before the stored events")
        if dict(request.model_input) != event["input"]:
            raise ValueError("choice-frontier replay input differs")
        if [dict(entry) for entry in request.menu_binding] != event["menu"]:
            raise ValueError("choice-frontier replay menu binding differs")
        observed = views.observe_choices(dict(request.model_input), session.menu_states(request), pixels=False)[
            "binding"
        ]
        if observed != event["view"]:
            raise ValueError("choice-frontier replay view binding differs")
        session.submit_output(event["raw_output"])
        if session.events[-1]["trusted_runtime_result"] != event["trusted_runtime_result"]:
            raise ValueError("choice-frontier replay trusted runtime result differs")
    if session.next_request() is not None:
        raise ValueError("choice-frontier replay continued past the stored events")
    if not session.complete:
        raise ValueError("choice-frontier replay remained incomplete")
    if session.result() != report["result"]:
        raise ValueError("choice-frontier replay result differs")
    return session.result()


# --------------------------------------------------------------------------- #
# smoke gate
# --------------------------------------------------------------------------- #


def smoke_gate(protocol: dict) -> str | None:
    # The frozen #132 adapter smoke gate (PASS) applies to the same frozen adapters.
    path = V1_ROOT / "smoke" / "smoke.json"
    if not path.is_file():
        return None
    return read_json(path)["gate"]


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #


def bindings(protocol: dict, tasks: list[dict]) -> list[dict]:
    # Models only (CPU controls live in the v2 zoo). Worker 0 = greedy (GPU 0),
    # worker 1 = w3 (GPU 1).
    rows = []
    index = 0
    seeds = protocol["evaluation"]["seeds"]
    for task in tasks:
        for worker, algorithm in enumerate(protocol["learned_algorithms"]):
            for condition in ("learned_adapter", "pretrained_base"):
                rows.append(
                    {
                        "index": index,
                        "worker": worker,
                        "kind": "models",
                        "task_id": task["row"]["task_id"],
                        "algorithm": algorithm,
                        "condition": condition,
                        "seed": int(seeds["learned"][0]),
                    }
                )
                index += 1
    return rows


def evaluate_inputs_stage() -> dict:
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    rows = bindings(protocol, tasks)
    manifest = {
        "schema_version": "choice_frontier_evaluation_inputs_v1",
        "protocol_id": protocol["protocol_id"],
        "bindings": rows,
        "counts": {
            "models": sum(1 for row in rows if row["kind"] == "models"),
            "controls": sum(1 for row in rows if row["kind"] == "controls"),
        },
    }
    if manifest["counts"]["models"] != 4 * len(membership()["task_ids"]) or manifest["counts"]["controls"] != 0:
        raise ValueError("choice-frontier v2 evaluation matrix differs from the frozen protocol")
    write(output_root(protocol) / "evaluation" / "bindings.json", manifest)
    return manifest


def evaluate_worker(worker: int, kind: str, endpoint: str) -> dict:
    protocol = load_protocol()
    tasks = load_tasks(protocol)
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    rows = [row for row in manifest["bindings"] if row["worker"] == worker and row["kind"] == kind]
    expected = sum(1 for row in manifest["bindings"] if row["kind"] == kind) // 2
    if len(rows) != expected:
        raise ValueError("choice-frontier worker partition differs from frozen equal coverage")
    if kind == "models":
        if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
            raise ValueError("choice-frontier model worker requires CUDA_VISIBLE_DEVICES isolation")
        if not os.environ.get("MASTER_PORT"):
            raise ValueError("choice-frontier model worker requires an explicit scheduler MASTER_PORT")
        gate = smoke_gate(protocol)
        if gate is None:
            raise ValueError("choice-frontier evaluation requires the frozen smoke gate")
        if gate == "FAIL":
            result = {
                "schema_version": "choice_frontier_evaluate_worker_v1",
                "worker": worker,
                "kind": kind,
                "gated_out_by_smoke": True,
                "episodes_completed": 0,
            }
            write(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json", result)
            return result
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    completed = 0
    retained = 0
    model_calls = 0
    started = time.monotonic()
    adapters = {}
    policy = None
    if kind == "models":
        adapters = {
            algorithm: str(V1_ROOT / "training" / CHOICE_ARM / algorithm / "final")
            for algorithm in protocol["learned_algorithms"]
        }
        for path in adapters.values():
            if not (ROOT / path / "adapter_model.safetensors").is_file():
                raise ValueError(f"choice-frontier adapter checkpoint missing: {path}")
        pending = [row for row in rows if not episode_paths(protocol, row)[0].exists()]
        if pending:
            from transformers import set_seed

            from examples.planning_benchmark_slice.visual_attention import configure_visual_attention
            from examples.planning_benchmark_slice.visual_model import VisualPolicy

            set_seed(int(protocol["training_seed"]))
            policy = VisualPolicy(
                model_id=protocol["model_id"],
                revision=protocol["model_revision"],
                adapter_paths={key: ROOT / value for key, value in adapters.items()},
                device="cuda:0",
                max_context_tokens=32768,
                max_new_tokens=384,
                max_batch_size=protocol["inference"]["max_batch_size"],
                max_batch_input_tokens=protocol["inference"]["max_padded_batch_input_tokens"],
                inference_dtype=protocol["inference"]["dtype"],
            )
            configure_visual_attention(policy.model, protocol["inference"]["attention"])
            policy.identity.update(memoize_identical_inputs=False)
    reports = []
    for binding in rows:
        condition = binding["condition"]
        checkpoint = adapters.get(binding["algorithm"]) if condition == "learned_adapter" else None

        def generate(example, condition=condition, algorithm=binding["algorithm"]):
            nonlocal model_calls
            adapter = algorithm if condition == "learned_adapter" else None
            output = policy.generate([example], adapter)[0]
            model_calls += 1
            return output, policy.last_generation_usage["generated_sequence_tokens"]

        generate_fn = generate if kind == "models" else None
        report, was_retained = run_binding(
            ROOT,
            protocol,
            task_by_id[binding["task_id"]],
            binding,
            checkpoint,
            endpoint,
            generate_fn,
        )
        retained += int(was_retained)
        reports.append(report["output"])
        completed += 1
        write(
            progress_path,
            {
                "completed": completed,
                "total": len(rows),
                "retained": retained,
                "model_calls": model_calls,
                "worker": worker,
                "kind": kind,
            },
        )
    if policy is not None:
        import torch

        del policy
        torch.cuda.empty_cache()
    result = {
        "schema_version": "choice_frontier_evaluate_worker_v1",
        "protocol_id": protocol["protocol_id"],
        "worker": worker,
        "kind": kind,
        "episodes_completed": completed,
        "episodes_retained": retained,
        "model_calls": model_calls,
        "elapsed_seconds": time.monotonic() - started,
        "outputs": reports,
    }
    write(attempt_dir / "worker-result.json", result)
    return result


def audit_evaluate_worker() -> dict:
    terminal = read_json(Path(os.environ["EXPANDED_TERMINAL_PATH"]))
    result = read_json(Path(os.environ["EXPANDED_ATTEMPT_DIR"]) / "worker-result.json")
    ok = terminal["status"] == "succeeded" and (
        result.get("episodes_completed", 0) > 0 or result.get("gated_out_by_smoke") is True
    )
    return {
        "schema_version": "choice_frontier_evaluate_audit_v1",
        "worker": result.get("worker"),
        "kind": result.get("kind"),
        "ok": ok,
    }


# --------------------------------------------------------------------------- #
# finalize / identity-audit / analyze
# --------------------------------------------------------------------------- #


def _load_episode(protocol: dict, binding: dict) -> dict:
    episode, _partial, _views = episode_paths(protocol, binding)
    return read_json(episode)


def finalize_stage(endpoint: str) -> dict:
    """Independent replay of every episode; complete coverage or explicit missingness."""

    protocol = load_protocol()
    tasks = load_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    manifest = read_json(output_root(protocol) / "evaluation" / "bindings.json")
    gate = smoke_gate(protocol)
    if gate is None:
        raise ValueError("choice-frontier finalize requires the frozen smoke gate")
    replayed = 0
    missing = []
    gated = []
    cells = {}
    for binding in manifest["bindings"]:
        episode, partial, _views = episode_paths(protocol, binding)
        if not episode.exists():
            if binding["kind"] == "models" and gate == "FAIL":
                gated.append(binding["index"])
                continue
            missing.append(binding["index"])
            continue
        if partial.exists():
            raise ValueError("choice-frontier finalize found a partial journal beside a completed episode")
        report = read_json(episode)
        independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], report, endpoint)
        replayed += 1
        key = (binding["task_id"], binding["algorithm"])
        cell = cells.setdefault(key, {})
        if binding["condition"] == "random_valid":
            cell.setdefault("random_valid", {})[str(binding["seed"])] = report["result"]
        else:
            cell[binding["condition"]] = report["result"]
    evaluation = {
        "schema_version": "choice_frontier_evaluation_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": replayed,
        "bindings_total": len(manifest["bindings"]),
        "missing_bindings": missing,
        "gated_out_by_smoke": gated,
        "smoke_gate": gate,
        "complete": not missing,
    }
    write(output_root(protocol) / "evaluation" / "evaluation.json", evaluation)
    serialized = {
        f"{task_id}|{algorithm}": cell
        for (task_id, algorithm), cell in sorted(cells.items())
    }
    write(
        output_root(protocol) / "evaluation" / "cells.json",
        {"schema_version": "choice_frontier_cells_v1", "cells": serialized},
    )
    return evaluation


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["prepare-views", "evaluate-inputs", "evaluate-worker", "audit-evaluate-worker", "finalize"],
    )
    parser.add_argument("--worker", type=int, choices=[0, 1], default=None)
    parser.add_argument("--kind", choices=["models"], default=None)
    parser.add_argument("--workers", type=int, default=4, help="CPU parallelism for prepare-views")
    parser.add_argument("--endpoint", default="http://127.0.0.1:18092")
    args = parser.parse_args(argv)

    if args.stage == "prepare-views":
        result = prepare_views_stage(workers=args.workers)
    elif args.stage == "evaluate-inputs":
        result = evaluate_inputs_stage()
    elif args.stage == "evaluate-worker":
        if args.worker is None or args.kind is None:
            raise ValueError("evaluate-worker requires --worker {0,1} --kind models")
        result = evaluate_worker(args.worker, args.kind, args.endpoint)
    elif args.stage == "audit-evaluate-worker":
        result = audit_evaluate_worker()
    elif args.stage == "finalize":
        result = finalize_stage(args.endpoint)
    else:  # pragma: no cover
        raise ValueError(args.stage)
    print(json.dumps(result, indent=2, sort_keys=True, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
