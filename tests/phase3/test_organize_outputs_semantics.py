from __future__ import annotations

from inspect import Parameter, signature
import json
from pathlib import Path

import pytest

from scripts.phase3.organize_outputs import OrganizerError, apply, verify
from scripts.phase3.output_layout_contracts import DEFAULT_OUTPUT_LAYOUT
from scripts.phase3.output_layout_journal import journal_path
from organize_outputs_support import repository


def test_public_api_uses_canonical_journal_without_receipt_override() -> None:
    assert tuple(signature(apply).parameters) == ("repository", "checkpoint")
    assert signature(apply).parameters["checkpoint"].kind is Parameter.KEYWORD_ONLY
    assert tuple(signature(verify).parameters) == ("repository",)


def test_complete_journal_requires_matching_destination_snapshot(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    apply(repository_root)
    prepared_path = journal_path(repository_root) / "prepared.json"
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    prepared["relocations"][0]["snapshot"] = {}
    prepared_path.write_text(json.dumps(prepared) + "\n", encoding="utf-8")

    with pytest.raises(OrganizerError, match="tree differs from prepared snapshot"):
        verify(repository_root)

    assert not (repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[0].source.value).exists()


def test_apply_rejects_unknown_root_before_creating_journal(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    unknown = repository_root / "outputs/unapproved-root"
    unknown.mkdir()

    with pytest.raises(OrganizerError, match="outputs root does not match migration state"):
        apply(repository_root)

    assert not journal_path(repository_root).exists()
    assert (repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[0].source.value).is_dir()


def test_source_and_moved_destination_mutations_stop_resume(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    move_verified = 0

    def mutate_second_source(checkpoint: str) -> None:
        nonlocal move_verified
        if checkpoint == "move_verified":
            move_verified += 1
            if move_verified == 1:
                source = repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[1].source.value / "payload-1.txt"
                source.write_text("changed\n", encoding="utf-8")

    with pytest.raises(OrganizerError, match="tree differs from prepared snapshot"):
        apply(repository_root, checkpoint=mutate_second_source)

    first_destination = repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[0].destination.value / "payload-0.txt"
    first_destination.write_text("changed\n", encoding="utf-8")
    with pytest.raises(OrganizerError, match="tree differs from prepared snapshot"):
        apply(repository_root)


def test_verify_rejects_destination_mutation_without_rewriting_complete_journal(tmp_path: Path) -> None:
    repository_root = repository(tmp_path)
    apply(repository_root)
    complete_path = journal_path(repository_root) / "complete.json"
    before = complete_path.read_bytes()
    destination = repository_root / DEFAULT_OUTPUT_LAYOUT.relocations[0].destination.value / "payload-0.txt"
    destination.write_text("changed\n", encoding="utf-8")

    with pytest.raises(OrganizerError, match="tree differs from prepared snapshot"):
        verify(repository_root)

    assert complete_path.read_bytes() == before
