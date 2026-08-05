# Decisions — production-p0-corpus-experiment-readiness

Architectural choices and rationales discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## 2026-08-03 - Todo 1

- `packet_sha256` inside the packet hashes the canonical packet payload before that field is added. The independently supplied owner artifact binds SHA-256 of the exact persisted packet bytes, avoiding a self-referential digest while protecting the approval boundary.
- Trace-v2 event hashes cover canonical `{event, previous_event_sha256, record_type, sequence}` bytes. The trailer's `stream_sha256` covers all canonical event lines and excludes the trailer to avoid recursion.
- Successful persistence requires caller-supplied expected event cardinality and rejects every completion status except `success_full_trace` as a success. Failure statuses cannot carry a success plan digest.
- Approval validation requires an independently supplied canonical owner record with nonempty owner identity and approval time. The worker publishes only an unapproved owner template and never fills those fields.

## 2026-08-03 - Todo 2

- Production ranges remain lazy and are materialized only per requested finite slice; the CLI publishes immutable range directories and receipt files rather than a monolithic stream.

## 2026-08-03 - Todo 2 verification remediation

- Canonical search now executes literal exhaustive branch recursion. The exact bootstrap remained bounded in practice, so no branch-sharing optimization was retained.
- GPFS compatibility is centralized in `cgas_characterization_checkpoint_fs.renameat2`: only the addressing mode changes after `EINVAL`; flags and atomic kernel no-replace behavior remain identical.

## 2026-08-03 - Todo 2 real GPFS remediation

- Candidate ranges use `receipt.json` as the last atomic hard-link commit marker. Reports use `exhaustion.json` as their last marker. Parent-directory `flock` serializes recovery and publication; exclusive `mkdir` preserves an external race winner.
- Missing-marker partials containing only expected regular files are recoverable under the lock. Commit-present or unexpected partials are never replaced and must pass exact verification or fail closed.

## 2026-08-03 - Trace-v2 owner checkpoint

- External checkpoint provenance was materialized from the direct user decision `Yes I approve` as `owner_id: "user"`, with `approved_at: "2026-08-03T14:56:48Z"`, scope `trace_v2_persistence_only`, and `owner_approved: true`.
- `.omo/evidence/cgas-production-p0/trace-v2-owner-approval.json` SHA-256 is `566d9f2cc814972245f7353b37ceb1c138aef5aee37271767699dc1e9da59c05`; the bound packet SHA-256 is `f7b93250c8302e30e8c9e15b163f2f1d3b69a57d2e7de4c58fe02e4ec67e289b`; contract SHA-256 is `5649fc7b7b4955a8879c3d997342a3d74594c9faa7458e5dc177bf3e977a0b9d`; policy SHA-256 is `559c3a7cc4fd4833726ca3a5dcbd09149b83915e0a77871e4d350c489bd76c1e`.
- The existing validator command exited zero twice and emitted the same canonical approval record. `.omo/evidence/cgas-production-p0/approved-trace-v2.json` SHA-256 is `bd6909f99ce32484f3a33863cde936c0a3128935dabaf85da783870ae7ee26a8`; its inode `2731556254`, size `585`, and mtime_ns `1785769259` were unchanged across the rerun, proving the second validation was read-only.
- Side-effect audit found no `tmp/cgas-p0-characterized/**` output and no Todo 3 cursor or scientific partition approval artifact was created. No cleanup was required; the cleanup receipt is an empty residue set.

## 2026-08-05 - Todo 3

- Round 1 is complete at checkpoint SHA-256 `fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853`; it binds approved trace `bd6909f99ce32484f3a33863cde936c0a3128935dabaf85da783870ae7ee26a8`, the exact candidate config digest, three legal ranges `{4:190,8:198,12:93}`, 481 accounting rows, 281 characterizations, and 53 paired-exact reservoir rows.
- Real trace bindings are persisted as `bfs.trace-v2.jsonl` and `iw.trace-v2.jsonl` under each candidate trace directory. The checkpoint requires stream digest, final-event digest, record count, contract digest, and completion status for both planner streams.
- Todo 4 remains blocked: round 1 is non-exhausted and no selector feedback was produced or consumed.
