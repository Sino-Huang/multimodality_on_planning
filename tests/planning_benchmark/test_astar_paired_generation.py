from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path

import pytest

from examples.planning_benchmark_slice.astar_episode import ASTAR_ACCEPTED_DELTA_LIMIT
from examples.planning_benchmark_slice.astar_paired_generation import (
    build_astar_pair_alignment,
    generate_frozen_astar_pair,
    preflight_frozen_astar_pair_generation,
)
from examples.planning_benchmark_slice.astar_paired_trace_audit import (
    audit_frozen_astar_pair,
    select_astar_teacher_snapshots,
)
from examples.planning_benchmark_slice.astar_phase import build_astar_paired_generation_request
from examples.planning_benchmark_slice.episode_evidence import read_episode_evidence, write_episode_evidence
from src.data_collect.generate import GenerationRequest, ValidExecutionStop, run_authorized_generation
from src.data_collect.governance import AuthorizationReceipt, GateReceipt, ReceiptBinding, StopOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/generate_astar_paired_expert_traces.py"


def test_direct_fixture_dry_run_has_progress_exact_terminal_status_and_no_writes(tmp_path: Path) -> None:
    output_root = tmp_path / "forbidden-output"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--fixture-dry-run", "--output-root", str(output_root)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    progress = [json.loads(line) for line in lines[:-1]]
    assert progress
    assert all(
        {"stage", "completed", "total", "elapsed_seconds", "estimated_remaining_seconds", "pair_id"}
        <= set(item)
        for item in progress
    )
    assert lines[-1] == (
        '{"fixture_only":true,"scientific_authorization":false,'
        '"status":"contract_validation_only","writes":0}'
    )
    assert not output_root.exists()


def test_real_dry_run_without_issue62_is_nonzero_and_writes_nothing(tmp_path: Path) -> None:
    output_root = tmp_path / "real-output"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--output-root", str(output_root)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert json.loads(completed.stdout) == {
        "fixture_only": False,
        "scientific_authorization": False,
        "status": "ancestor_authorization_absent",
        "writes": 0,
    }
    assert not output_root.exists()


def test_cli_does_not_start_from_merely_existing_phase_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import generate_astar_paired_expert_traces as cli

    freeze = tmp_path / "freeze.json"
    authorization = tmp_path / "authorization.json"
    freeze.write_text('{"outcome":"PASS"}\n', encoding="utf-8")
    authorization.write_text('{"outcome":"PASS","authorized_stages":["trace_generation"]}\n', encoding="utf-8")
    monkeypatch.setattr(cli, "_DEFAULT_FREEZE", freeze)
    monkeypatch.setattr(cli, "_DEFAULT_AUTHORIZATION", authorization)
    output = tmp_path / "output"
    assert cli.main(["--dry-run", "--output-root", str(output)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "ancestor_authorization_absent"
    assert not output.exists()


def test_post_start_typed_stop_is_governed_valid_stop(tmp_path: Path) -> None:
    output = (tmp_path / "output").resolve()
    binding = ReceiptBinding("contract", "attempt", output)
    gate = GateReceipt(binding, StopOutcome.PASS)
    request = GenerationRequest(
        binding=binding,
        gate_receipt=gate,
        authorization_receipt=AuthorizationReceipt(binding, gate.receipt_id),
        receipt_root=(tmp_path / "receipts").resolve(),
    )

    def execute() -> object:
        raise ValidExecutionStop(
            "resource_exhaustion",
            execution_result={"termination": "expansion_budget"},
        )

    receipt = run_authorized_generation(request, execute)
    assert receipt.outcome is StopOutcome.VALID_STOP
    assert receipt.status == "resource_exhaustion"
    assert receipt.scientific_completion is False
    assert receipt.execution_result == {"termination": "expansion_budget"}


def test_delta_limit_and_snapshot_order_are_frozen() -> None:
    assert ASTAR_ACCEPTED_DELTA_LIMIT == 16
    records = [
        {
            "adapter": "astar_hmax",
            "decision_index": index % 2,
            "difficulty": difficulty,
            "expansion_index": index // 2,
            "input_tokens": token,
            "input": {"fixture": index},
            "pair_id": pair_id,
            "target": {"typed_operation": index},
            "target_tokens": 1,
        }
        for index, (difficulty, token, pair_id) in enumerate(
            (
                ("easy", 30, "p3"),
                ("medium", 20, "p2"),
                ("hard", 10, "p1"),
                ("easy", 10, "p0"),
                ("medium", 30, "p4"),
                ("hard", 20, "p5"),
            )
        )
    ]
    first = select_astar_teacher_snapshots(records)
    second = select_astar_teacher_snapshots(list(reversed(records)))
    assert first == second
    assert len(first) == 6
    assert [item["selection_bin"] for item in first] == ["easy", "medium", "hard", "low", "middle", "high"]
    assert all("input" in item and "target" in item for item in first)


def test_alignment_counts_one_multi_action_expansion_as_one_source() -> None:
    source = "shared-source"
    decisions = [
        {
            "input": {
                "current": {"state_id": source},
                "successor_candidates": [
                    {"action": {"args": ["a"], "name": "move"}, "target_state_id": "target-a"},
                    {"action": {"args": ["b"], "name": "move"}, "target_state_id": "target-b"},
                ],
            },
            "operation": {"action": {"args": [argument], "name": "move"}, "source_state_id": source},
        }
        for argument in ("a", "b")
    ]
    episode = {
        "evidence": {
            "events": [{"decisions": decisions, "expanded_state_id": source}],
            "header": {"authority_id": "authority", "task": {"same": "bytes"}},
        }
    }
    alignment = build_astar_pair_alignment(
        {"pair_id": "pair", "semantic_task_identity": "identity"},
        {"astar_hmax": episode, "astar_landmark_count": episode},
    )
    assert alignment["aligned"] == [
        {
            "action_targets": [
                {"action": {"args": ["a"], "name": "move"}, "target_state_id": "target-a"},
                {"action": {"args": ["b"], "name": "move"}, "target_state_id": "target-b"},
            ],
            "source_state_id": source,
        }
    ]


def test_phase_bridge_rejects_non_pass_phase_authority(tmp_path: Path) -> None:
    from scripts.generate_astar_paired_expert_traces import _fixture_gate

    gate = _fixture_gate()
    gate.authorization["outcome"] = "VALID_STOP"
    binding = ReceiptBinding(gate.phase_id, "attempt", (tmp_path / "output").resolve())
    try:
        build_astar_paired_generation_request(
            gate,
            binding=binding,
            receipt_root=(tmp_path / "receipts").resolve(),
        )
    except ValueError as error:
        assert "PASS" in str(error)
    else:
        raise AssertionError("non-PASS persisted phase authority bridged to a start")


def test_phase_bridge_rejects_unpersisted_fabricated_pass(tmp_path: Path) -> None:
    from scripts.generate_astar_paired_expert_traces import _fixture_gate

    gate = _fixture_gate()
    binding = ReceiptBinding(gate.phase_id, "attempt", (tmp_path / "output").resolve())
    with pytest.raises(ValueError):
        build_astar_paired_generation_request(
            gate,
            binding=binding,
            receipt_root=(tmp_path / "receipts").resolve(),
        )


@pytest.mark.parametrize("component", ("task", "trace", "corpus", "model", "budget", "analysis"))
def test_phase_bridge_requires_exact_all_six_persisted_components_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    component: str,
) -> None:
    from examples.planning_benchmark_slice import astar_phase
    from scripts.generate_astar_paired_expert_traces import _fixture_gate

    persisted = _fixture_gate()
    supplied = deepcopy(persisted)
    supplied.components[component]["review_tamper"] = True
    monkeypatch.setattr(astar_phase, "load_astar_paired_phase_gate", lambda *_args, **_kwargs: persisted)
    output = (tmp_path / "output").resolve()
    binding = ReceiptBinding(supplied.phase_id, "attempt", output)
    with pytest.raises(ValueError, match="persisted peers"):
        build_astar_paired_generation_request(
            supplied,
            binding=binding,
            receipt_root=(tmp_path / "receipts").resolve(),
        )
    assert not output.exists()


def test_resume_discards_partial_staging_and_publishes_one_complete_pair(tmp_path: Path) -> None:
    from scripts.generate_astar_paired_expert_traces import _fixture_gate

    gate = _fixture_gate()
    output = (tmp_path / "output").resolve()
    binding = ReceiptBinding(gate.phase_id, "attempt", output)
    request = build_astar_paired_generation_request(
        gate,
        binding=binding,
        receipt_root=(tmp_path / "receipts").resolve(),
        fixture_only=True,
    )
    row = preflight_frozen_astar_pair_generation(gate)[0]
    partial = output / ".staging" / row["pair_id"]
    partial.mkdir(parents=True)
    (partial / "half.tmp").write_bytes(b"crash")
    item = generate_frozen_astar_pair(
        row=row,
        request=request,
        phase_gate=gate,
        resume=True,
        fixture_only=True,
    )
    pair_root = output / "pairs" / row["pair_id"]
    assert (pair_root / "pair.json").is_file()
    assert not partial.exists()
    assert [adapter["adapter"] for adapter in item["adapters"]] == [
        "astar_hmax",
        "astar_landmark_count",
    ]


def test_resume_does_not_discard_staging_that_contains_retained_pair_evidence(tmp_path: Path) -> None:
    from scripts.generate_astar_paired_expert_traces import _fixture_gate

    gate = _fixture_gate()
    output = (tmp_path / "output").resolve()
    binding = ReceiptBinding(gate.phase_id, "attempt", output)
    request = build_astar_paired_generation_request(
        gate,
        binding=binding,
        receipt_root=(tmp_path / "receipts").resolve(),
        fixture_only=True,
    )
    row = preflight_frozen_astar_pair_generation(gate)[0]
    retained = output / ".staging" / row["pair_id"] / "astar_hmax" / "evidence.jsonl.gz"
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b"retained-staging-evidence")
    with pytest.raises(FileExistsError, match="retained evidence"):
        generate_frozen_astar_pair(
            row=row,
            request=request,
            phase_gate=gate,
            resume=True,
            fixture_only=True,
        )
    assert retained.read_bytes() == b"retained-staging-evidence"


def test_resume_quarantines_crash_half_pair_but_rejects_different_complete_pair(tmp_path: Path) -> None:
    from scripts.generate_astar_paired_expert_traces import _fixture_gate

    gate = _fixture_gate()
    output = (tmp_path / "output").resolve()
    binding = ReceiptBinding(gate.phase_id, "attempt", output)
    request = build_astar_paired_generation_request(
        gate,
        binding=binding,
        receipt_root=(tmp_path / "receipts").resolve(),
        fixture_only=True,
    )
    row = preflight_frozen_astar_pair_generation(gate)[0]
    pair_root = output / "pairs" / row["pair_id"]
    half = pair_root / "astar_hmax" / "evidence.jsonl.gz"
    half.parent.mkdir(parents=True)
    incomplete_bytes = b"crash-half"
    half.write_bytes(incomplete_bytes)
    generate_frozen_astar_pair(
        row=row,
        request=request,
        phase_gate=gate,
        resume=True,
        fixture_only=True,
    )
    quarantined = output / ".quarantine" / row["pair_id"] / "astar_hmax" / "evidence.jsonl.gz"
    assert quarantined.read_bytes() == incomplete_bytes
    complete = pair_root / "pair.json"
    complete.write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="immutably"):
        generate_frozen_astar_pair(
            row=row,
            request=request,
            phase_gate=gate,
            resume=True,
            fixture_only=True,
        )


def test_resume_fails_without_moving_when_incomplete_pair_quarantine_exists(tmp_path: Path) -> None:
    from scripts.generate_astar_paired_expert_traces import _fixture_gate

    gate = _fixture_gate()
    output = (tmp_path / "output").resolve()
    binding = ReceiptBinding(gate.phase_id, "attempt", output)
    request = build_astar_paired_generation_request(
        gate,
        binding=binding,
        receipt_root=(tmp_path / "receipts").resolve(),
        fixture_only=True,
    )
    row = preflight_frozen_astar_pair_generation(gate)[0]
    pair_root = output / "pairs" / row["pair_id"]
    retained = pair_root / "astar_hmax" / "evidence.jsonl.gz"
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b"retained-incomplete")
    quarantine = output / ".quarantine" / row["pair_id"]
    quarantine.mkdir(parents=True)
    (quarantine / "earlier").write_bytes(b"earlier-incomplete")
    with pytest.raises(FileExistsError, match="quarantine already exists"):
        generate_frozen_astar_pair(
            row=row,
            request=request,
            phase_gate=gate,
            resume=True,
            fixture_only=True,
        )
    assert retained.read_bytes() == b"retained-incomplete"
    assert (quarantine / "earlier").read_bytes() == b"earlier-incomplete"


def test_expansion_budget_valid_stop_publishes_neither_half(tmp_path: Path) -> None:
    from scripts.generate_astar_paired_expert_traces import _fixture_gate

    gate = _fixture_gate()
    row = gate.components["task"]["pairs"][0]
    row["generation_max_expansions"] = 1
    gate.components["budget"]["generation_budget"]["max_expansions_by_difficulty"]["easy"] = 1
    output = (tmp_path / "output").resolve()
    binding = ReceiptBinding(gate.phase_id, "attempt", output)
    request = build_astar_paired_generation_request(
        gate,
        binding=binding,
        receipt_root=(tmp_path / "receipts").resolve(),
        fixture_only=True,
    )
    with pytest.raises(ValidExecutionStop):
        generate_frozen_astar_pair(
            row=row,
            request=request,
            phase_gate=gate,
            resume=True,
            fixture_only=True,
        )
    assert not (output / "pairs" / row["pair_id"]).exists()
    assert not (output / ".staging" / row["pair_id"]).exists()


@pytest.mark.parametrize(
    ("tamper", "counter"),
    (
        ("byte", "canonical_byte_parity_error_count"),
        ("token", "token_id_parity_error_count"),
        ("parse", "parse_rejection_count"),
        ("runtime", "runtime_rejection_count"),
    ),
)
def test_pair_audit_measures_independent_parity_parse_and_runtime_rejections(
    tmp_path: Path,
    tamper: str,
    counter: str,
) -> None:
    from scripts.generate_astar_paired_expert_traces import _fixture_gate

    gate = _fixture_gate()
    output = (tmp_path / "output").resolve()
    binding = ReceiptBinding(gate.phase_id, "attempt", output)
    request = build_astar_paired_generation_request(
        gate,
        binding=binding,
        receipt_root=(tmp_path / "receipts").resolve(),
        fixture_only=True,
    )
    row = preflight_frozen_astar_pair_generation(gate)[0]
    item = generate_frozen_astar_pair(
        row=row,
        request=request,
        phase_gate=gate,
        resume=True,
        fixture_only=True,
    )
    if tamper == "token":
        def live_token_ids(messages: Sequence[Mapping[str, str]]) -> Sequence[int]:
            return tuple(json.dumps(list(messages), sort_keys=True).encode())

        def teacher_token_ids(messages: Sequence[Mapping[str, str]]) -> Sequence[int]:
            return (*tuple(json.dumps(list(messages), sort_keys=True).encode()), 999)

        result = audit_frozen_astar_pair(
            row=row,
            pair_item=item,
            output_root=output,
            phase_gate=gate,
            fixture_only=True,
            input_token_ids=live_token_ids,
            teacher_input_token_ids=teacher_token_ids,
        )
    else:
        evidence_binding = item["adapters"][0]["evidence"]
        evidence_path = output / evidence_binding["path"]
        episode = read_episode_evidence(evidence_path)
        decision = episode["evidence"]["events"][0]["decisions"][0]
        if tamper == "byte":
            decision["input"]["current"]["g"] += 1
        elif tamper == "parse":
            decision["operation"]["action"]["args"] = [1]
        else:
            decision["operation"]["action"] = {"args": [], "name": "not-applicable"}
        write_episode_evidence(evidence_path, episode)
        payload = evidence_path.read_bytes()
        evidence_binding["sha256"] = hashlib.sha256(payload).hexdigest()
        evidence_binding["size_bytes"] = len(payload)
        result = audit_frozen_astar_pair(
            row=row,
            pair_item=item,
            output_root=output,
            phase_gate=gate,
            fixture_only=True,
        )
    assert result["audit_results"][counter] > 0
