from __future__ import annotations

import json
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from scripts.phase3.io_utils import relpath
from scripts.phase3 import planimation_pairing
from scripts.phase3 import planimation_pairing_implementation
from scripts.phase3 import generate_planimation_vlm
from scripts.phase3.planimation_pairing import PairingConfig, RenderConfig, _load_source_example, build_pairing_manifest, build_vlm_records, render_replay_states, validate_pairing_output


def _png() -> bytes:
    stream = BytesIO()
    image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    for x in range(20, 60):
        for y in range(40, 80):
            image.putpixel((x, y), (32, 96, 160, 255))
    image.save(stream, format="PNG")
    return stream.getvalue()


PNG = _png()
VFG = json.dumps({"visualStages": [{"stageName": "Initial Stage", "visualSprites": [{"name": "token", "minX": 0.2, "maxX": 0.6, "minY": 0.2, "maxY": 0.6}]}]})


def test_pairing_facade_preserves_public_and_verifier_hooks() -> None:
    # Given: callers that rely on the public pairing facade and verifier-facing hooks.
    required_symbols = (
        "PairingConfig",
        "RenderConfig",
        "build_pairing_manifest",
        "render_replay_states",
        "build_vlm_records",
        "validate_pairing_output",
        "validate_pair_record",
        "validate_state_render_record",
        "validate_vlm_record",
        "_load_source_example",
        "_render_receipt_is_valid",
        "_trace_identity",
        "_source_root_snapshot",
        "_source_jsonl_rows",
    )

    # When: compatibility consumers resolve every required symbol through both paths.
    facade_symbols = {name: getattr(planimation_pairing, name) for name in required_symbols}
    implementation_symbols = {name: getattr(planimation_pairing_implementation, name) for name in required_symbols}

    # Then: the facade keeps callable endpoints and direct aliases stable.
    assert all(callable(symbol) or isinstance(symbol, type) for symbol in facade_symbols.values())
    assert facade_symbols["_load_source_example"] is implementation_symbols["_load_source_example"]
    assert facade_symbols["_render_receipt_is_valid"] is implementation_symbols["_render_receipt_is_valid"]
    assert facade_symbols["_trace_identity"] is implementation_symbols["_trace_identity"]


def test_blocksworld_animation_profile_targets_on_table_predicate() -> None:
    # Given: the curriculum Blocksworld domain's predicate vocabulary.
    profile = Path("data/pddl_instances/blocksworld/blocksworld_AP.pddl")

    # When: the configured animation profile is inspected.
    profile_text = profile.read_text(encoding="utf-8")

    # Then: its table-placement rule targets the predicate emitted by the PDDL domain.
    assert "(:predicate on-table" in profile_text


def _render_artifacts(cache_dir: Path) -> dict[str, object]:
    frame = cache_dir / "frames" / "frame_000.png"
    frame.parent.mkdir(parents=True, exist_ok=True)
    frame.write_bytes(PNG)
    trace = cache_dir / "trace.vfg.json"
    trace.write_text(VFG, encoding="utf-8")
    return {"status": "success", "frame_path": relpath(frame), "trace_path": relpath(trace), "attempts": 1}
DOMAIN = """
(define (domain tiny)
  (:requirements :strips :typing)
  (:types loc - object)
  (:predicates (at ?x - loc) (connected ?x ?y - loc))
  (:action move
    :parameters (?from ?to - loc)
    :precondition (and (at ?from) (connected ?from ?to))
    :effect (and (at ?to) (not (at ?from))))
)
"""
PROBLEM = """
(define (problem tiny-p1)
  (:domain tiny)
  (:objects a b - loc)
  (:init (at a) (connected a b))
  (:goal (and (at b)))
)
"""


def test_pair_render_and_emit_vlm_records(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    config = PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"}), max_plan_length=64, max_trace_chars=1_000_000)

    manifest = build_pairing_manifest([source_root], output_root, config=config)

    pair = manifest["records"][0]
    assert pair["frame_alignment_status"] == "existing_exact_complete"
    assert pair["training_eligible"] is True
    assert pair["trace_size_chars"] > 0

    calls = {"count": 0}

    def fake_renderer(domain: Path, problem: Path, profile: Path, cache_dir: Path, _config: RenderConfig) -> dict[str, object]:
        calls["count"] += 1
        assert domain.exists() and problem.exists() and profile.exists()
        assert "(at a)" in problem.read_text(encoding="utf-8") or "(at b)" in problem.read_text(encoding="utf-8")
        return _render_artifacts(cache_dir)

    renders = render_replay_states(output_root, renderer=fake_renderer, config=RenderConfig(request_delay_seconds=0))
    assert renders["summary"]["status"] == {"success": 4}
    assert calls["count"] == 2

    summary = build_vlm_records(output_root, reasoning_budget_chars=8192)
    assert summary["full_records"] == {"train": 1, "dev": 0, "test": 0}
    assert summary["step_records"] == {"train": 1, "dev": 0, "test": 0}
    assert validate_pairing_output(output_root)["errors"] == []
    assert json.loads(next((output_root / "state_cache").rglob("result.json")).read_text(encoding="utf-8"))["status"] == "success"
    full = _rows(output_root / "full_reasoning_train.jsonl")[0]
    step = _rows(output_root / "step_vlm_train.jsonl")[0]
    assert full["target"]["planner_trace"]["algorithm"] == "greedy_best_first"
    assert step["target"]["next_action"] == "(move a b)"
    assert step["target"]["reasoning_context"]["context_status"] == "step_bound"
    output_manifest = json.loads((output_root / "diagnostics" / "hybrid_output_manifest.json").read_text(encoding="utf-8"))
    assert output_manifest["partial"] is False
    assert output_manifest["production_complete"] is True
    assert output_manifest["counts"]["full_records"] == {"train": 1, "dev": 0, "test": 0}
    assert output_manifest["counts"]["step_records"] == {"train": 1, "dev": 0, "test": 0}

    rerun = render_replay_states(output_root, renderer=fake_renderer, config=RenderConfig(request_delay_seconds=0))
    assert rerun["summary"]["cache_hits"] == 4
    assert calls["count"] == 2

    cache_result = json.loads(next((output_root / "state_cache").rglob("result.json")).read_text(encoding="utf-8"))
    assert cache_result["profile_path"].startswith("data/")
    assert len(cache_result["profile_sha256"]) == 64
    assert len(cache_result["png_sha256"]) == 64
    assert cache_result["png_dimensions"] == [100, 100]
    assert cache_result["semantic_image_qa"] == "validated_expected_object_coverage"


def test_render_replay_accepts_successful_pddl_upload_url(tmp_path: Path) -> None:
    # Given: a successful renderer result that includes its Planimation upload endpoint.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest(
        [source_root],
        output_root,
        config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})),
    )

    # When: replay rendering persists that endpoint in state-render records.
    def fake_renderer(_domain: Path, _problem: Path, _profile: Path, cache_dir: Path, _config: RenderConfig) -> dict[str, object]:
        return {**_render_artifacts(cache_dir), "used_pddl_url": "https://planimation.planning.domains/upload/pddl"}

    render_replay_states(output_root, renderer=fake_renderer, config=RenderConfig(request_delay_seconds=0))

    # Then: strict output validation accepts the renderer's success metadata.
    assert validate_pairing_output(output_root)["errors"] == []


def test_render_replay_emits_bounded_progress_events(tmp_path: Path) -> None:
    # Given: a renderable pairing fixture and a progress collector.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest(
        [source_root],
        output_root,
        config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})),
    )
    events: list[dict[str, object]] = []

    # When: replay rendering reaches two-state reporting intervals.
    renders = render_replay_states(
        output_root,
        renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir),
        config=RenderConfig(request_delay_seconds=0),
        progress_callback=events.append,
        progress_every=2,
    )

    # Then: start, bounded progress, and final summary events are emitted without per-state spam.
    assert [event["phase"] for event in events] == [
        "state_render_started",
        "state_render_progress",
        "state_render_progress",
        "state_render_finished",
    ]
    assert [event["processed_states"] for event in events[1:3]] == [2, 4]
    assert events[-1]["summary"] == renders["summary"]


def test_graphplan_render_uses_validated_extraction_not_raw_replay_transition(tmp_path: Path) -> None:
    # Given: Graphplan source data with forged raw replay-state atoms.
    source_root = _source_root(tmp_path, planner="graphplan")
    source_path = source_root / "train.jsonl"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["supervised_target"]["replay_transitions"][0]["state_before"] = ["(at b)"]
    source_path.write_text(json.dumps(source) + "\n", encoding="utf-8")
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"}), max_plan_length=64, max_trace_chars=1_000_000))
    observed_states: list[str] = []

    def fake_renderer(_domain: Path, problem: Path, _profile: Path, cache_dir: Path, _config: RenderConfig) -> dict[str, object]:
        observed_states.append(problem.read_text(encoding="utf-8"))
        return _render_artifacts(cache_dir)

    # When: the Graphplan state renderer is run.
    renders = render_replay_states(output_root, renderer=fake_renderer, config=RenderConfig(request_delay_seconds=0))

    # Then: the sole pre-action render comes from extracted-plan replay, not forged raw atoms.
    assert renders["summary"]["status"] == {"success": 2}
    assert len(observed_states) == 2
    assert "(at a)" in observed_states[0]


def test_render_replay_rejects_stale_cache_metadata_and_corrupt_png(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    config = PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"}))
    build_pairing_manifest([source_root], output_root, config=config)
    calls = {"count": 0}

    def fake_renderer(_domain: Path, _problem: Path, _profile: Path, cache_dir: Path, _config: RenderConfig) -> dict[str, object]:
        calls["count"] += 1
        return _render_artifacts(cache_dir)

    render_replay_states(output_root, renderer=fake_renderer, config=RenderConfig(request_delay_seconds=0))
    cache_dir = next((output_root / "state_cache").rglob("result.json")).parent
    (cache_dir / "frames" / "frame_000.png").write_bytes(b"\x89PNG\r\n\x1a\nnot-a-decodable-image")
    stale = json.loads((cache_dir / "result.json").read_text(encoding="utf-8"))
    stale["png_sha256"] = "0" * 64
    (cache_dir / "result.json").write_text(json.dumps(stale), encoding="utf-8")

    rerun = render_replay_states(output_root, renderer=fake_renderer, config=RenderConfig(request_delay_seconds=0))

    assert rerun["summary"]["cache_hits"] == 3
    assert calls["count"] == 3
    assert validate_pairing_output(output_root)["errors"] == []


def test_render_replay_profile_relocation_forces_new_cache_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    profile_root = Path("tmp") / f"phase3_profiles_{tmp_path.name}"
    first_profile = profile_root / "first.pddl"
    second_profile = profile_root / "second.pddl"
    profile_root.mkdir(parents=True, exist_ok=True)
    first_profile.write_text("(define (animation-profile grid))\n", encoding="utf-8")
    second_profile.write_text("(define (animation-profile grid-relocated))\n", encoding="utf-8")
    configured = {"path": first_profile}

    def load_config() -> SimpleNamespace:
        return SimpleNamespace(domains=(SimpleNamespace(domain_id="grid", render_profile_path=configured["path"]),))

    monkeypatch.setattr("src.data_collect.config.load_curriculum_config", load_config)
    calls = {"count": 0}

    def fake_renderer(_domain: Path, _problem: Path, _profile: Path, cache_dir: Path, _config: RenderConfig) -> dict[str, object]:
        calls["count"] += 1
        return _render_artifacts(cache_dir)

    render_replay_states(output_root, renderer=fake_renderer, config=RenderConfig(request_delay_seconds=0))
    configured["path"] = second_profile
    rerun = render_replay_states(output_root, renderer=fake_renderer, config=RenderConfig(request_delay_seconds=0))

    assert calls["count"] == 4
    assert rerun["summary"]["cache_hits"] == 2


def test_zero_action_solved_case_emits_one_full_frame_and_no_step_rows(tmp_path: Path) -> None:
    # Given: a solved source record with no action or replay transition.
    source_root = _source_root(tmp_path)
    source_path = source_root / "train.jsonl"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["supervised_target"]["plan"] = []
    source["supervised_target"]["replay_transitions"] = []
    source_path.write_text(json.dumps(source) + "\n", encoding="utf-8")
    problem_path = source_root / "instances" / "tiny-train-easy-0000" / "problem.pddl"
    problem_path.write_text(PROBLEM.replace("(at b)))", "(at a)))"), encoding="utf-8")
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))

    # When: the validated replay renderer and record builder run.
    renders = render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    summary = build_vlm_records(output_root)

    # Then: the initial/terminal frame supplies the one full record and no next-action row.
    assert renders["summary"]["status"] == {"success": 3}
    assert renders["records"][0]["transition"]["frame_role"] == "initial_terminal_full"
    assert summary["full_records"] == {"train": 1, "dev": 0, "test": 0}
    assert summary["step_records"] == {"train": 0, "dev": 0, "test": 0}


def test_missing_step_zero_is_a_controlled_no_record_failure(tmp_path: Path) -> None:
    # Given: a one-action render manifest whose required pre-action step zero was removed.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    manifest_path = output_root / "diagnostics" / "state_render_manifest.jsonl"
    manifest_path.write_text("\n".join(json.dumps(row) for row in _rows(manifest_path) if row["step_index"] != 0) + "\n", encoding="utf-8")

    # When: VLM records are built from the incomplete render manifest.
    summary = build_vlm_records(output_root)

    # Then: the terminal image cannot be substituted for the full-record initial image.
    assert summary["full_records"] == {"train": 0, "dev": 0, "test": 0}
    assert summary["step_records"] == {"train": 0, "dev": 0, "test": 0}
    assert summary["skipped"] == {"render_cardinality_mismatch": 1}


def test_invalid_plan_cardinality_emits_a_controlled_failed_state_row(tmp_path: Path) -> None:
    # Given: a source fixture whose persisted plan is not an action list.
    source_root = _source_root(tmp_path)
    source_path = source_root / "train.jsonl"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["supervised_target"]["plan"] = "not-an-action-list"
    source_path.write_text(json.dumps(source) + "\n", encoding="utf-8")
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))

    # When: replay rendering encounters the malformed source plan.
    renders = render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))

    # Then: it writes a controlled failed row instead of crashing during sort.
    assert renders["records"] == [
        {
            "schema_version": "phase3_planimation_vlm_v1",
            "pair_id": renders["records"][0]["pair_id"],
            "domain": "grid",
            "instance_id": "tiny-train-easy-0000",
            "split": "train",
            "planner": "gbfs",
            "step_index": -1,
            "status": "failed",
            "cache_hit": False,
            "message": "render_cardinality_invalid: plan must be a string list",
            "failure_kind": "render_cardinality_invalid",
        }
    ]
    assert planimation_pairing.validate_state_render_record(
        renders["records"][0], frozenset({str(renders["records"][0]["pair_id"])})
    ) == []


def test_hybrid_records_have_strict_nested_provenance_and_targets(tmp_path: Path) -> None:
    # Given: a complete one-action fixture with validated render receipts.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))

    # When: hybrid VLM records are emitted.
    build_vlm_records(output_root)
    full_schema = json.loads((output_root / "schema" / "full_reasoning.schema.json").read_text(encoding="utf-8"))
    full = _rows(output_root / "full_reasoning_train.jsonl")[0]
    step = _rows(output_root / "step_vlm_train.jsonl")[0]

    # Then: both records expose strict nested mode, target, artifact, and provenance contracts.
    assert full_schema["additionalProperties"] is False
    assert full["supervision_mode"] == "hybrid_full"
    assert step["supervision_mode"] == "hybrid_step"
    assert set(full["provenance"]) == {"event", "pair", "render", "state", "trace"}
    assert set(step["target"]) == {"kind", "next_action", "reasoning_context"}
    assert all(not Path(path).is_absolute() for path in full["artifact_paths"].values())


def test_generated_hybrid_schemas_validate_emitted_records_and_reject_extra_root_field(tmp_path: Path) -> None:
    # Given: emitted full and step records plus their persisted Draft 2020-12 schemas.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    build_vlm_records(output_root)
    full_schema = json.loads((output_root / "schema" / "full_reasoning.schema.json").read_text(encoding="utf-8"))
    step_schema = json.loads((output_root / "schema" / "step_vlm.schema.json").read_text(encoding="utf-8"))
    full = _rows(output_root / "full_reasoning_train.jsonl")[0]
    step = _rows(output_root / "step_vlm_train.jsonl")[0]

    # When: the actual emitted JSON instances are evaluated by the schema keywords they declare.
    full_errors = _draft202012_object_schema_errors(full, full_schema)
    step_errors = _draft202012_object_schema_errors(step, step_schema)
    extra_root = {**step, "unexpected_root": "value"}
    missing_root = {field: value for field, value in full.items() if field != "planner"}
    missing_nested = {**full, "artifact_paths": {field: value for field, value in full["artifact_paths"].items() if field != "image_path"}}
    extra_nested = {**step, "target": {**step["target"], "unexpected_nested": "value"}}

    # Then: valid records pass while closed root and nested schemas reject omissions and extras.
    assert full_errors == []
    assert step_errors == []
    assert "$.unexpected_root: additional property" in _draft202012_object_schema_errors(extra_root, step_schema)
    assert "$.planner: required property" in _draft202012_object_schema_errors(missing_root, full_schema)
    assert "$.artifact_paths.image_path: required property" in _draft202012_object_schema_errors(missing_nested, full_schema)
    assert "$.target.unexpected_nested: additional property" in _draft202012_object_schema_errors(extra_nested, step_schema)


@pytest.mark.parametrize("field_path", [("target",), ("provenance",), ("provenance", "render")])
def test_validate_hybrid_record_rejects_missing_nested_contract_fields(tmp_path: Path, field_path: tuple[str, ...]) -> None:
    # Given: a valid emitted full record.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    build_vlm_records(output_root)
    malformed = _rows(output_root / "full_reasoning_train.jsonl")[0]
    if field_path == ("target",):
        del malformed["target"]
    else:
        provenance = malformed["provenance"]
        assert isinstance(provenance, dict)
        if field_path == ("provenance",):
            del malformed["provenance"]
        else:
            del provenance["render"]

    # When: strict hybrid validation receives the malformed record.
    errors = planimation_pairing.validate_vlm_record(malformed)

    # Then: the missing nested contract is rejected rather than tolerated.
    assert errors


def test_validate_hybrid_record_rejects_unexpected_nested_contract_field(tmp_path: Path) -> None:
    # Given: a valid emitted step record.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    build_vlm_records(output_root)
    malformed = _rows(output_root / "step_vlm_train.jsonl")[0]
    provenance = malformed["provenance"]
    assert isinstance(provenance, dict)
    pair = provenance["pair"]
    assert isinstance(pair, dict)
    pair["unexpected"] = "value"

    # When: strict hybrid validation receives the extra nested field.
    errors = planimation_pairing.validate_vlm_record(malformed)

    # Then: the closed provenance schema rejects it.
    assert "provenance.pair unexpected unexpected" in errors


@pytest.mark.parametrize(
    ("record_file", "field_path", "value", "reason"),
    [
        ("full_reasoning_train.jsonl", ("language_context", "instruction"), 7, "schema type mismatch for language_context.instruction: expected string"),
        ("step_vlm_train.jsonl", ("step_index",), True, "schema type mismatch for step_index: expected integer"),
        ("step_vlm_train.jsonl", ("target", "next_action"), False, "schema type mismatch for target.next_action: expected string"),
        ("step_vlm_train.jsonl", ("target", "reasoning_context"), [], "schema type mismatch for target.reasoning_context: expected object"),
        ("full_reasoning_train.jsonl", ("provenance", "pair", "source_line_index"), True, "schema type mismatch for provenance.pair.source_line_index: expected integer"),
        ("full_reasoning_train.jsonl", ("provenance", "event", "action"), False, "schema type mismatch for provenance.event.action: expected string or null"),
        ("full_reasoning_train.jsonl", ("provenance", "state", "state_hash"), 1, "schema type mismatch for provenance.state.state_hash: expected string"),
        ("full_reasoning_train.jsonl", ("provenance", "render", "png_dimensions"), [100, True], "schema type mismatch for provenance.render.png_dimensions[1]: expected integer"),
        ("full_reasoning_train.jsonl", ("artifact_paths", "image_path"), "/tmp/forged.png", "artifact_paths image_path must be relative"),
    ],
)
def test_validate_hybrid_record_rejects_wrong_nested_value_types(
    tmp_path: Path, record_file: str, field_path: tuple[str, ...], value: object, reason: str
) -> None:
    # Given: a valid emitted record with one concrete nested contract value corrupted.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    build_vlm_records(output_root)
    malformed = _rows(output_root / record_file)[0]
    target: object = malformed
    for field in field_path[:-1]:
        assert isinstance(target, dict)
        target = target[field]
    assert isinstance(target, dict)
    target[field_path[-1]] = value

    # When: the hybrid record reaches the strict validation boundary.
    errors = planimation_pairing.validate_vlm_record(malformed)

    # Then: invalid scalar, object, and boolean-as-integer values are rejected.
    assert reason in errors


def test_bounded_smoke_writes_partial_selection_manifest(tmp_path: Path) -> None:
    # Given: one fixture pair with two renderable states.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))

    # When: a bounded smoke render selects exactly one state.
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0), max_states=1, output_mode="bounded-smoke")
    manifest = json.loads((output_root / "diagnostics" / "hybrid_output_manifest.json").read_text(encoding="utf-8"))

    # Then: the artifact is explicitly partial and accounts for the selected state and limit.
    assert manifest["partial"] is True
    assert manifest["output_mode"] == "bounded-smoke"
    assert manifest["selection"]["render_limit"] == 1
    assert len(manifest["selection"]["selected_state_ids"]) == 1
    assert len(manifest["selection"]["selected_pair_ids"]) == 1


def test_generator_rejects_render_limit_in_production_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: production mode is asked to apply a bounded render limit.
    output_root = _output_root(tmp_path)
    monkeypatch.setattr(sys, "argv", ["generate_planimation_vlm.py", "--output-root", str(output_root), "--render-limit", "1"])

    # When: the real CLI parser runs.
    with pytest.raises(SystemExit) as error:
        generate_planimation_vlm.main()

    # Then: it rejects the incompatible production request before building artifacts.
    assert error.value.code == 2
    assert not output_root.exists()


def test_generator_bounded_smoke_cli_writes_partial_manifest(tmp_path: Path) -> None:
    # Given: a temporary source fixture and an unreachable renderer endpoint.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    command = [sys.executable, "scripts/phase3/generate_planimation_vlm.py", "--dataset-root", str(source_root), "--output-root", str(output_root), "--domain", "grid", "--bucket", "easy", "--mode", "bounded-smoke", "--render-limit", "1", "--base-url", "http://127.0.0.1:9", "--timeout-seconds", "1", "--request-delay-seconds", "0"]

    # When: the real bounded CLI runs against the fixture root.
    result = subprocess.run(command, cwd=Path.cwd(), check=False, capture_output=True, text=True)

    # Then: it accepts the limit and writes an unmistakably partial artifact manifest.
    assert result.returncode == 0, result.stderr
    manifest = json.loads((output_root / "diagnostics" / "hybrid_output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["partial"] is True
    assert manifest["selection"]["render_limit"] == 1
    assert '"phase": "state_render_started"' in result.stderr
    assert '"phase": "state_render_finished"' in result.stderr


def test_validate_vlm_output_rejects_duplicate_and_split_leakage(tmp_path: Path) -> None:
    # Given: a complete production fixture with strict hybrid JSONL output.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))
    render_replay_states(output_root, renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir), config=RenderConfig(request_delay_seconds=0))
    build_vlm_records(output_root)
    duplicated = _rows(output_root / "step_vlm_train.jsonl")[0]
    duplicated["split"] = "dev"
    with (output_root / "step_vlm_train.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(duplicated) + "\n")

    # When: the emitted files are reloaded for strict output validation.
    errors = planimation_pairing.validate_vlm_output(output_root)

    # Then: duplicate IDs, split isolation, and manifest count reconciliation all fail.
    assert "duplicate VLM record_id" in errors
    assert "split leakage in step_vlm_train.jsonl" in errors
    assert "step record count reconciliation" in errors


def test_pair_manifest_marks_action_mismatch_and_recovery_excluded(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path, vfg_action="(move b a)", recovered=True)
    output_root = _output_root(tmp_path)
    config = PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"}))

    record = build_pairing_manifest([source_root], output_root, config=config)["records"][0]

    assert record["frame_alignment_status"] == "action_mismatch"
    assert record["training_eligible"] is False
    assert record["exclusion_reasons"] == ["recovery_trace"]


def test_pair_manifest_respects_trace_and_plan_limits(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    config = PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"}), max_plan_length=0, max_trace_chars=1)

    record = build_pairing_manifest([source_root], output_root, config=config)["records"][0]

    assert record["training_eligible"] is False
    assert record["exclusion_reasons"] == ["plan_length_exceeds_limit", "trace_size_exceeds_limit"]


def test_pair_manifest_freezes_jsonl_row_provenance_and_reloads_without_trace_file(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)

    record = build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"tiny"}), buckets=frozenset({"easy"})))["records"][0]

    assert record["source_root_id"] == source_root.name
    assert record["source_jsonl"] == "train.jsonl"
    assert record["source_line_index"] == 0
    assert len(record["source_record_sha256"]) == 64
    assert len(record["source_split_sha256"]) == 64
    assert len(record["source_root_sha256"]) == 64
    assert _load_source_example(record)["example_id"] == "example-0000"


def test_load_source_example_rejects_jsonl_source_drift(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    record = build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"tiny"}), buckets=frozenset({"easy"})))["records"][0]
    source_path = source_root / "train.jsonl"
    source_path.write_text(source_path.read_text(encoding="utf-8").replace("example-0000", "example-drifted"), encoding="utf-8")

    with pytest.raises(RuntimeError, match="source_snapshot_mismatch"):
        _load_source_example(record)


def test_pair_manifest_rejects_legacy_planner_identity(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path, planner="bfs")
    output_root = _output_root(tmp_path)

    with pytest.raises(RuntimeError, match="unsupported_active_planner: bfs"):
        build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"tiny"}), buckets=frozenset({"easy"})))


def test_pair_manifest_excludes_legacy_trace_contract_without_plan_level_fallback(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    source_path = source_root / "train.jsonl"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    del source["supervised_target"]["planner_trace"]["trace_contract_version"]
    source_path.write_text(json.dumps(source) + "\n", encoding="utf-8")

    record = build_pairing_manifest([source_root], _output_root(tmp_path), config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})))["records"][0]

    assert record["training_eligible"] is False
    assert record["exclusion_reasons"] == ["trace_contract_exclusion:missing_required_field: trace_contract_version"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("planner", "ff", "planner"),
        ("planner", "bfs", "unsupported_active_planner: bfs"),
        ("active_planner_id", "ff", "active_planner_id"),
        ("active_planner_id", "bfs", "unsupported_active_planner: bfs"),
        ("split", "dev", "split"),
        ("domain", "other", "domain"),
        ("instance_id", "other-instance", "instance_id"),
        ("plan_hash", "other-plan", "plan_hash"),
    ],
)
def test_load_source_example_rejects_manifest_identity_drift(tmp_path: Path, field: str, value: str, reason: str) -> None:
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    record = build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"tiny"}), buckets=frozenset({"easy"})))["records"][0]

    with pytest.raises(RuntimeError, match=reason):
        _load_source_example({**record, field: value})


def test_load_source_example_rejects_malformed_provenance_record(tmp_path: Path) -> None:
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    record = build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"tiny"}), buckets=frozenset({"easy"})))["records"][0]
    malformed = {key: value for key, value in record.items() if key != "source_root"}

    with pytest.raises(RuntimeError, match="source_snapshot_mismatch: malformed_provenance: source_root"):
        _load_source_example(malformed)


def test_validate_pairing_output_indexes_source_rows_once_per_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = _source_root(tmp_path)
    source_path = source_root / "train.jsonl"
    first = json.loads(source_path.read_text(encoding="utf-8"))
    second = {**first, "example_id": "example-0001", "plan_hash": "plan-hash-0001"}
    source_path.write_text("\n" + json.dumps(first) + "\n\n" + json.dumps(second) + "\n", encoding="utf-8")
    output_root = _output_root(tmp_path)
    records = build_pairing_manifest([source_root], output_root, config=PairingConfig(domains=frozenset({"tiny"}), buckets=frozenset({"easy"})))["records"]
    ordered_records = sorted(records, key=lambda record: record["source_line_index"])
    assert [record["source_line_index"] for record in ordered_records] == [1, 3]
    assert [_load_source_example(record)["example_id"] for record in ordered_records] == ["example-0000", "example-0001"]
    original_snapshot = planimation_pairing._source_root_snapshot
    original_rows = planimation_pairing._source_jsonl_rows
    snapshot_count = 0
    row_scan_count = 0

    def counted_snapshot(root: Path) -> dict[str, str]:
        nonlocal snapshot_count
        snapshot_count += 1
        return original_snapshot(root)

    def counted_rows(path: Path):
        nonlocal row_scan_count
        row_scan_count += 1
        yield from original_rows(path)

    monkeypatch.setattr(planimation_pairing, "_source_root_snapshot", counted_snapshot)
    monkeypatch.setattr(planimation_pairing, "_source_jsonl_rows", counted_rows)

    assert validate_pairing_output(output_root)["errors"] == []
    assert snapshot_count == 1
    assert row_scan_count == 1


def test_pairing_facade_forwards_source_index_hooks_to_manifest_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: source-index hooks replaced through the legacy facade.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    original_snapshot = planimation_pairing._source_root_snapshot
    original_rows = planimation_pairing._source_jsonl_rows
    snapshot_calls = 0
    row_calls = 0

    def counted_snapshot(root: Path) -> dict[str, str]:
        nonlocal snapshot_calls
        snapshot_calls += 1
        return original_snapshot(root)

    def counted_rows(path: Path):
        nonlocal row_calls
        row_calls += 1
        yield from original_rows(path)

    monkeypatch.setattr(planimation_pairing, "_source_root_snapshot", counted_snapshot)
    monkeypatch.setattr(planimation_pairing, "_source_jsonl_rows", counted_rows)

    # When: callers start the manifest workflow through its compatibility path.
    planimation_pairing.build_pairing_manifest(
        [source_root],
        output_root,
        config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})),
    )

    # Then: the implementation resolves the patched facade hooks.
    assert snapshot_calls == 1
    assert row_calls == 3


def test_pairing_facade_forwards_source_index_hooks_to_render_and_vlm_workflows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a manifest created before the facade's source-index hooks are patched.
    source_root = _source_root(tmp_path)
    output_root = _output_root(tmp_path)
    planimation_pairing.build_pairing_manifest(
        [source_root],
        output_root,
        config=PairingConfig(domains=frozenset({"grid"}), buckets=frozenset({"easy"})),
    )
    original_snapshot = planimation_pairing._source_root_snapshot
    original_rows = planimation_pairing._source_jsonl_rows
    snapshot_calls = 0
    row_calls = 0

    def counted_snapshot(root: Path) -> dict[str, str]:
        nonlocal snapshot_calls
        snapshot_calls += 1
        return original_snapshot(root)

    def counted_rows(path: Path):
        nonlocal row_calls
        row_calls += 1
        yield from original_rows(path)

    monkeypatch.setattr(planimation_pairing, "_source_root_snapshot", counted_snapshot)
    monkeypatch.setattr(planimation_pairing, "_source_jsonl_rows", counted_rows)

    # When: replay rendering and VLM construction execute through the public facade.
    planimation_pairing.render_replay_states(
        output_root,
        renderer=lambda _domain, _problem, _profile, cache_dir, _config: _render_artifacts(cache_dir),
        config=RenderConfig(request_delay_seconds=0),
    )
    planimation_pairing.build_vlm_records(output_root)

    # Then: both monkeypatched hooks reached the underlying source-backed operations.
    assert snapshot_calls == 2
    assert row_calls == 2


def _source_root(tmp_path: Path, *, vfg_action: str = "(move a b)", recovered: bool = False, planner: str = "gbfs") -> Path:
    root = Path("tmp") / f"phase3_pairing_{tmp_path.name}"
    if root.exists():
        shutil.rmtree(root)
    instance = root / "instances" / "tiny-train-easy-0000"
    render = instance / "render"
    frames = render / "frames"
    frames.mkdir(parents=True)
    domain = instance / "domain.pddl"
    problem = instance / "problem.pddl"
    profile = instance / "tiny_ap.pddl"
    domain.write_text(DOMAIN, encoding="utf-8")
    problem.write_text(PROBLEM, encoding="utf-8")
    profile.write_text("(define (animation-profile tiny))\n", encoding="utf-8")
    (frames / "frame_000.png").write_bytes(PNG)
    (frames / "frame_001.png").write_bytes(PNG)
    (render / "trace.vfg.json").write_text(json.dumps({"visualStages": [{"stageName": "Initial Stage"}, {"stageName": vfg_action}]}), encoding="utf-8")
    (render / "result.json").write_text(json.dumps({"render_profile_path": str(profile)}), encoding="utf-8")
    trace: dict[str, object] = {
        "trace_contract_version": "phase3_traversal_trace_v1",
        "algorithm": "greedy_best_first",
        "heuristic_source": "unsatisfied_goal_count",
        "expansion_count": 1,
        "visited_count": 2,
        "frontier_events": [{"event_kind": "expansion", "selected_state_atoms": ["(at a)", "(connected a b)"], "current_heuristic": {"heuristic_value": 1}, "successor_heuristics": [{"action": "(move a b)", "event_kind": "generation", "heuristic_value": 0, "is_goal": True}], "frontier_size_after": 0, "visited_count_after": 2, "tie_break_rule": "min_unsatisfied_goals_then_plan_length_then_generation_order"}],
    }
    if planner == "graphplan":
        trace = {
            "trace_contract_version": "phase3_traversal_trace_v1",
            "algorithm": "graphplan",
            "proposition_layers": [{"layer_index": 0, "propositions": ["(at a)", "(connected a b)"], "goal_present": False}],
            "action_layers": [{"layer_index": 0, "actions": ["(move a b)"], "mutex_pairs": [], "next_layer_index": 1}],
            "mutex_pairs": [],
            "extraction": {"approximation": "fixture", "goal_present_without_mutex": True, "mutex_scope": "action_level_only", "no_goods": [], "proposition_mutex_computed": False, "selected_goal_layer": 1, "selected_plan": ["(move a b)"], "source": "fixture"},
        }
    if recovered:
        trace["plan_recovery"] = {"is_exact_gbfs": False}
    example = {
        "schema_version": "phase3_supervised_planning_v1",
        "example_id": "example-0000",
        "domain": "grid",
        "instance_id": "tiny-train-easy-0000",
        "split": "train",
        "planner": planner,
        "plan_hash": "plan-hash",
        "trace_fidelity": "success_full_trace",
        "vision_supervision_available": True,
        "model_facing": {"domain_source": relpath(domain), "problem_source": relpath(problem), "vision": {"trace_path": relpath(render / "trace.vfg.json"), "frame_paths": [relpath(frames / "frame_000.png"), relpath(frames / "frame_001.png")]}},
        "supervised_target": {"plan": ["(move a b)"], "planner_trace": trace, "replay_transitions": [{"step_index": 0, "action": "(move a b)", "state_before": ["(at a)", "(connected a b)"], "state_after": ["(at b)", "(connected a b)"]}]},
        "evaluation_metadata": {},
    }
    (root / "train.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (root / "train.jsonl").write_text(json.dumps(example) + "\n", encoding="utf-8")
    for split in ("dev", "test"):
        (root / f"{split}.jsonl").write_text("", encoding="utf-8")
    diagnostics = root / "diagnostics"
    diagnostics.mkdir()
    accounting = {"instance_id": example["instance_id"], "bucket": "easy"}
    (diagnostics / "instance_accounting.jsonl").write_text(json.dumps(accounting) + "\n", encoding="utf-8")
    return root


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _draft202012_object_schema_errors(instance, schema, path: str = "$") -> list[str]:
    errors: list[str] = []
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: const mismatch")
    match schema.get("type"):
        case "object":
            if not isinstance(instance, dict):
                return [f"{path}: expected object"]
            required = schema.get("required", [])
            properties = schema.get("properties", {})
            for field in required:
                if field not in instance:
                    errors.append(f"{path}.{field}: required property")
            if schema.get("additionalProperties") is False:
                for field in instance:
                    if field not in properties:
                        errors.append(f"{path}.{field}: additional property")
            for field, field_schema in properties.items():
                if field in instance:
                    errors.extend(_draft202012_object_schema_errors(instance[field], field_schema, f"{path}.{field}"))
        case "string":
            if not isinstance(instance, str):
                errors.append(f"{path}: expected string")
        case "integer":
            if not isinstance(instance, int) or isinstance(instance, bool):
                errors.append(f"{path}: expected integer")
        case "array":
            if not isinstance(instance, list):
                return [f"{path}: expected array"]
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(instance):
                    errors.extend(_draft202012_object_schema_errors(item, item_schema, f"{path}[{index}]"))
        case ["string", "null"]:
            if instance is not None and not isinstance(instance, str):
                errors.append(f"{path}: expected string or null")
        case None:
            pass
        case _:
            errors.append(f"{path}: unsupported test schema type")
    return errors


def _output_root(tmp_path: Path) -> Path:
    root = Path("tmp") / f"phase3_pairing_output_{tmp_path.name}"
    if root.exists():
        shutil.rmtree(root)
    return root
