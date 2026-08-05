# Issues — production-p0-corpus-experiment-readiness

Problems and gotchas encountered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## 2026-08-03 - Todo 1

- The in-process LSP server cached missing-import diagnostics for newly created sibling modules, while the repository-configured `basedpyright` CLI resolved the same files with `0 errors, 0 warnings, 0 notes`. The authoritative static gate is clean.
- One disposable manual-driver command initially failed at shell quoting before executing project code. The corrected command used `bytes([10])` for LF construction, passed, and its temporary directory was removed automatically.

## 2026-08-03 - Todo 2

- The mounted filesystem returns `EINVAL` for directory `renameat2(RENAME_NOREPLACE)`; publication uses a checked absent-destination fallback while existing destinations still fail.

## 2026-08-03 - Todo 2 verification remediation

- The prior checked absent-destination fallback was still raceable because plain `os.rename` could replace an empty directory created between the check and mutation. It was removed from both publication paths.

## 2026-08-03 - Todo 2 real GPFS remediation

- The mocked second-call EEXIST test was a false positive because it never invoked GPFS. Real manual QA remained broken until directory rename publication was replaced entirely.

## 2026-08-03 - Todo 1 durability remediation

- Oracle reproduced `trace_v2_publication_failed` with a verifier-valid output still visible because `_install_stream` translated the post-link directory-fsync error without rolling back its link.
- The first standalone QA command failed at Python `-c` quoting before project code executed. The corrected fully enclosed driver ran against the workspace filesystem and observed rejected publication, absent output, and no temporary residue.

## 2026-08-05 - Todo 3

- The parent orchestration poll ended after 30 minutes of inactivity while the exact CLI was still active; process inspection confirmed it continued and eventually completed successfully. The immutable rerun required another long read-only scan of the 1.1 TB trace set and was therefore run in a persistent tmux session with a durable evidence log.
- The first long run's terminal output was not durable after its tmux session exited, but its published checkpoint and current index were verified directly. The rerun log now persists the terminal JSON result.
