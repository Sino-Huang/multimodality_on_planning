#!/usr/bin/env python
"""Choice-frontier v5 (#140): one DAgger round for the six #136/#138 adapters.

Protocol: ``configs/experiments/choice-frontier-v5/protocol.json`` /
``docs/experiments/choice-frontier/issue-140-protocol.md``. The frozen machinery is
imported read-only, never copied or edited: #136 (``run_choice_frontier_v3``: the
augmentation, dataset, policy loading, smoke tasks/runner) and #139
(``run_choice_frontier_v4_panels``: panel loading, episode runner and replay).
Every path resolves under ``outputs/choice-frontier/v5``. Stages:

- ``collect --algorithm A --seed S`` (GPU) — roll the base adapter (A, S) out on the
  #136 training tasks in walk order; at every decision with >= 2 menu states record
  the observation and the teacher label (the current frontier heap head).
- ``audit-collect-worker`` — completion hook (attempt dir = terminal path's parent).
- ``audit-collect`` — independent replay of every rollout, teacher labels recomputed.
- ``build-corpus`` — on-policy + replayed #136 records per cell; writes the membership.
- ``train --algorithm A --seed S`` / ``audit-train`` — continue-train the base adapter.
- ``smoke`` / ``audit-smoke`` — the #132 smoke gate on the seed-17 DAgger adapters.
- ``evaluate-inputs`` / ``evaluate-worker --panel P --algorithm A --seed S`` /
  ``audit-evaluate-worker`` — the DAgger adapters on the #135 panel (v2) and P2.
- ``finalize`` — independent replay of every evaluation episode.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.choice_frontier import (  # noqa: E402
    CHOICE_ARM,
    CHOICE_LEGEND,
    CHOICE_RECIPE_ID,
    CHOICE_SCHEMA,
    CHOICE_SYSTEM_MESSAGE,
    OUTPUT_KEY,
    ChoiceFrontierModelSession,
    ChoiceFrontierTask,
)
from examples.planning_benchmark_slice.choice_frontier_views import ChoiceFrontierTaskViews  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402
from scripts import run_choice_frontier_v3 as v3  # noqa: E402
from scripts import run_choice_frontier_v4_panels as v4p  # noqa: E402

PROTOCOL_PATH = ROOT / "configs/experiments/choice-frontier-v5/protocol.json"
CONFIG = ROOT / "configs/experiments/choice-frontier-v5"
MEMBERSHIP = CONFIG / "membership.json"
OUT = ROOT / "outputs/choice-frontier/v5"
V3_OUT = ROOT / "outputs/choice-frontier/v3"
V3_STORE = V3_OUT / "preparation/store.json"
V3_MEMBERSHIP_SHA256 = "f5cc9b2ac3b2fe8e94b7a8039e6b9cd828c701a8c5b707ddd7a3b01b2ca8c077"
CANDIDATE_FILES = (
    ROOT / "configs/experiments/choice-frontier-v2/candidates.json",
    ROOT / "configs/experiments/choice-frontier-v4/candidates.json",
)
ALGORITHMS = v3.ALGORITHMS
SEEDS = (17,)  # Amendment A1: seed 17 only (seeds 29/71 dropped for the 14:21 UTC deadline)
PANELS = ("v2", "p2")
INFERENCE_SEED = 17
MAX_RECORDS_PER_EPISODE = 32
TARGET_RECORDS = 1024
MINIMUM_RECORDS = 512
REPLAY_RECORDS = 1024
# Amendment A1: the first 512 on-policy records + the first 512 draws of the replay sampler.
CORPUS_ON_POLICY_RECORDS = 512
CORPUS_REPLAY_RECORDS = 512
AUGMENTATIONS = v3.AUGMENTATIONS
ENDPOINT = v3.ENDPOINT
COLLECTION_SCHEMA = "choice_frontier_v5_collection_episode_v1"
write = v3.write
canonical = v3.canonical
sha256_text = v3.sha256_text


def load_protocol() -> dict:
    protocol = read_json(PROTOCOL_PATH)
    protocol["root"] = str(ROOT)
    return protocol


def base_adapter(algorithm: str, seed: int) -> str:
    """The #136 (seed 17) or #138 (seeds 29/71) adapter; relative to ROOT."""

    path = v4p.adapter_dir(algorithm, seed)
    if not (path / "adapter_model.safetensors").is_file():
        raise ValueError(f"base adapter missing: {path}")
    return str(path.relative_to(ROOT))


def dagger_adapter(algorithm: str, seed: int) -> str:
    return str((OUT / "training" / algorithm / f"seed-{seed}" / "final").relative_to(ROOT))


def require_gpu_env(stage: str) -> None:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError(f"choice-frontier {stage} requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError(f"choice-frontier {stage} requires an explicit scheduler MASTER_PORT")


# --------------------------------------------------------------------------- #
# rollout universe
# --------------------------------------------------------------------------- #


def candidate_hashes() -> set[str]:
    return {c["problem_sha256"] for path in CANDIDATE_FILES for c in read_json(path)["candidates"]}


def reference_expansions(episode: dict) -> int:
    """R_task: expansions of the uncapped #136 exact-reference derivation episode."""

    if not episode["complete"]:
        raise ValueError(f"#136 derivation episode is incomplete: {episode['task_id']} {episode['algorithm']}")
    return sum(1 for d in episode["decisions"] if d["status"] == "expanded")


def rollout_universe(algorithm: str) -> dict:
    """#136 training tasks in the frozen walk order, with the recorded skips."""

    excluded = candidate_hashes()
    tasks, skips = [], []
    for record in v3.eligible_tasks():
        name = record["task_id"].split("/", 1)[1]
        if record["problem_sha256"] in excluded:
            skips.append({"task_id": record["task_id"], "reason": "candidate_overlap"})
            continue
        derived = V3_OUT / "preparation/episodes" / f"{name}.json.gz"
        view = V3_OUT / "train-views" / name / "result.json"
        if not derived.is_file() or not view.is_file():
            skips.append({"task_id": record["task_id"], "reason": "no_136_views"})
            continue
        view_result = read_json(view)
        episode = read_json(derived)["episodes"].get(algorithm)
        if view_result["outcome"] != "TRAIN_VIEWS_PASS" or episode is None:
            skips.append({"task_id": record["task_id"], "reason": "no_136_views"})
            continue
        r_task = reference_expansions(episode)
        if r_task < 1:
            skips.append({"task_id": record["task_id"], "reason": "zero_reference_expansions"})
            continue
        tasks.append(
            {
                "task_id": record["task_id"],
                "domain": record["domain"],
                "walk_position": record["walk_position"],
                "problem_sha256": record["problem_sha256"],
                "task_path": record["task_path"],
                "reference_expansions": r_task,
                "view_result": str(view.relative_to(ROOT)),
            }
        )
    if any(t["problem_sha256"] in excluded for t in tasks):
        raise AssertionError("a rollout task matches a #135/#139 candidate problem_sha256")
    return {"algorithm": algorithm, "tasks": tasks, "skips": skips}


def view_task(row: dict) -> dict:
    """The frozen #136 train views of a task, bound to its rollout row."""

    result = read_json(ROOT / row["view_result"])
    view_row = dict(result["binding"]["row"])
    if view_row["task_id"] != row["task_id"] or view_row["task_path"] != row["task_path"]:
        raise ValueError(f"#136 train view differs from the training task: {row['task_id']}")
    return {"row": view_row, "native_views": result["native_views"]}


# --------------------------------------------------------------------------- #
# on-policy episodes with teacher labels
# --------------------------------------------------------------------------- #


def new_session(authority, row: dict, algorithm: str, checkpoint: str) -> ChoiceFrontierModelSession:
    task = ChoiceFrontierTask(
        instance_id=row["task_id"], pair_id=row["task_id"], domain=row["domain"], algorithm=algorithm,
        exact_expansions=int(row["reference_expansions"]),
    )
    return ChoiceFrontierModelSession(
        authority=authority, task=task, arm="process_sft", seed=INFERENCE_SEED, adapter_id=checkpoint
    )


def teacher_label(session: ChoiceFrontierModelSession, request) -> tuple[str, str]:
    """Menu label and state ref of the exact heap head of the *current* frontier."""

    head = session.controller.frontier_head_state_id()
    if head is None:
        raise ValueError("choice-frontier frontier has no heap head")
    ref = session.controller._state_ref_by_id[head]
    label = next(entry["choice"] for entry in request.menu_binding if entry["state_ref"] == ref)
    return label, ref


def parsed_choice(raw_output: str) -> str | None:
    try:
        payload = json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(payload, dict) and set(payload) == {OUTPUT_KEY} and isinstance(payload[OUTPUT_KEY], str):
        return payload[OUTPUT_KEY]
    return None


def collection_paths(task_id: str, algorithm: str, seed: int) -> tuple[Path, Path]:
    name = task_id.replace("/", "__")
    episode = OUT / "collection/episodes" / name / f"{algorithm}-s{seed}.json.gz"
    views = OUT / "collection/views" / name / f"{algorithm}-s{seed}"
    return episode, views


def collection_identity(protocol: dict, row: dict, algorithm: str, seed: int, checkpoint: str) -> dict:
    episode, views = collection_paths(row["task_id"], algorithm, seed)
    return {
        "schema_version": COLLECTION_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "arm": CHOICE_ARM,
        "task_id": row["task_id"],
        "walk_position": row["walk_position"],
        "algorithm": algorithm,
        "condition": "learned_adapter",
        "training_seed": seed,
        "seed": INFERENCE_SEED,
        "reference_expansions": row["reference_expansions"],
        "decision_cap": 2 * row["reference_expansions"],
        "checkpoint": checkpoint,
        "output": str(episode.relative_to(ROOT)),
        "view_output": str(views.relative_to(ROOT)),
        "model_id": protocol["model_id"],
        "model_revision": protocol["model_revision"],
    }


def menu_indices_of(binding: dict) -> list[int]:
    return [index for role, index, _page in binding["input_pages"] if role == "frontier-choice"]


def episode_records(report: dict) -> list[dict]:
    """The first 32 decisions with >= 2 menu states, as training records."""

    records = []
    for event, decision in zip(report["events"], report["decisions"], strict=True):
        if len(event["menu"]) < 2:
            continue
        records.append(
            {
                "record_id": (
                    f"dagger:{report['task_id']}:{report['algorithm']}:s{report['training_seed']}:"
                    f"{event['decision_index']}"
                ),
                "task_id": report["task_id"],
                "algorithm": report["algorithm"],
                "training_seed": report["training_seed"],
                "decision_index": event["decision_index"],
                "status": event["trusted_runtime_result"].get("status"),
                "menu": event["menu"],
                "menu_indices": menu_indices_of(event["view"]),
                "menu_size": len(event["menu"]),
                "teacher_choice": decision["teacher_choice"],
                "teacher_state_ref": decision["teacher_state_ref"],
                "model_choice": decision["model_choice"],
                "agree": decision["agree"],
                "input_tokens": event["view"]["input_tokens"],
            }
        )
        if len(records) == MAX_RECORDS_PER_EPISODE:
            break
    return records


def run_collection_episode(protocol, row, algorithm, seed, checkpoint, endpoint, generate) -> tuple[dict, bool]:
    from PIL import Image

    episode_path, view_output = collection_paths(row["task_id"], algorithm, seed)
    expected = collection_identity(protocol, row, algorithm, seed, checkpoint)
    if episode_path.exists():
        report = read_json(episode_path)
        if any(report.get(key) != value for key, value in expected.items()):
            raise ValueError("retained collection episode binding differs")
        replay_collection_episode(report, row, endpoint)
        return report, True
    if view_output.exists():
        # An interrupted episode restarts from scratch; its live views are this run's own output.
        shutil.rmtree(view_output)
    views = ChoiceFrontierTaskViews(ROOT, view_task(row), view_output, endpoint)
    session = new_session(views.authority, row, algorithm, checkpoint)
    task_id = views.row["task_id"]
    decisions, measurements, scenes = [], [], {}
    overflow = None
    started = time.time()
    while (request := session.next_request()) is not None:
        raw = dict(request.model_input)
        try:
            example = views.observe_choices(raw, session.menu_states(request), pixels=True)
        except RuntimeError as error:
            if "OBSERVATION_OVERFLOW" not in str(error):
                raise
            overflow = {"decision_index": request.decision_index, "menu_size": len(request.menu_binding)}
            break
        native = views.scene_views.tasks[task_id]
        for index in [0, *menu_indices_of(example["binding"])]:
            scenes[str(index)] = native["scenes"][str(index)]
        label, ref = teacher_label(session, request)
        call_started = time.monotonic()
        try:
            generated, generated_tokens = generate(example)
        finally:
            for image in example["images"]:
                if isinstance(image, Image.Image):
                    image.close()
        measurements.append(
            {
                "event_index": len(session.events),
                "input_tokens": example["binding"]["input_tokens"],
                "generated_sequence_tokens": generated_tokens,
                "call_wall_seconds": time.monotonic() - call_started,
            }
        )
        session.submit_output(generated)
        event = session.events[-1]
        event["view"] = example["binding"]
        v3._register_admissions(session, views, event)
        choice = parsed_choice(generated)
        decisions.append(
            {
                "decision_index": request.decision_index,
                "teacher_choice": label,
                "teacher_state_ref": ref,
                "model_choice": choice,
                "agree": choice == label,
            }
        )
    native = views.scene_views.tasks[task_id]
    report = {
        **expected,
        "outcome": "RECORDED",
        "events": session.events,
        "decisions": decisions,
        "observation_overflow": overflow,
        "termination_reason": "observation_overflow" if overflow else session.termination_reason,
        "result": session.result() if session.complete else None,
        "pages": {"static_pages": native["static_pages"], "goal_pages": native["goal_pages"], "scenes": scenes},
        "call_measurements": measurements,
        "started": started,
        "finished": time.time(),
    }
    report["records"] = episode_records(report)
    views.save()
    write(episode_path, report)
    return report, False


def replay_collection_episode(report: dict, row: dict, endpoint: str) -> dict:
    """Independent replay: inputs, menus, views, runtime results and recomputed teacher labels."""

    _episode, view_output = collection_paths(report["task_id"], report["algorithm"], report["training_seed"])
    views = ChoiceFrontierTaskViews(ROOT, view_task(row), view_output, endpoint, read_only=True)
    session = new_session(views.authority, row, report["algorithm"], report["checkpoint"])
    if session.decision_cap != int(report["decision_cap"]):
        raise ValueError("collection replay decision cap differs")
    if len(report["events"]) != len(report["decisions"]):
        raise ValueError("collection episode events and decisions differ in length")
    for event, decision in zip(report["events"], report["decisions"], strict=True):
        request = session.next_request()
        if request is None:
            raise ValueError("collection replay ended before the stored events")
        if dict(request.model_input) != event["input"]:
            raise ValueError("collection replay input differs")
        if [dict(entry) for entry in request.menu_binding] != event["menu"]:
            raise ValueError("collection replay menu binding differs")
        observed = views.observe_choices(dict(request.model_input), session.menu_states(request), pixels=False)
        if observed["binding"] != event["view"]:
            raise ValueError("collection replay view binding differs")
        label, ref = teacher_label(session, request)
        if (label, ref) != (decision["teacher_choice"], decision["teacher_state_ref"]):
            raise ValueError("collection replay teacher label differs from the recomputed heap head")
        choice = parsed_choice(event["raw_output"])
        if choice != decision["model_choice"] or (choice == label) != decision["agree"]:
            raise ValueError("collection replay model choice/agreement differs")
        session.submit_output(event["raw_output"])
        if session.events[-1]["trusted_runtime_result"] != event["trusted_runtime_result"]:
            raise ValueError("collection replay trusted runtime result differs")
    if report["observation_overflow"] is not None:
        request = session.next_request()
        if request is None or request.decision_index != report["observation_overflow"]["decision_index"]:
            raise ValueError("collection replay overflow stop differs")
        try:
            views.observe_choices(dict(request.model_input), session.menu_states(request), pixels=False)
        except RuntimeError as error:
            if "OBSERVATION_OVERFLOW" not in str(error):
                raise
        else:
            raise ValueError("collection replay did not overflow at the stored stop")
    else:
        if session.next_request() is not None or not session.complete:
            raise ValueError("collection replay continued past the stored events")
        if session.result() != report["result"] or session.termination_reason != report["termination_reason"]:
            raise ValueError("collection replay result differs")
    if episode_records(report) != report["records"]:
        raise ValueError("collection episode records differ from the frozen record rule")
    return {"events": len(report["events"]), "records": len(report["records"])}


def collect_stage(algorithm: str, seed: int, endpoint: str) -> dict:
    require_gpu_env("collection")
    protocol = load_protocol()
    universe = rollout_universe(algorithm)
    checkpoint = base_adapter(algorithm, seed)
    progress = v3.progress_writer()
    policy = None
    model_calls = 0

    def generate(example):
        nonlocal model_calls
        output = policy.generate([example], algorithm)[0]
        model_calls += 1
        return output, policy.last_generation_usage["generated_sequence_tokens"]

    records = retained = 0
    episodes = []
    started = time.monotonic()
    for row in universe["tasks"]:
        if records >= TARGET_RECORDS:
            break
        episode_path, _views = collection_paths(row["task_id"], algorithm, seed)
        if policy is None and not episode_path.exists():
            policy = v3.load_policy(protocol, {algorithm: checkpoint})
        report, was_retained = run_collection_episode(protocol, row, algorithm, seed, checkpoint, endpoint, generate)
        retained += int(was_retained)
        records += len(report["records"])
        episodes.append(report["output"])
        progress("dagger_collect", completed=min(records, TARGET_RECORDS), total=TARGET_RECORDS,
                 episodes=len(episodes), retained=retained, model_calls=model_calls)
    result = {
        "schema_version": "choice_frontier_v5_collect_worker_v1",
        "protocol_id": protocol["protocol_id"],
        "algorithm": algorithm,
        "training_seed": seed,
        "checkpoint": checkpoint,
        "episodes": len(episodes),
        "episodes_retained": retained,
        "records_available": records,
        "walk_exhausted": records < TARGET_RECORDS,
        "model_calls": model_calls,
        "elapsed_seconds": time.monotonic() - started,
        "outputs": episodes,
    }
    write(OUT / "collection" / f"worker-{algorithm}-s{seed}.json", result)
    attempt_dir = os.environ.get("EXPANDED_ATTEMPT_DIR")
    if attempt_dir:
        write(Path(attempt_dir) / "worker-result.json", result)
    return result


def audit_worker_hook() -> dict:
    """Completion hook: the attempt dir is the terminal path's parent (the #136 fix)."""

    terminal_path = Path(os.environ["EXPANDED_TERMINAL_PATH"])
    terminal = read_json(terminal_path)
    path = terminal_path.parent / "worker-result.json"
    result = read_json(path) if path.is_file() else {}
    ok = terminal["status"] == "succeeded" and (
        result.get("episodes", result.get("episodes_completed", 0)) > 0 or result.get("gated_out_by_smoke") is True
    )
    return {
        "schema_version": "choice_frontier_v5_worker_audit_v1",
        "schema": result.get("schema_version"),
        "algorithm": result.get("algorithm"),
        "training_seed": result.get("training_seed"),
        "panel": result.get("panel"),
        "ok": ok,
    }


def cell_collection(algorithm: str, seed: int) -> tuple[dict, list[tuple[dict, dict]]]:
    """Rollout rows and their stored episodes for one cell, in walk order, up to the stop rule."""

    universe = rollout_universe(algorithm)
    pairs, records = [], 0
    for row in universe["tasks"]:
        if records >= TARGET_RECORDS:
            break
        episode_path, _views = collection_paths(row["task_id"], algorithm, seed)
        if not episode_path.exists():
            break
        report = read_json(episode_path)
        pairs.append((row, report))
        records += len(report["records"])
    return universe, pairs


def audit_collect_stage(endpoint: str) -> dict:
    protocol = load_protocol()
    cells = []
    for algorithm in ALGORITHMS:
        for seed in SEEDS:
            universe, pairs = cell_collection(algorithm, seed)
            mismatches, replayed, records, agree, decisions = [], 0, 0, 0, 0
            for row, report in pairs:
                try:
                    if report["checkpoint"] != base_adapter(algorithm, seed):
                        raise ValueError("collection checkpoint differs from the base adapter")
                    replay_collection_episode(report, row, endpoint)
                except ValueError as error:
                    mismatches.append({"task_id": row["task_id"], "error": str(error)})
                    continue
                replayed += 1
                records += len(report["records"])
                agree += sum(r["agree"] for r in report["records"])
                decisions += len(report["events"])
            walked = len(pairs)
            exhausted = walked == len(universe["tasks"]) and records < TARGET_RECORDS
            complete = records >= TARGET_RECORDS or exhausted
            cells.append(
                {
                    "algorithm": algorithm,
                    "training_seed": seed,
                    "episodes_replayed": replayed,
                    "replay_mismatches": mismatches,
                    "records_available": records,
                    "records_used": min(records, TARGET_RECORDS),
                    "walk_exhausted": exhausted,
                    "decisions": decisions,
                    "agreement_rate_records": agree / records if records else None,
                    "ok": not mismatches and complete and min(records, TARGET_RECORDS) >= MINIMUM_RECORDS,
                }
            )
    audit = {
        "schema_version": "choice_frontier_v5_collection_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "cells": cells,
        "ok": all(c["ok"] for c in cells),
    }
    write(OUT / "collection/audit.json", audit)
    return audit


# --------------------------------------------------------------------------- #
# build-corpus
# --------------------------------------------------------------------------- #


def frozen_136_membership() -> dict:
    membership = read_json(v3.MEMBERSHIP)
    if membership["membership_sha256"] != V3_MEMBERSHIP_SHA256 or v3.membership_sha(membership) != V3_MEMBERSHIP_SHA256:
        raise ValueError("#136 corpus membership_sha256 differs from f5cc9b2a...c077")
    return membership


def replay_sample(frozen_ids: list[str], algorithm: str, seed: int, count: int = REPLAY_RECORDS) -> list[str]:
    """1024 #136 records without replacement: ``random.Random(f"replay:{alg}:{seed}")``."""

    return random.Random(f"replay:{algorithm}:{seed}").sample(list(frozen_ids), count)


def sample_order(on_policy_ids: list[str], replay_ids: list[str], algorithm: str, seed: int) -> list[tuple[str, int]]:
    samples = [(rid, copy) for rid in [*on_policy_ids, *replay_ids] for copy in range(AUGMENTATIONS)]
    random.Random(f"order:dagger:{algorithm}:{seed}").shuffle(samples)
    return samples


def dagger_membership_sha(membership: dict) -> str:
    return sha256_text(
        canonical(
            {
                "cells": {
                    key: {
                        "on_policy_record_ids": cell["on_policy_record_ids"],
                        "replay_record_ids": cell["replay_record_ids"],
                        "samples": cell["samples"],
                    }
                    for key, cell in membership["cells"].items()
                }
            }
        )
    )


def build_corpus_stage() -> dict:
    protocol = load_protocol()
    audit = read_json(OUT / "collection/audit.json")
    if not audit["ok"]:
        raise ValueError("audit-collect has not passed for every cell")
    frozen = frozen_136_membership()
    records, tasks, cells = {}, {}, {}
    for algorithm in ALGORITHMS:
        for seed in SEEDS:
            _universe, pairs = cell_collection(algorithm, seed)
            chosen = []
            used_pairs = []
            for row, report in pairs:
                if len(chosen) == CORPUS_ON_POLICY_RECORDS:
                    break
                used_pairs.append((row, report))
                view_key = f"dagger:{row['task_id']}:{algorithm}:s{seed}"
                tasks[view_key] = {**report["pages"], "episode": report["output"]}
                for record in report["records"]:
                    if len(chosen) == CORPUS_ON_POLICY_RECORDS:
                        break
                    records[record["record_id"]] = {**record, "view_key": view_key, "split": "train"}
                    chosen.append(record["record_id"])
            if len(chosen) < MINIMUM_RECORDS:
                raise ValueError(f"cell {algorithm} s{seed} has fewer than {MINIMUM_RECORDS} on-policy records")
            replay_ids = replay_sample(frozen["training_record_ids"][algorithm], algorithm, seed)[
                :CORPUS_REPLAY_RECORDS
            ]
            used = [records[r] for r in chosen]
            cells[f"{algorithm}-s{seed}"] = {
                "algorithm": algorithm,
                "training_seed": seed,
                "base_adapter": base_adapter(algorithm, seed),
                "on_policy_records": len(chosen),
                "replay_records": len(replay_ids),
                "samples": AUGMENTATIONS * (len(chosen) + len(replay_ids)),
                "optimizer_updates": math.ceil(AUGMENTATIONS * (len(chosen) + len(replay_ids)) / 32),
                "episodes": len(used_pairs),
                "tasks": [row["task_id"] for row, _ in used_pairs],
                "on_policy_agreement_rate": sum(r["agree"] for r in used) / len(used),
                "on_policy_record_ids": chosen,
                "replay_record_ids": replay_ids,
            }
    store = {
        "schema_version": "choice_frontier_v5_store_v1",
        "arm": CHOICE_ARM,
        "recipe_id": CHOICE_RECIPE_ID,
        "tasks": tasks,
        "records": records,
        "counts": {"records": len(records), "episodes": len(tasks)},
    }
    write(OUT / "preparation/store.json", store)
    membership = {
        "schema_version": "choice_frontier_v5_membership_v1",
        "protocol": str(PROTOCOL_PATH.relative_to(ROOT)),
        "frozen_136_membership_sha256": V3_MEMBERSHIP_SHA256,
        "record_rule": protocol["collection"]["record_rule"],
        "stop_rule": protocol["collection"]["stop_rule"],
        "replay_sampler": protocol["corpus"]["replay_sampler"],
        "sample_order": protocol["corpus"]["sample_order"],
        "augmentations": AUGMENTATIONS,
        "store": str((OUT / "preparation/store.json").relative_to(ROOT)),
        "store_sha256": v3.sha256_file(OUT / "preparation/store.json"),
        "cells": cells,
    }
    membership["membership_sha256"] = dagger_membership_sha(membership)
    write(MEMBERSHIP, membership)
    return {
        "membership_sha256": membership["membership_sha256"],
        "cells": {k: {x: c[x] for x in ("on_policy_records", "samples", "episodes", "on_policy_agreement_rate")}
                  for k, c in cells.items()},
    }


def frozen_dagger_membership() -> dict:
    membership = read_json(MEMBERSHIP)
    if dagger_membership_sha(membership) != membership["membership_sha256"]:
        raise ValueError("choice-frontier v5 membership sha differs")
    return membership


# --------------------------------------------------------------------------- #
# train / audit-train (continue training the base adapter)
# --------------------------------------------------------------------------- #


class DaggerDataset(v3.AugmentedChoiceDataset):
    """On-policy + replayed #136 records under the #136 augmentation and example builder."""

    def __init__(self, store5: dict, store3: dict, membership: dict, algorithm: str, seed: int, split: str):
        cell = membership["cells"][f"{algorithm}-s{seed}"]
        records = {rid: {**store5["records"][rid], "task_id": store5["records"][rid]["view_key"]}
                   for rid in cell["on_policy_record_ids"]}
        tasks = {key: store5["tasks"][key] for key in {r["task_id"] for r in records.values()}}
        if split == "train":
            replay = {rid: store3["records"][rid] for rid in cell["replay_record_ids"]}
            self.samples = sample_order(cell["on_policy_record_ids"], cell["replay_record_ids"], algorithm, seed)
        else:
            diagnostic = frozen_136_membership()["diagnostic_record_ids"][algorithm]
            replay = {rid: store3["records"][rid] for rid in diagnostic}
            self.samples = [(rid, None) for rid in diagnostic]
        for record in replay.values():
            tasks[record["task_id"]] = store3["tasks"][record["task_id"]]
        self.store = {"records": {**records, **replay}, "tasks": tasks}
        for rid, _copy in self.samples:
            if rid not in self.store["records"]:
                raise ValueError("choice-frontier v5 dataset record lacks a frozen binding")
        self.records = [{"record_id": f"{rid}#aug{copy}" if copy is not None else rid} for rid, copy in self.samples]


def cell_dir(algorithm: str, seed: int) -> Path:
    return OUT / "training" / algorithm / f"seed-{seed}"


def train_stage(algorithm: str, seed: int) -> dict:
    require_gpu_env("training")
    protocol = load_protocol()
    if algorithm not in protocol["learned_algorithms"] or seed not in protocol["training_seeds"]:
        raise ValueError("choice-frontier v5 cell is not in the frozen protocol")
    training = protocol["training"]
    membership = frozen_dagger_membership()
    cell = membership["cells"][f"{algorithm}-s{seed}"]
    store5 = read_json(OUT / "preparation/store.json")
    if v3.sha256_file(OUT / "preparation/store.json") != membership["store_sha256"]:
        raise ValueError("choice-frontier v5 store sha differs from the membership")
    store3 = read_json(V3_STORE)
    base = base_adapter(algorithm, seed)
    if cell["base_adapter"] != base:
        raise ValueError("membership base adapter differs")
    progress = v3.progress_writer()

    def factory(root, config, algo, split):
        return DaggerDataset(store5, store3, membership, algo, seed, split)

    from examples.planning_benchmark_slice.visual_model import train_visual

    study = read_json(ROOT / training["study"])
    if v3.sha256_file(ROOT / training["study"]) != training["study_sha256"]:
        raise ValueError("study-v5 sha differs")
    if (study["model_id"], study["model_revision"]) != (protocol["model_id"], protocol["model_revision"]):
        raise ValueError("study-v5 backbone differs from the frozen protocol")
    config = {**study, "modality": CHOICE_ARM, "training_seed": int(seed)}
    output = cell_dir(algorithm, seed)
    deadline = time.monotonic() + float(training["max_seconds_per_cell"])
    started = time.monotonic()
    result = train_visual(
        config, ROOT, algorithm, output, deadline=deadline, progress=progress, dataset_factory=factory,
        init_adapter=str(ROOT / base),
    )
    result["arm"] = CHOICE_ARM
    result["train_samples"] = result.pop("train_records")
    result["training_record_ids"] = [*result["training_record_ids"][:8], "..."]
    summary = {
        "schema_version": "choice_frontier_v5_training_v1",
        "protocol_id": protocol["protocol_id"],
        "arm": CHOICE_ARM,
        "algorithm": algorithm,
        "seed": seed,
        "loaded_from": base,
        "sample_order_seed": f"order:dagger:{algorithm}:{seed}",
        "membership_sha256": membership["membership_sha256"],
        "cell": result,
        "wall_seconds": time.monotonic() - started,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "master_port": os.environ.get("MASTER_PORT"),
        "outcome": "PASS",
    }
    write(output / "report.json", summary)
    return summary


def audit_cell(membership: dict, algorithm: str, seed: int) -> dict:
    output = cell_dir(algorithm, seed)
    report_path = output / "report.json"
    if not report_path.is_file():
        return {"algorithm": algorithm, "seed": seed, "ok": False, "reason": "report missing"}
    report = read_json(report_path)
    cell = report["cell"]
    config_file = output / "final/adapter_config.json"
    adapter_config = read_json(config_file) if config_file.is_file() else {}
    expected = membership["cells"][f"{algorithm}-s{seed}"]
    checks = {
        "adapter_present": (output / "final/adapter_model.safetensors").is_file(),
        "loaded_from_base": report.get("loaded_from") == base_adapter(algorithm, seed) == expected["base_adapter"],
        "r_64": adapter_config.get("r") == 64,
        "alpha_128": adapter_config.get("lora_alpha") == 128,
        "dropout_0_05": adapter_config.get("lora_dropout") == 0.05,
        "steps": cell["steps"] == math.ceil(expected["samples"] / 32) == expected["optimizer_updates"],
        "a1_steps_64_samples_2048": cell["steps"] == 64 and cell["train_samples"] == 2048,
        "seed": cell["seed"] == seed == report["seed"],
        "samples": cell["train_samples"] == expected["samples"],
        "membership_sha": report.get("membership_sha256") == membership["membership_sha256"],
    }
    return {"algorithm": algorithm, "seed": seed, "checks": checks, "ok": all(checks.values())}


def audit_train_stage(algorithm: str | None = None, seed: int | None = None) -> dict:
    protocol = load_protocol()
    membership = frozen_dagger_membership()
    cells = [
        audit_cell(membership, a, s)
        for a in ALGORITHMS
        for s in SEEDS
        if (algorithm is None or a == algorithm) and (seed is None or s == seed)
    ]
    audit = {
        "schema_version": "choice_frontier_v5_train_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "cells": cells,
        "ok": bool(cells) and all(c["ok"] for c in cells),
    }
    name = "audit.json" if algorithm is None else f"audit-{algorithm}-s{seed}.json"
    write(OUT / "training" / name, audit)
    return audit


# --------------------------------------------------------------------------- #
# smoke gate (the #132 definition on the seed-17 DAgger adapters)
# --------------------------------------------------------------------------- #


def smoke_gate() -> str | None:
    path = OUT / "smoke/smoke.json"
    return read_json(path)["gate"] if path.is_file() else None


def smoke_stage(endpoint: str) -> dict:
    require_gpu_env("smoke")
    protocol = load_protocol()
    if smoke_gate() is not None:
        raise ValueError("choice-frontier smoke gate already exists; refusing an outcome-selected rerun")
    tasks = v3.smoke_tasks(protocol)
    rows = v3.smoke_bindings(protocol, tasks)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    training_seed = int(protocol["smoke_gate"]["training_seed"])
    adapters = {a: v3.adapter_path(protocol, a, training_seed) for a in protocol["learned_algorithms"]}
    if any(adapters[a] != dagger_adapter(a, training_seed) for a in adapters):
        raise ValueError("smoke adapters are not the v5 DAgger adapters")
    policy = v3.load_policy(protocol, adapters)
    model_calls = accepted_calls = 0
    episodes = []
    progress = v3.progress_writer()
    for position, binding in enumerate(rows):

        def generate(example, algorithm=binding["algorithm"]):
            nonlocal model_calls
            output = policy.generate([example], algorithm)[0]
            model_calls += 1
            return output, policy.last_generation_usage["generated_sequence_tokens"]

        report, _retained = v3.run_binding(
            ROOT, protocol, task_by_id[binding["task_id"]], binding, adapters[binding["algorithm"]], endpoint,
            generate, smoke=True,
        )
        calls = len(report["events"])
        invalid = report["result"]["invalid_operation_count"]
        accepted_calls += calls - invalid
        episodes.append(
            {
                "task_id": binding["task_id"],
                "algorithm": binding["algorithm"],
                "training_seed": training_seed,
                "calls": calls,
                "accepted": calls - invalid,
                "goal_reached": report["result"]["goal_reached"],
                "termination_reason": report["result"]["termination_reason"],
            }
        )
        progress("choice_smoke", completed=position + 1, total=len(rows))
    rate = accepted_calls / model_calls if model_calls else 0.0
    threshold = float(protocol["smoke_gate"]["threshold"])
    result = {
        "schema_version": "choice_frontier_smoke_v1",
        "protocol_id": protocol["protocol_id"],
        "training_seed": training_seed,
        "adapters": adapters,
        "episodes": episodes,
        "model_calls": model_calls,
        "accepted_calls": accepted_calls,
        "schema_valid_grounded_rate": rate,
        "threshold": threshold,
        "gate": "PASS" if rate >= threshold else "FAIL",
    }
    write(OUT / "smoke/smoke.json", result)
    attempt_dir = os.environ.get("EXPANDED_ATTEMPT_DIR")
    if attempt_dir:
        write(Path(attempt_dir) / "worker-result.json", {**result, "episodes_completed": len(episodes)})
    return result


def audit_smoke_stage(endpoint: str) -> dict:
    protocol = load_protocol()
    report = read_json(OUT / "smoke/smoke.json")
    tasks = v3.smoke_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    replayed = accepted_calls = model_calls = 0
    for binding in v3.smoke_bindings(protocol, tasks):
        episode, _partial, _views = v3.episode_paths(protocol, binding, smoke=True)
        stored = read_json(episode)
        if stored["checkpoint"] != dagger_adapter(binding["algorithm"], 17):
            raise ValueError("smoke episode checkpoint is not the seed-17 DAgger adapter")
        v3.independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], stored, endpoint, smoke=True)
        replayed += 1
        model_calls += len(stored["events"])
        accepted_calls += len(stored["events"]) - stored["result"]["invalid_operation_count"]
    rate = accepted_calls / model_calls if model_calls else 0.0
    threshold = float(protocol["smoke_gate"]["threshold"])
    gate = "PASS" if rate >= threshold else "FAIL"
    audit = {
        "schema_version": "choice_frontier_smoke_audit_v1",
        "protocol_id": protocol["protocol_id"],
        "episodes_replayed": replayed,
        "recomputed_rate": rate,
        "stored_rate": report["schema_valid_grounded_rate"],
        "gate": gate,
        "matches_stored": report["gate"] == gate and abs(rate - report["schema_valid_grounded_rate"]) < 1e-9,
    }
    audit["ok"] = audit["matches_stored"] and replayed == int(protocol["smoke_gate"]["episodes"])
    write(OUT / "smoke/audit.json", audit)
    return audit


# --------------------------------------------------------------------------- #
# evaluation on the #135 panel (v2) and the #139 P2 panel
# --------------------------------------------------------------------------- #


def panel_protocol(panel: str) -> dict:
    protocol = load_protocol()
    spec = protocol["evaluation"]["panels"][panel]
    return {
        **protocol,
        "protocol_id": f"{protocol['protocol_id']}-{panel}",
        "panel": panel,
        "output_root": spec["output"],
        "evaluation": {**protocol["evaluation"], "membership_sha256": spec["membership_sha256"]},
    }


def panel_tasks(protocol: dict) -> list[dict]:
    panel = protocol["panel"]
    if panel == "v2":
        return v3.load_tasks(protocol)
    if v4p.membership(panel)["membership_sha256"] != protocol["evaluation"]["membership_sha256"]:
        raise ValueError(f"{panel} membership_sha256 differs from the frozen v5 protocol")
    return v4p.load_tasks(protocol)


def evaluation_bindings(tasks: list[dict]) -> list[dict]:
    rows = []
    for worker, algorithm in enumerate(ALGORITHMS):
        for seed in SEEDS:
            for task in tasks:
                rows.append(
                    {
                        "index": len(rows),
                        "worker": worker,
                        "kind": "models",
                        "task_id": task["row"]["task_id"],
                        "algorithm": algorithm,
                        "condition": "learned_adapter",
                        "seed": INFERENCE_SEED,
                        "training_seed": seed,
                    }
                )
    return rows


def evaluate_inputs_stage() -> dict:
    counts = {}
    for panel in PANELS:
        protocol = panel_protocol(panel)
        tasks = panel_tasks(protocol)
        if len(tasks) != protocol["evaluation"]["panels"][panel]["tasks"]:
            raise ValueError(f"{panel} task count differs from the frozen protocol")
        rows = evaluation_bindings(tasks)
        manifest = {
            "schema_version": "choice_frontier_evaluation_inputs_v1",
            "protocol_id": protocol["protocol_id"],
            "panel": panel,
            "membership_sha256": protocol["evaluation"]["membership_sha256"],
            "adapters": {f"{a}-s{s}": dagger_adapter(a, s) for a in ALGORITHMS for s in SEEDS},
            "bindings": rows,
            "counts": {"models": len(rows)},
        }
        write(ROOT / protocol["output_root"] / "evaluation/bindings.json", manifest)
        counts[panel] = len(rows)
    return counts


def evaluate_worker(panel: str, algorithm: str, seed: int, endpoint: str) -> dict:
    require_gpu_env("model worker")
    protocol = panel_protocol(panel)
    tasks = panel_tasks(protocol)
    manifest = read_json(ROOT / protocol["output_root"] / "evaluation/bindings.json")
    rows = [r for r in manifest["bindings"] if r["algorithm"] == algorithm and r["training_seed"] == seed]
    if len(rows) != len(tasks):
        raise ValueError("choice-frontier v5 worker partition differs from frozen coverage")
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    gate = smoke_gate()
    if gate is None:
        raise ValueError("choice-frontier evaluation requires the frozen smoke gate")
    if gate == "FAIL":
        result = {"schema_version": "choice_frontier_evaluate_worker_v1", "gated_out_by_smoke": True,
                  "episodes_completed": 0, "panel": panel, "algorithm": algorithm, "training_seed": seed}
        write(attempt_dir / "worker-result.json", result)
        return result
    audit = read_json(OUT / "training" / f"audit-{algorithm}-s{seed}.json")
    if not audit["ok"]:
        raise ValueError("DAgger adapter did not pass audit-train")
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    checkpoint = dagger_adapter(algorithm, seed)
    if checkpoint != manifest["adapters"][f"{algorithm}-s{seed}"]:
        raise ValueError("evaluation adapter differs from the bindings manifest")
    policy = None
    if any(not v4p.episode_paths(protocol, row)[0].exists() for row in rows):
        policy = v3.load_policy(protocol, {algorithm: checkpoint})
    completed = retained = model_calls = 0
    started = time.monotonic()
    reports = []
    for binding in rows:

        def generate(example):
            nonlocal model_calls
            output = policy.generate([example], algorithm)[0]
            model_calls += 1
            return output, policy.last_generation_usage["generated_sequence_tokens"]

        report, was_retained = v4p.run_binding(
            ROOT, protocol, task_by_id[binding["task_id"]], binding, checkpoint, endpoint, generate
        )
        retained += int(was_retained)
        reports.append(report["output"])
        completed += 1
        write(progress_path, {"completed": completed, "total": len(rows), "retained": retained,
                              "model_calls": model_calls, "panel": panel, "algorithm": algorithm,
                              "training_seed": seed})
    result = {
        "schema_version": "choice_frontier_evaluate_worker_v1",
        "protocol_id": protocol["protocol_id"],
        "panel": panel,
        "algorithm": algorithm,
        "training_seed": seed,
        "episodes_completed": completed,
        "episodes_retained": retained,
        "model_calls": model_calls,
        "elapsed_seconds": time.monotonic() - started,
        "outputs": reports,
    }
    write(attempt_dir / "worker-result.json", result)
    return result


def finalize_stage(endpoint: str) -> dict:
    """Independent replay of every v5 evaluation episode; complete coverage or explicit missingness."""

    gate = smoke_gate()
    if gate is None:
        raise ValueError("choice-frontier finalize requires the frozen smoke gate")
    summary = {}
    for panel in PANELS:
        protocol = panel_protocol(panel)
        tasks = panel_tasks(protocol)
        task_by_id = {task["row"]["task_id"]: task for task in tasks}
        root = ROOT / protocol["output_root"] / "evaluation"
        manifest = read_json(root / "bindings.json")
        replayed = 0
        missing, mismatches, gated = [], [], []
        cells = {}
        for binding in manifest["bindings"]:
            episode, partial, _views = v4p.episode_paths(protocol, binding)
            if not episode.exists():
                (gated if gate == "FAIL" else missing).append(binding["index"])
                continue
            if partial.exists():
                mismatches.append({"index": binding["index"], "error": "partial journal beside completed episode"})
                continue
            report = read_json(episode)
            try:
                if any(report.get(k) != binding[k]
                       for k in ("task_id", "algorithm", "condition", "seed", "training_seed")):
                    raise ValueError("episode identity differs from its binding")
                if report["checkpoint"] != dagger_adapter(binding["algorithm"], binding["training_seed"]):
                    raise ValueError("episode checkpoint is not the DAgger adapter")
                v4p.independently_replay(ROOT, protocol, task_by_id[binding["task_id"]], report, endpoint)
            except ValueError as error:
                mismatches.append({"index": binding["index"], "error": str(error)})
                continue
            replayed += 1
            cells[f"{binding['task_id']}|{binding['algorithm']}|s{binding['training_seed']}"] = report["result"]
        evaluation = {
            "schema_version": "choice_frontier_evaluation_v1",
            "protocol_id": protocol["protocol_id"],
            "panel": panel,
            "episodes_replayed": replayed,
            "bindings_total": len(manifest["bindings"]),
            "missing_bindings": missing,
            "replay_mismatches": mismatches,
            "gated_out_by_smoke": gated,
            "smoke_gate": gate,
            "complete": not missing and not mismatches,
        }
        write(root / "evaluation.json", evaluation)
        write(root / "cells.json", {"schema_version": "choice_frontier_cells_v1", "cells": dict(sorted(cells.items()))})
        summary[panel] = {k: evaluation[k] for k in ("episodes_replayed", "bindings_total", "complete")}
        summary[panel]["missing"] = len(missing)
        summary[panel]["mismatches"] = len(mismatches)
    return summary


def validate_stage() -> dict:
    protocol = load_protocol()
    arm = read_json(ROOT / "configs/experiments/choice-frontier-v4/seeds-protocol.json")["arms"][CHOICE_ARM]
    checks = {
        "recipe_id": arm["recipe_id"] == CHOICE_RECIPE_ID,
        "schema": arm["schema"] == CHOICE_SCHEMA,
        "legend": arm["legend"] == CHOICE_LEGEND,
        "system_message": arm["system_message"] == CHOICE_SYSTEM_MESSAGE,
        "model_pin": read_json(v3.V1_PROTOCOL)["model_revision"] == protocol["model_revision"],
        "v3_inference": read_json(ROOT / v3.PROTOCOL_PATH)["inference"] == protocol["inference"],
        "frozen_136_membership": frozen_136_membership()["membership_sha256"] == V3_MEMBERSHIP_SHA256,
        "base_adapters_present": all(base_adapter(a, s) for a in ALGORITHMS for s in SEEDS),
        "panel_memberships": all(
            read_json(ROOT / spec["membership"])["membership_sha256"] == spec["membership_sha256"]
            for spec in protocol["evaluation"]["panels"].values()
        ),
    }
    universes = {a: rollout_universe(a) for a in ALGORITHMS}
    return {
        "checks": checks,
        "ok": all(checks.values()),
        "rollout_tasks": {a: len(u["tasks"]) for a, u in universes.items()},
        "skips": {a: {r: sum(s["reason"] == r for s in u["skips"]) for r in {s["reason"] for s in u["skips"]}}
                  for a, u in universes.items()},
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=[
            "validate",
            "collect",
            "audit-collect-worker",
            "audit-collect",
            "build-corpus",
            "train",
            "audit-train",
            "smoke",
            "audit-smoke",
            "evaluate-inputs",
            "evaluate-worker",
            "audit-evaluate-worker",
            "finalize",
        ],
    )
    parser.add_argument("--algorithm", choices=list(ALGORITHMS), default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--panel", choices=PANELS, default=None)
    parser.add_argument("--endpoint", default=ENDPOINT)
    args = parser.parse_args(argv)
    needs_cell = {"collect", "train", "evaluate-worker"}
    if args.stage in needs_cell and (args.algorithm is None or args.seed is None):
        raise ValueError(f"{args.stage} requires --algorithm and --seed")

    if args.stage == "validate":
        result = validate_stage()
    elif args.stage == "collect":
        result = collect_stage(args.algorithm, args.seed, args.endpoint)
    elif args.stage in ("audit-collect-worker", "audit-evaluate-worker"):
        result = audit_worker_hook()
    elif args.stage == "audit-collect":
        result = audit_collect_stage(args.endpoint)
    elif args.stage == "build-corpus":
        result = build_corpus_stage()
    elif args.stage == "train":
        result = train_stage(args.algorithm, args.seed)
    elif args.stage == "audit-train":
        result = audit_train_stage(args.algorithm, args.seed)
    elif args.stage == "smoke":
        result = smoke_stage(args.endpoint)
    elif args.stage == "audit-smoke":
        result = audit_smoke_stage(args.endpoint)
    elif args.stage == "evaluate-inputs":
        result = evaluate_inputs_stage()
    elif args.stage == "evaluate-worker":
        if args.panel is None:
            raise ValueError("evaluate-worker requires --panel")
        result = evaluate_worker(args.panel, args.algorithm, args.seed, args.endpoint)
    elif args.stage == "finalize":
        result = finalize_stage(args.endpoint)
    else:  # pragma: no cover
        raise ValueError(args.stage)
    print(json.dumps(result, indent=2, sort_keys=True, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
