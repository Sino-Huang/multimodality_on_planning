from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.phase3 import cgas_provenance
from scripts.phase3.pddl import parse_task


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPOSITORY_ROOT / "tests/fixtures/planning/blocksworld_nontrivial.json"


def test_verify_regenerates_rows_and_requires_digest_bound_approval(tmp_path: Path) -> None:
    # Given: an approved corpus with its retained authoritative manifest.
    output_root = tmp_path / "cgas"
    generated = _run_cgas(
        "--source-manifest", str(_write_fixture_manifest(tmp_path)), "--output-root", str(output_root)
    )
    assert generated.returncode == 0, generated.stderr
    assert (output_root / "source_manifest.jsonl").is_file()
    assert (output_root / "approved.json").is_file()

    # When: a trainable row is modified without changing its stored record id.
    train_path = output_root / "source" / "train.jsonl"
    rows = [json.loads(line) for line in train_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["selected_action"] = "(tampered action)"
    train_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    verified = _run_cgas("--verify", "--output-root", str(output_root))

    # Then: the recomputation rejects and withdraws the directly readable source rows.
    assert verified.returncode != 0
    report = json.loads(verified.stdout)
    assert report["accepted_rows"] == 0
    assert any(item["reason"] == "recomputed_row_mismatch" for item in report["errors"])
    assert not (output_root / "source").exists()
    assert (output_root / ".invalid-source").is_dir()


def test_verify_rejects_tampered_partition_and_missing_approval(tmp_path: Path) -> None:
    # Given: an approved corpus copied for independent tampering checks.
    output_root = tmp_path / "cgas"
    generated = _run_cgas(
        "--source-manifest", str(_write_fixture_manifest(tmp_path)), "--output-root", str(output_root)
    )
    assert generated.returncode == 0, generated.stderr
    candidate = tmp_path / "candidate"
    shutil.copytree(output_root, candidate)

    # When: a structural-OOD membership is changed to a train instance.
    manifest_path = candidate / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["partitions"]["structural_ood"]["ids"] = ["blocksworld-train-fixture-0000"]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    verified = _run_cgas("--verify", "--output-root", str(candidate))

    # Then: partition tampering invalidates and withdraws the candidate.
    assert verified.returncode != 0
    assert any(item["reason"] == "manifest_partition_mismatch" for item in json.loads(verified.stdout)["errors"])
    assert not (candidate / "source").exists()


def test_publish_restores_previous_root_when_candidate_move_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: an approved root and a complete staged replacement.
    output_root = tmp_path / "published"
    output_root.mkdir()
    (output_root / "approved.txt").write_text("previous", encoding="utf-8")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "candidate.txt").write_text("next", encoding="utf-8")
    real_replace = os.replace

    def fail_second_move(source: Path | str, destination: Path | str) -> None:
        if Path(source) == candidate and Path(destination) == output_root:
            raise OSError("injected candidate move failure")
        real_replace(source, destination)

    monkeypatch.setattr(cgas_provenance.os, "replace", fail_second_move)

    # When: publication fails after the old root has been moved aside.
    with pytest.raises(OSError, match="injected candidate move failure"):
        cgas_provenance._publish(candidate, output_root)

    # Then: the approved root remains available at its contract path.
    assert (output_root / "approved.txt").read_text(encoding="utf-8") == "previous"
    assert candidate.is_dir()


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (("domain", "logistics", "source_domain_mismatch"), ("object_count", 999, "structural_ood_object_count_mismatch"), ("horizon", 999, "structural_ood_horizon_mismatch"), ("composition", "fabricated", "structural_ood_composition_mismatch")),
)
def test_cgas_rejects_invalid_declared_source_contract(tmp_path: Path, field: str, value: str | int, reason: str) -> None:
    # Given: a valid manifest with one independently invalid declaration.
    manifest_path = _write_fixture_manifest(tmp_path)
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    target = rows[0] if field == "domain" else rows[-1]
    target[field] = value
    manifest_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    # When: the real CLI attempts publication.
    result = _run_cgas("--source-manifest", str(manifest_path), "--output-root", str(tmp_path / "output"))

    # Then: no source corpus is published and the field-specific contract reason is exposed.
    assert result.returncode != 0
    assert reason in result.stderr
    assert not (tmp_path / "output" / "source").exists()


def test_cgas_retains_calibration_only_in_manifest_and_creates_nested_output(tmp_path: Path) -> None:
    # Given: a valid source manifest extended with a unique calibration member.
    manifest_path = _write_fixture_manifest(tmp_path)
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    calibration = dict(rows[0])
    calibration["instance_id"] = "blocksworld-calibration-fixture-0000"
    calibration["split"] = "calibration"
    rows.append(calibration)
    manifest_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    output_root = tmp_path / "fresh" / "nested" / "output"

    # When: publication targets a parent hierarchy that does not exist yet.
    result = _run_cgas("--source-manifest", str(manifest_path), "--output-root", str(output_root))

    # Then: calibration is retained in the partition manifest but has no trainable JSONL.
    assert result.returncode == 0, result.stderr
    manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["partitions"]["calibration"]["ids"] == ["blocksworld-calibration-fixture-0000"]
    assert sorted(path.name for path in (output_root / "source").glob("*.jsonl")) == ["dev.jsonl", "test.jsonl", "train.jsonl"]


def test_cgas_rejects_semantic_pddl_domain_and_duplicate_id(tmp_path: Path) -> None:
    # Given: a manifest whose PDDL domain is semantic-non-Blocksworld.
    manifest_path = _write_fixture_manifest(tmp_path)
    domain_path = tmp_path / "domain.pddl"
    domain_path.write_text(domain_path.read_text(encoding="utf-8").replace("(domain blocksworld)", "(domain logistics)"), encoding="utf-8")

    # When: the real CLI parses the changed PDDL.
    semantic = _run_cgas("--source-manifest", str(manifest_path), "--output-root", str(tmp_path / "semantic"))

    # Then: it rejects before publication.
    assert semantic.returncode != 0
    assert "pddl_domain_mismatch" in semantic.stderr

    # Given: a separate valid manifest with a duplicate train identity.
    duplicate_manifest = _write_fixture_manifest(tmp_path / "duplicate")
    rows = [json.loads(line) for line in duplicate_manifest.read_text(encoding="utf-8").splitlines()]
    rows.append(dict(rows[0]))
    duplicate_manifest.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    # When: the real CLI receives the duplicate declaration.
    duplicate = _run_cgas("--source-manifest", str(duplicate_manifest), "--output-root", str(tmp_path / "duplicate-output"))

    # Then: it rejects the duplicate identity deterministically.
    assert duplicate.returncode != 0
    assert "duplicate_instance_id" in duplicate.stderr


def test_cgas_rejects_initially_solved_split_without_planner_transition_rows(tmp_path: Path) -> None:
    # Given: a valid manifest whose dev problem is solved by its initial state.
    manifest_path = _write_fixture_manifest(tmp_path)
    solved_problem = tmp_path / "solved-dev.pddl"
    solved_problem.write_text((tmp_path / "problem.pddl").read_text(encoding="utf-8").replace("(and (on a b))", "(arm-empty)"), encoding="utf-8")
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    next(row for row in rows if row["split"] == "dev")["problem_path"] = str(solved_problem)
    manifest_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    # When: the real CLI regenerates planner transitions for every required split.
    output_root = tmp_path / "planner-empty"
    result = _run_cgas("--source-manifest", str(manifest_path), "--output-root", str(output_root))

    # Then: publication fails before any approved trainable corpus appears.
    assert result.returncode != 0
    assert "missing_required_planner_rows:dev:breadth_first_search" in result.stderr
    assert not (output_root / "approved.json").exists()
    assert not (output_root / "source").exists()


def _write_fixture_manifest(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    domain_path = root / "domain.pddl"
    problem_path = root / "problem.pddl"
    domain_path.write_text(fixture["domain_pddl"].replace("(domain blocksworld-4ops)", "(domain blocksworld)"), encoding="utf-8")
    problem_path.write_text(fixture["problem_pddl"].replace("(:domain blocksworld-4ops)", "(:domain blocksworld)"), encoding="utf-8")
    rows = [
        {
            "domain": "blocksworld",
            "instance_id": f"blocksworld-{split}-fixture-0000",
            "problem_path": str(problem_path),
            "domain_path": str(domain_path),
            "split": split,
            "structural_ood": False,
        }
        for split in ("train", "dev", "test")
    ]
    rows.append(
        {
            "domain": "blocksworld",
            "instance_id": "blocksworld-ood-heldout-0000",
            "problem_path": str(problem_path),
            "domain_path": str(domain_path),
            "split": "structural_ood",
            "structural_ood": True,
            "object_count": 3,
            "horizon": 2,
            "composition": cgas_provenance.canonical_composition(parse_task(domain_path, problem_path)),
        }
    )
    path = root / "instances.jsonl"
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return path


def _run_cgas(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.phase3.cgas_provenance", *arguments],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
