# Phase 3 CGAS Final Bundle Publication

`regular_bundle_linkat_v1` publishes one `cgas-final-bundle-v1` mode-0600 regular file. The final path is never a directory, symlink, or adopted existing entry.

The bundle is deterministic and contains only canonical run-contract, JSONL, and manifest bytes. Its byte identity is contract-scoped provenance for the exact run contract, not a cross-shard scientific-determinism claim. Histories sharing one contract must produce identical bundle bytes; different shard-count contracts intentionally produce different run-contract and bundle byte identities even when their scientific JSONL and manifest bytes are identical. Published verification opens a no-follow regular descriptor, checks owner/mode/link count and stable identity, parses logical members in memory without extraction or writes, and reuses the private-candidate authoritative row, replay, and manifest verifier.

The live GPFS transaction creates an anonymous mode-0600 `O_TMPFILE` inode in an external owner-mode-0700 private root. It writes and fsyncs deterministic bundle bytes, pins regular type/mode/owner/link count zero/size through the held descriptor, and runs authoritative scientific bundle verification on bytes read from that descriptor before publication. No private bundle source pathname is created.

The GPFS probe observed `ENOENT` from empty-path `linkat(AT_EMPTY_PATH)`. Publication therefore uses `linkat(AT_FDCWD, /proc/self/fd/<fd>, trusted_state_dirfd, final_name, AT_SYMLINK_FOLLOW)` relative to the pinned state child.

There is no private source unlink or private-parent fsync because the anonymous inode has no namespace entry. The final name is one safe component below the pinned mode-0700 `<repository>/tmp/.cgas-characterization` child; the shared `tmp` parent is never a publication destination.

Focused verification run:

```bash
source ~/cd_vlaplan && pytest -q --basetemp "tmp/cgas-final-bundle-doc-qa" tests/phase3/test_cgas_characterization_final_publication.py
git diff --check
```

Result: `3 passed`; `git diff --check` produced no output.
