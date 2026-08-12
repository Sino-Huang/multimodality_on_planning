from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scripts.phase3.cgas_candidate_accounting import PlannerInput
from scripts.phase3.cgas_pilot_expansion_index import state_sha256
from scripts.phase3.planimation_pairing_contracts import RenderConfig, RendererResult, StateRenderer

_MINIMAL_DOMAIN = (
    "(define (domain blocksworld-4ops) (:requirements :strips) "
    "(:predicates (clear ?x) (on-table ?x) (arm-empty) (holding ?x) (on ?x ?y)))"
)

_BUNDLE_02_SEMANTIC_INPUT = """(define (problem 0322c69e499f0e2ba7161d25787a1260a275bd22382438a7f48e51e9da3737c4-\
00014e0bdfd513580c65f03b94e5c0a1)
  (:domain blocksworld-4ops)
  (:objects b00 b01 b02 b03 b04 b05 b06 b07)
  (:init
  (arm-empty)
  (clear b03)
  (clear b04)
  (clear b07)
  (on b01 b00)
  (on b02 b01)
  (on b03 b02)
  (on b04 b05)
  (on b07 b06)
  (on-table b00)
  (on-table b05)
  (on-table b06)
)
  (:goal (and
    (on b01 b00)
    (on b02 b01)
    (on b04 b03)
    (on b05 b04)
    (on b07 b06)
  ))
)
"""

_BUNDLE_03_GOLDEN = (
    b"\n\n"
    b"(define (problem cgas-phase3-regression-replay-03-canonicalized-pilot-delta)\n"
    b"(:domain blocksworld-4ops)\n"
    b"(:objects b1 b2 b3 b4 b5 b6 b7 b8 )\n"
    b"(:init\n"
    b"  (arm-empty)\n"
    b"  (clear b4)\n"
    b"  (clear b5)\n"
    b"  (clear b8)\n"
    b"  (on b2 b1)\n"
    b"  (on b3 b2)\n"
    b"  (on b4 b3)\n"
    b"  (on b5 b6)\n"
    b"  (on b8 b7)\n"
    b"  (on-table b1)\n"
    b"  (on-table b6)\n"
    b"  (on-table b7)\n"
    b")\n"
    b"(:goal\n"
    b"(and\n"
    b"(on b2 b1)\n"
    b"(on b3 b2)\n"
    b"(on b5 b4)\n"
    b"(on b6 b5)\n"
    b"(on b8 b7))\n"
    b")\n"
    b")\n"
    b"\n"
    b"\n"
)

_TWELVE_OBJECT_INPUT = """(define (problem twelve-object-fixture)
  (:domain blocksworld-4ops)
  (:objects b00 b01 b02 b03 b04 b05 b06 b07 b08 b09 b10 b11)
  (:init
  (clear b05)
  (clear b07)
  (clear b08)
  (clear b10)
  (holding b09)
  (on b01 b00)
  (on b02 b01)
  (on b04 b03)
  (on b05 b04)
  (on b07 b06)
  (on b10 b11)
  (on b11 b02)
  (on-table b00)
  (on-table b03)
  (on-table b06)
  (on-table b08)
)
  (:goal (and
    (on b01 b00)
    (on b10 b11)
    (holding b09)
  ))
)
"""

_LEGACY_B1_INPUT = """(define (problem legacy-fixture)
  (:domain blocksworld-4ops)
  (:objects b1 b2 b3)
  (:init
  (arm-empty)
  (on b1 b2)
  (on-table b1)
  (on-table b3)
)
  (:goal (and (on b1 b2)))
)
"""


def _jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8"
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    from scripts.phase3.cgas_candidate_accounting import planner_input_record
    from scripts.phase3.cgas_candidate_space import build_candidate

    atoms = ["(arm-empty)", "(clear b00)", "(on-table b00)"]
    digest = state_sha256(atoms)
    candidate = build_candidate(1, 0)
    planner = PlannerInput(1, 0, "emitted", candidate.candidate_id, 0, candidate)
    source = planner_input_record(planner)
    source_digest = hashlib.sha256(
        (json.dumps(source, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()
    ).hexdigest()
    index_row: dict[str, object] = {
        "schema_version": "cgas_phase3_pilot_expansion_index_v1",
        "candidate_id": candidate.candidate_id,
        "instance_id": candidate.candidate_id,
        "object_count": 1,
        "raw_rank": 0,
        "role": "train",
        "planner": "bfs",
        "row_id": "row-0",
        "event_sequence": 0,
        "event_sha256": hashlib.sha256(b"event-row-0").hexdigest(),
        "trace_path": "traces/row-0.jsonl",
        "trace_stream_sha256": hashlib.sha256(b"stream-row-0").hexdigest(),
        "trace_contract_id": "cgas_trace_contract_v3",
        "trace_contract_sha256": hashlib.sha256(b"contract").hexdigest(),
        "replay_plan_member": True,
        "replay_step_index": 0,
        "source_record_sha256": source_digest,
        "state_atoms": atoms,
        "state_sha256": digest,
    }
    request_row = {"partitions": ["train|1|bfs"], "state_atoms": atoms, "state_sha256": digest}
    index = tmp_path / "index.jsonl"
    request = tmp_path / "request.jsonl"
    _jsonl(index, [index_row])
    _jsonl(request, [request_row])
    return index, request, index_row


def _fake_renderer(counter: list[str]) -> StateRenderer:
    def render(_domain: Path, _problem: Path, _profile: Path, cache: Path, _config: RenderConfig) -> RendererResult:
        from PIL import Image

        counter.append(cache.name)
        frames = cache / "frames"
        frames.mkdir(parents=True, exist_ok=True)
        frame = frames / "frame_000.png"
        image = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        for x in range(20, 60):
            for y in range(40, 80):
                image.putpixel((x, y), (255, 0, 0, 255))
        image.save(frame)
        trace = cache / "trace.vfg.json"
        trace.write_text(
            json.dumps(
                {
                    "visualStages": [
                        {
                            "stageName": "Initial Stage",
                            "visualSprites": [{"name": "token", "minX": 0.2, "maxX": 0.6, "minY": 0.2, "maxY": 0.6}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return {
            "status": "success",
            "attempts": 1,
            "frame_path": str(frame),
            "trace_path": str(trace),
            "used_pddl_url": "fixture",
        }

    return render


def test_rejects_request_digest_mismatch_before_render(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    row = json.loads(request.read_text())
    row["state_sha256"] = "0" * 64
    _jsonl(request, [row])
    calls: list[str] = []
    with pytest.raises(PilotRenderError, match="request_state_hash_mismatch"):
        render_missing_states(
            PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out"), renderer=_fake_renderer(calls)
        )
    assert calls == []


def test_rejects_ambiguous_state_source_before_render(tmp_path: Path) -> None:
    from scripts.phase3.cgas_candidate_accounting import planner_input_record
    from scripts.phase3.cgas_candidate_space import build_candidate
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, row = _fixture(tmp_path)
    other_candidate = build_candidate(2, 0)
    other_source = planner_input_record(
        PlannerInput(2, 0, "emitted", other_candidate.candidate_id, 0, other_candidate)
    )
    other = {
        **row,
        "candidate_id": other_candidate.candidate_id,
        "instance_id": other_candidate.candidate_id,
        "object_count": 2,
        "raw_rank": 0,
        "row_id": "row-1",
        "source_record_sha256": hashlib.sha256(
            (
                json.dumps(
                    other_source,
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        ).hexdigest(),
    }
    _jsonl(index, [row, other])
    domain = tmp_path / "domain.pddl"
    domain.write_text("domain", encoding="utf-8")
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    calls: list[str] = []
    with pytest.raises(PilotRenderError, match="request_state_source_ambiguous"):
        render_missing_states(
            PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile),
            renderer=_fake_renderer(calls),
        )
    assert calls == []


def test_mapping_selects_one_ambiguous_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_candidate_accounting import planner_input_record
    from scripts.phase3.cgas_candidate_space import build_candidate
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderRequest, render_missing_states
    from scripts.phase3.cgas_pilot_representative_mapping import build_representative_mapping

    index, request, row = _fixture(tmp_path)
    other_candidate = build_candidate(2, 0)
    other_source = planner_input_record(
        PlannerInput(2, 0, "emitted", other_candidate.candidate_id, 0, other_candidate)
    )
    other = {
        **row,
        "candidate_id": other_candidate.candidate_id,
        "instance_id": other_candidate.candidate_id,
        "object_count": 2,
        "raw_rank": 0,
        "row_id": "row-1",
        "event_sha256": hashlib.sha256(b"event-row-1").hexdigest(),
        "trace_path": "traces/row-1.jsonl",
        "trace_stream_sha256": hashlib.sha256(b"stream-row-1").hexdigest(),
        "replay_plan_member": False,
        "replay_step_index": None,
        "source_record_sha256": hashlib.sha256(
            (
                json.dumps(
                    other_source,
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        ).hexdigest(),
    }
    _jsonl(index, [other, row])
    result = build_representative_mapping(request, index, tmp_path / "mapping")
    domain = tmp_path / "domain.pddl"
    domain.write_text("domain", encoding="utf-8")
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    problem = (
        "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) "
        "(:init (arm-empty)) (:goal (and)))"
    )
    monkeypatch.setattr("scripts.phase3.cgas_pilot_planimation_adapter._candidate_problem", lambda _row: problem)
    calls: list[str] = []
    rendered = render_missing_states(
        PilotRenderRequest(
            tmp_path,
            request,
            index,
            tmp_path / "outputs/out",
            domain,
            profile,
            representative_mapping_path=result.mapping_path,
            expected_mapping_sha256=result.mapping_sha256,
            expected_mapping_count=1,
        ),
        renderer=_fake_renderer(calls),
    )
    record = json.loads(rendered.manifest_path.read_text())
    assert record["source_row_id"] == "row-0"
    assert record["representative_mapping_sha256"] == result.mapping_sha256


@pytest.mark.parametrize(
    ("mutation", "expected_rule"),
    [
        (
            lambda row: row["selection"].update({"policy_id": "other_policy_v1"}),
            "representative_mapping_policy_mismatch",
        ),
        (
            lambda row: row.update({"schema_version": "cgas_phase3_pilot_wrong_schema"}),
            "representative_mapping_schema_mismatch",
        ),
        (lambda row: row.update({"state_atoms": ["(wrong)"]}), "representative_mapping_state_mismatch"),
        (
            lambda row: row["bindings"].update({"request_sha256": "0" * 64}),
            "representative_mapping_bindings_mismatch",
        ),
        (
            lambda row: row["representative"].update({"row_id": "not-in-index"}),
            "representative_mapping_source_mismatch",
        ),
    ],
)
def test_mapping_binding_fast_fails_before_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Callable[[dict[str, object]], None],
    expected_rule: str,
) -> None:
    from scripts.phase3.cgas_candidate_accounting import planner_input_record
    from scripts.phase3.cgas_candidate_space import build_candidate
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states
    from scripts.phase3.cgas_pilot_representative_mapping import build_representative_mapping

    index, request, row = _fixture(tmp_path)
    other_candidate = build_candidate(2, 0)
    other_source = planner_input_record(
        PlannerInput(2, 0, "emitted", other_candidate.candidate_id, 0, other_candidate)
    )
    other = {
        **row,
        "candidate_id": other_candidate.candidate_id,
        "instance_id": other_candidate.candidate_id,
        "object_count": 2,
        "raw_rank": 0,
        "row_id": "row-1",
        "event_sha256": hashlib.sha256(b"event-row-1").hexdigest(),
        "trace_path": "traces/row-1.jsonl",
        "trace_stream_sha256": hashlib.sha256(b"stream-row-1").hexdigest(),
        "replay_plan_member": False,
        "replay_step_index": None,
        "source_record_sha256": hashlib.sha256(
            (
                json.dumps(
                    other_source,
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        ).hexdigest(),
    }
    _jsonl(index, [other, row])
    result = build_representative_mapping(request, index, tmp_path / "mapping")
    mapping_row = json.loads(result.mapping_path.read_text())
    mutation(mapping_row)
    mutated = json.dumps(mapping_row, sort_keys=True, separators=(",", ":")) + "\n"
    result.mapping_path.write_text(mutated, encoding="utf-8")
    domain = tmp_path / "domain.pddl"
    domain.write_text("domain", encoding="utf-8")
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    calls: list[str] = []
    with pytest.raises(PilotRenderError, match=expected_rule):
        render_missing_states(
            PilotRenderRequest(
                tmp_path,
                request,
                index,
                tmp_path / "outputs/out",
                domain,
                profile,
                representative_mapping_path=result.mapping_path,
            ),
            renderer=_fake_renderer(calls),
        )
    assert calls == []


def test_mapping_binding_mismatch_and_count_mismatch_fast_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.phase3.cgas_candidate_accounting import planner_input_record
    from scripts.phase3.cgas_candidate_space import build_candidate
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states
    from scripts.phase3.cgas_pilot_representative_mapping import build_representative_mapping

    index, request, row = _fixture(tmp_path)
    other_candidate = build_candidate(2, 0)
    other_source = planner_input_record(
        PlannerInput(2, 0, "emitted", other_candidate.candidate_id, 0, other_candidate)
    )
    other = {
        **row,
        "candidate_id": other_candidate.candidate_id,
        "instance_id": other_candidate.candidate_id,
        "object_count": 2,
        "raw_rank": 0,
        "row_id": "row-1",
        "event_sha256": hashlib.sha256(b"event-row-1").hexdigest(),
        "trace_path": "traces/row-1.jsonl",
        "trace_stream_sha256": hashlib.sha256(b"stream-row-1").hexdigest(),
        "replay_plan_member": False,
        "replay_step_index": None,
        "source_record_sha256": hashlib.sha256(
            (
                json.dumps(
                    other_source,
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        ).hexdigest(),
    }
    _jsonl(index, [other, row])
    result = build_representative_mapping(request, index, tmp_path / "mapping")
    domain = tmp_path / "domain.pddl"
    domain.write_text("domain", encoding="utf-8")
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    calls: list[str] = []
    with pytest.raises(PilotRenderError, match="representative_mapping_binding_mismatch"):
        render_missing_states(
            PilotRenderRequest(
                tmp_path,
                request,
                index,
                tmp_path / "outputs/out",
                domain,
                profile,
                representative_mapping_path=result.mapping_path,
                expected_mapping_sha256="0" * 64,
            ),
            renderer=_fake_renderer(calls),
        )
    assert calls == []
    calls.clear()
    with pytest.raises(PilotRenderError, match="representative_mapping_count_mismatch"):
        render_missing_states(
            PilotRenderRequest(
                tmp_path,
                request,
                index,
                tmp_path / "outputs/out",
                domain,
                profile,
                representative_mapping_path=result.mapping_path,
                expected_mapping_count=999,
            ),
            renderer=_fake_renderer(calls),
        )
    assert calls == []


def test_mapping_dropped_row_fast_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_candidate_accounting import planner_input_record
    from scripts.phase3.cgas_candidate_space import build_candidate
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states
    from scripts.phase3.cgas_pilot_representative_mapping import build_representative_mapping

    index, request, row = _fixture(tmp_path)
    other_candidate = build_candidate(2, 0)
    other_source = planner_input_record(
        PlannerInput(2, 0, "emitted", other_candidate.candidate_id, 0, other_candidate)
    )
    other = {
        **row,
        "candidate_id": other_candidate.candidate_id,
        "instance_id": other_candidate.candidate_id,
        "object_count": 2,
        "raw_rank": 0,
        "row_id": "row-1",
        "event_sha256": hashlib.sha256(b"event-row-1").hexdigest(),
        "trace_path": "traces/row-1.jsonl",
        "trace_stream_sha256": hashlib.sha256(b"stream-row-1").hexdigest(),
        "replay_plan_member": False,
        "replay_step_index": None,
        "source_record_sha256": hashlib.sha256(
            (
                json.dumps(
                    other_source,
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode()
        ).hexdigest(),
    }
    _jsonl(index, [other, row])
    result = build_representative_mapping(request, index, tmp_path / "mapping")
    result.mapping_path.write_text("", encoding="utf-8")
    domain = tmp_path / "domain.pddl"
    domain.write_text("domain", encoding="utf-8")
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    calls: list[str] = []
    with pytest.raises(PilotRenderError, match="representative_mapping_state_set_mismatch"):
        render_missing_states(
            PilotRenderRequest(
                tmp_path,
                request,
                index,
                tmp_path / "outputs/out",
                domain,
                profile,
                representative_mapping_path=result.mapping_path,
            ),
            renderer=_fake_renderer(calls),
        )
    assert calls == []


def test_renderer_receives_bound_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "bound-profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    problem = (
        "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) "
        "(:init (arm-empty) (clear b00) (on-table b00)) (:goal (and)))\n"
    )
    monkeypatch.setattr("scripts.phase3.cgas_pilot_planimation_adapter._candidate_problem", lambda _row: problem)
    observed: list[Path] = []
    fake = _fake_renderer([])

    def capture(
        domain_path: Path, problem_path: Path, profile_path: Path, cache: Path, config: RenderConfig
    ) -> RendererResult:
        observed.append(profile_path)
        return fake(domain_path, problem_path, profile_path, cache, config)

    render_missing_states(
        PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile), renderer=capture
    )
    assert observed == [profile.resolve()]


def test_renders_digest_bound_manifest_and_resumes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    problem = (
        "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) "
        "(:init (arm-empty) (clear b00) (on-table b00)) (:goal (and)))\n"
    )
    monkeypatch.setattr("scripts.phase3.cgas_pilot_planimation_adapter._candidate_problem", lambda _row: problem)
    calls: list[str] = []
    render_request = PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile)
    first = render_missing_states(render_request, renderer=_fake_renderer(calls))
    second = render_missing_states(render_request, renderer=_fake_renderer(calls))
    rows = [json.loads(line) for line in first.manifest_path.read_text().splitlines()]
    assert first.counts == {
        "requested": 1,
        "processed": 1,
        "succeeded": 1,
        "failed": 0,
        "duplicate": 0,
        "collision": 0,
        "remaining": 0,
    }
    assert second.counts["processed"] == 0
    assert len(calls) == 1
    assert rows[0]["state_sha256"] == json.loads(request.read_text())["state_sha256"]
    assert rows[0]["transition"]["state_before"] == json.loads(request.read_text())["state_atoms"]
    assert len(rows[0]["png_sha256"]) == 64


def test_counts_identical_request_duplicates_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    request.write_text(request.read_text() * 2, encoding="utf-8")
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.phase3.cgas_pilot_planimation_adapter._candidate_problem",
        lambda _row: (
            "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) (:init (arm-empty)) (:goal (and)))"
        ),
    )
    calls: list[str] = []
    result = render_missing_states(
        PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile),
        renderer=_fake_renderer(calls),
    )
    assert result.counts["requested"] == 1
    assert result.counts["duplicate"] == 1
    assert len(calls) == 1


def test_rejects_run_contract_drift_on_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.phase3.cgas_pilot_planimation_adapter._candidate_problem",
        lambda _row: (
            "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) (:init (arm-empty)) (:goal (and)))"
        ),
    )
    render_request = PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile)
    render_missing_states(render_request, renderer=_fake_renderer([]))
    profile.write_text("changed", encoding="utf-8")
    with pytest.raises(PilotRenderError, match="run_contract_mismatch"):
        render_missing_states(render_request, renderer=_fake_renderer([]))


def test_rejects_default_renderer_dependency_drift_on_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_adapter as adapter

    index, request, _ = _fixture(tmp_path)
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    monkeypatch.setattr(
        adapter,
        "_candidate_problem",
        lambda _row: (
            "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) (:init (arm-empty)) (:goal (and)))"
        ),
    )
    render_request = adapter.PilotRenderRequest(
        tmp_path,
        request,
        index,
        tmp_path / "outputs/out",
        domain,
        profile,
    )
    adapter.render_missing_states(render_request, renderer=_fake_renderer([]))
    original = adapter.file_sha256

    def changed_digest(path: Path) -> str:
        if path.name == "planimation_phase1_client.py":
            return "0" * 64
        return original(path)

    monkeypatch.setattr(adapter, "file_sha256", changed_digest)
    with pytest.raises(adapter.PilotRenderError, match="run_contract_mismatch"):
        adapter.render_missing_states(render_request, renderer=_fake_renderer([]))


def test_rejects_output_root_outside_repository(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(PilotRenderError, match="output_root_invalid"):
        render_missing_states(PilotRenderRequest(repository, request, index, tmp_path / "outside"))


def test_rejects_output_root_symlink_escape(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    repository = tmp_path / "repository"
    (repository / "outputs").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    output = repository / "outputs/render"
    output.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PilotRenderError, match="output_root_invalid"):
        render_missing_states(PilotRenderRequest(repository, request, index, output))


def test_rejects_candidate_identity_drift_before_render(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, row = _fixture(tmp_path)
    row["candidate_id"] = "0" * 64
    _jsonl(index, [row])
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    calls: list[str] = []
    with pytest.raises(PilotRenderError, match="candidate_identity_mismatch"):
        render_missing_states(
            PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile),
            renderer=_fake_renderer(calls),
        )
    assert calls == []


def test_rejects_unsafe_instance_identity_before_render(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, row = _fixture(tmp_path)
    row["instance_id"] = "../../outside"
    _jsonl(index, [row])
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    with pytest.raises(PilotRenderError, match="instance_identity_mismatch"):
        render_missing_states(PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile))
    assert not (tmp_path / "outside").exists()


def test_rejects_source_record_digest_drift_before_render(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, row = _fixture(tmp_path)
    row["source_record_sha256"] = "0" * 64
    _jsonl(index, [row])
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    calls: list[str] = []
    with pytest.raises(PilotRenderError, match="source_record_hash_mismatch"):
        render_missing_states(
            PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile),
            renderer=_fake_renderer(calls),
        )
    assert calls == []


def test_persists_digest_bound_run_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.phase3.cgas_pilot_planimation_adapter._candidate_problem",
        lambda _row: (
            "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) (:init (arm-empty)) (:goal (and)))"
        ),
    )
    output = tmp_path / "outputs/out"
    result = render_missing_states(
        PilotRenderRequest(tmp_path, request, index, output, domain, profile), renderer=_fake_renderer([])
    )
    contract = json.loads((output / "diagnostics/run-contract.json").read_text())
    report = json.loads(result.report_path.read_text())
    assert contract["request_sha256"] == hashlib.sha256(request.read_bytes()).hexdigest()
    assert contract["expansion_index_sha256"] == hashlib.sha256(index.read_bytes()).hexdigest()
    assert contract["domain_sha256"] == hashlib.sha256(domain.read_bytes()).hexdigest()
    assert contract["profile_sha256"] == hashlib.sha256(profile.read_bytes()).hexdigest()
    assert report["resume_command"].startswith(
        "source ~/cd_vlaplan && python -m scripts.phase3.cgas_pilot_planimation_adapter"
    )


def test_rejects_expected_production_binding_mismatch(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    with pytest.raises(PilotRenderError, match="request_binding_mismatch"):
        render_missing_states(
            PilotRenderRequest(
                tmp_path,
                request,
                index,
                tmp_path / "outputs/out",
                expected_request_sha256="0" * 64,
                expected_request_count=1,
            )
        )


def test_rejects_conflicting_successful_resume_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.phase3.cgas_pilot_planimation_adapter._candidate_problem",
        lambda _row: (
            "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) (:init (arm-empty)) (:goal (and)))"
        ),
    )
    render_request = PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile)
    result = render_missing_states(render_request, renderer=_fake_renderer([]))
    record = json.loads(result.manifest_path.read_text())
    record["png_sha256"] = "0" * 64
    checkpoint = result.manifest_path.with_name("render-checkpoint.jsonl")
    with checkpoint.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    with pytest.raises(PilotRenderError, match="manifest_success_collision"):
        render_missing_states(render_request, renderer=_fake_renderer([]))


def test_retries_prior_failed_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.phase3.cgas_pilot_planimation_adapter._candidate_problem",
        lambda _row: (
            "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) (:init (arm-empty)) (:goal (and)))"
        ),
    )
    render_request = PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile)

    def temporary_failure(
        _domain: Path, _problem: Path, _profile: Path, _cache: Path, _config: RenderConfig
    ) -> RendererResult:
        return {"status": "failed", "attempts": 1, "message": "temporary"}

    render_missing_states(render_request, renderer=temporary_failure)
    calls: list[str] = []
    result = render_missing_states(render_request, renderer=_fake_renderer(calls))
    assert result.counts["processed"] == 1
    assert result.counts["succeeded"] == 1
    assert len(calls) == 1


def test_rejects_modified_prior_png(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    problem = (
        "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) "
        "(:init (arm-empty) (clear b00) (on-table b00)) (:goal (and)))\n"
    )
    monkeypatch.setattr("scripts.phase3.cgas_pilot_planimation_adapter._candidate_problem", lambda _row: problem)
    render_request = PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile)
    first = render_missing_states(render_request, renderer=_fake_renderer([]))
    record = json.loads(first.manifest_path.read_text())
    Path(record["frame_path"]).write_bytes(b"modified")
    with pytest.raises(PilotRenderError, match="manifest_png_hash_mismatch"):
        render_missing_states(render_request, renderer=_fake_renderer([]))


def test_failed_renderer_is_not_promoted_from_unrelated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.cgas_candidate_space import build_candidate
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderRequest, render_missing_states

    index, request, row = _fixture(tmp_path)
    row["candidate_id"] = build_candidate(1, 0).candidate_id
    _jsonl(index, [row])
    domain = tmp_path / "domain.pddl"
    domain.write_text(
        "(define (domain blocksworld-4ops) (:requirements :strips) (:predicates (arm-empty) (clear ?x) (on-table ?x)))",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    unrelated = tmp_path / "outputs/out/state_cache/unrelated/frames"
    unrelated.mkdir(parents=True)
    (unrelated / "frame_000.png").write_bytes(b"not-this-render")
    (unrelated.parent / "trace.vfg.json").write_text('{"visualStages":[]}', encoding="utf-8")
    monkeypatch.setattr(
        "scripts.phase3.cgas_pilot_planimation_adapter._candidate_problem",
        lambda _row: (
            "(define (problem fixture) (:domain blocksworld-4ops) (:objects b00) (:init (arm-empty)) (:goal (and)))"
        ),
    )

    def fail(_domain: Path, _problem: Path, _profile: Path, _cache: Path, _config: RenderConfig) -> RendererResult:
        return {"status": "failed", "attempts": 1, "message": "expected"}

    result = render_missing_states(
        PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile), renderer=fail
    )
    assert result.counts["failed"] == 1
    assert result.counts["succeeded"] == 0


def test_replay_alignment_preserves_authoritative_rows(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_replay_alignment import build_replay_alignment

    index, _request, row = _fixture(tmp_path)
    cache = tmp_path / "render"
    rendered = _fake_renderer([])(tmp_path / "domain", tmp_path / "problem", tmp_path / "profile", cache, RenderConfig())
    png = Path(str(rendered.get("frame_path")))
    trace = Path(str(rendered.get("trace_path")))
    manifest = tmp_path / "manifest.jsonl"
    _jsonl(
        manifest,
        [
            {
                "status": "success",
                "state_sha256": row["state_sha256"],
                "png_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
                "frame_path": str(png),
                "vfg_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
                "trace_path": str(trace),
            }
        ],
    )
    result = build_replay_alignment(
        index,
        manifest,
        tmp_path / "alignment",
        expected_authoritative_count=1,
        expected_index_sha256=hashlib.sha256(index.read_bytes()).hexdigest(),
    )
    records = [json.loads(line) for line in result.output_path.read_text().splitlines()]
    assert result.counts == {"authoritative": 1, "accepted": 1, "missing": 0, "duplicate": 0, "collision": 0}
    assert records[0]["source_row_id"] == "row-0"
    assert records[0]["replay_step_index"] == 0


def test_replay_alignment_rejects_missing_render(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_replay_alignment import ReplayAlignmentError, build_replay_alignment

    index, _request, _row = _fixture(tmp_path)
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("", encoding="utf-8")
    with pytest.raises(ReplayAlignmentError, match="missing_replay_render"):
        build_replay_alignment(
            index,
            manifest,
            tmp_path / "alignment",
            expected_authoritative_count=1,
            expected_index_sha256=hashlib.sha256(index.read_bytes()).hexdigest(),
        )


def test_replay_alignment_enforces_frozen_bindings_by_default(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_replay_alignment import ReplayAlignmentError, build_replay_alignment

    index, _request, _row = _fixture(tmp_path)
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("", encoding="utf-8")
    with pytest.raises(ReplayAlignmentError, match="authoritative_count_mismatch"):
        build_replay_alignment(index, manifest, tmp_path / "alignment")


def test_replay_alignment_rejects_artifact_outside_render_root(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_replay_alignment import ReplayAlignmentError, build_replay_alignment

    index, _request, row = _fixture(tmp_path)
    render_root = tmp_path / "render-root"
    manifest = render_root / "diagnostics" / "state_render_manifest.jsonl"
    outside = tmp_path / "outside"
    rendered = _fake_renderer([])(
        tmp_path / "domain", tmp_path / "problem", tmp_path / "profile", outside, RenderConfig()
    )
    png = Path(str(rendered.get("frame_path")))
    trace = Path(str(rendered.get("trace_path")))
    _jsonl(
        manifest,
        [
            {
                "status": "success",
                "state_sha256": row["state_sha256"],
                "png_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
                "frame_path": str(png),
                "vfg_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
                "trace_path": str(trace),
            }
        ],
    )
    with pytest.raises(ReplayAlignmentError, match="render_artifact_path_invalid"):
        build_replay_alignment(
            index,
            manifest,
            tmp_path / "alignment",
            expected_authoritative_count=1,
            expected_index_sha256=hashlib.sha256(index.read_bytes()).hexdigest(),
        )


def test_production_resume_command_preserves_frozen_contract(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import (
        PRODUCTION_INDEX_COUNT,
        PRODUCTION_INDEX_SHA256,
        PRODUCTION_MAPPING_COUNT,
        PRODUCTION_MAPPING_SHA256,
        PRODUCTION_REQUEST_COUNT,
        PRODUCTION_REQUEST_SHA256,
        PilotRenderRequest,
        _resume_command,
    )

    mapping = tmp_path / "mapping.jsonl"
    mapping.write_text("", encoding="utf-8")
    request = PilotRenderRequest(
        tmp_path,
        tmp_path / "request.jsonl",
        tmp_path / "index.jsonl",
        tmp_path / "output",
        expected_request_sha256=PRODUCTION_REQUEST_SHA256,
        expected_request_count=PRODUCTION_REQUEST_COUNT,
        expected_index_sha256=PRODUCTION_INDEX_SHA256,
        expected_index_count=PRODUCTION_INDEX_COUNT,
        representative_mapping_path=mapping,
        expected_mapping_sha256=PRODUCTION_MAPPING_SHA256,
        expected_mapping_count=PRODUCTION_MAPPING_COUNT,
        config=RenderConfig(timeout_seconds=17, request_delay_seconds=0.0, max_attempts=1),
    )
    command = _resume_command(request, tmp_path / "domain.pddl", tmp_path / "profile.pddl")
    assert "--production-contract" in command
    assert f"--representative-mapping-path {mapping}" in command
    assert f"--expected-mapping-sha256 {PRODUCTION_MAPPING_SHA256}" in command
    assert f"--expected-mapping-count {PRODUCTION_MAPPING_COUNT}" in command
    assert "--timeout-seconds 17" in command
    assert "--request-delay-seconds 0.0" in command
    assert "--max-attempts 1" in command


def test_production_resume_command_without_mapping_omits_contract(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import (
        PRODUCTION_INDEX_COUNT,
        PRODUCTION_INDEX_SHA256,
        PRODUCTION_REQUEST_COUNT,
        PRODUCTION_REQUEST_SHA256,
        PilotRenderRequest,
        _resume_command,
    )

    request = PilotRenderRequest(
        tmp_path,
        tmp_path / "request.jsonl",
        tmp_path / "index.jsonl",
        tmp_path / "output",
        expected_request_sha256=PRODUCTION_REQUEST_SHA256,
        expected_request_count=PRODUCTION_REQUEST_COUNT,
        expected_index_sha256=PRODUCTION_INDEX_SHA256,
        expected_index_count=PRODUCTION_INDEX_COUNT,
        config=RenderConfig(timeout_seconds=17, request_delay_seconds=0.0, max_attempts=1),
    )
    command = _resume_command(request, tmp_path / "domain.pddl", tmp_path / "profile.pddl")
    assert "--production-contract" not in command


def test_production_resume_command_with_mapping_but_off_contract_omits_contract(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import (
        PRODUCTION_REQUEST_SHA256,
        PilotRenderRequest,
        _resume_command,
    )

    mapping = tmp_path / "mapping.jsonl"
    mapping.write_text("", encoding="utf-8")
    request = PilotRenderRequest(
        tmp_path,
        tmp_path / "request.jsonl",
        tmp_path / "index.jsonl",
        tmp_path / "output",
        expected_request_sha256=PRODUCTION_REQUEST_SHA256,
        representative_mapping_path=mapping,
        config=RenderConfig(timeout_seconds=17, request_delay_seconds=0.0, max_attempts=1),
    )
    command = _resume_command(request, tmp_path / "domain.pddl", tmp_path / "profile.pddl")
    assert "--production-contract" not in command


def test_cli_rejects_mapping_expectations_without_mapping_path() -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import main

    base = [
        "request.jsonl",
        "index.jsonl",
        "--repository-root",
        ".",
        "--output-root",
        "tmp/out",
        "--domain-path",
        "domain.pddl",
        "--profile-path",
        "profile.pddl",
    ]
    with pytest.raises(SystemExit):
        main([*base, "--expected-mapping-sha256", "0" * 64])
    with pytest.raises(SystemExit):
        main([*base, "--expected-mapping-count", "1"])
    with pytest.raises(SystemExit):
        main([*base, "--production-contract"])


def test_planimation_renderer_uses_only_canonical_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3.planimation_pairing_rendering import render_state_with_planimation

    observed: list[list[str]] = []
    vfg = json.dumps(
        {
            "visualStages": [
                {
                    "stageName": "Initial Stage",
                    "visualSprites": [{"name": "token", "minX": 0.2, "maxX": 0.6, "minY": 0.2, "maxY": 0.6}],
                }
            ]
        }
    ).encode()

    def post(
        _domain: Path,
        _problem: Path,
        _profile: Path,
        candidates: list[str],
        _timeout: int,
    ) -> tuple[bytes, str]:
        observed.append(candidates)
        return vfg, candidates[0]

    monkeypatch.setattr("scripts.planimation_phase1.post_pddl_for_vfg", post)
    cache = tmp_path / "cache"
    cache.mkdir()
    result = render_state_with_planimation(
        tmp_path / "domain.pddl",
        tmp_path / "problem.pddl",
        tmp_path / "profile.pddl",
        cache,
        RenderConfig(max_attempts=1),
    )
    assert result["status"] == "success"
    assert observed == [["https://planimation.planning.domains/upload/pddl"]]


def test_planimation_compat_formatter_matches_bundle_03_golden_bytes(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import format_planimation_compat_problem
    from scripts.phase3.pddl import parse_task

    domain = tmp_path / "domain.pddl"
    domain.write_text(_MINIMAL_DOMAIN, encoding="utf-8")
    problem = tmp_path / "problem.pddl"
    problem.write_text(_BUNDLE_02_SEMANTIC_INPUT, encoding="utf-8")
    formatted = format_planimation_compat_problem(
        parse_task(domain, problem),
        problem_name="cgas-phase3-regression-replay-03-canonicalized-pilot-delta",
    )
    assert formatted is not None
    assert formatted.encode("utf-8") == _BUNDLE_03_GOLDEN


def test_planimation_compat_formatter_renames_twelve_objects_without_collisions(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import format_planimation_compat_problem
    from scripts.phase3.pddl import parse_task

    domain = tmp_path / "domain.pddl"
    domain.write_text(_MINIMAL_DOMAIN, encoding="utf-8")
    problem = tmp_path / "problem.pddl"
    problem.write_text(_TWELVE_OBJECT_INPUT, encoding="utf-8")
    formatted = format_planimation_compat_problem(parse_task(domain, problem))
    assert formatted is not None
    assert "(:objects b1 b2 b3 b4 b5 b6 b7 b8 b9 b10 b11 b12 )" in formatted
    assert "b00" not in formatted
    assert "b09" not in formatted
    assert "(on b11 b12)" in formatted  # (on b10 b11) across the b1/b10 token boundary
    assert "(on b12 b3)" in formatted  # (on b11 b02)
    assert "(holding b10)" in formatted  # (holding b09)
    assert "(clear b11)" in formatted  # (clear b10)
    compat = tmp_path / "compat.pddl"
    compat.write_text(formatted, encoding="utf-8")
    parsed = parse_task(domain, compat)
    assert set(parsed.objects_by_type["object"]) == {f"b{index}" for index in range(1, 13)}
    assert ("on", "b11", "b12") in parsed.init
    assert ("holding", "b10") in parsed.init
    assert ("on", "b2", "b1") in parsed.init
    assert ("on-table", "b1") in parsed.init


def test_planimation_compat_formatter_passes_through_legacy_b1_namespace(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import format_planimation_compat_problem
    from scripts.phase3.pddl import parse_task

    domain = tmp_path / "domain.pddl"
    domain.write_text(_MINIMAL_DOMAIN, encoding="utf-8")
    problem = tmp_path / "problem.pddl"
    problem.write_text(_LEGACY_B1_INPUT, encoding="utf-8")
    assert format_planimation_compat_problem(parse_task(domain, problem)) is None


def test_planimation_compat_renderer_passes_through_legacy_b1_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_adapter as adapter
    from scripts.phase3.planimation_pairing_contracts import RenderConfig

    domain = tmp_path / "domain.pddl"
    domain.write_text(_MINIMAL_DOMAIN, encoding="utf-8")
    problem = tmp_path / "problem.pddl"
    problem.write_text(_LEGACY_B1_INPUT, encoding="utf-8")
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    observed: list[Path] = []

    def fake(
        _domain: Path, problem_path: Path, _profile: Path, _cache: Path, _config: RenderConfig
    ) -> RendererResult:
        observed.append(problem_path)
        return {"status": "success", "attempts": 1}

    monkeypatch.setattr(adapter, "render_state_with_planimation", fake)
    result = adapter.render_state_with_planimation_compat(
        domain, problem, profile, cache, RenderConfig(max_attempts=1)
    )
    assert result["status"] == "success"
    assert observed == [problem]
    assert list(cache.iterdir()) == []


def test_planimation_compat_default_renderer_uploads_compat_and_keeps_cache_b00(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.phase3.cgas_pilot_planimation_adapter as adapter
    from scripts.phase3.cgas_candidate_accounting import planner_input_record
    from scripts.phase3.cgas_candidate_space import build_candidate
    from scripts.phase3.pddl import canonical_atom, parse_task

    atoms = [
        "(arm-empty)",
        "(clear b03)",
        "(clear b04)",
        "(clear b07)",
        "(on b01 b00)",
        "(on b02 b01)",
        "(on b03 b02)",
        "(on b04 b05)",
        "(on b07 b06)",
        "(on-table b00)",
        "(on-table b05)",
        "(on-table b06)",
    ]
    digest = state_sha256(atoms)
    candidate = build_candidate(8, 0)
    source = planner_input_record(PlannerInput(8, 0, "emitted", candidate.candidate_id, 0, candidate))
    source_digest = hashlib.sha256(
        (json.dumps(source, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()
    ).hexdigest()
    index_row: dict[str, object] = {
        "schema_version": "cgas_phase3_pilot_expansion_index_v1",
        "candidate_id": candidate.candidate_id,
        "instance_id": candidate.candidate_id,
        "object_count": 8,
        "raw_rank": 0,
        "role": "train",
        "planner": "bfs",
        "row_id": "row-0",
        "event_sequence": 0,
        "event_sha256": hashlib.sha256(b"event-row-0").hexdigest(),
        "trace_path": "traces/row-0.jsonl",
        "trace_stream_sha256": hashlib.sha256(b"stream-row-0").hexdigest(),
        "trace_contract_id": "cgas_trace_contract_v3",
        "trace_contract_sha256": hashlib.sha256(b"contract").hexdigest(),
        "replay_plan_member": True,
        "replay_step_index": 0,
        "source_record_sha256": source_digest,
        "state_atoms": atoms,
        "state_sha256": digest,
    }
    request_row = {"partitions": ["train|8|bfs"], "state_atoms": atoms, "state_sha256": digest}
    index = tmp_path / "index.jsonl"
    request = tmp_path / "request.jsonl"
    _jsonl(index, [index_row])
    _jsonl(request, [request_row])
    domain = tmp_path / "domain.pddl"
    domain.write_text(_MINIMAL_DOMAIN, encoding="utf-8")
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    monkeypatch.setattr(adapter, "_candidate_problem", lambda _row: _BUNDLE_02_SEMANTIC_INPUT)
    captured: list[tuple[Path, bytes, Path]] = []

    def fake_inner(
        domain_path: Path, problem_path: Path, profile_path: Path, cache_dir: Path, config: RenderConfig
    ) -> RendererResult:
        captured.append((problem_path, problem_path.read_bytes(), cache_dir))
        return _fake_renderer([])(domain_path, problem_path, profile_path, cache_dir, config)

    monkeypatch.setattr(adapter, "render_state_with_planimation", fake_inner)
    result = adapter.render_missing_states(
        adapter.PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile)
    )
    assert result.counts["succeeded"] == 1
    assert len(captured) == 1
    compat_path, compat_bytes, cache_dir = captured[0]
    assert compat_path == cache_dir / "problem.planimation-compat.pddl"
    assert b"(:objects b1 b2 b3 b4 b5 b6 b7 b8 )" in compat_bytes
    assert b"b00" not in compat_bytes
    cache_problem = cache_dir / "problem.pddl"
    assert cache_problem.exists()
    assert b"b00" in cache_problem.read_bytes()
    parsed = parse_task(domain, cache_problem)
    assert {obj for obj in parsed.objects_by_type["object"]} == {f"b{index:02d}" for index in range(8)}
    assert sorted(canonical_atom(atom) for atom in parsed.init) == sorted(atoms)
    record = json.loads(result.manifest_path.read_text())
    assert record["state_sha256"] == digest
    assert record["candidate_id"] == candidate.candidate_id
    assert record["source_record_sha256"] == source_digest
    assert record["transition"]["state_before"] == sorted(atoms)


def test_planimation_renderer_plan_forwarding_preserves_old_call_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.phase3.planimation_pairing_rendering import render_state_with_planimation

    vfg = json.dumps(
        {
            "visualStages": [
                {
                    "stageName": "Initial Stage",
                    "visualSprites": [{"name": "token", "minX": 0.2, "maxX": 0.6, "minY": 0.2, "maxY": 0.6}],
                }
            ]
        }
    ).encode()
    calls: list[dict[str, Any]] = []

    def post(*args: Any, **kwargs: Any) -> tuple[bytes, str]:
        calls.append({"args": args, "kwargs": kwargs})
        return vfg, str(args[3][0])

    monkeypatch.setattr("scripts.planimation_phase1.post_pddl_for_vfg", post)
    cache = tmp_path / "cache"
    cache.mkdir()
    domain = tmp_path / "domain.pddl"
    problem = tmp_path / "problem.pddl"
    profile = tmp_path / "profile.pddl"
    for path in (domain, problem, profile):
        path.write_text("x", encoding="utf-8")

    result = render_state_with_planimation(domain, problem, profile, cache, RenderConfig(max_attempts=1))
    assert result["status"] == "success"
    assert len(calls) == 1
    assert calls[0]["kwargs"] == {}
    assert calls[0]["args"][3] == ["https://planimation.planning.domains/upload/pddl"]
    assert len(calls[0]["args"]) == 5  # historical five-positional shape, no plan kwarg

    result = render_state_with_planimation(
        domain, problem, profile, cache, RenderConfig(max_attempts=1, plan="(pickup b1)")
    )
    assert result["status"] == "success"
    assert len(calls) == 2
    assert calls[1]["kwargs"] == {"plan": "(pickup b1)"}
    assert calls[1]["args"][3] == ["https://planimation.planning.domains/upload/pddl"]
    assert len(calls[1]["args"]) == 5


def test_cache_identity_binds_plan_only_when_present(tmp_path: Path) -> None:
    from scripts.phase3.planimation_pairing_rendering import _cache_identity
    from scripts.phase3.traversal_state_types import JSONValue

    domain = tmp_path / "domain.pddl"
    domain.write_text("(define (domain d))", encoding="utf-8")
    problem = tmp_path / "problem.pddl"
    problem.write_text("(define (problem p))", encoding="utf-8")
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    pair: dict[str, JSONValue] = {"domain_path": str(domain), "problem_path": str(problem)}
    state_atoms = ["(arm-empty)"]
    renderer = _fake_renderer([])

    default = _cache_identity(pair, state_atoms, profile, renderer, RenderConfig())
    explicit_none = _cache_identity(pair, state_atoms, profile, renderer, RenderConfig(plan=None))
    assert default == explicit_none  # explicit plan=None keeps the historical identity

    plan_a = _cache_identity(pair, state_atoms, profile, renderer, RenderConfig(plan="(pickup b1)"))
    plan_b = _cache_identity(pair, state_atoms, profile, renderer, RenderConfig(plan="(stack b1 b2)"))
    assert plan_a != default
    assert plan_a != plan_b
    assert plan_a["cache_key"] != default["cache_key"]
    assert plan_b["cache_key"] != plan_a["cache_key"]


def test_supplied_plan_validation() -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderError, _supplied_plan

    assert _supplied_plan({}) is None
    assert _supplied_plan({"supplied_plan": "(pickup b1)"}) == "(pickup b1)"
    for invalid in ("", "   ", "no-parentheses-text", 42, None, ["(pickup b1)"]):
        with pytest.raises(PilotRenderError, match="supplied_plan_invalid"):
            _supplied_plan({"supplied_plan": invalid})


def test_render_state_carries_supplied_plan_to_renderer_and_writes_digest(
    tmp_path: Path,
) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderRequest, render_missing_states
    from scripts.phase3.io_utils import stable_hash

    index, request, row = _fixture(tmp_path)
    row["supplied_plan"] = "(pickup b1)"
    _jsonl(index, [row])
    domain = tmp_path / "domain.pddl"
    domain.write_text(_MINIMAL_DOMAIN, encoding="utf-8")
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    observed: list[str | None] = []

    def capture(
        domain_path: Path, problem_path: Path, profile_path: Path, cache_dir: Path, config: RenderConfig
    ) -> RendererResult:
        observed.append(config.plan)
        return _fake_renderer([])(domain_path, problem_path, profile_path, cache_dir, config)

    result = render_missing_states(
        PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile),
        renderer=capture,
    )
    assert result.counts["succeeded"] == 1
    assert observed == ["(pickup b1)"]
    record = json.loads(result.manifest_path.read_text())
    assert record["supplied_plan_sha256"] == stable_hash("(pickup b1)")


def test_render_state_without_supplied_plan_omits_digest(tmp_path: Path) -> None:
    from scripts.phase3.cgas_pilot_planimation_adapter import PilotRenderRequest, render_missing_states

    index, request, _ = _fixture(tmp_path)
    domain = tmp_path / "domain.pddl"
    domain.write_text(_MINIMAL_DOMAIN, encoding="utf-8")
    profile = tmp_path / "profile.pddl"
    profile.write_text("profile", encoding="utf-8")
    observed: list[str | None] = []

    def capture(
        domain_path: Path, problem_path: Path, profile_path: Path, cache_dir: Path, config: RenderConfig
    ) -> RendererResult:
        observed.append(config.plan)
        return _fake_renderer([])(domain_path, problem_path, profile_path, cache_dir, config)

    result = render_missing_states(
        PilotRenderRequest(tmp_path, request, index, tmp_path / "outputs/out", domain, profile),
        renderer=capture,
    )
    assert result.counts["succeeded"] == 1
    assert observed == [None]
    record = json.loads(result.manifest_path.read_text())
    assert "supplied_plan_sha256" not in record
