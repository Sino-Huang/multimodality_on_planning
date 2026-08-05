# Production P0 Finite CGAS Candidates - 2026-08-03

Todo 2 implements deterministic lazy finite candidate streams for object counts 4, 8, and 12. Stable initial states and historical partial goals are generated from integer partitions and SHA-256 family ordering; candidate identity uses two-sorted directed graph refinement, individualization, and canonical leaf bytes. Lehmer unranking uses integer divmod and never materializes the full large stream.

The production configuration is `configs/cgas/production_p0_candidates.json` with quotas 190, 198, and 93. Bootstrap produced frontiers 4=600, 8=594, 12=558 with 13 immutable ranges. A later 12-object slice at start rank 550 with count 8 produced 7 emitted rows and 1 solved row.

The mounted filesystem returns `EINVAL` for directory `renameat2(RENAME_NOREPLACE)`, so publication has a narrow checked absent-destination `os.rename` fallback; existing destinations still fail instead of being replaced.

## Verification remediation

The checked `os.rename` fallback was unsafe under a destination-creation race and has been removed. Both range and report publication now use the shared `renameat2` wrapper. On GPFS, a relative-dirfd invocation returns `EINVAL`; the wrapper resolves both pinned parent descriptors through `/proc/self/fd` and retries atomically with absolute paths plus `AT_FDCWD`, retaining `RENAME_NOREPLACE`.

Canonical graph search no longer reuses automorphic branch results. Every member of the selected lowest-color nonsingleton object cell is passed through depth-marker individualization and recursive refinement. The exact bootstrap remains fast and preserves frontiers `{4: 600, 8: 594, 12: 558}`, 13 ranges, and later-slice receipt hashes.

## Real GPFS publication correction

Directory `RENAME_NOREPLACE` is unsupported on repository GPFS for both relative and absolute addressing. The valid protocol is parent-directory locking, exclusive destination `mkdir`, atomic hard-link installation of payload files, directory fsync, and atomic receipt/commit-marker hard link last. An exception before or after the marker triggers removal of the publisher-owned destination; a crash leaves a missing-marker partial that the next publisher recovers under the same lock. Exact completed destinations are fully verified and returned read-only.
