# ICLR 2027 Method-Centered Story

Date: 2026-07-28

## 2026-07-31 release-scope quarantine

This note is a deferred research hypothesis for the ICLR 2027 story, not a current CGAS release receipt. The current `planning_cgas_v1` release boundary is only `data/planning_cgas_v1/release_manifest.json`, published after the fail-closed loader gate. Any future CGAS training, live or bounded memory, route labels, route calibration, calibration analysis, memory baselines, and attention analysis must start from that manifest and must pass a new release or experiment gate before being described as delivered.

The current release claims only manifest-bound trainable records and loader readiness. It does not deliver or approve CGAS model training, a live memory interface, memory-backed baselines, final route labels, calibration or route-calibration results, or attention-based analysis.

## Recommended paper direction

Center the future paper on **Certificate-Guided Adaptive Scaffolding (CGAS)**, not on a broad modality-affordance analysis. In that deferred method, CGAS would predict whether a candidate next search certificate needs no support, a compact prior-certificate delta, or a bounded external-memory operation. This is not implemented or trained in the current `planning_cgas_v1` release.

## Why it is potentially novel

Generic process supervision, trajectory ranking, adaptive computation, modality dropout, and self-regulated tool invocation all have close prior work. CGAS should claim only the planner-specific combination: counterfactual certificate validity plus minimum-cost scaffold selection. Phrase priority as “to our knowledge” and repeat a closest-work check before submission.

## Paper scope

- Deferred primary scope: BFS and IW, which have unambiguous stateful invariants.
- Deferred baselines: direct VLA, always-on compact certificate, always-on memory, matched generic confidence router, uniform process supervision, and modality-dropout or fusion baseline.
- Deferred outcomes: verifier-checked certificate fidelity, structural OOD success, tool/token cost, and route optimality.
- Deferred analysis: a small calibration failure matrix, a route-calibration curve, and optionally one targeted controller ablation. Attention is not a headline contribution, and no attention result is claimed by the current release.

## Requirements before claiming results

- Reconcile BFS versus GBFS and FF/Graphplan approximation semantics before any paper result.
- Build aligned visual steps, semantic transition fidelity evaluation, and a live bounded memory interface as a later milestone.
- Ensure future memory entries come only from model predictions or prior verifier-approved updates, never an oracle queue.

## Source of truth

Full online research, sources, risks, and method specification: `.omo/ulw-research/20260728-014929/SYNTHESIS.md`.
