# Learnings — production-p0-corpus-experiment-readiness

Conventions, patterns, and successful approaches discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## 2026-08-03 - Todo 1

- The fixture release contains 34 regular files. Its `release_manifest.json` remains SHA-256 `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`; the complete path/type/size/content inventory digest is `fb7012d6c340e7339b922f84e0db7d170af680132df37e7f810932850e27ff7a`.
- A constant-memory trace stream can bind each canonical event line independently, hash only emitted event-line bytes into the stream digest, and add one final canonical trailer without retaining prior event payloads.
- Exact-byte immutable rerun checks are needed at packet/template and archive boundaries; semantic equality alone is insufficient for owner approval or fixture preservation.

## 2026-08-03 - Todo 2

- Production bootstrap produced frontiers `{4: 600, 8: 594, 12: 558}` across 13 immutable ranges.
- A later 12-object slice at rank 550 with count 8 produced 7 emitted rows and 1 solved row, with independent receipt hashes for raw accounting and planner inputs.

## 2026-08-03 - Todo 2 verification remediation

- Automorphism-result reuse violated the literal every-member branch contract: runtime observation recorded only members `[0, 1]` where the selected top-level cell was `[0, 1, 2]`.
- GPFS rejects relative-dirfd `renameat2(RENAME_NOREPLACE)` with `EINVAL` but accepts the same atomic operation with absolute paths and `AT_FDCWD`; retrying the syscall preserves no-replace semantics without a userspace race.

## 2026-08-03 - Todo 2 real GPFS remediation

- The prior absolute-path conclusion was wrong: real candidate directories on GPFS return `EINVAL` for both relative-dirfd and absolute `AT_FDCWD` `RENAME_NOREPLACE`. The earlier success was on `/tmp`, a different filesystem.
- GPFS does support exclusive directory creation and no-replace regular-file hard links. A locked receipt-last protocol published all required bootstrap and exact slice artifacts successfully and preserved 49 file byte/digest/mtime observations on rerun.

## 2026-08-03 - Todo 1 durability remediation

- A successful file fsync and verifier pass are insufficient for acceptance: failure of the parent-directory fsync after `os.link` must remove the link and fsync the directory again before returning `trace_v2_publication_failed`.
- Holding an advisory lock on the parent directory across collision inspection, no-replace hard-link creation, directory fsync, and rollback makes the invocation-owned `installed` state sufficient; an inode `stat` followed by `unlink` would retain a check-then-act race.
- Exact immutable reruns remain read-only: the second identical write returns the same verification while preserving output inode, size, and mtime.

## 2026-08-05 - Todo 3

- Caching canonical BFS state IDs and maintaining the visited-ID list incrementally preserved the locked real-fixture trace digest `9f6fb29a80e4363ab3055f5ef7c4984aab3eb60a161fa4da254cd21bc0852c70f` while materially reducing repeated hashing and sorting.
- The exact round-1 run reused 117 verified trace directories, then persisted 281 actual candidate characterizations and 481 contiguous accounting rows across immutable trace-v2 BFS/IW streams. Successful traces were never truncated; the largest observed BFS stream was 12,824,621,775 bytes.
- Historical round-1 replay validates the complete checkpoint and every bound trace stream before returning `read_only=true`; the exact rerun returned `status=ok` while preserving checkpoint/index/sample trace inode, size, mtime, and SHA-256 values.

## 2026-08-05 - Independent Todo 3 round-1 artifact QA

- Independent verification confirmed checkpoint SHA-256 `fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853`, canonical round-1 index binding, exact counts `481` accounting / `281` characterizations / `53` paired exact, and all null predecessor/feedback plus cursor/range/policy/selector/approval bindings.
- The exact plan CLI rerun ran for 3h36m in persistent tmux and used the authoritative checkpoint validator over all `562` bound streams (`1,202,839,603,149` bytes). It returned exit 0 with `status=ok` and `read_only=true`; checkpoint, index, and the actual largest 22,806,128,198-byte BFS stream preserved inode, size, mtime, and whole-file SHA-256.
- Approval-before-side-effects, all six dual-commit interruption points, and torn/stale-index recovery with repeated historical replay passed (`8 passed`). No selector attempt, round-2 checkpoint, finite-exhaustion receipt, temporary partial, tmux session, characterization process, or replay process remained. Independent verdict: `confirmed`.

## 2026-08-04T14:20:50Z - Independent Todo 3 QA verification

- Verdict: `confirmed` for the current workspace source/test state. This lane did not replay or hash-copy the 1.1 TB trace tree and therefore makes no new artifact-integrity claim.
- Required focused command exited 0 with `41 passed in 52.67s`: `source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_candidate_characterization.py tests/phase3/test_cgas_candidate_characterization_contracts.py tests/phase3/test_cgas_planner_trace_streaming.py tests/phase3/test_cgas_trace_contract_v2.py`.
- Explicit dual-commit selection exited 0 with `6 passed, 14 deselected in 20.73s`; explicit finite-exhaustion selection exited 0 with `1 passed, 19 deselected in 1.94s`.
- Adjacent planner semantic-parity/performance command exited 0 with `22 passed in 1.03s`.
- Exact 20-file Todo 3 Basedpyright scope exited 0 with `0 errors, 0 warnings, 0 notes`; the matching Ruff scope exited 0 with `All checks passed!`.
- Per-file LSP diagnostics returned no diagnostics for all 20 Todo 3 Python source/test files. No LSP daemon timeout occurred, so no LSP evidence is missing.
- The 16-source no-excuse checker exited 0 with `no violations in 16 file(s)`. Focused searches found no TODO/FIXME/HACK markers, `Any`/`as any`, type/pyright ignores, empty catches, or unimplemented stubs.
- Truncation/limit review found only general retained-memory paths. Todo 3 passes a trace sink, which streams every BFS/IW event and makes `trace_complete=true`; IW recovery is explicitly disabled. Required quota/limit and successful-no-truncation tests passed.
- Cleanup receipt: no persistent QA resources were created. Pytest temporary directories were framework-managed; no product, test, plan, Boulder, generated trace, checkpoint, or current-index bytes were changed by this verification.
- The exact inherited broader regression command was independently rerun and exited 0 with `90 passed in 54.17s`; it adds planner parity/performance, partition characterization, and Todo 2 candidate/remediation coverage to the required focused set.
