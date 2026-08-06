from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from cgas_production_population_support import (
    CURRENT_CHECKPOINT,
    feasible_manifest_fixture,
    feasible_population_fixture,
    population_fixture,
    rows_fixture,
)

from scripts.phase3 import cgas_production_population
from scripts.phase3.cgas_candidate_characterization_contracts import CandidateCharacterizationError
from scripts.phase3.cgas_partition_selection import RoleRecord, SelectionFeasibilityError
from scripts.phase3.cgas_production_population import PopulationRequest, _accepted_manifest, _select_rows, run
from scripts.phase3.cgas_production_population_contracts import _load_checkpoint


def test_selector_characterization_pins_current_round_one_diagnostics() -> None:
    rows = rows_fixture()
    assert len({str(row["instance_id"]) for row in rows}) == 53

    with pytest.raises(SelectionFeasibilityError) as captured:
        _select_rows(rows)

    assert captured.value.reason == "calibration_exact_39_unavailable"


def test_selector_feedback_protocol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    population = population_fixture()
    monkeypatch.setattr(cgas_production_population, "load_population_input", lambda *_args: population)
    output = tmp_path / "population"

    report = run(PopulationRequest(tmp_path, None, tmp_path / "current.json", output))

    result = json.loads(report.result.read_text(encoding="utf-8"))
    assert result["status"] == "selector_infeasible"
    assert result["reason"] == "calibration_exact_39_unavailable"
    assert result["diagnostics"] == {
        "calibration_required": 39,
        "object_counts": {"4": 33, "12": 20},
        "paired_exact_rows": 53,
        "reservoir_rows": 53,
        "signature_count": 11,
    }
    assert result["non_exhausted_streams"] == [4, 8, 12]
    assert "accepted_manifest_sha256" not in result
    assert all("cursor" not in key for key in result)
    assert not (output / "accepted_manifest.jsonl").exists()


def test_exact_result_reuse_preserves_bytes_inode_and_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    population = population_fixture()
    monkeypatch.setattr(cgas_production_population, "load_population_input", lambda *_args: population)
    request = PopulationRequest(tmp_path, None, tmp_path / "current.json", tmp_path / "population")
    first = run(request)
    before = (first.result.read_bytes(), first.result.stat().st_ino, first.result.stat().st_mtime_ns)

    second = run(request)

    assert second.read_only is True
    assert (second.result.read_bytes(), second.result.stat().st_ino, second.result.stat().st_mtime_ns) == before


def test_mismatched_existing_result_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    population = population_fixture()
    monkeypatch.setattr(cgas_production_population, "load_population_input", lambda *_args: population)
    request = PopulationRequest(tmp_path, None, tmp_path / "current.json", tmp_path / "population")
    first = run(request)
    first.result.write_bytes(b"{}\n")

    with pytest.raises(CandidateCharacterizationError, match="selector_result_collision"):
        run(request)

    assert first.result.read_bytes() == b"{}\n"


def test_interrupted_result_publication_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    population = population_fixture()
    monkeypatch.setattr(cgas_production_population, "load_population_input", lambda *_args: population)
    monkeypatch.setattr(
        cgas_production_population.os,
        "link",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("injected")),
    )
    output = tmp_path / "population"

    with pytest.raises(CandidateCharacterizationError, match="immutable_publication_failed"):
        run(PopulationRequest(tmp_path, None, tmp_path / "current.json", output))

    assert tuple(output.iterdir()) == ()


def test_accepted_manifest_rejects_authoritative_row_parity_mismatch() -> None:
    rows, records = feasible_manifest_fixture()
    first = records[0]
    mismatched = (
        RoleRecord(first.instance_id, "f" * 64, first.source_split, first.composition_signature, first.role),
        *records[1:],
    )

    with pytest.raises(SelectionFeasibilityError, match="selector_manifest_parity_invalid"):
        _accepted_manifest(rows, mismatched)


def test_accepted_manifest_requires_paired_exact_authoritative_characterization() -> None:
    rows, records = feasible_manifest_fixture()
    uncharacterized = tuple({key: value for key, value in row.items() if key != "status"} for row in rows)

    with pytest.raises(SelectionFeasibilityError, match="accepted_manifest_authoritative_parity_unavailable"):
        _accepted_manifest(uncharacterized, records)


def test_checkpoint_rejects_emitted_accounting_without_characterizations(tmp_path: Path) -> None:
    payload = json.loads(CURRENT_CHECKPOINT.read_bytes())
    empty_digest = hashlib.sha256(b"").hexdigest()
    payload["characterization"] = {"canonical_jsonl": "", "row_count": 0, "sha256": empty_digest}
    payload["reservoir"] = {
        "canonical_jsonl": "",
        "row_count": 0,
        "sha256": empty_digest,
        "signature_count": 0,
        "signatures": [],
    }
    checkpoint_root = tmp_path / "checkpoints"
    checkpoint_root.mkdir()
    checkpoint = checkpoint_root / "reservoir_checkpoint_000001.json"
    checkpoint.write_text(
        json.dumps(payload, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    )

    with pytest.raises(CandidateCharacterizationError, match="checkpoint_emitted_characterization_invalid"):
        _load_checkpoint(checkpoint)


def test_accepted_manifest_emits_exact_deterministic_481_row_matrix() -> None:
    rows, records = feasible_manifest_fixture()

    first = _accepted_manifest(rows, records)
    second = _accepted_manifest(tuple(reversed(rows)), tuple(reversed(records)))

    accepted = tuple(json.loads(line) for line in first.splitlines())
    assert first == second
    assert len(accepted) == 481
    assert len({str(row["instance_id"]) for row in accepted}) == 481
    assert Counter(str(row["split"]) for row in accepted) == Counter({"train": 402, "dev": 39, "test": 40})
    assert Counter(int(row["object_count"]) for row in accepted) == Counter({4: 190, 8: 198, 12: 93})
    assert Counter((str(row["split"]), int(row["object_count"])) for row in accepted) == Counter(
        {("train", 4): 190, ("train", 8): 198, ("train", 12): 14, ("dev", 12): 39, ("test", 12): 40}
    )
    roles_by_signature: dict[str, set[str]] = {}
    for row in accepted:
        roles_by_signature.setdefault(str(row["composition_signature"]), set()).add(str(row["split"]))
    assert all(len(roles) == 1 for roles in roles_by_signature.values())
    assert len({str(row["composition_signature"]) for row in accepted if row["split"] == "test"}) >= 10
    assert len(hashlib.sha256(first).hexdigest()) == 64


def test_run_publishes_feasible_manifest_with_exact_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    population, selection, expected_manifest = feasible_population_fixture()
    monkeypatch.setattr(cgas_production_population, "load_population_input", lambda *_args: population)
    monkeypatch.setattr(cgas_production_population, "_select_rows", lambda _rows: selection)

    report = run(PopulationRequest(tmp_path, None, tmp_path / "current.json", tmp_path / "population"))

    result = json.loads(report.result.read_bytes())
    manifest = tmp_path / "population/accepted_manifest.jsonl"
    assert result["status"] == "selector_feasible"
    assert manifest.read_bytes() == expected_manifest
    assert result["accepted_manifest_sha256"] == hashlib.sha256(expected_manifest).hexdigest()
    assert sorted(path.name for path in report.result.parent.iterdir()) == [
        "accepted_manifest.jsonl",
        report.result.name,
    ]


def test_run_reuses_exact_feasible_result_and_manifest_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    population, selection, _ = feasible_population_fixture()
    monkeypatch.setattr(cgas_production_population, "load_population_input", lambda *_args: population)
    monkeypatch.setattr(cgas_production_population, "_select_rows", lambda _rows: selection)
    request = PopulationRequest(tmp_path, None, tmp_path / "current.json", tmp_path / "population")
    first = run(request)
    manifest = first.result.parent / "accepted_manifest.jsonl"
    before = (
        first.result.stat().st_ino,
        first.result.stat().st_mtime_ns,
        manifest.stat().st_ino,
        manifest.stat().st_mtime_ns,
    )

    second = run(request)

    assert second.read_only is True
    assert (
        second.result.stat().st_ino,
        second.result.stat().st_mtime_ns,
        manifest.stat().st_ino,
        manifest.stat().st_mtime_ns,
    ) == before


def test_run_rejects_tampered_feasible_manifest_without_rewriting_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    population, selection, _ = feasible_population_fixture()
    monkeypatch.setattr(cgas_production_population, "load_population_input", lambda *_args: population)
    monkeypatch.setattr(cgas_production_population, "_select_rows", lambda _rows: selection)
    request = PopulationRequest(tmp_path, None, tmp_path / "current.json", tmp_path / "population")
    first = run(request)
    result_before = first.result.read_bytes()
    manifest = first.result.parent / "accepted_manifest.jsonl"
    manifest.write_bytes(b"{}\n")

    with pytest.raises(CandidateCharacterizationError, match="accepted_manifest_binding_invalid"):
        run(request)

    assert first.result.read_bytes() == result_before
    assert manifest.read_bytes() == b"{}\n"
