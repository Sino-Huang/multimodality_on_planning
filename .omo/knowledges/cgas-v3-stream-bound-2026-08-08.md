# CGAS trace v3 stream bound

M1 slice 3 implements the trace-v3 per-record write bound in
`scripts/phase3/cgas_trace_stream_v2.py`.

## Contract binding

- `TraceWriteRequest.contract_id` is explicit and defaults to the signed v2 contract for existing callers.
- Writer and verifier dispatch through signed v2/v3 bindings for contract ID, contract digest, record bounds, and the v3-only byte bound.
- The writer self-verifies its temporary stream before publication; v3 trailers must carry the v3 contract ID and digest.

## Size behavior

- v3 checks `len(line)` immediately before `handle.write(line)` against `cgas_trace_contract_v3.MAX_EVENT_BYTES` (`65_536`).
- Exactly `65,536` bytes is accepted; `65,537` bytes raises `TraceStreamError("trace_v3_record_size_exceeded", request.output)`.
- Rejected writes leave an existing destination byte-for-byte unchanged and remove the temporary file.
- v2 remains unbounded at this layer, so event lines larger than the v3 limit retain v2 semantics.

## Verification evidence

- Focused RED before production edits: 5 failures in the new v3 stream-bound tests.
- Required three-suite gate: `36 passed`.
- Required seven-suite gate: `73 passed`.
- All CGAS gate: `447 passed, 9 failed`; the nine failures are the pre-existing planner-probe and Qwen/release dependency failures from the handoff.
- Surface audit: `62/62` classified, `0` unclassified, `0` stale; no audit artifacts moved.
- Release manifests remain SHA-256 `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`.
