from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# The digest the decision packet published to the owner. If the module disagrees with
# this, the owner is being asked to sign a number the code does not produce.
# Source: .claude/evidence/cgas-trace-contract-v3/owner-decision-packet/contract-surface.json
V3_POLICY_SHA256 = "51acff53d15652663d2212902d3d94261e44de9e3edf66b9970fc3c75197d436"

# sha256 of .claude/evidence/cgas-production-p0/approved-trace-v2.json, which is also
# the approved_trace_sha256 recorded in reservoir_checkpoint_000001.json.
V2_APPROVAL_SHA256 = "bd6909f99ce32484f3a33863cde936c0a3128935dabaf85da783870ae7ee26a8"

READER_LINE_CEILING = 16 * 1024 * 1024  # cgas_trace_stream_v2.verify_trace_stream, read side only


def _event_with_line_size(target: int, path: Path) -> dict[str, str]:
    from scripts.phase3 import cgas_trace_stream_v2 as stream

    event = {"payload": ""}
    preimage = {
        "event": event,
        "previous_event_sha256": None,
        "record_type": "event",
        "sequence": 0,
    }
    current = hashlib.sha256(stream._canonical_bytes(preimage, path)).hexdigest()
    base_line = stream._canonical_bytes({"current_event_sha256": current, **preimage}, path) + b"\n"
    return {"payload": "x" * (target - len(base_line))}


def test_v3_pins_the_policy_the_decision_packet_specifies() -> None:
    # Given: the policy the owner decision packet asks to be authorized.
    from scripts.phase3.cgas_trace_contract_v3 import POLICY_LIMITS, POLICY_SHA256

    # When: the module's policy is canonicalised.
    # Then: it is exactly the packet's policy, and its digest is the published one.
    assert POLICY_LIMITS == {
        "local_iw_escalate": 1,
        "local_iw_max_width": 2,
        "local_iw_novelty_max_expansions": 50_000,
        "local_iw_recovery": "disabled",
        "local_iw_width": 1,
        "local_max_applicable_actions": 2_000,
        "max_expansions": 10_000,
        "max_grounded_actions": 100_000,
        "max_grounded_atoms": 100_000,
        "max_plan_length": 128,
    }
    assert POLICY_SHA256 == V3_POLICY_SHA256


def test_v3_policy_differs_from_v2_in_exactly_the_three_escalation_keys() -> None:
    # Given: the frozen v2 policy and the proposed v3 policy.
    from scripts.phase3.cgas_trace_contract_v2 import POLICY_LIMITS as V2
    from scripts.phase3.cgas_trace_contract_v3 import POLICY_LIMITS as V3

    # When: the two are compared key by key.
    changed = {key for key in set(V2) | set(V3) if V2.get(key) != V3.get(key)}

    # Then: only width escalation and its expansion margin move. Nothing else in the
    # planner policy is being renegotiated under cover of the contract change.
    assert changed == {"local_iw_escalate", "local_iw_max_width", "local_iw_novelty_max_expansions"}
    assert "local_iw_escalate" not in V2
    assert V2["local_iw_max_width"] == 1 and V3["local_iw_max_width"] == 2


def test_iw_record_bound_counts_every_width_pass_not_only_the_solving_one() -> None:
    # Given: v2's IW record bound, which prices a single search pass.
    from scripts.phase3.cgas_trace_contract_v2 import IW_MAX_RECORDS as V2_IW
    from scripts.phase3.cgas_trace_contract_v3 import (
        IW_MAX_RECORDS,
        IW_WIDTHS,
        POLICY_LIMITS,
        build_migration_packet,
    )

    # When: escalation runs every width from local_iw_width to local_iw_max_width into
    # one stream, each pass resetting its own expansion counter.
    cap = POLICY_LIMITS["local_iw_novelty_max_expansions"]
    actions = POLICY_LIMITS["local_max_applicable_actions"]

    # Then: the bound carries a width factor v2's formula omits.
    assert IW_WIDTHS == 2
    assert IW_MAX_RECORDS == 1 + 2 * IW_WIDTHS * cap * actions + 2 == 400_000_003
    assert IW_MAX_RECORDS > V2_IW
    formula = build_migration_packet()["bounds_proof"]["iw"]["formula"]
    assert "widths" in formula


def test_bfs_record_bound_is_carried_unchanged_from_v2() -> None:
    # Given: BFS is untouched by width escalation.
    from scripts.phase3.cgas_trace_contract_v2 import BFS_MAX_RECORDS as V2_BFS
    from scripts.phase3.cgas_trace_contract_v3 import BFS_MAX_RECORDS

    # Then: its record bound carries over exactly.
    assert BFS_MAX_RECORDS == V2_BFS == 1_000_010_002


def test_max_event_bytes_sits_below_the_reader_line_ceiling() -> None:
    # Given: verify_trace_stream already refuses any line over 16 MiB, and
    # write_trace_stream has no counterpart -- a writer can produce a stream its own
    # verifier rejects.
    from scripts.phase3.cgas_trace_contract_v3 import MAX_EVENT_BYTES, build_migration_packet

    # Then: the write-side bound closes that asymmetry rather than widening it, and both
    # ceilings are signed together so they cannot drift apart.
    assert MAX_EVENT_BYTES == 65_536
    assert MAX_EVENT_BYTES < READER_LINE_CEILING
    record_size = build_migration_packet()["bounds_proof"]["record_size"]
    assert record_size["max_event_bytes"] == MAX_EVENT_BYTES
    assert record_size["reader_line_ceiling"] == READER_LINE_CEILING


def test_v3_accepts_an_event_line_at_the_signed_byte_limit(tmp_path: Path) -> None:
    from scripts.phase3 import cgas_trace_contract_v3 as v3
    from scripts.phase3.cgas_trace_stream_v2 import TraceWriteRequest, verify_trace_stream, write_trace_stream

    output = tmp_path / "v3-boundary.jsonl"
    event = _event_with_line_size(v3.MAX_EVENT_BYTES, output)
    request = TraceWriteRequest(output, "bfs", "failed_no_plan_extracted", (), 1, v3.CONTRACT_ID)

    write_trace_stream(request, (event,))
    verified = verify_trace_stream(output)

    assert len(output.read_bytes().splitlines(keepends=True)[0]) == v3.MAX_EVENT_BYTES
    assert verified.contract_id == v3.CONTRACT_ID
    assert verified.contract_sha256 == v3.NEW_CONTRACT_SHA256


def test_v3_rejects_the_first_byte_over_the_signed_limit(tmp_path: Path) -> None:
    from scripts.phase3 import cgas_trace_contract_v3 as v3
    from scripts.phase3.cgas_trace_stream_v2 import TraceStreamError, TraceWriteRequest, write_trace_stream

    output = tmp_path / "v3-too-large.jsonl"
    event = _event_with_line_size(v3.MAX_EVENT_BYTES + 1, output)
    request = TraceWriteRequest(output, "bfs", "failed_no_plan_extracted", (), 1, v3.CONTRACT_ID)

    with pytest.raises(TraceStreamError) as raised:
        write_trace_stream(request, (event,))

    assert raised.value == TraceStreamError("trace_v3_record_size_exceeded", output)
    assert not output.exists()
    assert not tuple(tmp_path.glob(f".{output.name}-*"))


def test_v3_rejection_preserves_existing_destination_byte_for_byte(tmp_path: Path) -> None:
    from scripts.phase3 import cgas_trace_contract_v3 as v3
    from scripts.phase3.cgas_trace_stream_v2 import TraceStreamError, TraceWriteRequest, write_trace_stream

    output = tmp_path / "v3-existing.jsonl"
    output.write_bytes(b"accepted destination bytes\n")
    before = output.read_bytes()
    event = _event_with_line_size(v3.MAX_EVENT_BYTES + 1, output)
    request = TraceWriteRequest(output, "bfs", "failed_no_plan_extracted", (), 1, v3.CONTRACT_ID)

    with pytest.raises(TraceStreamError, match="trace_v3_record_size_exceeded"):
        write_trace_stream(request, (event,))

    assert output.read_bytes() == before
    assert not tuple(tmp_path.glob(f".{output.name}-*"))


def test_v3_writer_and_verifier_bind_the_same_trailer_contract(tmp_path: Path) -> None:
    from scripts.phase3 import cgas_trace_contract_v3 as v3
    from scripts.phase3.cgas_trace_stream_v2 import TraceWriteRequest, verify_trace_stream, write_trace_stream

    output = tmp_path / "v3-success.jsonl"
    request = TraceWriteRequest(output, "bfs", "success_full_trace", ("(finish)",), 1, v3.CONTRACT_ID)

    written = write_trace_stream(request, ({"state": "goal"},))
    verified = verify_trace_stream(output)
    trailer = json.loads(output.read_bytes().splitlines()[-1])

    assert written == verified
    assert trailer["contract_id"] == v3.CONTRACT_ID
    assert trailer["contract_sha256"] == v3.NEW_CONTRACT_SHA256


def test_v2_accepts_event_lines_larger_than_the_v3_limit(tmp_path: Path) -> None:
    from scripts.phase3 import cgas_trace_contract_v3 as v3
    from scripts.phase3.cgas_trace_stream_v2 import TraceWriteRequest, verify_trace_stream, write_trace_stream

    output = tmp_path / "v2-large.jsonl"
    event = _event_with_line_size(v3.MAX_EVENT_BYTES + 1, output)
    request = TraceWriteRequest(output, "bfs", "failed_no_plan_extracted", (), 1)

    write_trace_stream(request, (event,))
    verified = verify_trace_stream(output)

    assert len(output.read_bytes().splitlines(keepends=True)[0]) == v3.MAX_EVENT_BYTES + 1
    assert verified.contract_id == "cgas_trace_contract_v2"


def test_contract_digest_covers_the_event_body_not_only_the_framing() -> None:
    # Given: v2's contract dict described stream framing only, so dropping event-body
    # fields left NEW_CONTRACT_SHA256 unchanged -- an event-shape change could pass
    # unsigned. v3 closes that.
    from scripts.phase3 import cgas_trace_contract_v3 as v3

    contract = dict(v3._NEW_CONTRACT)
    assert v3.NEW_CONTRACT_SHA256 == _digest(contract)

    # When: any part of the event-body delta is altered.
    # Then: the contract digest moves.
    for key in ("bfs_event_fields_removed", "iw_event_fields_removed", "iw_event_fields_added", "max_event_bytes"):
        assert key in contract, key
        mutated = dict(contract)
        mutated[key] = ["tampered"] if isinstance(contract[key], list) else 1
        assert _digest(mutated) != v3.NEW_CONTRACT_SHA256, key


def test_contract_pins_the_fields_off_plan_certificates_need() -> None:
    # Given: decision 2 of the packet -- v3 must not foreclose harvesting certificates
    # from expansions the replayed plan never visits.
    from scripts.phase3 import cgas_trace_contract_v3 as v3

    contract = dict(v3._NEW_CONTRACT)
    retained = contract["retained_for_off_plan_certificates"]

    # Then: retention is a signed contract property, not an accident a later
    # size-reduction pass could optimise away.
    assert retained == ["actions_considered", "enqueued", "state_atoms", "successors"]
    mutated = dict(contract)
    mutated["retained_for_off_plan_certificates"] = ["state_atoms"]
    assert _digest(mutated) != v3.NEW_CONTRACT_SHA256


def test_packet_publishes_unapproved_and_is_immutable_on_rerun(tmp_path: Path) -> None:
    # Given: fresh packet destinations.
    from scripts.phase3.cgas_trace_contract_v3 import publish_migration_packet

    packet_path = tmp_path / "packet.json"
    template_path = tmp_path / "owner.template.json"

    # When: the migration packet is published twice.
    first = publish_migration_packet(packet_path, template_path)
    packet_before = packet_path.read_bytes()
    template_before = template_path.read_bytes()
    second = publish_migration_packet(packet_path, template_path)

    # Then: publication carries no approval and the rerun is byte-for-byte read-only.
    packet = json.loads(packet_before)
    template = json.loads(template_before)
    assert packet["owner_approved"] is False
    assert template["owner_approved"] is False
    assert template["approval_scope"] == "trace_v3_persistence_and_policy"
    assert first.status == "published"
    assert second.status == "already_published"
    assert first.packet_sha256 == second.packet_sha256 == hashlib.sha256(packet_before).hexdigest()
    assert packet_path.read_bytes() == packet_before
    assert template_path.read_bytes() == template_before


def test_packet_refuses_to_overwrite_the_signed_v2_artifacts(tmp_path: Path) -> None:
    # Given: the published, signed v2 packet.
    from scripts.phase3.cgas_trace_contract_v2 import TraceContractPacketError
    from scripts.phase3.cgas_trace_contract_v3 import publish_migration_packet

    v2_packet = REPOSITORY_ROOT / ".claude/evidence/cgas-production-p0/trace-v2-migration-packet.json"
    before = v2_packet.read_bytes()

    # When: v3 is published over it.
    # Then: it fails closed and leaves the v2 bytes untouched.
    with pytest.raises(TraceContractPacketError):
        publish_migration_packet(v2_packet, tmp_path / "owner.template.json")
    assert v2_packet.read_bytes() == before


def test_packet_chains_to_the_signed_v2_approval() -> None:
    # Given: the owner's 2026-08-03 approval of trace-v2.
    from scripts.phase3.cgas_trace_contract_v2 import CONTRACT_ID as V2_CONTRACT_ID
    from scripts.phase3.cgas_trace_contract_v3 import (
        PREDECESSOR_CONTRACT_ID,
        TRACE_V2_APPROVAL_SHA256,
        build_migration_packet,
    )

    approval = REPOSITORY_ROOT / ".claude/evidence/cgas-production-p0/approved-trace-v2.json"

    # Then: the supersession is auditable -- v3 names what it replaces and pins its digest.
    assert TRACE_V2_APPROVAL_SHA256 == V2_APPROVAL_SHA256
    assert hashlib.sha256(approval.read_bytes()).hexdigest() == TRACE_V2_APPROVAL_SHA256
    assert PREDECESSOR_CONTRACT_ID == V2_CONTRACT_ID
    packet = build_migration_packet()
    assert packet["predecessor_approval_sha256"] == TRACE_V2_APPROVAL_SHA256
    assert packet["predecessor_contract_id"] == V2_CONTRACT_ID
    assert packet["delta_scope"] == "persistence_and_policy"


def test_validate_packet_bytes_rejects_a_tampered_packet(tmp_path: Path) -> None:
    # Given: a correctly published packet.
    from scripts.phase3.cgas_trace_contract_v2 import TraceContractPacketError
    from scripts.phase3.cgas_trace_contract_v3 import publish_migration_packet, validate_packet_bytes

    packet_path = tmp_path / "packet.json"
    publish_migration_packet(packet_path, tmp_path / "owner.template.json")
    contents = packet_path.read_bytes()
    assert validate_packet_bytes(contents, packet_path)["contract_id"] == "cgas_trace_contract_v3"

    # When: the self-digest is broken, or a signed value is changed while the self-digest
    # is recomputed to match.
    payload = json.loads(contents)
    stale = dict(payload)
    stale["packet_sha256"] = "0" * 64

    resigned = dict(payload)
    resigned["policy_limits"] = {**payload["policy_limits"], "local_iw_max_width": 3}
    body = {key: value for key, value in resigned.items() if key != "packet_sha256"}
    resigned["packet_sha256"] = _digest(body)

    # Then: both are refused. A self-consistent forgery still fails against the module.
    for tampered in (stale, resigned):
        with pytest.raises(TraceContractPacketError):
            validate_packet_bytes(_canonical(tampered), packet_path)


def test_importing_v3_does_not_mutate_the_frozen_v2_contract() -> None:
    # Given: v2's digests are pinned by its own tests and recorded in
    # reservoir_checkpoint_000001.json, which must not change.
    import scripts.phase3.cgas_trace_contract_v3  # noqa: F401
    from scripts.phase3.cgas_trace_contract_v2 import (
        IW_MAX_RECORDS,
        NEW_CONTRACT_SHA256,
        POLICY_LIMITS,
        POLICY_SHA256,
    )

    # Then: importing v3 leaves every one of them exactly as it was.
    assert NEW_CONTRACT_SHA256 == "5649fc7b7b4955a8879c3d997342a3d74594c9faa7458e5dc177bf3e977a0b9d"
    assert POLICY_SHA256 == "559c3a7cc4fd4833726ca3a5dcbd09149b83915e0a77871e4d350c489bd76c1e"
    assert IW_MAX_RECORDS == 40_000_003
    assert POLICY_LIMITS["local_iw_max_width"] == 1
    assert "local_iw_escalate" not in POLICY_LIMITS


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _signed_approval(packet_path: Path, owner_id: str = "test-only-owner", **overrides: object) -> dict[str, object]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    approval: dict[str, object] = {
        "approval_scope": "trace_v3_persistence_and_policy",
        "approved_at": "2026-08-07T00:00:00Z",
        "contract_id": "cgas_trace_contract_v3",
        "contract_sha256": packet["new_contract_sha256"],
        "owner_approved": True,
        "owner_id": owner_id,
        "packet_sha256": hashlib.sha256(packet_path.read_bytes()).hexdigest(),
        "policy_sha256": packet["policy_sha256"],
        "schema_version": "cgas_trace_contract_owner_approval_v1",
    }
    approval.update(overrides)
    return approval


def test_owner_approval_validates_and_publishes_an_approved_v3_contract(tmp_path: Path) -> None:
    # Given: an immutable v3 packet and a separately supplied owner decision.
    from scripts.phase3.cgas_trace_contract_approval import validate_owner_approval
    from scripts.phase3.cgas_trace_contract_v3 import NEW_CONTRACT_SHA256, POLICY_SHA256, publish_migration_packet

    packet = tmp_path / "packet.json"
    publish_migration_packet(packet, tmp_path / "owner.template.json")
    owner = tmp_path / "owner-approval.json"
    owner.write_bytes(_canonical(_signed_approval(packet)))
    output = tmp_path / "approved.json"

    # When: the approval is validated against the exact packet bytes.
    approved = validate_owner_approval(packet, owner, output)

    # Then: the published record binds the v3 contract, not v2's, and carries the
    # owner artifact's own digest so the signature cannot be swapped after the fact.
    assert approved.status == "approved_trace_v3"
    assert approved.contract_sha256 == NEW_CONTRACT_SHA256
    assert approved.policy_sha256 == POLICY_SHA256
    assert approved.owner_approval_sha256 == hashlib.sha256(owner.read_bytes()).hexdigest()
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["contract_id"] == "cgas_trace_contract_v3"
    assert record["approval_scope"] == "trace_v3_persistence_and_policy"
    assert record["owner_approved"] is True
    assert record["owner_id"] == "test-only-owner"


def test_approval_refuses_a_v3_signature_against_the_v2_packet(tmp_path: Path) -> None:
    # Given: a v3 owner signature and the signed v2 packet it does not describe.
    from scripts.phase3.cgas_trace_contract_approval import TraceApprovalError, validate_owner_approval
    from scripts.phase3.cgas_trace_contract_v3 import publish_migration_packet

    v3_packet = tmp_path / "packet.json"
    publish_migration_packet(v3_packet, tmp_path / "owner.template.json")
    owner = tmp_path / "owner-approval.json"
    owner.write_bytes(_canonical(_signed_approval(v3_packet)))
    v2_packet = REPOSITORY_ROOT / ".claude/evidence/cgas-production-p0/trace-v2-migration-packet.json"
    output = tmp_path / "approved.json"

    # When: the v3 signature is pointed at the v2 packet.
    # Then: cross-contract approval fails closed and publishes nothing.
    with pytest.raises(TraceApprovalError):
        validate_owner_approval(v2_packet, owner, output)
    assert not output.exists()


def test_approval_never_synthesizes_the_owner_for_v3(tmp_path: Path) -> None:
    # Given: v3 approvals missing the two fields that make them attributable.
    from scripts.phase3.cgas_trace_contract_approval import TraceApprovalError, validate_owner_approval
    from scripts.phase3.cgas_trace_contract_v3 import publish_migration_packet

    packet = tmp_path / "packet.json"
    publish_migration_packet(packet, tmp_path / "owner.template.json")
    output = tmp_path / "approved.json"

    for index, mutate in enumerate(
        (
            lambda value: value.pop("owner_id"),
            lambda value: value.pop("approved_at"),
            lambda value: value.update({"owner_id": "   "}),
            lambda value: value.update({"owner_approved": False}),
        )
    ):
        approval = _signed_approval(packet)
        mutate(approval)
        owner = tmp_path / f"owner-{index}.json"
        owner.write_bytes(_canonical(approval))

        # When/Then: each is refused and nothing is published.
        with pytest.raises(TraceApprovalError):
            validate_owner_approval(packet, owner, output)
    assert not output.exists()


def test_approval_refuses_a_v3_packet_tampered_after_signature(tmp_path: Path) -> None:
    # Given: a validly signed v3 approval.
    from scripts.phase3.cgas_trace_contract_approval import TraceApprovalError, validate_owner_approval
    from scripts.phase3.cgas_trace_contract_v3 import publish_migration_packet

    packet = tmp_path / "packet.json"
    publish_migration_packet(packet, tmp_path / "owner.template.json")
    owner = tmp_path / "owner-approval.json"
    owner.write_bytes(_canonical(_signed_approval(packet)))
    validate_owner_approval(packet, owner, tmp_path / "approved.json")

    # When: the packet bytes change after the owner signed them.
    packet.write_bytes(packet.read_bytes().replace(b'"owner_approved":false', b'"owner_approved":true'))

    # Then: the stale approval is refused under a v3 rule, with no side effect.
    stale = tmp_path / "stale-approved.json"
    with pytest.raises(TraceApprovalError, match="trace_v3_approval_packet_mismatch"):
        validate_owner_approval(packet, owner, stale)
    assert not stale.exists()


def test_the_committed_v2_approval_still_reproduces_byte_for_byte(tmp_path: Path) -> None:
    # Given: the owner's real 2026-08-03 v2 approval and the record published from it.
    # This is the regression guard on making the approval path contract-aware: the v2
    # lineage must be bit-identical, because reservoir_checkpoint_000001.json binds it.
    from scripts.phase3.cgas_trace_contract_approval import validate_owner_approval

    evidence = REPOSITORY_ROOT / ".claude/evidence/cgas-production-p0"
    committed = (evidence / "approved-trace-v2.json").read_bytes()
    output = tmp_path / "approved-trace-v2.json"

    # When: the same inputs are re-validated today.
    approved = validate_owner_approval(
        evidence / "trace-v2-migration-packet.json", evidence / "trace-v2-owner-approval.json", output
    )

    # Then: the bytes are identical to what the checkpoint chain already records.
    assert output.read_bytes() == committed
    assert approved.status == "approved_trace_v2"
    assert json.loads(committed)["approval_scope"] == "trace_v2_persistence_only"
