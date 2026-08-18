from __future__ import annotations

from pathlib import Path

import pytest

from src.data_collect.splits import (
    SplitLedger,
    SplitLedgerFormatError,
    SplitReassignmentError,
    split_assignment_id,
    whole_instance_identity,
)


DOMAIN = b"""; source-specific comment
(define   (domain tiny)
  (:predicates (ready)))
"""
PROBLEM = b"""(define (problem old-name)
  (:domain tiny)
  (:init (ready))
  (:goal (ready)))
"""


def test_whole_instance_identity_depends_only_on_normalized_pddl_content(tmp_path: Path) -> None:
    first_root = tmp_path / "legacy" / "train" / "legacy-id"
    second_root = tmp_path / "replacement" / "test" / "new-id"
    first_root.mkdir(parents=True)
    second_root.mkdir(parents=True)
    (first_root / "domain.pddl").write_bytes(DOMAIN)
    (first_root / "problem.pddl").write_bytes(PROBLEM)
    (second_root / "domain.pddl").write_bytes(
        b"(define (domain tiny) ; moved corpus\n (:predicates (ready)))"
    )
    (second_root / "problem.pddl").write_bytes(
        b"(define   (problem old-name) (:domain tiny) (:init (ready)) (:goal (ready)))"
    )

    first = whole_instance_identity(first_root / "domain.pddl", first_root / "problem.pddl")
    second = whole_instance_identity(second_root / "domain.pddl", second_root / "problem.pddl")

    assert first == second
    assert first.startswith("sha256:")
    assert whole_instance_identity(DOMAIN, PROBLEM.replace(b"(ready)))", b"(missing)))")) != first


def test_split_assignment_id_is_stable_for_one_identity_and_split() -> None:
    first = split_assignment_id("sha256:whole-instance", "train")

    assert first == split_assignment_id("sha256:whole-instance", "train")
    assert first.startswith("sha256:")
    assert first != split_assignment_id("sha256:whole-instance", "test")
    assert first != split_assignment_id("sha256:other-instance", "train")


def test_split_ledger_adds_unknown_identities_without_rewriting_existing_entries(tmp_path: Path) -> None:
    ledger_path = tmp_path / "split-ledger.jsonl"
    ledger = SplitLedger(ledger_path)

    assert ledger.split_for("sha256:first") is None
    assert ledger.assign("sha256:first", "train") == "train"
    first_bytes = ledger_path.read_bytes()
    assert first_bytes == (
        '{"assignment_id":"'
        + split_assignment_id("sha256:first", "train")
        + '","identity":"sha256:first","split":"train"}\n'
    ).encode()
    assert ledger.assignment_id_for("sha256:first") == split_assignment_id("sha256:first", "train")

    assert ledger.assign("sha256:first", "train") == "train"
    assert ledger_path.read_bytes() == first_bytes
    assert ledger.assign("sha256:second", "dev") == "dev"
    assert ledger_path.read_bytes().startswith(first_bytes)
    assert SplitLedger(ledger_path).assignments() == {
        "sha256:first": "train",
        "sha256:second": "dev",
    }


def test_split_ledger_rejects_reassignment_and_leaves_ledger_unchanged(tmp_path: Path) -> None:
    ledger_path = tmp_path / "split-ledger.jsonl"
    ledger = SplitLedger(ledger_path)
    ledger.assign("sha256:fixed", "test")
    original = ledger_path.read_bytes()

    with pytest.raises(SplitReassignmentError, match="sha256:fixed.*test.*train"):
        ledger.assign("sha256:fixed", "train")

    assert ledger_path.read_bytes() == original
    assert ledger.split_for("sha256:fixed") == "test"


def test_split_ledger_reloads_before_extension_to_prevent_stale_reassignment(tmp_path: Path) -> None:
    ledger_path = tmp_path / "split-ledger.jsonl"
    first_writer = SplitLedger(ledger_path)
    stale_writer = SplitLedger(ledger_path)
    first_writer.assign("sha256:shared", "dev")
    original = ledger_path.read_bytes()

    with pytest.raises(SplitReassignmentError, match="sha256:shared.*dev.*test"):
        stale_writer.assign("sha256:shared", "test")

    assert ledger_path.read_bytes() == original
    assert stale_writer.split_for("sha256:shared") == "dev"


def test_split_ledger_rejects_conflicting_records_for_one_identity(tmp_path: Path) -> None:
    ledger_path = tmp_path / "split-ledger.jsonl"
    ledger_path.write_text(
        "".join(
            (
                '{"assignment_id":"'
                + split_assignment_id("sha256:shared", split)
                + '","identity":"sha256:shared","split":"'
                + split
                + '"}\n'
            )
            for split in ("train", "test")
        ),
        encoding="utf-8",
    )

    with pytest.raises(SplitLedgerFormatError, match="Conflicting assignments.*sha256:shared"):
        SplitLedger(ledger_path)
