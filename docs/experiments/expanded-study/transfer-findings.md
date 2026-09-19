# Transfer findings: does learning search algorithms help other reasoning tasks?

Finalized 2026-09-19. Scope: zero-shot transfer of all twelve verified planning-trained LoRA
adapters (BFS, best_first_width, best_first_add_w3, best_first_add_greedy × text/visual/multimodal)
plus the Qwen3-VL-8B-Instruct base to FOLIO (200), GSM8K (200) and HumanEval (164), under the frozen
protocols `transfer-protocol.json` (v1, BFS) and `transfer-protocol-v2.json` (user-authorized
exhaustive extension, same frozen subsets/prompts/decoding byte-identically).

## Headline result

**No statistically reliable transfer effect, in either direction, in any of the 36
benchmark/adapter comparisons.** Paired per-example McNemar exact tests against the base cell:
smallest raw p = 0.0227 (folio / iw_text, +12 examples); after Holm correction across the 36
comparisons, smallest adjusted p = 0.82. See
[transfer-paired-analysis.md](transfer-paired-analysis.md).

## Observed accuracies (accuracy / pass@1)

| Benchmark | base | BFS t/v/m | IW t/v/m | A*-w3 t/v/m | A*-greedy t/v/m |
| --- | --- | --- | --- | --- | --- |
| FOLIO | .600 | .600/.605/.605 | .660/.645/.645 | .590/.575/.590 | .590/.590/.590 |
| GSM8K | .955 | .950/.945/.965 | .960/.965/.960 | .950/.965/.945 | .950/.955/.950 |
| HumanEval | .780 | .793/.799/.780 | .768/.762/.756 | .817/.799/.774 | .799/.811/.793 |

The only suggestive pattern is IW (best_first_width) on FOLIO (+4.5–6pp, consistent across the
three IW modalities, which share the algorithm but not the training data). It does not survive
multiplicity correction and rests on 9–12 flipped examples out of 200; treat it as
hypothesis-generating only. No cell degrades materially below base — search SFT did not damage
general capability.

## Interpretation for the manuscript

The planning-search SFT effect is **task-specific**: it produces large in-domain gains (baseline:
process SFT 125/288 vs base 0/288 on unseen planning tasks) but shows no detectable zero-shot
transfer to first-order-logic reasoning, grade-school math, or code generation. This is a clean
negative/secondary result and should be reported as such, with the IW/FOLIO hint disclosed as an
uncorrected exploratory observation requiring prospective (pre-registered, multi-seed) replication.

## Limitations

- Single training seed (17); no seed variance estimated (program decision).
- Subsets of 200/200/164 examples detect only large effects (≳5–7pp) reliably.
- Zero-shot only; no adaptation protocol was run.
- Base-model pretraining contamination is not auditable by this project (disclosed, not measured).
- FOLIO uses the official v0.0 validation split (GitHub release); the HF v2 update is access-gated.
- The v2 extension was authorized after the v1 BFS results were observed; it is exhaustive over
  all remaining trained cells and reused the v1 frozen evaluation byte-identically.

## Evidence and accounting

- v1: [transfer-results.md](transfer-results.md) + byte-identical `transfer-*.json`; all audits PASS.
- v2: [transfer-v2-results.md](transfer-v2-results.md) + byte-identical `transfer-v2-*.json`; all audits PASS.
- Paired analysis: [transfer-paired-analysis.md](transfer-paired-analysis.md) (script `scripts/analyze_transfer_paired.py`, CPU-only, reproducible from retained raw predictions).
- Leakage: zero content overlap with the SFT corpus (7 trivial numeric 8-gram collisions reported per item).
- Cost: transfer branch 3.5993/24 GPU-hours; program total 48.252/336. Issues #104–#107 closed.
