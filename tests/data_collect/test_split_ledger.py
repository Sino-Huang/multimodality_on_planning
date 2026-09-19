from __future__ import annotations

import json
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
    assert json.loads(first) == {
        "domain": "( define ( domain tiny ) ( :predicates ( ready ) ) )",
        "problem": "( define ( problem old-name ) ( :domain tiny ) ( :init ( ready ) ) ( :goal ( ready ) ) )",
    }
    assert whole_instance_identity(DOMAIN, PROBLEM.replace(b"(ready)))", b"(missing)))")) != first


def test_split_assignment_id_is_stable_for_one_identity_and_split() -> None:
    first = split_assignment_id("whole-instance", "train")

    assert first == split_assignment_id("whole-instance", "train")
    assert json.loads(first) == {"identity": "whole-instance", "split": "train"}
    assert first != split_assignment_id("whole-instance", "test")
    assert first != split_assignment_id("other-instance", "train")


def test_split_ledger_adds_unknown_identities_without_rewriting_existing_entries(tmp_path: Path) -> None:
    ledger_path = tmp_path / "split-ledger.jsonl"
    ledger = SplitLedger(ledger_path)

    assert ledger.split_for("first") is None
    assert ledger.assign("first", "train") == "train"
    first_bytes = ledger_path.read_bytes()
    expected = {
        "assignment_id": split_assignment_id("first", "train"),
        "identity": "first",
        "split": "train",
    }
    assert first_bytes == (json.dumps(expected, separators=(",", ":"), sort_keys=True) + "\n").encode()
    assert ledger.assignment_id_for("first") == split_assignment_id("first", "train")

    assert ledger.assign("first", "train") == "train"
    assert ledger_path.read_bytes() == first_bytes
    assert ledger.assign("second", "dev") == "dev"
    assert ledger_path.read_bytes().startswith(first_bytes)
    assert SplitLedger(ledger_path).assignments() == {
        "first": "train",
        "second": "dev",
    }


def test_split_ledger_rejects_reassignment_and_leaves_ledger_unchanged(tmp_path: Path) -> None:
    ledger_path = tmp_path / "split-ledger.jsonl"
    ledger = SplitLedger(ledger_path)
    ledger.assign("fixed", "test")
    original = ledger_path.read_bytes()

    with pytest.raises(SplitReassignmentError, match="fixed.*test.*train"):
        ledger.assign("fixed", "train")

    assert ledger_path.read_bytes() == original
    assert ledger.split_for("fixed") == "test"


def test_split_ledger_reloads_before_extension_to_prevent_stale_reassignment(tmp_path: Path) -> None:
    ledger_path = tmp_path / "split-ledger.jsonl"
    first_writer = SplitLedger(ledger_path)
    stale_writer = SplitLedger(ledger_path)
    first_writer.assign("shared", "dev")
    original = ledger_path.read_bytes()

    with pytest.raises(SplitReassignmentError, match="shared.*dev.*test"):
        stale_writer.assign("shared", "test")

    assert ledger_path.read_bytes() == original
    assert stale_writer.split_for("shared") == "dev"


def test_split_ledger_rejects_conflicting_records_for_one_identity(tmp_path: Path) -> None:
    ledger_path = tmp_path / "split-ledger.jsonl"
    ledger_path.write_text(
        "".join(
            json.dumps(
                {
                    "assignment_id": split_assignment_id("shared", split),
                    "identity": "shared",
                    "split": split,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
            for split in ("train", "test")
        ),
        encoding="utf-8",
    )

    with pytest.raises(SplitLedgerFormatError, match="Conflicting assignments.*shared"):
        SplitLedger(ledger_path)
