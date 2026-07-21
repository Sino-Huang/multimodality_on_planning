# Phase 3 Hybrid Traversal Release Knowledge

Date: 2026-07-15

- Hybrid output is split into strict `hybrid_full` records with planner-trace targets and strict `hybrid_step` records with next-action targets. Both carry frozen pair, event, state, trace, render, and relative artifact provenance.
- Production rejects render limits and requires complete contiguous coverage from step zero. Bounded smoke is partial by contract and cannot pass release or rollout promotion.
- Source identity is the root ID and hash, relative JSONL path, physical line, split hash, record hash, pair ID, and plan hash. Never infer `phase3_traversal_trace_v1` for legacy rows.
- FF, GBFS, and IW render only validated concrete states. Graphplan layers, mutexes, and extraction metadata remain nonvisual; only a fully validated extracted-plan replay can produce render candidates.
- Release verification is layered as `manifest`, `render`, and `release`. Release requires production-complete output, six split JSONL files, strict schemas, semantic render receipts, artifact hashes, split isolation, coverage, and reconciled counts.
- Rollout order is fixture, changed-canary, stratified-pilot, complete-domain, then frozen-full. Each stage uses a hashed frozen selection and an approved receipt before advancement.
- The 2026-07-15 temporary fixture passed release and fixture promotion with one pair, two state renders, one train full record, and one train step record.
- Active-source promotion is blocked: the probed 15-puzzle root has 688 pairs and zero strict-v1 eligible rows because all lack `trace_contract_version`. Do not claim canary images, frozen-full rendering, active corpus release, or corpus completion.
- The broad Phase 3 generator test timeout is independent. The bounded full suite exited 124 after 600.01 seconds, and the isolated generator node exited 124 after 180.00 seconds.
- Exact reusable commands and evidence paths are in `doc/detailed_implementation_summary/phase3_hybrid_traversal_rendering_release_evidence_2026-07-15.md` and `.omo/evidence/phase3-task-10-documentation-command-log-2026-07-15.json`.
