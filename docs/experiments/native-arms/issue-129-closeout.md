# Issue #129 closeout — native-arms v2: image-only state/history arms trained and evaluated

Ask (#129, amending #128): complete the #128 experiment under the corrected
v2 admission (post-training smoke gate instead of pretrained-base format
compliance), keeping every other frozen element of `native-arms-v1`. All of
it executed and verified; the ticket closes as delivered.

## Delivered

- **Freeze before any v2 launch** (commit `4736a8f`):
  `configs/experiments/native-arms/native-arms-v2-protocol.json` (sha256
  `37c93625…ad40`) + `docs/experiments/native-arms/native-arms-v2-amendment.md`;
  admission-v2 **PASS** (7.67 GPU-h required of 11.91 window remainder).
- **Training**: 4 fresh adapters (2 arms × best_first_add_greedy/w3), the
  frozen v5 recipe verbatim — 512 frozen-membership records, 1 epoch, 16
  updates, seed 17, LoRA r64/α128; audit hooks verified every cell (steps 16,
  512 records, adapter config r=64/α=128, checkpoints present). Jobs
  `na-v1-train-{nomem,seq}` succeeded (0.5013 + 0.5501 GPU-h).
- **Smoke gate (pre-registered)**: 62/62 schema-valid grounded calls on BOTH
  arms (6 held-out smoke episodes each; threshold 0.5) — the trained policies
  fully learned the output contract, confirming the v1 gate had measured
  pretrained-base format compliance rather than rung feasibility.
- **Complete evaluation, zero missingness**: 216/216 new bindings recorded and
  independently replayed (144 GPU model episodes: 72 clean + 72 corruption,
  learned capped at 2× reference decisions, pretrained_base hard-capped at 1
  call; 72 CPU random_valid episodes on the new seeds
  {5077, 6131, 7409, 8527}) plus 72/72 reused replay-verified comparators
  (frozen visual-state process_sft/pretrained_base, text-state seed-17
  random_valid and exact_reference). `evaluation.json` outcome **PASS**;
  `analysis.json` holds all 144 paired cells.
- **Budget**: 3.2086 / 12.0 GPU-h actual window spend (probes 0.093, training
  1.051, smoke 0.255 incl. one fixed crash attempt, evaluation 1.810 incl.
  two fixed crash attempts — all resume reasons recorded in the ledger;
  controls CPU). Failed attempts retain their hours per policy.
  expanded-nine-day-v1 untouched.

## Results (paired whole-problem, n = 18 per contrast; bootstrap 61813, 10k, 95%)

| Contrast | Δ | 95% interval | Material |
| --- | ---: | --- | --- |
| learned nomem − published frozen visual-state learned | +0.111 | [0.000, +0.278] | no |
| learned seq − published frozen visual-state learned | +0.111 | [0.000, +0.278] | no |
| ladder: seq − nomem | 0.000 | [0.000, 0.000] | no |
| learned − pretrained_base (per arm) | +1.000 | [+1.000, +1.000] | yes |
| corruption visual-blank: seq corrupted − clean | 0.000 | [0.000, 0.000] | no |
| corruption visual-degraded: seq corrupted − clean | 0.000 | [0.000, 0.000] | no |

Clean success: **visual-nomem-state 18/18, visual-seq-state 18/18** (zero
invalid operations in every episode), published frozen visual-state 16/18.
pretrained_base 0/36 under both new contracts. exact_reference 18/18 oracle;
random_valid at ceiling on the five frozen seeds — per the frozen #54
saturation rule **no structural-advantage claim is made**.

## Interpretation (recorded per the frozen null-result rule)

Both arms — trained with **no textual search state, no g/h/priority scalars,
no candidate scores, no membership flags** — solve every clean panel task,
numerically above the published frozen visual-state arm (not material). The
K=8 history-frame window neither helps nor hurts on these tasks (ladder Δ
exactly 0). The corruption payoff is the pre-registered leak signal: under
`visual-seq-state` the images are the only state+history channel, yet
blanking or mosaicking **every** attached image (including history frames)
leaves success at 18/18 — a null effect with a degenerate [0,0] interval.
Combined with #126 (language corruption catastrophic when the scaffold
carried the state), the consistent reading is that the decision-relevant
signal these policies extract is the **grounded unscored candidate menu
itself** — the applicable-action set is a state fingerprint sufficient to
reconstruct the reference search on these tasks — while neither the rendered
scenes nor the removed scalar scaffold is necessary once the menu is present.
The images-only hypothesis is therefore answered in the negative on this
panel: state facts and history can be image-only without collapsing, because
the menu already carries what the policy uses.

## Execution repairs (recorded in the ledger, none alters an episode or verdict)

1. Smoke attempt 1 crashed: episode identity lacked the `modality` field the
   shared resume helpers read; fixed (identity carries `modality=arm`), stale
   partials deleted, jobs rerun.
2. Models-0 attempt 1 crashed at the corruption group: the worker built its
   policy with an empty adapter bank (adapters were wired for the clean phase
   only); fixed by loading the per-arm adapters for every models group. All
   72 clean learned episodes were already complete and replay-verified on
   resume.
3. Models-0 attempt 2 failed in seconds: with a fully-retained group the
   adapter map was only built when pending work existed, so retained episodes
   failed the checkpoint identity check; fixed by building the static
   per-arm map per group. Attempt 3 completed the 36 corruption episodes.
4. Finalize comparator identity compared `arm` through the engine-arm map;
   baseline episodes store the arm value directly — fixed. Analysis `by_key`
   tuples were built 5-wide but queried 4-wide (all contrasts n=0) — fixed.

## Scope discipline

#128's published VALID_STOP evidence and the v1 protocol remain untouched;
v2 was a strictly prospective amendment frozen before any trained-arm outcome
existed. No outcome-selected variants, no favourable replacements, only final
checkpoints evaluated, every episode independently replayed, complete
coverage with explicit gated-out accounting (none gated: both smoke gates
passed). Does not close or modify any other ticket.
