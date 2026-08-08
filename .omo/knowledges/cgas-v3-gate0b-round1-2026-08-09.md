# CGAS trace-v3 Gate 0b round 1

Gate 0b passed on 2026-08-09. The isolated root `tmp/cgas-p0-characterized-v3` contains checkpoint 1,
an independent current index, 281 characterized candidates, 158 paired-exact rows, and 562 verified
v3 streams totaling 3,000,099,088 bytes. Regeneration exited 0 in 7:46.76 wall time; replay exited 0
with `read_only=true` and every stream/checkpoint/current hash unchanged.

The reusable verifier is `scripts/phase3/cgas_gate0b_verifier.py`. It selects the contract from the
signed checkpoint/approval and stream trailer bindings, never from filenames or event fields. It
checks the explicit approval/contract/policy digest on every characterization and verifies that the
checkpoint-bound stream set exactly equals the isolated output stream set.

Semantic comparison found 281/281 candidate overlap, zero BFS summary or identity mismatches, zero
IW regressions, 112 expected width-2 lifts, 53 common IW successes, and 116 common failures. A
deterministic 24-stream BFS sample covered 22,036 events; the complete bound-v2 IW scan covered
14,252 events. Both had zero retained-field and certificate mismatches. Evidence is under
`.claude/evidence/cgas-trace-contract-v3/gate0b-round1-2026-08-09/`.

The v2 corpus remains intact: 1,116 streams, 2,418,948,358,346 bytes, unchanged checkpoint/current/
approval/release digests, and no checkpoint 2. Any later v2 byte release is a separate destructive
task and was not performed here.
