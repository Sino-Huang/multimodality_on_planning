# Modality corruption/removal stress tests — frozen design (#126)

Frozen on 20 September 2026 before any corrupted-observation model outcome exists.
Machine-readable protocol: `configs/experiments/expanded-study/modality-stress-protocol.json`
(authoritative on key names). Admission artifact:
`outputs/expanded-study/v1/modality-stress/admission.json`, recomputed by
`scripts/qualify_expanded_modality_stress.py` from existing evidence only.

## Lineage and deliverable

Recasts the historical CGAS proposal's secondary stress tests
(`docs/research_proposal.md` §6.1 "observation corruption or removal", P3
"vision-only/language-only stress tests") onto the Search-Process-Policy target.
Executed branches (#124, v1 #96/#98) perturbed names, render style, scale and
initial states but never the observation modalities; this ticket extends
robustness evidence along the modality axis with no CGAS machinery. It does not
close or modify #96/#98.

Frozen, already-verified checkpoints (the six v3/v5 baseline adapters, seed 17,
16 steps; no retraining) are evaluated inference-only on modality-degradation
variants of the frozen 24-problem expanded panel. The underlying PDDL tasks,
reference costs, decision caps and page structure are identical to the clean
panel evaluation; only the model-facing observation is corrupted, deterministically,
inside the existing replay machinery.

## Frozen corruption families

| Family | Arms | Channel | Strength | Transform |
| --- | --- | --- | --- | --- |
| visual-blank | visual-state, multimodal-state | visual | removal | every attached image → uniform RGB (128,128,128), same size/mode |
| visual-degraded | visual-state, multimodal-state | visual | corruption | every image → 16×16 mosaic (BILINEAR down, NEAREST up), same size/mode |
| text-shuffled | text-state, multimodal-state | language | corruption | every user-message text part → whitespace tokens permuted by seeded Fisher-Yates (master seed 42613; per-text seed from sha256 of the clean text) |
| text-masked | text-state, multimodal-state | language | corruption | every maximal `[A-Za-z0-9]+` run in user-message text parts → U+25AE |

The system message (the standing one-line output contract) and all image parts
for language families stay clean; all text parts for visual families stay clean.
Corruption is a deterministic function of the clean observation and the frozen
seed rule, so independent replay reproduces the corrupted observation and its
recomputed `input_tokens` exactly; visual families never change token counts.
Injection is `StressTaskViews.observe` in
`examples/planning_benchmark_slice/expanded_modality_stress.py`, after page
assembly and before the model call, with the token count recomputed and the 32K
gate re-checked on the corrupted messages — the same subclass seam the v2
evaluation used for its call cap.

## Frozen scope and membership

Source tasks: the 24 frozen `expanded-panel-v2-qualified` problems. Every
admitted source task yields all four families on every applicable arm: 4
families × 2 arms = 8 variant cells per (task, algorithm), 16 per task across
the two frozen learned algorithms (best_first_add_greedy, best_first_add_w3).

Membership rule (frozen): rank source tasks by (estimand seconds, task_id),
cheapest prefix of size k; choose the uniform k maximizing admitted tasks
subject to the estimand fitting the branch remainder; VALID_STOP if no k ≥ 4
fits and the k=4 shortfall exceeds the 11.89 GPU-h maximum transfer.

Admission recomputation (existing evidence only): **decision PASS, k = 9**,
membership sha256 `20ea888d5199d53bbbe2e7cfa14aeee11e3c4cd7cff956103147ed1a7328e854`:

storage-compact-919000, elevators-compact-914002, ferry-compact-915000,
15puzzle-compact-910000, towers_of_hanoi-compact-920000, visitall-compact-921000,
depot-compact-912000, blocksworld-expanded-911101, 15puzzle-expanded-910109
(8 of 12 domains; 7 compact / 2 expanded — cheapest-prefix cost ordering, frozen
before outcomes; domain/stratum imbalance is reported, never repaired).

## Frozen estimand and budget

Per GPU episode price = hard decision-call cap × frozen per-(algorithm, arm)
max observed probe call time (v2 probe `per_combo_bounds`
`max_observed_call_seconds`; corruption preserves image dimensions and page
structure exactly, so the clean probe maxima remain valid bounds). Learned cell
cap = 2 × reference decisions; pretrained_base cell = exactly 1 call (frozen
288/288 first-decision-invalid baseline evidence), hard-enforced. CPU controls
and reused comparators price at zero. Safety factor 1.25; 2 planned worker jobs
× 112.254 s overhead.

required = 20.950878016686893 × 1.25 + 0.0623633493658983 = **26.250960870224514 GPU-h**
branch remainder (cap 32, spent 3.8189364778333237) = **28.181063522166674 GPU-h**
headroom = 1.9301026519421605 GPU-h → **no transfer**; total program cap 336 and
the 2026-09-21T11:55:19Z scheduler cutoff are unchanged. Next rung k=10 requires
30.500431411344973 GPU-h and does not fit. The issue's not-bound-by-the-cutoff
clause is a VALID_STOP safety valve, not a schedule amendment: if the frozen
scope cannot launch inside the admissible window, the ticket stops without
partial-outcome harvesting.

## Conditions, controls and comparators

New episodes (360 bindings): per (task × family × arm × algorithm),
learned_adapter and pretrained_base (288 GPU episodes); per (task × algorithm),
random_valid on the new frozen rollout seeds {1013, 2027, 3041, 4001} (72 CPU
episodes). Reused replay-verified baseline evidence (144 episodes, zero new GPU
cost, each independently replayed at finalize): clean process_sft and clean
pretrained_base per (task, arm, algorithm) — the clean arms of every degradation
contrast — plus seed-17 random_valid and exact_reference per (task, algorithm).

Control invariance (frozen gate, re-verified by the admission script):
random_valid and exact_reference decisions are computed by the authoritative
session from the trusted search state, never from the observation; all 96
(task × algorithm × condition) baseline triples verified arm-invariant. CPU
controls are therefore bound per (task, algorithm, seed), shared across families
and arms.

## Analysis (frozen)

Paired whole-problem analysis; strata domain, stratum-origin, corruption family;
tiny-strata rule (<8 paired instances: descriptive-only). Primary contrasts:
per-family degradation (corrupted vs clean learned, paired by task × arm ×
algorithm); channel isolation within the multimodal arm (text- vs
visual-channel corruption); learned vs best control (max of corrupted
pretrained_base and five-seed random_valid frequency; exact_reference reported
separately as oracle bound); validity/cost. Bootstrap over whole source tasks
within family, seed 90717, 10,000 resamples, 95% percentile, materiality =
interval excludes 0. Saturation rule (#54): no structural-advantage claim when
the best control is at ceiling. Complete coverage or explicit missingness
published per family and stratum; partial coverage never satisfies the gate.
