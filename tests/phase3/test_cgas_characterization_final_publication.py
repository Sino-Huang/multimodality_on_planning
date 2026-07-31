from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from cgas_characterization_assembly_support import synthetic_request, write_checkpoint_history
from scripts.phase3.cgas_characterization_assembly import assemble_characterization_candidate
import scripts.phase3.cgas_characterization_final_publication as final_publication
from scripts.phase3.cgas_characterization_final_publication import FinalPublicationError, publish_final_bundle
from scripts.phase3.cgas_characterization_state_directory import open_trusted_state_directory
from scripts.phase3.cgas_characterization_verifier import VerificationRequest, verify_characterization


def test_publish_final_bundle_is_verified_regular_file_and_never_adopts_collision(tmp_path: Path) -> None:
    # Given: a verifier-clean private three-file candidate and separate same-filesystem roots.
    request, candidate_private_root = synthetic_request(tmp_path)
    write_checkpoint_history(request, tuple(range(481)))
    candidate = assemble_characterization_candidate(request, candidate_private_root).candidate_root
    final_parent = request.repository_root / "tmp" / ".cgas-characterization"
    private_publish_root = final_parent / "private-publish"
    private_publish_root.mkdir(mode=0o700)
    private_publish_root.chmod(0o700)
    destination = final_parent / "characterization.cgas"

    # When: the approved GPFS bundle profile publishes through descriptor-rooted linkat.
    with open_trusted_state_directory(request.repository_root, create=False) as state:
        publish_final_bundle(request, candidate, destination, private_publish_root, state)
    published = VerificationRequest(request.repository_root, request.source_manifest, request.checkpoint_root, destination, request.module_roots)

    # Then: consumers verify the public regular file read-only and a later publisher cannot adopt it.
    assert (verify_characterization(published).valid, stat.S_IMODE(destination.stat().st_mode), destination.stat().st_nlink) == (True, 0o600, 1)
    assert not tuple(private_publish_root.iterdir())
    with open_trusted_state_directory(request.repository_root, create=False) as state:
        with pytest.raises(FinalPublicationError, match="destination_collision"):
            publish_final_bundle(request, candidate, destination, private_publish_root, state)
    assert destination.is_file()
    assert not destination.is_symlink()
    assert os.stat(destination).st_nlink == 1


def test_publish_final_bundle_has_no_private_namespace_source_for_mutator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a verified candidate and a namespace mutator at the final descriptor-pinned link boundary.
    request, candidate_private_root = synthetic_request(tmp_path)
    write_checkpoint_history(request, tuple(range(481)))
    candidate = assemble_characterization_candidate(request, candidate_private_root).candidate_root
    final_parent = request.repository_root / "tmp" / ".cgas-characterization"
    private_publish_root = final_parent / "private-publish"
    private_publish_root.mkdir(mode=0o700)
    private_publish_root.chmod(0o700)
    destination = final_parent / "characterization.cgas"
    original_link = final_publication.linkat_proc_fd

    def assert_no_source_name_then_link(source_fd: int, destination_fd: int, destination_name: bytes) -> None:
        assert not tuple(private_publish_root.iterdir())
        original_link(source_fd, destination_fd, destination_name)

    monkeypatch.setattr(final_publication, "linkat_proc_fd", assert_no_source_name_then_link)

    # When: the mutator attempts to discover a private source before publication.
    with open_trusted_state_directory(request.repository_root, create=False) as state:
        publish_final_bundle(request, candidate, destination, private_publish_root, state)

    # Then: no source name existed, and the final inode is verifier-clean.
    published = VerificationRequest(request.repository_root, request.source_manifest, request.checkpoint_root, destination, request.module_roots)
    assert verify_characterization(published).publishable is True
    assert not tuple(private_publish_root.iterdir())


def test_publish_final_bundle_rejects_attacker_parent_outside_trusted_repository_tmp(tmp_path: Path) -> None:
    # Given: a verified candidate and an attacker-controlled destination parent outside repository tmp.
    request, candidate_private_root = synthetic_request(tmp_path)
    write_checkpoint_history(request, tuple(range(481)))
    candidate = assemble_characterization_candidate(request, candidate_private_root).candidate_root
    attacker = tmp_path / "attacker"
    attacker.mkdir(mode=0o700)

    # When: publication is directed to the attacker parent through an otherwise safe filename.
    with open_trusted_state_directory(request.repository_root, create=False) as state:
        with pytest.raises(FinalPublicationError, match="trusted_state"):
            publish_final_bundle(request, candidate, attacker / "characterization.cgas", candidate_private_root, state)

    # Then: no arbitrary caller-selected ancestor receives the public entry.
    assert not tuple(attacker.iterdir())
