# Production P0 Todo 3 Round 1

Todo 3 round 1 completed on 2026-08-05 after exact unbounded execution and an exact immutable replay. The runner reused 117 previously verified immutable trace directories and produced 281 actual candidate characterizations across 4/8/12-object batches `{190,198,93}`. The checkpoint contains 481 contiguous accounting rows (`emitted=281`, `duplicate=52`, `solved=148`), 53 paired-exact reservoir rows, and 34 signatures. Cursors are `{4:190,8:198,12:93}` and all streams remain non-exhausted, so Todo 4 remains blocked pending selector feedback.

Checkpoint: `tmp/cgas-p0-characterized/checkpoints/reservoir_checkpoint_000001.json`, SHA-256 `fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853`. Current index SHA-256 is `1b23b2c76fb1b77b85a0549b89fc5b4e3c503668e03c46db6443650b64fcacdf`.

Every characterization binds actual `bfs.trace-v2.jsonl` and `iw.trace-v2.jsonl` streams with stream digest, final-event digest, record count, contract digest, and completion status. A real BFS stream reached 12,824,621,775 bytes and 10,000 events without truncation. The immutable rerun returned `status=ok, read_only=true` and preserved inode, size, mtime, and SHA-256 for the checkpoint, index, and sampled BFS/IW files.

The BFS optimization caches canonical state IDs and incrementally maintains sorted visited IDs; the locked real-fixture trace digest remains unchanged. Focused/adjacent/fault tests passed 90 tests; Ruff, basedpyright, no-excuse/size audit, and LSP all passed.
