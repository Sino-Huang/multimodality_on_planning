# CGAS Release Boundary Manifest Handoff

Date: 2026-07-31

`data/planning_cgas_v1/release_manifest.json` is the only authorized handoff for future CGAS milestones after Todo 6. Future experiment plans, training jobs, memory work, route-label work, calibration work, and attention analysis must consume that manifest as their starting artifact, not intermediate evidence folders, fixture QA output, draft partition artifacts, or stale Todo 5 publication notes.

Current release scope:

1. Published: manifest-bound source, alignment, steps, Qwen conversion, strict preflight, and native loader smoke evidence for 12 emitted rows.
2. Deferred: live memory, bounded memory interfaces, memory baselines, route labels, route calibration, calibration analysis, CGAS model training or implementation, and attention analysis.
3. Guardrail: no downstream document should claim those deferred items as delivered unless a later release or experiment gate explicitly approves them from `data/planning_cgas_v1/release_manifest.json`.

Release identity:

1. Manifest path: `data/planning_cgas_v1/release_manifest.json`.
2. Manifest SHA-256: `3bc894314f4fa674ff36489c664d8cc9db7f23e2144c5ffcef1444fd30feb6c3`.
3. Loader evidence: strict preflight accepted 12 emitted rows with zero identity, message, tokenization, empty-label, null-image, and null-grid counters; the native loader batch reported image tensors and grid metadata present.
