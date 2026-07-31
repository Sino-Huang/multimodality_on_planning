# Phase 3 CGAS Characterization Checkpoint

## Scope

Implemented canonical per-row checkpoint parsing and descriptor-rooted, durable no-replace publication. This is an isolated library boundary only: no runner, CLI, final publication, corpus, renderer, network, approval, or commit path changed.

## Contract

- Leaves are exactly `0000.json` through `0480.json` and must be mode-0600 regular files.
- The compact sorted UTF-8 JSON envelope binds `run_fingerprint`, `row_index`, `instance_id`, and `row_digest`.
- Load parses JSON once, rejects noncanonical bytes, incorrect field sets, wrong bindings, symlinks, and invalid file metadata.
- Load pins its descriptor before and after `pread`: it requires a current-owner, mode-0600, regular leaf with link count exactly 1 and preserves the device/inode/size identity. Hardlinked or owner-mismatch leaves fail with `checkpoint must be owner regular mode 0600 single-link`.
- Publication requires a canonical, non-symlink, owner-controlled mode-0700 private root on the same filesystem. It must be external to the checkpoint root, with equality, either ancestor/descendant relationship, and descriptor-identical aliases rejected before temporary creation. It handles short writes, fsyncs the file, verifies inode/owner/mode/bytes/link count, and uses Linux `renameat2(RENAME_NOREPLACE)` as its primary path.
- Only `ENOSYS`, `EINVAL`, and `EOPNOTSUPP` invoke the GPFS-compatible fallback: descriptor-rooted `linkat` creates the non-replace destination, destination-directory fsync persists that name, descriptor-rooted unlink removes the private name, and private-directory fsync persists removal. Existing paths are never replaced. Link failure and collision retain/report only external private residue; a post-link error reports a `checkpoint link publication durability indeterminate` error and retains/reports a private residue only if it still has a name.
- `renameat2_noreplace_linkat_v1` is explicitly bound in the run contract policy. The contract fingerprint therefore changes for any protocol revision, while primary and fallback publication preserve the same canonical checkpoint bytes and scientific output.
- A focused AST regression forbids ordinary `os.rename`, `os.replace`, `Path.rename`, `Path.replace`, and `exists` call sites in the publication protocol. It pins one injected renameat2 primary operation, one injected linkat fallback operation, and explicit filesystem-wrapper imports.
- The single-writer owner-review contract has no foreign-admission ledger. Checkpoint safety is enforced by the active no-follow owner-mode validation and command-wide lifecycle lock.
- The pin scope checks `RLIMIT_NOFILE` against the current `/proc/self/fd` count plus accepted leaves, root descriptor, and reserve before opening anything. It fails closed on insufficient or unobservable capacity, and closes every opened leaf plus the root descriptor on every success and error path.
- The verifier callback boundary is pinned too: runner snapshots raw owner-mode-0600 single-link leaves and holds their descriptors before invoking the callback. Raw malformed regular leaves are retained without parsing so the verifier remains the authority on validity. Immediately after the callback, runner rescans names and pinned metadata/bytes, compares verifier-approved entries and canonical envelopes to the pre-callback descriptors, and rejects any replacement, add, removal, or same-inode content mutation as `checkpoint_state_drift` before characterization.
- Pin validation reuses the canonical checkpoint parser with the verifier's exact `CheckpointExpectation`; it no longer maintains a stale local four-field envelope schema. The same parser validates the optional canonical `row` payload and its digest alongside fingerprint, index, and instance binding, so sequential/reverse shards and resume accept row-bearing checkpoints while forged rows fail.
- `cgas_characterization_contract_pins` applies the same descriptor-lifetime discipline to `run-contract.json`: it opens the work directory and contract leaf with no-follow flags before verifier execution, validates owner mode `0600`, single-link, byte cap, and canonical bytes, and retains both descriptors through shard/resume completion. It compares the namespace entry, descriptor device/inode/size/link count, and reread canonical bytes after verification, before and after each row, and at return. Verifier reports carry contract bytes/fingerprint for comparison to this pinned snapshot; contract substitution, unlink, hardlink, extra link, and in-place content drift fail as `run_contract_drift`.

## Verification Commands

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_characterization_contract.py tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_checkpoint_publication.py tests/phase3/test_cgas_characterization_checkpoint_linkat.py tests/phase3/test_cgas_characterization_runner.py tests/phase3/test_cgas_characterization_runner_resume.py tests/phase3/test_cgas_characterization_verifier.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_checkpoint.py scripts/phase3/cgas_characterization_checkpoint_publication.py scripts/phase3/cgas_characterization_checkpoint_fs.py scripts/phase3/cgas_characterization_contract.py tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_checkpoint_publication.py tests/phase3/test_cgas_characterization_checkpoint_linkat.py tests/phase3/test_cgas_characterization_contract.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_characterization_checkpoint.py scripts/phase3/cgas_characterization_checkpoint_publication.py scripts/phase3/cgas_characterization_checkpoint_fs.py scripts/phase3/cgas_characterization_contract.py
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_characterization_runner.py tests/phase3/test_cgas_characterization_runner_resume.py tests/phase3/test_cgas_characterization_work.py tests/phase3/test_cgas_characterization_verifier.py tests/phase3/test_cgas_characterization_checkpoint.py tests/phase3/test_cgas_characterization_checkpoint_publication.py tests/phase3/test_cgas_characterization_assembly.py tests/phase3/test_cgas_characterization_runner_checkpoint_fds.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_checkpoint.py scripts/phase3/cgas_characterization_runner.py scripts/phase3/cgas_characterization_verifier.py
```

Observed results: `86 passed`, `0 errors, 0 warnings, 0 notes`, and successful compilation.

The descriptor-pinning regression suite passed twice with `102 passed` each time. It includes exact same-byte replacement, unlink, hardlink, rename, actual competing-shard publication, low-soft-limit rejection, and verifier-callback replacement/addition/removal/same-inode mutation. A direct `/proc/self/fd` driver confirmed an accepted descriptor was present inside the pin scope and that the count returned to its baseline after scope exit.

The expanded suite passed a second full run with `109 passed` in 63.07 seconds. The repository-local GPFS driver performed 20 same-byte contract unlink/recreate substitutions while retaining the contract descriptor; `require_current()` rejected the result and the `/proc/self/fd` count returned to baseline after scope exit. Compileall, LOC checks (contract pins 103, runner 185, verifier 232, contract FD tests 78), and `git diff --check` passed.

## Manual QA and Cleanup

An explicit synthetic driver created a checkpoint, loaded it back, then attempted a second publication. It printed:

```text
published=True
collision=checkpoint destination collision; immutable=True
```

Wave 2 additionally rejected same-root, private-descendant, checkpoint-descendant, symlink-alias, and descriptor-identical staging roots before allocation. Wave 3 manually exercised the actual repository-local GPFS mount: primary publication, forced ENOSYS fallback, forced EINVAL collision, link failure, destination-fsync/unlink/private-fsync post-link faults, and direct hardlink rejection by `load_checkpoint()`. Successful fallback preserved canonical bytes with current ownership, mode 0600, link count 1, and no private name; adding a hard link raised the count to 2 and caused the stable loader rejection. All disposable GPFS QA roots were removed automatically.
