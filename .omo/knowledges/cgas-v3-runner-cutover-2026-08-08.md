# CGAS trace-v3 runner cutover

The candidate-characterization runner now binds the signed trace-v3 approval, policy, model
literals, stream paths, row keys, and checkpoint trace contract explicitly. Active characterization
uses `cgas_trace_contract_v3`, `trace-v3-migration-packet.json`, `trace-v3-owner-approval.json`,
`.trace-v3.jsonl`, and `trace_v3`; it never infers a contract from a filename or event fields.

Checkpoint validation dispatches by the signed contract digest. The released checkpoint-1 lineage
continues to parse as v2 with approval SHA-256
`bd6909f99ce32484f3a33863cde936c0a3128935dabaf85da783870ae7ee26a8` and v2 contract digest
`5649fc7b7b4955a8879c3d997342a3d74594c9faa7458e5dc177bf3e977a0b9d`; a v2 stream presented at a
v3 checkpoint boundary is rejected.

## Verification

- True RED before implementation: 6 focused tests; the three preservation/compatibility guards
  were already green. Focused cutover suite: `31 passed`.
- Contract/certificate gate: `57 passed` across reader shim, IW delta, certificates, counterfactuals,
  fixture archive, and v2/v3 contract suites.
- Broad CGAS gate: `456 passed, 9 failed`; the nine failures are pre-existing alternative-profile/
  blocker-probe and Qwen/release dependency failures, including the environment mismatch
  `huggingface-hub==1.22.0` versus the existing `transformers` requirement `<1.0`.
- Runner characterization suites: `23 passed` after migrating their test fixture to v3.
- Ruff and basedpyright passed on all changed production/test modules (`0 errors` from basedpyright).
- Contract-surface audit regenerated and passed: `62 occurrences; 62 classified; 0 unclassified; 0 stale`.
- Bounded smoke used one existing pure candidate (8 objects, raw rank 2) in a fresh repository-local
  temporary root. BFS and IW v3 streams both verified with `verify_trace_stream`, each had 2 event
  records, and a second characterization replay produced identical bindings. v2/v3 overlap checks
  reproduced BFS `frontier_after`/`visited_after`, IW `seen_feature_delta`, and the success-plan digest.
- Checkpoint 1, current index, and the signed v2 approval retained their recorded SHA-256 values:
  `fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853`,
  `1b23b2c76fb1b77b85a0549b89fc5b4e3c503668e03c46db6443650b64fcacdf`, and
  `bd6909f99ce32484f3a33863cde936c0a3128935dabaf85da783870ae7ee26a8`.
- Full-repository `pytest -q` was started but remained in uninterruptible I/O for over 10 minutes
  without a summary; it was stopped and is reported as runtime-limited, not passed.

No corpus round, cursor advance, checkpoint 2, signed v2 stream, or release artifact was modified.
