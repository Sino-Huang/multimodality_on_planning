from __future__ import annotations

import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

import scripts.phase3.cgas_characterization_work as work
from cgas_characterization_runner_support import Sink, contract, execution, request

from scripts.phase3.cgas_characterization_contract import MAX_RUN_CONTRACT_BYTES
from scripts.phase3.cgas_characterization_runner import RunMode, RunnerError, run
from scripts.phase3.cgas_characterization_verifier import VerificationRequest, verify_characterization


@pytest.mark.parametrize("boundary", ("root", "checkpoints", "contract", "file_sync", "directory_sync"))
def test_partial_initialization_is_never_resumable_or_verifiable(
    tmp_path: Path, boundary: str
) -> None:
    # Given: an initialization operation that fails immediately after one durable boundary.
    run_request = request(tmp_path, "final")
    run_contract = contract()
    hooks = _hooks(boundary)

    # When: fresh initialization leaves its explicit failed residue behind.
    with pytest.raises(work.WorkRootError, match="initialize_failed"):
        work.initialize_work_root(run_request.final_root, run_contract.canonical_bytes, hooks)

    # Then: work inspection, verifier, shard, and resume reject before any characterizer call.
    with pytest.raises(work.WorkRootError, match="incomplete_initialization"):
        work.require_work_root(run_request.final_root, run_contract.canonical_bytes)
    report = verify_characterization(
        VerificationRequest(run_request.repository_root, run_request.source_manifest, run_request.final_root.with_name("final.work"), None)
    )
    assert report.valid is False
    assert report.errors[0].startswith("work_root incomplete_initialization")
    calls: list[str] = []
    run_execution = execution(run_contract, calls, Sink())
    for mode in (RunMode.SHARD, RunMode.RESUME):
        with pytest.raises(RunnerError, match="incomplete_initialization"):
            run(run_request, mode, run_execution)
    assert calls == []


def test_successful_initialization_has_exact_resumable_tree_and_fresh_refuses_it(tmp_path: Path) -> None:
    # Given: one new final root and a canonical immutable contract.
    run_request = request(tmp_path, "final")
    run_contract = contract()

    # When: initialization completes all file and directory durability boundaries.
    work_root = work.initialize_work_root(run_request.final_root, run_contract.canonical_bytes)

    # Then: only the exact initialized tree is accepted and fresh cannot replace it.
    assert work.require_work_root(run_request.final_root, run_contract.canonical_bytes) == work_root
    assert {path.name for path in work_root.iterdir()} == {"checkpoints", "run-contract.json"}
    with pytest.raises(work.WorkRootError, match="fresh_root_exists"):
        work.initialize_work_root(run_request.final_root, run_contract.canonical_bytes)


def test_successful_initialization_syncs_marker_creation_and_removal(tmp_path: Path) -> None:
    # Given: hookable directory fsync operations that record every durability boundary.
    run_request = request(tmp_path, "final")
    calls: list[int] = []

    def record_directory_sync(descriptor: int) -> None:
        calls.append(descriptor)
        work._fsync_descriptor(descriptor)

    hooks = work.WorkInitializationHooks(os.mkdir, work._write_contents_at, work._fsync_descriptor, record_directory_sync, work._mkdir_at)

    # When: a fresh work root completes initialization.
    work.initialize_work_root(run_request.final_root, contract().canonical_bytes, hooks)

    # Then: marker creation, checkpoint creation, payload creation, and marker removal are each durable.
    assert len(calls) == 8


@pytest.mark.parametrize("entry_name", ("final", "final.work"))
@pytest.mark.parametrize("entry_kind", ("dangling_symlink", "symlink", "file", "directory", "fifo"))
def test_fresh_rejects_every_existing_final_or_work_entry_before_mutation(
    tmp_path: Path, entry_name: str, entry_kind: str
) -> None:
    # Given: one unsafe directory entry at either fresh lifecycle root location.
    run_request = request(tmp_path, "final")
    _create_entry(tmp_path / entry_name, entry_kind)
    other = tmp_path / ("final.work" if entry_name == "final" else "final")

    # When: fresh initialization checks both root entries.
    with pytest.raises(work.WorkRootError, match="fresh_root_exists"):
        work.initialize_work_root(run_request.final_root, contract().canonical_bytes)

    # Then: it performs no mutation at the otherwise absent sibling root.
    assert os.path.lexists(other) is False


@pytest.mark.parametrize("entry_kind", ("dangling_symlink", "symlink", "file", "fifo"))
def test_require_rejects_unsafe_existing_work_entries(tmp_path: Path, entry_kind: str) -> None:
    # Given: a non-directory work-root entry that may bypass path-following existence checks.
    run_request = request(tmp_path, "final")
    _create_entry(tmp_path / "final.work", entry_kind)

    # When: resume inspects the deterministic work-root entry.
    with pytest.raises(work.WorkRootError, match="unsafe_work_root_entry"):
        work.require_work_root(run_request.final_root, contract().canonical_bytes)

    # Then: no unsafe entry is accepted as resumable state.
    assert os.path.lexists(tmp_path / "final.work") is True


@pytest.mark.parametrize("entry_kind", ("dangling_symlink", "symlink", "file", "directory", "fifo"))
def test_require_rejects_every_final_entry_even_with_valid_work_root(tmp_path: Path, entry_kind: str) -> None:
    # Given: an initialized work root followed by an unsafe final-root entry.
    run_request = request(tmp_path, "final")
    run_contract = contract()
    work.initialize_work_root(run_request.final_root, run_contract.canonical_bytes)
    _create_entry(run_request.final_root, entry_kind)

    # When: resume inspects final and work entries through the parent descriptor.
    with pytest.raises(work.WorkRootError, match="resume_root_missing_or_final_present"):
        work.require_work_root(run_request.final_root, run_contract.canonical_bytes)

    # Then: existing final entries always block resume, including dangling symlinks.
    assert os.path.lexists(run_request.final_root) is True


def test_repo_local_dangling_final_symlink_rejects_fresh_before_work_creation() -> None:
    # Given: a dangling final-root symlink physically created under this repository checkout.
    with TemporaryDirectory(prefix=".cgas-work-root-", dir=Path.cwd()) as temporary:
        root = Path(temporary)
        run_request = request(root, "final")
        run_request.final_root.symlink_to(root / "missing-target")

        # When: fresh initialization receives that GPFS-local dangling entry.
        with pytest.raises(work.WorkRootError, match="fresh_root_exists"):
            work.initialize_work_root(run_request.final_root, contract().canonical_bytes)

        # Then: no sibling work root is created through the dangling-entry bypass.
        assert os.path.lexists(root / "final.work") is False


def test_initialize_rejects_post_guard_work_root_replacement(tmp_path: Path) -> None:
    # Given: a root-creation hook that replaces its new directory with a dangling symlink.
    run_request = request(tmp_path, "final")

    def replace_new_directory(path: Path, mode: int) -> None:
        os.mkdir(path, mode)
        os.rmdir(path)
        path.symlink_to(path.with_name("missing-target"))

    hooks = work.WorkInitializationHooks(
        replace_new_directory, work._write_contents_at, work._fsync_descriptor, work._fsync_descriptor, work._mkdir_at
    )

    # When: initialization re-checks the just-created root through a no-follow descriptor.
    with pytest.raises(work.WorkRootError, match="initialize_failed"):
        work.initialize_work_root(run_request.final_root, contract().canonical_bytes, hooks)

    # Then: it preserves the substituted residue and never writes children through it.
    assert (tmp_path / "final.work").is_symlink()


@pytest.mark.parametrize("boundary", ("marker", "checkpoints", "contract", "file_sync"))
def test_post_normalization_work_root_swap_never_writes_through_substitute(tmp_path: Path, boundary: str) -> None:
    # Given: each post-normalization operation can replace the public root entry with an outside symlink.
    run_request = request(tmp_path, "final")
    outside = tmp_path / "outside"
    parked = tmp_path / "parked"
    outside.mkdir()
    swapped = False

    def swap() -> None:
        nonlocal swapped
        if not swapped:
            os.rename(tmp_path / "final.work", parked)
            (tmp_path / "final.work").symlink_to(outside, target_is_directory=True)
            swapped = True

    def write_contents(parent: int, name: str, contents: bytes) -> None:
        if boundary == "marker" and name == ".initializing":
            swap()
        work._write_contents_at(parent, name, contents)

    def mkdir_checkpoints(parent: int, name: str, mode: int) -> None:
        work._mkdir_at(parent, name, mode)
        if boundary == "checkpoints":
            swap()

    def fsync_file(descriptor: int) -> None:
        work._fsync_descriptor(descriptor)
        if boundary == "file_sync":
            swap()

    def fsync_directory(descriptor: int) -> None:
        work._fsync_descriptor(descriptor)
        if boundary == "contract" and not swapped:
            swap()

    hooks = work.WorkInitializationHooks(os.mkdir, write_contents, fsync_file, fsync_directory, mkdir_checkpoints)

    # When: initialization continues through the descriptor after its public pathname is replaced.
    with pytest.raises(work.WorkRootError, match="initialize_indeterminate"):
        work.initialize_work_root(run_request.final_root, contract().canonical_bytes, hooks)

    # Then: no marker, checkpoint, or contract was written into the substituted outside target.
    assert list(outside.iterdir()) == []
    assert (parked / "run-contract.json").is_file()
    with pytest.raises(work.WorkRootError, match="unsafe_work_root_entry"):
        work.require_work_root(run_request.final_root, contract().canonical_bytes)


@pytest.mark.parametrize("size", (MAX_RUN_CONTRACT_BYTES + 1, 1 << 40))
def test_oversize_sparse_contract_rejects_work_runner_and_verifier_before_read(
    tmp_path: Path, size: int
) -> None:
    # Given: an exact initialized tree whose owner-safe contract leaf is sparse and oversized.
    run_request = request(tmp_path, "final")
    run_contract = contract()
    work.initialize_work_root(run_request.final_root, run_contract.canonical_bytes)
    _replace_contract_with_sparse_file(tmp_path / "final.work" / "run-contract.json", size)

    # When: work, runner, and verifier inspect the persisted contract descriptor.
    with pytest.raises(work.WorkRootError, match="incomplete_initialization"):
        work.require_work_root(run_request.final_root, run_contract.canonical_bytes)
    report = verify_characterization(
        VerificationRequest(run_request.repository_root, run_request.source_manifest, tmp_path / "final.work", None)
    )
    calls: list[str] = []
    run_execution = execution(run_contract, calls, Sink())
    with pytest.raises(RunnerError, match="incomplete_initialization"):
        run(run_request, RunMode.RESUME, run_execution)

    # Then: the stable failures occur before pread, canonical parsing, or characterization.
    assert report.errors[0].startswith("work_root incomplete_initialization")
    assert calls == []


def test_repo_local_sgid_parent_normalizes_work_and_checkpoint_modes_for_resume_publication() -> None:
    # Given: a repository-local SGID parent that would otherwise taint child directory modes.
    with TemporaryDirectory(prefix=".cgas-sgid-", dir=Path.cwd()) as temporary:
        root = Path(temporary)
        root.chmod(stat.S_ISGID | 0o700)
        run_request = request(root, "final")
        run_request.private_root.chmod(0o700)
        run_contract = contract(count=1)
        calls: list[str] = []
        run_execution = execution(run_contract, calls, Sink())

        # When: fresh initialization and resume publish the one canonical checkpoint.
        work_root = run(run_request, RunMode.FRESH, run_execution).work_root
        assert stat.S_IMODE(work_root.stat().st_mode) == 0o700
        assert stat.S_IMODE((work_root / "checkpoints").stat().st_mode) == 0o700
        report = run(run_request, RunMode.RESUME, run_execution)

        # Then: the exact-mode root is resumable and checkpoint publication completes.
        assert (report.characterized_count, calls) == (1, ["synthetic-0000"])
        assert (work_root / "checkpoints" / "0000.json").is_file()


def _create_entry(path: Path, entry_kind: str) -> None:
    match entry_kind:
        case "dangling_symlink":
            path.symlink_to(path.with_name("missing-target"))
        case "symlink":
            target = path.with_name("target")
            target.write_bytes(b"target")
            path.symlink_to(target)
        case "file":
            path.write_bytes(b"entry")
        case "directory":
            path.mkdir()
        case "fifo":
            os.mkfifo(path)
        case unreachable:
            raise AssertionError(unreachable)


def _replace_contract_with_sparse_file(path: Path, size: int) -> None:
    path.unlink()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        os.ftruncate(descriptor, size)
    finally:
        os.close(descriptor)


def _hooks(boundary: str) -> work.WorkInitializationHooks:
    def fail_after(operation):
        def wrapped(*args):
            operation(*args)
            raise OSError(boundary)

        return wrapped

    match boundary:
        case "root":
            return work.WorkInitializationHooks(fail_after(os.mkdir), work._write_contents_at, work._fsync_descriptor, work._fsync_descriptor, work._mkdir_at)
        case "checkpoints":
            return work.WorkInitializationHooks(os.mkdir, work._write_contents_at, work._fsync_descriptor, work._fsync_descriptor, fail_after(work._mkdir_at))
        case "contract":
            return work.WorkInitializationHooks(os.mkdir, fail_after(work._write_contents_at), work._fsync_descriptor, work._fsync_descriptor, work._mkdir_at)
        case "file_sync":
            return work.WorkInitializationHooks(os.mkdir, work._write_contents_at, fail_after(work._fsync_descriptor), work._fsync_descriptor, work._mkdir_at)
        case "directory_sync":
            return work.WorkInitializationHooks(os.mkdir, work._write_contents_at, work._fsync_descriptor, fail_after(work._fsync_descriptor), work._mkdir_at)
        case unreachable:
            raise AssertionError(unreachable)
