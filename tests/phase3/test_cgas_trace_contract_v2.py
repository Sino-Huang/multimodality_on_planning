from __future__ import annotations

import hashlib
import importlib.util
import json
import tracemalloc
from collections.abc import Iterator
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RELEASE_SHA256 = "3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3"


def test_fixture_v1_immutable_and_v2_unapproved(tmp_path: Path) -> None:
    # Given: the frozen release before any trace-v2 implementation exists.
    release = REPOSITORY_ROOT / "data/planning_cgas_v1/release_manifest.json"
    module = importlib.util.find_spec("scripts.phase3.cgas_trace_contract_v2")

    # When: the separately versioned migration contract is requested.
    # Then: trace-v1 stays exact and v2 must provide an unapproved immutable packet.
    assert hashlib.sha256(release.read_bytes()).hexdigest() == RELEASE_SHA256
    assert module is not None, "missing unapproved trace-v2 migration packet contract"
    from scripts.phase3.cgas_trace_contract_v2 import publish_migration_packet

    publication = publish_migration_packet(tmp_path / "packet.json", tmp_path / "owner.template.json")
    packet = json.loads((tmp_path / "packet.json").read_text(encoding="utf-8"))
    template = json.loads((tmp_path / "owner.template.json").read_text(encoding="utf-8"))
    assert packet["owner_approved"] is False
    assert template["owner_approved"] is False
    assert publication.packet_sha256 == hashlib.sha256((tmp_path / "packet.json").read_bytes()).hexdigest()


def test_packet_pins_persistence_only_policy_bounds_and_publication_paths(tmp_path: Path) -> None:
    from scripts.phase3.cgas_trace_contract_v2 import (
        BFS_MAX_RECORDS,
        FIXTURE_CORPUS_ROOT,
        IW_MAX_RECORDS,
        POLICY_LIMITS,
        PRODUCTION_CORPUS_ROOT,
        PRODUCTION_STAGING_ROOT,
        publish_migration_packet,
    )

    # Given: fresh packet destinations.
    packet_path = tmp_path / "packet.json"
    template_path = tmp_path / "owner.template.json"

    # When: the migration packet is published twice.
    first = publish_migration_packet(packet_path, template_path)
    packet_before = packet_path.read_bytes()
    template_before = template_path.read_bytes()
    second = publish_migration_packet(packet_path, template_path)
    packet = json.loads(packet_before)

    # Then: rerun is read-only and policy/search bounds are exact.
    assert first.packet_sha256 == second.packet_sha256
    assert first.owner_template_sha256 == second.owner_template_sha256
    assert first.status == "published"
    assert second.status == "already_published"
    assert packet_path.read_bytes() == packet_before
    assert template_path.read_bytes() == template_before
    assert packet["delta_scope"] == "persistence_only"
    assert packet["policy_limits"] == POLICY_LIMITS
    assert BFS_MAX_RECORDS == 1_000_010_002
    assert IW_MAX_RECORDS == 40_000_003
    assert FIXTURE_CORPUS_ROOT == Path("data/planning_cgas_fixture_v1")
    assert PRODUCTION_STAGING_ROOT == Path("tmp/cgas-production-stage")
    assert PRODUCTION_CORPUS_ROOT == Path("data/planning_cgas_v1")


def test_stream_bytes_chain_trailer_and_tamper_detection(tmp_path: Path) -> None:
    from scripts.phase3.cgas_trace_stream_v2 import (
        TraceStreamError,
        TraceWriteRequest,
        verify_trace_stream,
        write_trace_stream,
    )

    # Given: two events in reverse-key insertion order and a complete BFS plan.
    output = tmp_path / "trace.jsonl"
    request = TraceWriteRequest(output, "bfs", "success_full_trace", ("(finish)",), 2)

    # When: the stream is written and verified.
    written = write_trace_stream(request, iter(({"z": 2, "a": ["x"]}, {"state": "goal"})))
    verified = verify_trace_stream(output)
    installed = output.stat()
    rerun = write_trace_stream(request, iter(({"z": 2, "a": ["x"]}, {"state": "goal"})))
    lines = output.read_bytes().splitlines()

    # Then: bytes are canonical, contiguous, chained, and trailer-bound.
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    trailer = json.loads(lines[2])
    assert lines[0].startswith(b'{"current_event_sha256":')
    assert first["sequence"] == 0 and first["previous_event_sha256"] is None
    assert second["sequence"] == 1 and second["previous_event_sha256"] == first["current_event_sha256"]
    assert trailer["record_count"] == 2
    assert trailer["final_event_sha256"] == second["current_event_sha256"]
    assert written == verified
    assert rerun == written
    current = output.stat()
    assert (current.st_ino, current.st_size, current.st_mtime_ns) == (
        installed.st_ino,
        installed.st_size,
        installed.st_mtime_ns,
    )

    tampered = tmp_path / "tampered.jsonl"
    changed = bytearray(output.read_bytes())
    changed[changed.index(b'"goal"') + 1] = ord("G")
    tampered.write_bytes(changed)
    with pytest.raises(TraceStreamError, match="trace_v2_hash_chain_mismatch"):
        verify_trace_stream(tampered)
    changed_trailer = [*lines[:-1], lines[-1].replace(b'"record_count":2', b'"record_count":3')]
    tampered.write_bytes(b"\n".join(changed_trailer) + b"\n")
    with pytest.raises(TraceStreamError, match="trace_v2_trailer_mismatch"):
        verify_trace_stream(tampered)


def test_writer_memory_is_bounded_and_success_cannot_truncate(tmp_path: Path) -> None:
    from scripts.phase3.cgas_trace_stream_v2 import TraceStreamError, TraceWriteRequest, write_trace_stream

    # Given: a lazy event source much larger than the writer's fixed buffers.
    output = tmp_path / "large.jsonl"
    event_count = 20_000
    request = TraceWriteRequest(output, "iw", "failed_no_plan_extracted", (), event_count)

    # When: events are consumed and persisted one at a time.
    tracemalloc.start()
    write_trace_stream(request, ({"index": index} for index in range(event_count)))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Then: memory does not scale with stream bytes and short success is rejected.
    assert peak < 4_000_000
    short = TraceWriteRequest(tmp_path / "short.jsonl", "bfs", "success_full_trace", ("(finish)",), 2)
    with pytest.raises(TraceStreamError, match="trace_v2_record_count_mismatch"):
        write_trace_stream(short, iter(({"only": 1},)))
    assert not short.output.exists()


def test_fsync_failure_prevents_stream_acceptance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.phase3 import cgas_trace_stream_v2

    # Given: a file fsync failure after all canonical bytes are written.
    output = tmp_path / "trace.jsonl"
    request = cgas_trace_stream_v2.TraceWriteRequest(output, "bfs", "success_full_trace", (), 0)

    # When: durability cannot be established.
    def fail_fsync(_descriptor: int) -> None:
        raise OSError("injected fsync failure")

    monkeypatch.setattr(cgas_trace_stream_v2, "_fsync_descriptor", fail_fsync)
    with pytest.raises(cgas_trace_stream_v2.TraceStreamError, match="trace_v2_fsync_failed"):
        cgas_trace_stream_v2.write_trace_stream(request, iter(()))

    # Then: no stream is accepted and no temporary file remains.
    assert not output.exists()
    assert not tuple(tmp_path.glob(".trace.jsonl-*"))


def test_directory_fsync_failure_rolls_back_only_current_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.phase3 import cgas_trace_stream_v2

    # Given: file fsync succeeds, but parent-directory fsync fails after installation.
    output = tmp_path / "trace.jsonl"
    request = cgas_trace_stream_v2.TraceWriteRequest(output, "bfs", "success_full_trace", (), 0)
    real_fsync = cgas_trace_stream_v2._fsync_descriptor
    fsync_calls = 0

    def fail_directory_fsync(descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 2:
            raise OSError("injected directory fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(cgas_trace_stream_v2, "_fsync_descriptor", fail_directory_fsync)

    # When: publication cannot establish directory-entry durability.
    with pytest.raises(cgas_trace_stream_v2.TraceStreamError, match="trace_v2_publication_failed"):
        cgas_trace_stream_v2.write_trace_stream(request, iter(()))

    # Then: this invocation's link and temporary file are both absent.
    assert fsync_calls == 3
    assert not output.exists()
    assert not tuple(tmp_path.glob(".trace.jsonl-*"))


def test_competing_output_survives_publication_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.phase3 import cgas_trace_stream_v2

    # Given: another publisher wins the output path between collision check and link.
    accepted = tmp_path / "accepted.jsonl"
    accepted_request = cgas_trace_stream_v2.TraceWriteRequest(accepted, "bfs", "success_full_trace", (), 0)
    cgas_trace_stream_v2.write_trace_stream(accepted_request, iter(()))
    accepted_bytes = accepted.read_bytes()
    output = tmp_path / "trace.jsonl"
    request = cgas_trace_stream_v2.TraceWriteRequest(output, "bfs", "success_full_trace", (), 0)
    real_link = cgas_trace_stream_v2.os.link

    def publish_competing_output(_temporary: Path, destination: Path, *, follow_symlinks: bool) -> None:
        real_link(accepted, destination, follow_symlinks=follow_symlinks)
        raise FileExistsError(destination)

    monkeypatch.setattr(cgas_trace_stream_v2.os, "link", publish_competing_output)

    # When: this invocation loses the atomic link race.
    with pytest.raises(cgas_trace_stream_v2.TraceStreamError, match="trace_v2_publication_failed"):
        cgas_trace_stream_v2.write_trace_stream(request, iter(()))

    # Then: rollback preserves the competing immutable output.
    assert output.read_bytes() == accepted_bytes
    assert not tuple(tmp_path.glob(".trace.jsonl-*"))


def test_interruption_malformed_input_and_stale_output_fail_without_mutation(tmp_path: Path) -> None:
    from scripts.phase3.cgas_trace_stream_v2 import (
        TraceStreamError,
        TraceWriteRequest,
        verify_trace_stream,
        write_trace_stream,
    )

    # Given: an interrupting source, malformed bytes, and one immutable valid stream.
    interrupted = tmp_path / "interrupted.jsonl"
    request = TraceWriteRequest(interrupted, "bfs", "failed_no_plan_extracted", (), 2)

    def interrupting_events() -> Iterator[dict[str, int]]:
        yield {"index": 0}
        raise KeyboardInterrupt

    # When: each invalid or stale operation reaches the persistence boundary.
    with pytest.raises(KeyboardInterrupt):
        write_trace_stream(request, interrupting_events())
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_bytes(b'{"record_type":"event"}\nnot-json\n')
    with pytest.raises(TraceStreamError, match="trace_v2_noncanonical_jsonl"):
        verify_trace_stream(malformed)
    stable = tmp_path / "stable.jsonl"
    stable_request = TraceWriteRequest(stable, "iw", "failed_no_plan_extracted", (), 1)
    write_trace_stream(stable_request, iter(({"value": "first"},)))
    before = stable.read_bytes()
    with pytest.raises(TraceStreamError, match="trace_v2_output_collision"):
        write_trace_stream(stable_request, iter(({"value": "stale"},)))

    # Then: interruption leaves no residue and stale publication preserves accepted bytes.
    assert not interrupted.exists()
    assert not tuple(tmp_path.glob(".interrupted.jsonl-*"))
    assert stable.read_bytes() == before


def test_approval_binds_independent_exact_packet_and_never_synthesizes_owner(tmp_path: Path) -> None:
    from scripts.phase3.cgas_trace_contract_approval import TraceApprovalError, validate_owner_approval
    from scripts.phase3.cgas_trace_contract_v2 import publish_migration_packet

    # Given: an immutable packet and a separately supplied test-only owner decision.
    packet = tmp_path / "packet.json"
    template = tmp_path / "owner.template.json"
    publish_migration_packet(packet, template)
    packet_record = json.loads(packet.read_text(encoding="utf-8"))
    owner = tmp_path / "test-only-owner-approval.json"
    owner.write_text(
        json.dumps(
            {
                "approved_at": "2026-08-03T00:00:00Z",
                "approval_scope": "trace_v2_persistence_only",
                "contract_id": "cgas_trace_contract_v2",
                "contract_sha256": packet_record["new_contract_sha256"],
                "owner_approved": True,
                "owner_id": "test-only-owner",
                "packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
                "policy_sha256": packet_record["policy_sha256"],
                "schema_version": "cgas_trace_contract_owner_approval_v1",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    # When: exact approval is validated, then packet bytes are changed.
    output = tmp_path / "approved.json"
    approved = validate_owner_approval(packet, owner, output)
    packet.write_bytes(packet.read_bytes().replace(b'"owner_approved":false', b'"owner_approved":true'))

    # Then: the independent artifact binds exact bytes and stale approval emits nothing.
    assert approved.owner_approval_sha256 == hashlib.sha256(owner.read_bytes()).hexdigest()
    assert json.loads(owner.read_text(encoding="utf-8"))["owner_id"] == "test-only-owner"
    with pytest.raises(TraceApprovalError, match="trace_v2_approval_packet_mismatch"):
        validate_owner_approval(packet, owner, tmp_path / "stale-approved.json")
    assert not (tmp_path / "stale-approved.json").exists()
