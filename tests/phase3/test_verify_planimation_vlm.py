from __future__ import annotations

import json
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

from scripts.phase3.io_utils import relpath
from scripts.phase3.planimation_pairing import PairingConfig, RenderConfig, build_pairing_manifest, build_vlm_records, render_replay_states, validate_state_render_record
from scripts.phase3.rollout_gates import assess_promotion, prepare_selection


def test_release_mode_accepts_complete_output_and_rejects_required_failures(tmp_path: Path) -> None:
    # Given: a complete production root with one rendered, strict hybrid example.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    build_vlm_records(output_root)

    # When: the actual release CLI checks the complete root and independently corrupted roots.
    valid = _verify(output_root, "release")
    missing = _verify(_output_root(tmp_path, "missing"), "release")
    malformed_root = _copy_root(output_root, tmp_path, "malformed")
    (malformed_root / "full_reasoning_train.jsonl").write_text("{not-json}\n", encoding="utf-8")
    malformed = _verify(malformed_root, "release")
    duplicate_root = _copy_root(output_root, tmp_path, "duplicate")
    step_path = duplicate_root / "step_vlm_train.jsonl"
    step_path.write_text(step_path.read_text(encoding="utf-8") * 2, encoding="utf-8")
    duplicate = _verify(duplicate_root, "release")
    partial_root = _copy_root(output_root, tmp_path, "partial")
    _set_manifest(partial_root, "partial", True)
    partial = _verify(partial_root, "release")
    split_leak_root = _copy_root(output_root, tmp_path, "split-leak")
    leaked = json.loads((split_leak_root / "step_vlm_train.jsonl").read_text(encoding="utf-8"))
    leaked["split"] = "dev"
    (split_leak_root / "step_vlm_train.jsonl").write_text(json.dumps(leaked) + "\n", encoding="utf-8")
    split_leak = _verify(split_leak_root, "release")
    stale_root = _copy_root(output_root, tmp_path, "stale")
    pairing_path = stale_root / "diagnostics" / "pairing_manifest.jsonl"
    stale_pair = json.loads(pairing_path.read_text(encoding="utf-8"))
    stale_pair["source_record_sha256"] = "0" * 64
    pairing_path.write_text(json.dumps(stale_pair) + "\n", encoding="utf-8")
    stale = _verify(stale_root, "release")
    invalid_image_root = _copy_root(output_root, tmp_path, "invalid-image")
    image_path = _record_image_path(invalid_image_root)
    image_path.write_bytes(b"not-a-png")
    invalid_image = _verify(invalid_image_root, "release")

    # Then: release permits the complete root and emits stable reasons for every closed-gate failure.
    assert valid.returncode == 0, valid.stderr
    assert json.loads(valid.stdout)["counts"] == {"full_records": {"dev": 0, "test": 0, "train": 1}, "pair_records": 1, "search_traversal_records": {"dev": 0, "test": 0, "train": 2}, "state_render_records": 4, "step_records": {"dev": 0, "test": 0, "train": 1}}
    assert missing.returncode == 1 and "missing_required_file: diagnostics/pairing_manifest.jsonl" in missing.stderr
    assert malformed.returncode == 1 and "malformed_jsonl: full_reasoning_train.jsonl" in malformed.stderr
    assert duplicate.returncode == 1 and "duplicate VLM record_id" in duplicate.stderr
    assert partial.returncode == 1 and "release_requires_production_complete" in partial.stderr
    assert stale.returncode == 1 and "source_record_sha256" in stale.stderr
    assert invalid_image.returncode == 1 and "invalid_render_image" in invalid_image.stderr
    assert split_leak.returncode == 1 and "split leakage in step_vlm_train.jsonl" in split_leak.stderr


def test_manifest_and_render_modes_validate_their_respective_artifact_boundaries(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path, "modes")
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))

    manifest = _verify(output_root, "manifest")
    missing_render = _verify(output_root, "render")
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    render = _verify(output_root, "render")

    assert manifest.returncode == 0, manifest.stderr
    assert missing_render.returncode == 1
    assert "missing_required_file: reports/state_render_summary.json" in missing_render.stderr
    assert render.returncode == 0, render.stderr


def test_release_evaluates_concrete_types_from_persisted_hybrid_schema(tmp_path: Path) -> None:
    # Given: a complete release fixture whose persisted schema changes an integer contract.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path, "persisted-schema")
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    build_vlm_records(output_root)
    schema_path = output_root / "schema" / "full_reasoning.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["properties"]["provenance"]["properties"]["pair"]["properties"]["source_line_index"] = {"type": "string"}
    schema_path.write_text(json.dumps(schema), encoding="utf-8")

    # When: release validates persisted full-record schema semantics.
    result = _verify(output_root, "release")

    # Then: it rejects the integer record value against the altered persisted schema.
    assert result.returncode == 1
    assert "schema type mismatch for provenance.pair.source_line_index: expected string" in result.stderr


def test_release_rejects_boolean_pair_manifest_integer_fields(tmp_path: Path) -> None:
    # Given: a release-valid fixture copied with persisted pair sizes changed to booleans.
    output_root = _complete_rollout_root(tmp_path, "pair-boolean")
    pairing_path = output_root / "diagnostics" / "pairing_manifest.jsonl"
    pair = json.loads(pairing_path.read_text(encoding="utf-8"))
    pair["plan_length"] = True
    pair["trace_size_chars"] = True
    pairing_path.write_text(json.dumps(pair) + "\n", encoding="utf-8")

    # When: the release CLI validates persisted pair-manifest primitives.
    result = _verify(output_root, "release")

    # Then: bool values cannot satisfy the integer contract.
    assert result.returncode == 1
    assert "pair plan_length must be an integer" in result.stderr
    assert "pair trace_size_chars must be an integer" in result.stderr


def test_release_rejects_boolean_state_render_step_index(tmp_path: Path) -> None:
    # Given: a release-valid fixture copied with a persisted state step index changed to a boolean.
    output_root = _complete_rollout_root(tmp_path, "state-boolean")
    render_path = output_root / "diagnostics" / "state_render_manifest.jsonl"
    rows = [json.loads(line) for line in render_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["step_index"] = True
    render_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    # When: the release CLI validates persisted state-render primitives.
    result = _verify(output_root, "release")

    # Then: bool values cannot satisfy the integer step-index contract.
    assert result.returncode == 1
    assert "state render step_index must be an integer" in result.stderr


def test_release_rejects_mixed_state_render_variants(tmp_path: Path) -> None:
    # Given: complete state rows altered to mix success-only and failure-only fields.
    output_root = _complete_rollout_root(tmp_path, "mixed-state-variants")
    render_path = output_root / "diagnostics" / "state_render_manifest.jsonl"
    rows = [json.loads(line) for line in render_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["message"] = "unexpected success message"
    rows[1]["status"] = "failed"
    rows[1]["message"] = "controlled failure"
    render_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    # When: the release CLI reads the contradictory persisted state variants.
    result = _verify(output_root, "release")

    # Then: it rejects fields that are invalid for the declared status.
    assert result.returncode == 1
    assert "state render unexpected message" in result.stderr
    assert "state render unexpected frame_path" in result.stderr


def test_release_handles_a_valid_controlled_failed_state_row(tmp_path: Path) -> None:
    # Given: an otherwise valid source whose persisted plan cannot produce render transitions.
    source_root = _source_root(tmp_path)
    source_path = source_root / "train.jsonl"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["supervised_target"]["plan"] = "malformed"
    source_path.write_text(json.dumps(source) + "\n", encoding="utf-8")
    output_root = _output_root(tmp_path, "controlled-failure")
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))

    # When: the renderer persists the controlled failure and release checks the root.
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    failed_row = json.loads((output_root / "diagnostics" / "state_render_manifest.jsonl").read_text(encoding="utf-8"))
    result = _verify(output_root, "release")

    # Then: the persisted row validates; release fails only for missing required success coverage.
    assert validate_state_render_record(failed_row, frozenset({str(failed_row["pair_id"])})) == []
    assert result.returncode == 1
    assert "render coverage reconciliation" in result.stderr


def test_fixture_promotion_requires_frozen_selection_and_release_receipt(tmp_path: Path) -> None:
    # Given: a fresh strict fixture root and its frozen fixture selection.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path, "rollout")
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    selection = prepare_selection(output_root, "fixture")
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"}), selected_pair_ids=frozenset(selection["selected_pair_ids"])))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    build_vlm_records(output_root)

    # When: the gate assesses release-verifier evidence against the frozen selection.
    decision = assess_promotion(output_root, "fixture", output_root / "diagnostics" / "rollout_selection.json")

    # Then: the fixture is promotable only with complete strict receipts.
    assert decision.approved is True
    assert decision.reasons == ()
    assert json.loads((output_root / "diagnostics" / "rollout_promotion_receipt.json").read_text(encoding="utf-8"))["semantic_image_qa"] == "verified_by_release"

    # When: the same receipt is assessed with a tampered frozen selection.
    selection_path = output_root / "diagnostics" / "rollout_selection.json"
    tampered = json.loads(selection_path.read_text(encoding="utf-8"))
    tampered["selected_pair_ids"] = []
    selection_path.write_text(json.dumps(tampered), encoding="utf-8")
    blocked = assess_promotion(output_root, "fixture", selection_path)

    # Then: no release-backed artifact can bypass a broken selection freeze.
    assert blocked.approved is False
    assert "frozen_selection_integrity_failure" in blocked.reasons


def test_promotion_rejects_stale_manifest_forged_prior_receipt_and_missing_artifacts(tmp_path: Path) -> None:
    # Given: a release-valid fixture, its frozen selection, and an approved fixture receipt.
    fixture_root = _complete_rollout_root(tmp_path, "fixture")
    prepare_selection(fixture_root, "fixture")
    fixture_decision = assess_promotion(fixture_root, "fixture", fixture_root / "diagnostics" / "rollout_selection.json")
    assert fixture_decision.approved is True

    # When: a later assessment receives each invalid provenance condition.
    stale_root = _copy_root(fixture_root, tmp_path, "stale-manifest")
    prepare_selection(stale_root, "fixture")
    stale_manifest = stale_root / "diagnostics" / "pairing_manifest.jsonl"
    stale_pair = json.loads(stale_manifest.read_text(encoding="utf-8"))
    stale_pair["source_root_sha256"] = "0" * 64
    stale_manifest.write_text(json.dumps(stale_pair) + "\n", encoding="utf-8")
    stale = assess_promotion(stale_root, "fixture", stale_root / "diagnostics" / "rollout_selection.json")
    forged_receipt = _copy_root(fixture_root, tmp_path, "forged-prior") / "diagnostics" / "rollout_promotion_receipt.json"
    forged_payload = json.loads(forged_receipt.read_text(encoding="utf-8"))
    forged_payload["approved"] = False
    forged_receipt.write_text(json.dumps(forged_payload), encoding="utf-8")
    later_root = _complete_rollout_root(tmp_path, "later")
    prepare_selection(later_root, "changed-canary")
    forged = assess_promotion(later_root, "changed-canary", later_root / "diagnostics" / "rollout_selection.json", forged_receipt)
    missing_root = _copy_root(fixture_root, tmp_path, "missing-artifacts")
    (missing_root / "diagnostics" / "state_render_manifest.jsonl").unlink()
    missing = assess_promotion(missing_root, "fixture", missing_root / "diagnostics" / "rollout_selection.json")

    # Then: each condition fails closed and still persists a diagnostic receipt.
    assert "frozen_pairing_manifest_hash_mismatch" in stale.reasons
    assert "output_pairing_manifest_pair_identity_mismatch" in stale.reasons
    assert "prior_promotion_receipt_integrity_failure" in forged.reasons
    assert "missing_artifact:diagnostics/state_render_manifest.jsonl" in missing.reasons
    assert json.loads((missing_root / "diagnostics" / "rollout_promotion_receipt.json").read_text(encoding="utf-8"))["approved"] is False


def _complete_rollout_root(tmp_path: Path, suffix: str) -> Path:
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path, suffix)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    build_vlm_records(output_root)
    return output_root


def _verify(output_root: Path, mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/phase3/verify_planimation_vlm.py", "--output-root", str(output_root), "--mode", mode],
        cwd=Path.cwd(),
        check=False,
        capture_output=True,
        text=True,
    )


def _copy_root(source: Path, tmp_path: Path, suffix: str) -> Path:
    destination = _output_root(tmp_path, suffix)
    shutil.copytree(source, destination)
    return destination


def _set_manifest(output_root: Path, key: str, value: bool) -> None:
    path = output_root / "diagnostics" / "hybrid_output_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest[key] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _record_image_path(output_root: Path) -> Path:
    record = json.loads((output_root / "full_reasoning_train.jsonl").read_text(encoding="utf-8"))
    return Path(record["artifact_paths"]["image_path"])


def _render_artifacts(cache_dir: Path) -> dict[str, object]:
    frame = cache_dir / "frames" / "frame_000.png"
    frame.parent.mkdir(parents=True, exist_ok=True)
    frame.write_bytes(_png())
    trace = cache_dir / "trace.vfg.json"
    trace.write_text(json.dumps({"visualStages": [{"stageName": "Initial Stage", "visualSprites": [{"name": "token", "minX": 0.2, "maxX": 0.6, "minY": 0.2, "maxY": 0.6}]}]}), encoding="utf-8")
    return {"status": "success", "frame_path": relpath(frame), "trace_path": relpath(trace), "attempts": 1}


def _png() -> bytes:
    stream = BytesIO()
    image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    for x in range(20, 60):
        for y in range(40, 80):
            image.putpixel((x, y), (32, 96, 160, 255))
    image.save(stream, format="PNG")
    return stream.getvalue()


def _source_root(tmp_path: Path) -> Path:
    root = Path("tmp") / f"phase3_release_source_{tmp_path.name}"
    if root.exists():
        shutil.rmtree(root)
    instance = root / "instances" / "tiny-train-easy-0000"
    render = instance / "render"
    frames = render / "frames"
    frames.mkdir(parents=True)
    domain = instance / "domain.pddl"
    problem = instance / "problem.pddl"
    profile = instance / "tiny_ap.pddl"
    domain.write_text("""(define (domain tiny) (:requirements :strips :typing) (:types loc - object) (:predicates (at ?x - loc) (connected ?x ?y - loc)) (:action move :parameters (?from ?to - loc) :precondition (and (at ?from) (connected ?from ?to)) :effect (and (at ?to) (not (at ?from)))))""", encoding="utf-8")
    problem.write_text("""(define (problem tiny-p1) (:domain tiny) (:objects a b - loc) (:init (at a) (connected a b)) (:goal (and (at b))))""", encoding="utf-8")
    profile.write_text("(define (animation-profile tiny))\n", encoding="utf-8")
    (frames / "frame_000.png").write_bytes(_png())
    (frames / "frame_001.png").write_bytes(_png())
    (render / "trace.vfg.json").write_text(json.dumps({"visualStages": [{"stageName": "Initial Stage"}, {"stageName": "(move a b)"}]}), encoding="utf-8")
    (render / "result.json").write_text(json.dumps({"render_profile_path": str(profile)}), encoding="utf-8")
    example = {"schema_version": "phase3_supervised_planning_v1", "example_id": "example-0000", "domain": "grid", "instance_id": "tiny-train-easy-0000", "split": "train", "planner": "gbfs", "plan_hash": "plan-hash", "trace_fidelity": "success_full_trace", "vision_supervision_available": True, "model_facing": {"domain_source": relpath(domain), "problem_source": relpath(problem), "vision": {"trace_path": relpath(render / "trace.vfg.json"), "frame_paths": [relpath(frames / "frame_000.png"), relpath(frames / "frame_001.png")]}}, "supervised_target": {"plan": ["(move a b)"], "planner_trace": {"trace_contract_version": "phase3_traversal_trace_v1", "algorithm": "greedy_best_first", "heuristic_source": "unsatisfied_goal_count", "expansion_count": 1, "visited_count": 2, "frontier_events": [{"event_kind": "expansion", "selected_state_atoms": ["(at a)", "(connected a b)"], "current_heuristic": {"heuristic_value": 1}, "successor_heuristics": [{"action": "(move a b)", "event_kind": "generation", "heuristic_value": 0, "is_goal": True}], "frontier_size_after": 0, "visited_count_after": 2, "tie_break_rule": "min_unsatisfied_goals_then_plan_length_then_generation_order"}]}, "replay_transitions": [{"step_index": 0, "action": "(move a b)", "state_before": ["(at a)", "(connected a b)"], "state_after": ["(at b)", "(connected a b)"]}]}, "evaluation_metadata": {}}
    (root / "train.jsonl").write_text(json.dumps(example) + "\n", encoding="utf-8")
    for split in ("dev", "test"):
        (root / f"{split}.jsonl").write_text("", encoding="utf-8")
    diagnostics = root / "diagnostics"
    diagnostics.mkdir()
    (diagnostics / "instance_accounting.jsonl").write_text(json.dumps({"instance_id": "tiny-train-easy-0000", "bucket": "easy"}) + "\n", encoding="utf-8")
    return root


def _output_root(tmp_path: Path, suffix: str = "output") -> Path:
    root = Path("tmp") / f"phase3_release_{suffix}_{tmp_path.name}"
    if root.exists():
        shutil.rmtree(root)
    return root
