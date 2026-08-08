# Trace-v3 Gate 0b round-1 evidence

Gate 0b passed on 2026-08-09 from start commit
`8f6718c6be992d3f0b48794bdb29a3b10a2fef9a`.

## Regeneration

- Command: `python -m scripts.phase3.cgas_candidate_characterization next-round --round 1`
  with the signed v3 approval, production P0 config, existing pure candidate root, and isolated
  `tmp/cgas-p0-characterized-v3` output root.
- Exit: 0; wall 7:46.76; user 450.37 s; system 5.55 s; peak RSS 122,804 KiB.
- Checkpoint: `0fa9d3e5bcad06e6e50381a2142d4b6777818feffb0e1a4012c010a1fdebf76b`.
- Current index: `e86d42a7ec94c29169cadb4eb65baa93e5b4502eda65bc9bbb333b5c9a2bce97`.
- Accounting rows: 481; characterized candidates: 281; paired-exact rows: 158.
- Streams: 562 (281 BFS, 281 IW); 1,428,919 event records; 3,000,099,088 bytes.
- Largest event: 9,915 bytes against signed `MAX_EVENT_BYTES=65,536`.

## Replay And Verification

- Exact replay exit 0, `read_only=true`, wall 1:18.31.
- `streams.before.sha256` equals `streams.after.sha256` for all 562 files.
- `checkpoint.before.sha256` equals `checkpoint.after.sha256` for checkpoint/current.
- `verification.json` records exhaustive `verify_trace_stream` results and explicit v3 contract,
  digest, planner, completion, record-count, success-plan, byte, and checkpoint bindings.
- No checkpoint 2 was created and no v2 predecessor was used.

## Semantic Comparison

- Candidate overlap: 281/281; no identity, BFS summary, IW regression, or plan-binding mismatch.
- Approved IW policy effect: 112 new exact successes; 53 common successes; 116 common failures.
- BFS rule: 24 checkpoint-bound v2 streams sorted by `(byte size, candidate id)`, every
  `floor(281/24)`th stream with the final pick replaced by the largest; first 3,000 events.
- BFS result: 22,036 events, zero retained-field mismatches, zero certificate mismatches.
- IW rule: all 281 checkpoint-bound v2 streams and every event against the v3 width-1 prefix.
- IW result: 14,252 events, zero retained-field mismatches, zero certificate mismatches.

## Gates

- Focused: `95 passed in 40.59s`.
- Broad CGAS: `460 passed, 9 failed in 141.89s`. The nine RED tests are the unchanged three
  alternative-profile/blocker-probe failures and six Qwen/release failures; the latter reproduce
  `huggingface-hub==1.22.0` against the installed `transformers` requirement `<1.0`.
- Ruff on changed files: pass. The broader `scripts/phase3 tests/phase3` sweep reports 1,348
  pre-existing style findings outside this patch.
- basedpyright on changed files: 0 errors, 0 warnings, 0 notes.
- Contract surface: 62 occurrences, 62 classified, 0 unclassified, 0 stale.

## Immutable V2 Boundary

- Release and fixture manifests: `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`.
- V2 checkpoint 1: `fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853`.
- V2 current index: `1b23b2c76fb1b77b85a0549b89fc5b4e3c503668e03c46db6443650b64fcacdf`.
- Signed v2 approval: `bd6909f99ce32484f3a33863cde936c0a3128935dabaf85da783870ae7ee26a8`.
- V2 inventory: 1,116 streams (558 BFS, 558 IW), 2,418,948,358,346 bytes. No v2 file was deleted or modified.
