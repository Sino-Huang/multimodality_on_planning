# Todo 4 Production Population Selector

- Todo 4 must validate canonical embedded checkpoint, accounting, characterization, reservoir, range, and selector bindings without reading retained trace streams. The trace corpus has about 1.1 TB apparent size and is outside the Todo 4 selection boundary.
- The immutable round-1 checkpoint digest is `fa70f298d77834421f328fb56821e60e4cbd9d5324963251b2d88ba2e5134853` and its paired-exact reservoir has 53 rows, 34 signatures, and object counts 4:14, 8:23, 12:16.
- The unchanged selector deterministically returns `calibration_exact_39_unavailable`; Todo 4 publishes immutable feedback only, with no accepted-manifest or cursor fields.
- Exact reruns verify bindings before returning `read_only=true` and preserve result/index/checkpoint bytes, inode, size, and mtime.
- Feedback model canonical serialization omits status-inapplicable null fields: infeasible results omit accepted manifest fields; feasible results omit reason.
- Todo 4 checkpoint verification must cross-bind the complete set of `status=emitted` accounting candidate IDs to the unique characterization candidate IDs. Artifact digests/counts alone do not prevent a semantically torn checkpoint with emitted accounting and an empty characterization/reservoir.
- Feasible manifest assembly is gated by paired-exact authoritative rows and exact selector-record parity for identity, source-record digest, source split, and composition signature before quota/signature checks and immutable publication.
