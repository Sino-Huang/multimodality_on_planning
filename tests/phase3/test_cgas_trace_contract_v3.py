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
