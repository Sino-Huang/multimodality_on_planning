from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .cgas_characterization_bundle import BundleMember, build_bundle
from .cgas_characterization_checkpoint_fs import linkat_proc_fd
from .cgas_characterization_final_members import FINAL_MEMBER_NAMES
from .cgas_characterization_state_directory import StateDirectoryError, TrustedStateDirectory
from .cgas_characterization_verifier import VerificationRequest, verify_characterization

_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_ANONYMOUS_FLAGS: Final = os.O_TMPFILE | os.O_RDWR | os.O_CLOEXEC
_MAX_BUNDLE_BYTES: Final = 3 * 128 * 1024 * 1024 + 16 * 1024 + 25


@dataclass(frozen=True, slots=True)
class FinalPublicationError(RuntimeError):
    rule: str
    destination: Path
    residue: Path | None = None

    def __str__(self) -> str:
        suffix = f"; private_bundle={self.residue}" if self.residue is not None else ""
        return f"final publication {self.rule}: {self.destination}{suffix}"


def publish_final_bundle(
    request: VerificationRequest, candidate_root: Path, final_path: Path, private_root: Path, state: TrustedStateDirectory
) -> None:
    """Publish one verified candidate as an immutable GPFS-compatible regular bundle."""
    candidate_report = verify_characterization(
        VerificationRequest(request.repository_root, request.source_manifest, request.checkpoint_root, candidate_root, request.module_roots)
    )
    if not candidate_report.publishable:
        raise FinalPublicationError("candidate_not_publishable", final_path)
    contents = _bundle_contents(candidate_root, candidate_report.contract_fingerprint, final_path)
    destination_descriptor = _trusted_destination(final_path, state)
    private_descriptor = _private_directory(private_root, final_path)
    descriptor: int | None = None
    try:
        destination_status = os.fstat(destination_descriptor)
        private_status = os.fstat(private_descriptor)
        if destination_status.st_dev != private_status.st_dev:
            raise FinalPublicationError("private_root_not_same_filesystem", final_path)
        if (destination_status.st_dev, destination_status.st_ino) == (private_status.st_dev, private_status.st_ino):
            raise FinalPublicationError("private_root_not_external", final_path)
        try:
            descriptor = os.open(private_root, _ANONYMOUS_FLAGS, 0o600)
        except OSError as error:
            raise FinalPublicationError("otmpfile_unsupported", final_path) from error
        os.fchmod(descriptor, 0o600)
        _write_sync(descriptor, contents, final_path)
        _anonymous_status(descriptor, len(contents), final_path)
        _verify_anonymous_bundle(descriptor, len(contents), candidate_report.contract_fingerprint, final_path)
        _anonymous_status(descriptor, len(contents), final_path)
        try:
            linkat_proc_fd(descriptor, destination_descriptor, os.fsencode(final_path.name))
        except FileExistsError as error:
            raise FinalPublicationError("destination_collision", final_path) from error
        except OSError as error:
            raise FinalPublicationError("linkat_procfd_failed", final_path) from error
        _complete_link(descriptor, destination_descriptor, final_path)
        os.close(descriptor)
        descriptor = None
    except FinalPublicationError:
        raise
    except OSError as error:
        raise FinalPublicationError("publication_failed", final_path) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(private_descriptor)
        os.close(destination_descriptor)


def _bundle_contents(candidate: Path, fingerprint: str | None, destination: Path) -> bytes:
    if fingerprint is None:
        raise FinalPublicationError("candidate_not_publishable", destination)
    members = tuple(BundleMember(name, _candidate_member(candidate, name)) for name in ("run-contract.json", "characterization.jsonl", "characterization_manifest.json"))
    return build_bundle(members, fingerprint)


def _candidate_member(candidate: Path, name: str) -> bytes:
    if name not in FINAL_MEMBER_NAMES:
        raise FinalPublicationError("candidate_member_profile", candidate)
    return (candidate / name).read_bytes()


def _directory(path: Path, destination: Path) -> int:
    try:
        return os.open(path, _DIRECTORY_FLAGS)
    except OSError as error:
        raise FinalPublicationError("directory_open_failed", destination) from error


def _trusted_destination(destination: Path, state: TrustedStateDirectory) -> int:
    try:
        expected = state.final_path(destination.name)
    except StateDirectoryError as error:
        raise FinalPublicationError("destination_not_trusted_state_component", destination) from error
    if destination != expected:
        raise FinalPublicationError("destination_not_trusted_state_component", destination)
    try:
        descriptor = os.dup(state.descriptor)
    except OSError as error:
        raise FinalPublicationError("trusted_state_duplicate_failed", destination) from error
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISDIR(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o700 or status.st_uid != os.geteuid():
            raise FinalPublicationError("trusted_state_not_owner_mode0700", destination)
        return descriptor
    except FinalPublicationError:
        os.close(descriptor)
        raise


def _private_directory(path: Path, destination: Path) -> int:
    descriptor = _directory(path, destination)
    status = os.fstat(descriptor)
    if stat.S_IMODE(status.st_mode) != 0o700 or status.st_uid != os.geteuid():
        os.close(descriptor)
        raise FinalPublicationError("private_root_not_owned_mode0700", destination)
    return descriptor


def _write_sync(descriptor: int, contents: bytes, destination: Path) -> None:
    offset = 0
    try:
        while offset < len(contents):
            written = os.write(descriptor, contents[offset:])
            if written <= 0:
                raise OSError(errno.EIO, "bundle write made no progress")
            offset += written
        os.fsync(descriptor)
    except OSError as error:
        raise FinalPublicationError("anonymous_bundle_write_or_fsync_failed", destination) from error


def _anonymous_status(descriptor: int, expected_size: int, destination: Path) -> None:
    status = os.fstat(descriptor)
    if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600 or status.st_uid != os.geteuid() or status.st_nlink != 0 or status.st_size != expected_size:
        raise FinalPublicationError("anonymous_bundle_metadata_changed", destination)


def _verify_anonymous_bundle(descriptor: int, expected_size: int, fingerprint: str | None, destination: Path) -> None:
    if expected_size > _MAX_BUNDLE_BYTES:
        raise FinalPublicationError("anonymous_bundle_too_large", destination)
    contents = os.pread(descriptor, expected_size + 1, 0)
    if len(contents) != expected_size:
        raise FinalPublicationError("anonymous_bundle_changed", destination)
    from .cgas_characterization_bundle import parse_bundle

    if fingerprint is None or parse_bundle(contents).run_fingerprint != fingerprint:
        raise FinalPublicationError("anonymous_bundle_verification_failed", destination)


def _complete_link(source_descriptor: int, destination_descriptor: int, destination: Path) -> None:
    try:
        source = os.fstat(source_descriptor)
        destination_status = os.stat(destination.name, dir_fd=destination_descriptor, follow_symlinks=False)
        if not stat.S_ISREG(source.st_mode) or stat.S_IMODE(source.st_mode) != 0o600 or source.st_uid != os.geteuid() or source.st_nlink != 1 or (source.st_dev, source.st_ino) != (destination_status.st_dev, destination_status.st_ino) or destination_status.st_nlink != 1:
            raise FinalPublicationError("destination_inode_mismatch", destination)
        os.fsync(destination_descriptor)
    except OSError as error:
        raise FinalPublicationError("link_durability_indeterminate", destination) from error
