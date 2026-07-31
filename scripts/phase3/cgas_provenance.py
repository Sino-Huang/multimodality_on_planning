from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Final, Mapping, Sequence

from .cgas_bfs import ALGORITHM as BFS_ALGORITHM
from .cgas_bfs import TIE_BREAK, run_fifo_bfs
from .local_iw import run_iterated_width
from .local_planner_types import LocalPlannerRequest
from .pddl import PDDLTask, ground_actions, parse_task, replay_plan
from .cgas_serialization import ProvenanceError, canonical as _canonical, corpus_digest as _corpus_digest, digest as _digest, digest_text as _digest_text, read_json as _read_json, read_jsonl as _read_jsonl, stable_row_id as _stable_row_id, write_json as _write_json, write_jsonl as _write_jsonl

SPLITS: Final = ("train", "dev", "test")
DEFAULT_LIMITS: Final = {"max_expansions": 10000, "max_plan_length": 128, "max_trace_steps": 10000, "max_grounded_actions": 100000, "max_grounded_atoms": 100000, "gbfs_max_depth": 128, "gbfs_max_expansions": 10000, "local_iw_width": 1, "local_iw_max_width": 1, "local_iw_novelty_max_expansions": 10000, "local_max_applicable_actions": 2000}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish or verify Blocksworld CGAS P0 planner provenance.")
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("data/planning_cgas_v1"))
    parser.add_argument("--verify", action="store_true")
    return parser


def build_corpus(source_manifest: Path, output_root: Path) -> dict[str, int | list[dict[str, str]] | dict[str, dict[str, int]]]:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.candidate-", dir=output_root.parent))
    try:
        _write_jsonl(candidate / "source_manifest.jsonl", _snapshot_sources(_read_jsonl(source_manifest), source_manifest, candidate))
        rows, manifest = _regenerate(candidate / "source_manifest.jsonl")
        _write_rows(candidate, rows)
        _write_json(candidate / "manifest.json", manifest)
        _write_json(candidate / "approved.json", {"corpus_digest": _corpus_digest(candidate, SPLITS)})
        report = verify_corpus(candidate, withdraw=False)
        if report["errors"]:
            raise ProvenanceError("candidate_verification_failed")
        _publish(candidate, output_root)
        return report
    except (OSError, ProvenanceError, json.JSONDecodeError):
        shutil.rmtree(candidate, ignore_errors=True)
        raise


def verify_corpus(output_root: Path, *, withdraw: bool = True) -> dict[str, int | list[dict[str, str]] | dict[str, dict[str, int]]]:
    errors: list[dict[str, str]] = []
    try:
        expected_rows, expected_manifest = _regenerate(output_root / "source_manifest.jsonl")
        actual_manifest = _read_json(output_root / "manifest.json")
        if _canonical(actual_manifest) != _canonical(expected_manifest):
            errors.append(_rejection("manifest", "manifest_partition_mismatch"))
        approval = _read_json(output_root / "approved.json")
        if approval.get("corpus_digest") != _corpus_digest(output_root, SPLITS):
            errors.append(_rejection("approval", "approval_digest_mismatch"))
        for split in SPLITS:
            actual = _read_jsonl(output_root / "source" / f"{split}.jsonl")
            expected = expected_rows[split]
            if _canonical(actual) != _canonical(expected):
                errors.append(_rejection(split, "recomputed_row_mismatch"))
    except (OSError, ProvenanceError, json.JSONDecodeError):
        errors.append(_rejection("corpus", "missing_authoritative_provenance"))
    errors.sort(key=lambda item: (item["record_id"], item["reason"]))
    if errors and withdraw:
        _withdraw(output_root)
    counts = {split: {BFS_ALGORITHM: 0, "iterated_width": 0} for split in SPLITS}
    if not errors:
        for split, rows in expected_rows.items():
            for row in rows:
                planner = row["planner"]
                if not isinstance(planner, dict):
                    raise ProvenanceError("invalid_planner")
                counts[split][str(planner["algorithm"])] += 1
    accepted = 0 if errors else sum(sum(by_algorithm.values()) for by_algorithm in counts.values())
    return {"accepted_rows": accepted, "counts": counts, "errors": errors, "rejections": errors}


def _regenerate(source_manifest: Path) -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    instances = _read_jsonl(source_manifest)
    if not instances:
        raise ProvenanceError("empty_source_manifest")
    rows = {split: [] for split in SPLITS}
    ood_members: list[dict[str, object]] = []
    manifest_digest = _digest(source_manifest)
    memberships: dict[str, set[str]] = {split: set() for split in (*SPLITS, "structural_ood", "calibration")}
    seen_ids: set[str] = set()
    for instance in sorted(instances, key=lambda value: _text(value, "instance_id")):
        instance_id = _text(instance, "instance_id")
        if instance_id in seen_ids:
            raise ProvenanceError("duplicate_instance_id")
        seen_ids.add(instance_id)
        if _text(instance, "domain") != "blocksworld":
            raise ProvenanceError("source_domain_mismatch")
        split = _text(instance, "split")
        domain_path = _source_path(instance, "domain_path", source_manifest)
        problem_path = _source_path(instance, "problem_path", source_manifest)
        task = parse_task(domain_path, problem_path)
        if task.domain_name != "blocksworld":
            raise ProvenanceError("pddl_domain_mismatch")
        grounded, status = ground_actions(task, max_grounded_actions=DEFAULT_LIMITS["max_grounded_actions"], max_grounded_atoms=DEFAULT_LIMITS["max_grounded_atoms"])
        if status is not None:
            raise ProvenanceError("grounding_failed")
        bfs = run_fifo_bfs(task, tuple(grounded), DEFAULT_LIMITS)
        if bfs.status != "success_full_trace":
            raise ProvenanceError("bfs_trace_not_exact")
        if split == "structural_ood":
            memberships[split].add(_text(instance, "instance_id"))
            ood_members.append(_ood_member(instance, task, bfs.plan))
            continue
        if split == "calibration":
            memberships[split].add(instance_id)
            continue
        if split not in SPLITS:
            raise ProvenanceError("invalid_split")
        iw = run_iterated_width(LocalPlannerRequest("iw", task, tuple(grounded), DEFAULT_LIMITS))
        if iw.status != "success_full_trace" or "plan_recovery" in iw.trace:
            raise ProvenanceError("iw_trace_not_exact")
        memberships[split].add(_text(instance, "instance_id"))
        for algorithm, plan, trace in ((BFS_ALGORITHM, list(bfs.plan), bfs.trace), ("iterated_width", iw.plan, iw.trace)):
            replay = replay_plan(task, plan, grounded_actions=grounded)
            if replay["replay_ok"] is not True or replay["goal_satisfied"] is not True:
                raise ProvenanceError("replay_failed")
            rows[split].extend(_transition_rows(instance, algorithm, trace, replay, manifest_digest, domain_path, problem_path))
    if not ood_members or any(not memberships[split] for split in SPLITS) or any(memberships[left] & memberships[right] for left in memberships for right in memberships if left < right):
        raise ProvenanceError("partition_overlap")
    _require_planner_coverage(rows)
    partition: dict[str, dict[str, object]] = {name: {"ids": sorted(ids)} for name, ids in memberships.items() if ids}
    partition["structural_ood"]["members"] = ood_members
    return rows, {"schema_version": "planning_cgas_source_v2", "partitions": partition, "source_manifest_digest": manifest_digest}


def _require_planner_coverage(rows: dict[str, list[dict[str, object]]]) -> None:
    for split in SPLITS:
        algorithms: set[str] = set()
        for row in rows[split]:
            planner = row.get("planner")
            if isinstance(planner, dict):
                algorithms.add(str(planner["algorithm"]))
        for algorithm in (BFS_ALGORITHM, "iterated_width"):
            if algorithm not in algorithms:
                raise ProvenanceError(f"missing_required_planner_rows:{split}:{algorithm}")


def _transition_rows(instance: dict[str, object], algorithm: str, trace: Mapping[str, object], replay: dict[str, object], manifest_digest: str, domain_path: Path, problem_path: Path) -> list[dict[str, object]]:
    source_digest = ":".join((_digest(domain_path), _digest(problem_path), manifest_digest))
    transitions = replay["transitions"]
    if not isinstance(transitions, list):
        raise ProvenanceError("invalid_replay")
    replay_id = f"{_text(instance, 'instance_id')}::{algorithm}::{_digest_text(_canonical(transitions))[:12]}"
    planner = _planner(algorithm, trace)
    records: list[dict[str, object]] = []
    for transition in transitions:
        if not isinstance(transition, dict):
            raise ProvenanceError("invalid_transition")
        row: dict[str, object] = {"domain": "blocksworld", "instance_id": _text(instance, "instance_id"), "planner": planner, "planner_trace": trace, "replay": {"replay_ok": True, "replay_validation_id": replay_id}, "selected_action": transition["action"], "source_invocation": _invocation(manifest_digest, trace), "source_digest": source_digest, "split": _text(instance, "split"), "state_after": transition["state_after"], "state_before": transition["state_before"], "state_before_id": _digest_text(_canonical(transition["state_before"])), "step_index": transition["step_index"], "structural_ood": False, "trace_contract_version": trace["trace_contract_version"]}
        row["record_id"] = _stable_row_id(row)
        records.append(row)
    return records


def _planner(algorithm: str, trace: Mapping[str, object]) -> dict[str, object]:
    is_bfs = algorithm == BFS_ALGORITHM
    return {"action_tie_break": TIE_BREAK, "algorithm": algorithm, "implementation": "scripts.phase3.cgas_bfs.run_fifo_bfs" if is_bfs else "scripts.phase3.local_iw.run_iterated_width", "implementation_hash": _digest(Path(__file__).with_name("cgas_bfs.py" if is_bfs else "local_iw.py")), "limits": DEFAULT_LIMITS, "trace_contract_version": trace["trace_contract_version"], "version": "cgas_p0_v2", **({} if is_bfs else {"width": 1})}


def _ood_member(instance: dict[str, object], task: PDDLTask, plan: tuple[str, ...]) -> dict[str, object]:
    derived = {"instance_id": _text(instance, "instance_id"), "object_count": len(task.objects_by_type["object"]), "horizon": len(plan), "composition": canonical_composition(task)}
    for field in ("object_count", "horizon", "composition"):
        declared = instance.get(field)
        if declared != derived[field]:
            raise ProvenanceError(f"structural_ood_{field}_mismatch")
    return derived


def canonical_composition(task: PDDLTask) -> str:
    return _canonical({"goal": sorted(task.goal), "init": sorted(task.init)})


def _invocation(manifest_digest: str, trace: Mapping[str, object]) -> dict[str, object]:
    return {"arguments": {"limits": DEFAULT_LIMITS, "source_manifest_digest": manifest_digest}, "implementation_revision": _digest(Path(__file__)), "module": "scripts.phase3.cgas_provenance", "trace_contract_version": trace["trace_contract_version"]}


def _write_rows(root: Path, rows: dict[str, list[dict[str, object]]]) -> None:
    source = root / "source"
    source.mkdir()
    for split in SPLITS:
        _write_jsonl(source / f"{split}.jsonl", rows[split])


def _snapshot_sources(instances: list[dict[str, object]], source_manifest: Path, candidate: Path) -> list[dict[str, object]]:
    pddl_root = candidate / "pddl"
    pddl_root.mkdir()
    snapshots: list[dict[str, object]] = []
    for instance in instances:
        snapshot = dict(instance)
        for field in ("domain_path", "problem_path"):
            source = _source_path(instance, field, source_manifest)
            destination = pddl_root / f"{_digest(source)}.pddl"
            if not destination.exists():
                shutil.copyfile(source, destination)
            snapshot[field] = str(destination.relative_to(candidate))
        snapshots.append(snapshot)
    return snapshots


def _source_path(instance: dict[str, object], field: str, manifest: Path) -> Path:
    path = Path(_text(instance, field))
    return path if path.is_absolute() else manifest.parent / path


def _publish(candidate: Path, output_root: Path) -> None:
    previous = output_root.with_name(f".{output_root.name}.previous")
    if previous.exists():
        shutil.rmtree(previous)
    moved_previous = output_root.exists()
    if moved_previous:
        os.replace(output_root, previous)
    try:
        os.replace(candidate, output_root)
    except OSError:
        if moved_previous and previous.exists():
            os.replace(previous, output_root)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def _withdraw(output_root: Path) -> None:
    source = output_root / "source"
    quarantine = output_root / ".invalid-source"
    if source.exists():
        if quarantine.exists():
            shutil.rmtree(quarantine)
        os.replace(source, quarantine)
    approval = output_root / "approved.json"
    if approval.exists():
        approval.unlink()


def _rejection(identity: str, reason: str) -> dict[str, str]:
    return {"record_id": f"recomputed-{_digest_text(identity)[:24]}", "reason": reason}


def _text(value: dict[str, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str):
        raise ProvenanceError(f"missing_{field}")
    return item




def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        report = verify_corpus(args.output_root) if args.verify else build_corpus(_required_manifest(args.source_manifest), args.output_root)
    except (OSError, ProvenanceError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(_canonical(report))
    return 1 if args.verify and report["errors"] else 0


def _required_manifest(path: Path | None) -> Path:
    if path is None:
        raise ProvenanceError("source_manifest_required")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
