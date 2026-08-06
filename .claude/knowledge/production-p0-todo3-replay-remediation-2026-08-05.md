# Production P0 Todo 3 Replay Remediation

Existing immutable BFS/IW trace reuse must report replay truth, not normalize a truncated rerun into a complete characterization. Replay uses a discard sink so every logical trace event is emitted without retaining events in memory or publishing replacement streams. Reuse rejects `success_truncated_trace` from either the verified stream trailer or the replay result before comparing planner, status, and plan digest.

The corrected round-1 historical replay verified all checkpoint-bound trace streams and returned `status=ok`, `read_only=true`, and `receipt=null`. The checkpoint SHA-256 remains `fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853`; the current index SHA-256 remains `1b23b2c76fb1b77b85a0549b89fc5b4e3c503668e03c46db6443650b64fcacdf`. Sampled BFS and IW streams retained exact inode, size, mtime, and SHA-256 values. The final independent Oracle gate returned `confirmed`.

For future replay changes, require all three layers: a regression for truncated success rejection, a real discard-sink replay proving zero retained events and no stream replacement, and an exact immutable checkpoint replay with pre/post metadata and digest comparison.
