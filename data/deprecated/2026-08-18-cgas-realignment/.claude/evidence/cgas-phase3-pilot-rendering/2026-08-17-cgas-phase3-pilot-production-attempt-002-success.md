# CGAS Pilot Production Attempt 002 Success

Issue #8 attempt-002 completed under the separately authorized local LAMA-first
contract recorded in
`authorization-20260817-cgas-07-pilot-production-attempt-002.json`. The bounded
two-case certification passed first at
`outputs/image_frames/cgas-lama-first-production-smoke-20260817-attempt-001`.

Attempt-002 is immutable legacy adapter-v3 evidence. It does not claim that the
current adapter-v4 or production-v3/v4 authorization code emitted or can resume
its records.

The production attempt used output root
`outputs/image_frames/cgas-phase3-pilot-production-attempt-002`, loopback port
18084, Fast Downward `lama-first` revision
`b9fba250f5269a20cb0e950375720281621fb030`, and pinned Planimation backend
`94d82afb5ee122ce579dd11ca1953b7c85ca5824`. Every upload carried a locally
generated nonempty supplied plan plus the loopback containment URL
`http://127.0.0.1:18084/forbidden-solver`.

The command exited 0. Final accounting is requested 16,822, processed 16,822,
succeeded 16,822, failed 0, remaining 0, duplicate 0, and collision 0. All
16,822 records have `planning_submitted` provenance, one local LAMA plan, and
one Planimation request. The manifest and checkpoint contain the exact frozen
request state set with no omissions or duplicate identities.

The final offline audit passed 32 checks. It confirmed all 16,822 artifact and
plan paths exist inside attempt-002, independently rehashed and semantically
validated a deterministic 130-record sample, observed exactly 16,822 project-
client POSTs to `http://127.0.0.1:18084/upload/pddl`, and found zero backend
errors or forbidden-solver requests. Network evidence is limited to project-
client interception and loopback forbidden-solver containment; it is not an
OS-level network capture.

The independently reviewable read-only audit is
`audit_cgas_issue8_attempt002.py`; its retained command and PASS output are in
`2026-08-17-cgas-phase3-pilot-production-attempt-002-audit-result.txt`, with
the durable capture basis in
`2026-08-17-cgas-phase3-pilot-production-attempt-002-execution-receipt.json`.

Attempt-001 remains permanently aborted and separate. No attempt-001 record or
artifact was imported, repaired, retried, or inferred. This attempt performed
state rendering only; it did not create replay alignment, Qwen rows, model
training data, or start training.
