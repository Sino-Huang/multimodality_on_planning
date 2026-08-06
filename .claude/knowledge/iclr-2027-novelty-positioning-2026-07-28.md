# ICLR 2027 Novelty Positioning

Date: 2026-07-28

## 2026-07-31 release-scope quarantine

This note is future research positioning, not a current release claim. The current CGAS release boundary is `data/planning_cgas_v1/release_manifest.json` only. Any later live-memory study, tool condition, causal repair, calibration, or attention analysis must start from that manifest and pass a separate experiment gate before it can be described as delivered.

## Durable conclusion

The project should not claim novelty for search-trace SFT, generic algorithm learning, curriculum learning, external scratchpads, or systematic generalization in isolation. Neural algorithmic reasoning and CLRS/CLRS-Text are direct precedents.

The deferred contribution hypothesis is a controlled causal study of resource interfaces: whether information-equated visual, textual, and live external-memory access interact with a precisely defined planner family to change verifier-measured search invariants, and whether a diagnostic-driven lightweight repair corrects the failure on structural OOD.

## Local readiness

The repository implements meaningful planning-data, trace, rendering, and validation infrastructure. It does not yet implement/run the actual Phase 4+ VLM/SFT/tool/evaluation study. Current local evidence includes no aligned visual model treatment, no live read/write tool condition, lexical rather than semantic zero-shot fidelity scoring, historical BFS-only rows, and a later BFS-to-GBFS drift. Treat all current outputs as infrastructure, not research results.

## Non-negotiable design requirements

- Future studies should run all eight subsets of `{vision, language, tool}`; the existing four-arm layout cannot support hard-boundary or necessity claims.
- Future studies should equalize task information, token/context/computation budget, and tool budget; any environment-owned live memory API is deferred.
- Future studies should separate named-algorithm execution from unlabeled algorithm-choice behavior.
- Future studies should verify state-transition and per-family invariants, then evaluate length, object count, branching, compositional, renderer, modality-corruption, and tool-budget OOD.
- Attention remains deferred descriptive analysis only. Use pre-registered probes plus head/path ablation and activation patching for any later causal claim.
- Keep BFS and GBFS distinct; do not call approximations canonical FF/Graphplan without a clear qualification.

## Candidate intervention

Invariant-Gated Process Repair: use the executable verifier to label the first violated invariant, selectively reweight matching process targets, and add consistency masking only for a diagnosed conflicting modality. Compare against uniform trace SFT, outcome-only, full auxiliary supervision, generic modality dropout, and parameter-matched adapters. Claim it only after selective OOD improvement and a causal component test.

## Sources

Full citations and evidence are in `.omo/ulw-research/20260728-000959/SYNTHESIS.md`.
