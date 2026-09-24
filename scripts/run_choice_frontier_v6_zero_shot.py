#!/usr/bin/env python
"""Choice-frontier v6 (#141): a zero-shot base Qwen3-VL-8B chooser through the validated instrument.

Protocol: ``configs/experiments/choice-frontier-v6/protocol.json`` /
``docs/experiments/choice-frontier/issue-141-protocol.md``. The frozen machinery is
imported read-only, never copied or edited: #136 (``run_choice_frontier_v3``: policy
loading, the #135 panel loader, smoke tasks) and #139 (``run_choice_frontier_v4_panels``:
the P2 loader, reference costs and the partial-journal restore/commit helpers). The
session factory, episode runner and replay are local because the arm is a new condition
(``zero_shot_base``: the base model, the frozen observation with one appended system
sentence, a deterministic output extractor, cap 2 x R_t). Every path resolves under
``outputs/choice-frontier/v6``. Stages:

- ``validate`` — frozen pins (model, inference, system-message prefix/sha, panels).
- ``smoke`` / ``audit-smoke`` — the #132 smoke definition on this arm (descriptive).
- ``evaluate-inputs`` / ``evaluate-worker --panel P --algorithm A`` /
  ``audit-evaluate-worker`` — the arm on the #135 panel (v2) and the #139 P2 panel.
- ``finalize`` — independent replay of every evaluation episode (extractor re-applied).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.planning_benchmark_slice.choice_frontier import (  # noqa: E402
    CHOICE_ARM,
    CHOICE_SYSTEM_MESSAGE,
    OUTPUT_KEY,
    ChoiceFrontierModelSession,
    ChoiceFrontierTask,
    canonical_choice,
)
from examples.planning_benchmark_slice.choice_frontier_views import ChoiceFrontierTaskViews  # noqa: E402
from examples.planning_benchmark_slice.scene_assets import read_json  # noqa: E402
from scripts import run_choice_frontier_v3 as v3  # noqa: E402
from scripts import run_choice_frontier_v4_panels as v4p  # noqa: E402

PROTOCOL_PATH = ROOT / "configs/experiments/choice-frontier-v6/protocol.json"
OUT = ROOT / "outputs/choice-frontier/v6"
ALGORITHMS = v3.ALGORITHMS
PANELS = ("v2", "p2")
CONDITION = "zero_shot_base"
ENGINE_ARM = "pretrained_base"  # the session's model-arm label; no adapter, cap overridden to 2 x R_t
INFERENCE_SEED = 17
ENDPOINT = "http://127.0.0.1:18848"
EPISODE_SCHEMA = "choice_frontier_v6_episode_v1"
SYSTEM_SUFFIX = (
    ' Reply with exactly one JSON object and nothing else, of the form {"expand_choice": "<label>"}, '
    "where <label> is one of the frontier_menu choices (c0, c1, ...). Choose the frontier state whose scene "
    "appears closest to satisfying the goal pages."
)
SYSTEM_MESSAGE = CHOICE_SYSTEM_MESSAGE + SYSTEM_SUFFIX
SYSTEM_MESSAGE_SHA256 = "d2ea2b658b2fdb8a0b4c2c8cadd7be612186b56eac4526301634d6e62c919022"
JSON_OBJECT = re.compile(r"\{[^{}]*\}")
BARE_LABEL = re.compile(r"c[0-9]+")
write = v3.write


def load_protocol() -> dict:
    protocol = read_json(PROTOCOL_PATH)
    protocol["root"] = str(ROOT)
    return protocol


def require_gpu_env(stage: str) -> None:
    if os.environ.get("CUDA_VISIBLE_DEVICES") is None:
        raise ValueError(f"choice-frontier {stage} requires CUDA_VISIBLE_DEVICES isolation")
    if not os.environ.get("MASTER_PORT"):
        raise ValueError(f"choice-frontier {stage} requires an explicit scheduler MASTER_PORT")


# --------------------------------------------------------------------------- #
# the arm: prompt and deterministic output extraction
# --------------------------------------------------------------------------- #


def extract_choice(text: str) -> tuple[str, str]:
    """(submitted output, rule): first bare JSON choice object, else a bare label, else the raw text."""

    for match in JSON_OBJECT.finditer(text):
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and set(payload) == {OUTPUT_KEY} and isinstance(payload[OUTPUT_KEY], str):
            return canonical_choice(payload[OUTPUT_KEY]), "json_object"
    stripped = text.strip()
    if BARE_LABEL.fullmatch(stripped):
        return canonical_choice(stripped), "bare_label"
    return text, "raw"


def prompted(example: dict) -> dict:
    """The frozen observation with the v6 system message; images and user content are shared unchanged."""

    system = example["messages"][0]
    if system["role"] != "system" or system["content"] != CHOICE_SYSTEM_MESSAGE:
        raise ValueError("choice-frontier observation lacks the frozen system message")
    return {**example, "messages": [{**system, "content": SYSTEM_MESSAGE}, *example["messages"][1:]]}


# --------------------------------------------------------------------------- #
# panels, bindings and episode paths
# --------------------------------------------------------------------------- #


def panel_protocol(panel: str) -> dict:
    protocol = load_protocol()
    spec = protocol["evaluation"]["panels"][panel]
    return {
        **protocol,
        "protocol_id": f"{protocol['protocol_id']}-{panel}",
        "panel": panel,
        "evaluation": {**protocol["evaluation"], "membership_sha256": spec["membership_sha256"]},
    }


def panel_tasks(protocol: dict) -> list[dict]:
    panel = protocol["panel"]
    if panel == "v2":
        tasks = v3.load_tasks(protocol)
    else:
        if v4p.membership(panel)["membership_sha256"] != protocol["evaluation"]["membership_sha256"]:
            raise ValueError(f"{panel} membership_sha256 differs from the frozen v6 protocol")
        tasks = v4p.load_tasks(protocol)
    if len(tasks) != protocol["evaluation"]["panels"][panel]["tasks"]:
        raise ValueError(f"{panel} task count differs from the frozen v6 protocol")
    return tasks


def stage_root(panel: str | None) -> Path:
    return OUT / "smoke" if panel is None else OUT / "evaluation" / panel


def episode_paths(panel: str | None, binding: dict) -> tuple[Path, Path, Path]:
    base = stage_root(panel)
    task_name = binding["task_id"].replace("/", "__")
    name = f"{binding['algorithm']}-{binding['condition']}-{binding['seed']}"
    episode = base / "episodes" / task_name / f"{name}.json.gz"
    return episode, episode.with_name(episode.name + ".partial.json.gz"), base / "views" / task_name / name


def make_bindings(tasks: list[dict]) -> list[dict]:
    rows = []
    for worker, algorithm in enumerate(ALGORITHMS):
        for task in tasks:
            rows.append({"index": len(rows), "worker": worker, "kind": "models", "task_id": task["row"]["task_id"],
                         "algorithm": algorithm, "condition": CONDITION, "seed": INFERENCE_SEED,
                         "training_seed": None})
    return rows


def new_session(task: dict, algorithm: str, views: ChoiceFrontierTaskViews) -> ChoiceFrontierModelSession:
    choice_task = ChoiceFrontierTask(
        instance_id=task["row"]["task_id"],
        pair_id=task["row"]["task_id"],
        domain=task["row"]["domain"],
        algorithm=algorithm,
        exact_expansions=v4p.reference_expansions(task, algorithm),
    )
    # decision_cap=None: the session's own 2 x R_t binding budget (the relaxed call cap).
    return ChoiceFrontierModelSession(authority=views.authority, task=choice_task, arm=ENGINE_ARM,
                                      seed=INFERENCE_SEED, adapter_id=None, decision_cap=None)


def identity(protocol: dict, panel: str | None, binding: dict, episode: Path, view_output: Path) -> dict:
    return {
        "schema_version": EPISODE_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "panel": panel,
        "binding_index": binding["index"],
        "worker": binding["worker"],
        "kind": binding["kind"],
        "arm": CHOICE_ARM,
        "task_id": binding["task_id"],
        "algorithm": binding["algorithm"],
        "condition": binding["condition"],
        "seed": binding["seed"],
        "training_seed": binding["training_seed"],
        "output": str(episode.relative_to(ROOT)),
        "view_output": str(view_output.relative_to(ROOT)),
        "checkpoint": None,
        "model_id": protocol["model_id"],
        "model_revision": protocol["model_revision"],
        "system_message_sha256": SYSTEM_MESSAGE_SHA256,
        "oracle_assisted_valid_operation_control": False,
    }


# --------------------------------------------------------------------------- #
# episode runner and independent replay
# --------------------------------------------------------------------------- #


def run_binding(protocol, panel, task, binding, endpoint, generate) -> tuple[dict, bool]:
    from PIL import Image

    episode, partial_path, view_output = episode_paths(panel, binding)
    expected = identity(protocol, panel, binding, episode, view_output)
    if episode.exists():
        if partial_path.exists():
            raise ValueError("completed choice-frontier episode retains a conflicting partial journal")
        report = read_json(episode)
        if any(report.get(key) != value for key, value in expected.items()):
            raise ValueError("retained choice-frontier episode binding differs")
        independently_replay(protocol, panel, task, report, endpoint)
        return report, True
    views = ChoiceFrontierTaskViews(ROOT, task, view_output, endpoint)
    session = new_session(task, binding["algorithm"], views)
    saved = read_json(partial_path) if partial_path.exists() else {
        **expected, "decision_cap": session.decision_cap, "events": [], "call_measurements": [], "pending": None,
        "started": time.time(), "active_wall_seconds": 0.0,
    }
    if any(saved.get(key) != value for key, value in expected.items()):
        raise ValueError("partial choice-frontier episode binding differs")
    attempt_started = time.monotonic()
    v4p._restore_events(session, views, saved)
    v4p._commit_pending(session, views, saved)
    saved["active_wall_seconds"] += time.monotonic() - attempt_started
    write(partial_path, saved)
    checkpoint_started = time.monotonic()
    while (request := session.next_request()) is not None:
        raw = dict(request.model_input)
        example = views.observe_choices(raw, session.menu_states(request), pixels=True)
        call_started = time.monotonic()
        try:
            text, generated_tokens, prompt_tokens = generate(prompted(example))
        finally:
            for image in example["images"]:
                if isinstance(image, Image.Image):
                    image.close()
        submitted, rule = extract_choice(text)
        measurement = {
            "event_index": len(session.events),
            "model_call": True,
            "input_tokens": example["binding"]["input_tokens"],
            "prompt_input_tokens": prompt_tokens,
            "generated_sequence_tokens": generated_tokens,
            "call_wall_seconds": time.monotonic() - call_started,
            "model_text": text,
            "extraction_rule": rule,
        }
        saved["pending"] = {"input": raw, "binding": example["binding"], "raw_output": submitted,
                            "measurement": measurement}
        saved["active_wall_seconds"] += time.monotonic() - checkpoint_started
        write(partial_path, saved)
        checkpoint_started = time.monotonic()
        v4p._commit_pending(session, views, saved)
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


def independently_replay(protocol: dict, panel: str | None, task: dict, report: dict, endpoint: str) -> dict:
    binding = {k: report[k] for k in ("task_id", "algorithm", "condition", "seed")}
    _episode, _partial, view_output = episode_paths(panel, binding)
    if report["system_message_sha256"] != SYSTEM_MESSAGE_SHA256 or report["condition"] != CONDITION:
        raise ValueError("choice-frontier v6 episode is not the frozen zero-shot arm")
    if hashlib.sha256(SYSTEM_MESSAGE.encode()).hexdigest() != SYSTEM_MESSAGE_SHA256:
        raise ValueError("v6 system message differs from its frozen sha256")
    views = ChoiceFrontierTaskViews(ROOT, task, view_output, endpoint, read_only=True)
    session = new_session(task, report["algorithm"], views)
    if session.decision_cap != int(report["decision_cap"]):
        raise ValueError("choice-frontier replay decision cap differs")
    measurements = report["call_measurements"]
    if len(measurements) != len(report["events"]):
        raise ValueError("choice-frontier replay call measurements differ from the events")
    for index, (event, measurement) in enumerate(zip(report["events"], measurements, strict=True)):
        if measurement["event_index"] != index or extract_choice(measurement["model_text"]) != (
            event["raw_output"], measurement["extraction_rule"]
        ):
            raise ValueError("choice-frontier replay extractor output differs")
        request = session.next_request()
        if request is None:
            raise ValueError("choice-frontier replay ended before the stored events")
        if dict(request.model_input) != event["input"]:
            raise ValueError("choice-frontier replay input differs")
        if [dict(entry) for entry in request.menu_binding] != event["menu"]:
            raise ValueError("choice-frontier replay menu binding differs")
        observed = views.observe_choices(dict(request.model_input), session.menu_states(request), pixels=False)
        if observed["binding"] != event["view"]:
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


def load_zero_shot_policy(protocol: dict):
    policy = v3.load_policy(protocol, {})
    calls = {"n": 0}

    def generate(example):
        output = policy.generate([example], None)[0]
        calls["n"] += 1
        usage = policy.last_generation_usage
        return output, usage["generated_sequence_tokens"], usage["input_tokens"][0]

    return generate, calls


# --------------------------------------------------------------------------- #
# smoke (descriptive; does not gate the evaluation)
# --------------------------------------------------------------------------- #


def smoke_rows(tasks: list[dict]) -> list[dict]:
    rows = make_bindings(tasks)
    if len(rows) != 6:
        raise ValueError("choice-frontier smoke binding count differs from the #132 definition")
    return rows


def smoke_summary(protocol: dict, reports: list[dict]) -> dict:
    calls = sum(len(r["events"]) for r in reports)
    accepted = sum(len(r["events"]) - r["result"]["invalid_operation_count"] for r in reports)
    rate = accepted / calls if calls else 0.0
    threshold = float(protocol["smoke_gate"]["threshold"])
    return {"model_calls": calls, "accepted_calls": accepted, "schema_valid_grounded_rate": rate,
            "threshold": threshold, "gate": "PASS" if rate >= threshold else "FAIL", "gates_evaluation": False}


def smoke_stage(endpoint: str) -> dict:
    require_gpu_env("smoke")
    protocol = load_protocol()
    if (OUT / "smoke/smoke.json").is_file():
        raise ValueError("choice-frontier v6 smoke already exists; refusing a rerun")
    tasks = v3.smoke_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    generate, _calls = load_zero_shot_policy(protocol)
    reports, episodes = [], []
    for binding in smoke_rows(tasks):
        report, _retained = run_binding(protocol, None, task_by_id[binding["task_id"]], binding, endpoint, generate)
        reports.append(report)
        episodes.append({"task_id": binding["task_id"], "algorithm": binding["algorithm"],
                         "calls": len(report["events"]),
                         "accepted": len(report["events"]) - report["result"]["invalid_operation_count"],
                         "goal_reached": report["result"]["goal_reached"],
                         "termination_reason": report["result"]["termination_reason"],
                         "extraction_rules": [m["extraction_rule"] for m in report["call_measurements"]]})
    result = {"schema_version": "choice_frontier_smoke_v1", "protocol_id": protocol["protocol_id"],
              "condition": CONDITION, "episodes": episodes, **smoke_summary(protocol, reports)}
    write(OUT / "smoke/smoke.json", result)
    attempt_dir = os.environ.get("EXPANDED_ATTEMPT_DIR")
    if attempt_dir:
        write(Path(attempt_dir) / "worker-result.json", {**result, "episodes_completed": len(episodes)})
    return result


def audit_smoke_stage(endpoint: str) -> dict:
    protocol = load_protocol()
    stored = read_json(OUT / "smoke/smoke.json")
    tasks = v3.smoke_tasks(protocol)
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    reports = []
    for binding in smoke_rows(tasks):
        report = read_json(episode_paths(None, binding)[0])
        independently_replay(protocol, None, task_by_id[binding["task_id"]], report, endpoint)
        reports.append(report)
    recomputed = smoke_summary(protocol, reports)
    audit = {"schema_version": "choice_frontier_smoke_audit_v1", "protocol_id": protocol["protocol_id"],
             "episodes_replayed": len(reports), "recomputed": recomputed,
             "matches_stored": all(stored[k] == recomputed[k] for k in recomputed)}
    audit["ok"] = audit["matches_stored"] and len(reports) == 6
    write(OUT / "smoke/audit.json", audit)
    return audit


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #


def evaluate_inputs_stage() -> dict:
    counts = {}
    for panel in PANELS:
        protocol = panel_protocol(panel)
        rows = make_bindings(panel_tasks(protocol))
        write(stage_root(panel) / "bindings.json", {
            "schema_version": "choice_frontier_evaluation_inputs_v1",
            "protocol_id": protocol["protocol_id"],
            "panel": panel,
            "membership_sha256": protocol["evaluation"]["membership_sha256"],
            "condition": CONDITION,
            "system_message_sha256": SYSTEM_MESSAGE_SHA256,
            "bindings": rows,
            "counts": {"models": len(rows)},
        })
        counts[panel] = len(rows)
    if sum(counts.values()) != load_protocol()["evaluation"]["model_episodes"]:
        raise ValueError("choice-frontier v6 evaluation matrix differs from the frozen protocol")
    return counts


def evaluate_worker(panel: str, algorithm: str, endpoint: str) -> dict:
    require_gpu_env("model worker")
    protocol = panel_protocol(panel)
    tasks = panel_tasks(protocol)
    manifest = read_json(stage_root(panel) / "bindings.json")
    rows = [r for r in manifest["bindings"] if r["algorithm"] == algorithm]
    if len(rows) != len(tasks):
        raise ValueError("choice-frontier v6 worker partition differs from frozen coverage")
    attempt_dir = Path(os.environ["EXPANDED_ATTEMPT_DIR"])
    progress_path = Path(os.environ["EXPANDED_PROGRESS_PATH"])
    task_by_id = {task["row"]["task_id"]: task for task in tasks}
    generate = calls = None
    if any(not episode_paths(panel, row)[0].exists() for row in rows):
        generate, calls = load_zero_shot_policy(protocol)
    started = time.monotonic()
    completed = retained = 0
    outputs = []
    for binding in rows:
        report, was_retained = run_binding(protocol, panel, task_by_id[binding["task_id"]], binding, endpoint,
                                           generate)
        retained += int(was_retained)
        completed += 1
        outputs.append(report["output"])
        write(progress_path, {"completed": completed, "total": len(rows), "retained": retained,
                              "model_calls": calls["n"] if calls else 0, "panel": panel, "algorithm": algorithm})
    result = {"schema_version": "choice_frontier_evaluate_worker_v1", "protocol_id": protocol["protocol_id"],
              "panel": panel, "algorithm": algorithm, "condition": CONDITION, "episodes_completed": completed,
              "episodes_retained": retained, "model_calls": calls["n"] if calls else 0,
              "elapsed_seconds": time.monotonic() - started, "outputs": outputs}
    write(attempt_dir / "worker-result.json", result)
    return result


def audit_worker_hook() -> dict:
    """Completion hook: the attempt dir is the terminal path's parent (the #136 fix)."""

    terminal_path = Path(os.environ["EXPANDED_TERMINAL_PATH"])
    terminal = read_json(terminal_path)
    path = terminal_path.parent / "worker-result.json"
    result = read_json(path) if path.is_file() else {}
    ok = terminal["status"] == "succeeded" and result.get("episodes_completed", 0) > 0
    return {"schema_version": "choice_frontier_worker_audit_v1", "panel": result.get("panel"),
            "algorithm": result.get("algorithm"), "ok": ok}


def finalize_stage(endpoint: str) -> dict:
    summary = {}
    for panel in PANELS:
        protocol = panel_protocol(panel)
        task_by_id = {task["row"]["task_id"]: task for task in panel_tasks(protocol)}
        manifest = read_json(stage_root(panel) / "bindings.json")
        replayed = 0
        missing, mismatches, cells = [], [], {}
        for binding in manifest["bindings"]:
            episode, partial, _views = episode_paths(panel, binding)
            if not episode.exists():
                missing.append(binding["index"])
                continue
            if partial.exists():
                mismatches.append({"index": binding["index"], "error": "partial journal beside completed episode"})
                continue
            report = read_json(episode)
            try:
                if any(report.get(k) != binding[k]
                       for k in ("task_id", "algorithm", "condition", "seed", "training_seed")):
                    raise ValueError("episode identity differs from its binding")
                independently_replay(protocol, panel, task_by_id[binding["task_id"]], report, endpoint)
            except ValueError as error:
                mismatches.append({"index": binding["index"], "error": str(error)})
                continue
            replayed += 1
            cells[f"{binding['task_id']}|{binding['algorithm']}|{CONDITION}"] = report["result"]
        evaluation = {"schema_version": "choice_frontier_evaluation_v1", "protocol_id": protocol["protocol_id"],
                      "panel": panel, "episodes_replayed": replayed, "bindings_total": len(manifest["bindings"]),
                      "missing_bindings": missing, "replay_mismatches": mismatches,
                      "complete": not missing and not mismatches}
        write(stage_root(panel) / "evaluation.json", evaluation)
        write(stage_root(panel) / "cells.json", {"schema_version": "choice_frontier_cells_v1",
                                                 "cells": dict(sorted(cells.items()))})
        summary[panel] = {"replayed": replayed, "total": len(manifest["bindings"]), "missing": len(missing),
                          "mismatches": len(mismatches), "complete": evaluation["complete"]}
    return summary


def validate_stage() -> dict:
    protocol = load_protocol()
    v3_protocol = read_json(ROOT / v3.PROTOCOL_PATH)
    checks = {
        "model_pin": (protocol["model_id"], protocol["model_revision"])
        == (v3_protocol["model_id"], v3_protocol["model_revision"]),
        "v3_inference": protocol["inference"] == v3_protocol["inference"],
        "system_message_prefix": SYSTEM_MESSAGE.startswith(CHOICE_SYSTEM_MESSAGE),
        "system_message_sha256": hashlib.sha256(SYSTEM_MESSAGE.encode()).hexdigest() == SYSTEM_MESSAGE_SHA256
        == protocol["arm"]["system_message_sha256"],
        "system_message_protocol": protocol["arm"]["system_message"] == SYSTEM_MESSAGE,
        "panel_memberships": all(
            read_json(ROOT / spec["membership"])["membership_sha256"] == spec["membership_sha256"]
            for spec in protocol["evaluation"]["panels"].values()
        ),
        "panel_tasks": all(len(panel_tasks(panel_protocol(p))) == protocol["evaluation"]["panels"][p]["tasks"]
                           for p in PANELS),
        "smoke_tasks": len(v3.smoke_tasks(protocol)) == 3,
    }
    return {"checks": checks, "ok": all(checks.values())}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["validate", "smoke", "audit-smoke", "evaluate-inputs", "evaluate-worker",
                                          "audit-evaluate-worker", "finalize"])
    parser.add_argument("--panel", choices=PANELS, default=None)
    parser.add_argument("--algorithm", choices=list(ALGORITHMS), default=None)
    parser.add_argument("--endpoint", default=ENDPOINT)
    args = parser.parse_args(argv)
    if args.stage == "validate":
        result = validate_stage()
    elif args.stage == "smoke":
        result = smoke_stage(args.endpoint)
    elif args.stage == "audit-smoke":
        result = audit_smoke_stage(args.endpoint)
    elif args.stage == "evaluate-inputs":
        result = evaluate_inputs_stage()
    elif args.stage == "evaluate-worker":
        if args.panel is None or args.algorithm is None:
            raise ValueError("evaluate-worker requires --panel and --algorithm")
        result = evaluate_worker(args.panel, args.algorithm, args.endpoint)
    elif args.stage == "audit-evaluate-worker":
        result = audit_worker_hook()
    elif args.stage == "finalize":
        result = finalize_stage(args.endpoint)
    else:  # pragma: no cover
        raise ValueError(args.stage)
    print(json.dumps(result, indent=2, sort_keys=True, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
