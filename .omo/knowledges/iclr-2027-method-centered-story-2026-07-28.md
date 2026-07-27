# ICLR 2027 Method-Centered Story

Date: 2026-07-28

## Recommended paper direction

Center the paper on **Certificate-Guided Adaptive Scaffolding (CGAS)**, not on a broad modality-affordance analysis. CGAS predicts whether a candidate next search certificate needs no support, a compact prior-certificate delta, or a bounded external-memory operation. It is trained with counterfactual minimum-cost labels supplied by an executable planner verifier.

## Why it is potentially novel

Generic process supervision, trajectory ranking, adaptive computation, modality dropout, and self-regulated tool invocation all have close prior work. CGAS should claim only the planner-specific combination: counterfactual certificate validity plus minimum-cost scaffold selection. Phrase priority as “to our knowledge” and repeat a closest-work check before submission.

## Paper scope

- Primary: BFS and IW, which have unambiguous stateful invariants.
- Primary baselines: direct VLA, always-on compact certificate, always-on memory, matched generic confidence router, uniform process supervision, and modality-dropout/robust-fusion baseline.
- Primary outcomes: verifier-checked certificate fidelity, structural OOD success, tool/token cost, and route optimality.
- Analysis: a small calibration failure matrix, a route-calibration curve, and optionally one targeted controller ablation. Attention is not a headline contribution.

## Requirements before claiming results

- Reconcile BFS versus GBFS and FF/Graphplan approximation semantics.
- Build aligned visual steps, semantic transition fidelity evaluation, and a live bounded memory interface.
- Ensure memory entries come only from model predictions or prior verifier-approved updates, never an oracle queue.

## Source of truth

Full online research, sources, risks, and method specification: `.omo/ulw-research/20260728-014929/SYNTHESIS.md`.
