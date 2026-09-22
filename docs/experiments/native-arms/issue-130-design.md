# Reviewer-blocking experiments R1–R4 — frozen design (#130)

Frozen on 21 September 2026 (UTC) before any R1–R4 model outcome exists and
before any GPU launch of the `followup-reviewer-v1` window
(`docs/experiments/native-arms/schedule-r130.json`, cap 20 GPU-h, branches
`reviewer_stress` 6 + `second_backbone` 14; independent ledger
`outputs/reviewer-v130/v1/budget.json`). Authorized by the user after
reviewing the external paper review. #126/#127/#128/#129 published evidence
is untouched.

## R1 — Menu manipulation (native-arms-v3 protocol, R1 cells)

Inference-only on the frozen #129 adapters, clean images, 9-task frozen
panel, 2 families × 2 arms × 2 algorithms × learned_adapter = 72 GPU
episodes:

- **menu-permutation** — the unscored candidate menu's entries permuted by a
  seeded Fisher-Yates; seed = `int(sha256(f"{51121}|menu-permutation|{sha256(canonical(clean_menu))}")[:8])`,
  master seed 51121 (disjoint from every prior frozen seed). Entries stay
  intact and copyable, so any degradation is information/ordering, not
  output-contract destruction.
- **distractor-injection** — up to k=3 schema-valid but currently
  inapplicable grounded actions per decision, harvested from the task's
  frozen scene-catalog producing actions minus the currently applicable set,
  injected at seeded positions. The trusted runtime still validates against
  the true state, so picking a distractor is an invalid operation; the
  per-decision injected set is recorded in the view binding and the analysis
  reports success plus distractor pick-rate.

Reading grid: menu-riding-via-content → permutation may hurt, distractors
picked rarely; order-exploitation → permutation collapses, distractors
ignored; scene-reading → both ignored (consistent with #129's corruption
null). Deterministic transforms; independent replay recomputes identical
menus and token counts (verified CPU-side before launch).

## R2 — Text-corruption decomposition + the missing cross cell

- **CPU decomposition** over the published #126 text-corrupted learned
  episodes (text-shuffled/text-masked × text-state/multimodal-state × 9
  tasks × 2 algorithms = 72 episodes): classify each episode as all_invalid
  (every emitted operation schema-invalid = output-contract destruction),
  partial_valid (valid operations emitted but the search failed =
  information loss), or goal_reached. This separates the copyability
  confound from the information story in the #126 claim.
- **text-masked × visual-state** — 18 GPU episodes on the frozen v5
  visual-state adapters via the #126 corruption seam: the one arm where
  text corruption isolates the scaffold from the state images.

## R3 — InternVL3.5-8B × best_first_add_greedy (second-backbone v3)

`configs/experiments/expanded-study/second-backbone-protocol-v3.json`
(validates against the pinned machinery): the v2 backbone null ran BFS — the
family where the primary backbone's SFT is itself 0/24 — so it carries no
information about the headline family. v3 keeps everything v2 froze (backbone
pin, 512-record recipe, seed 17, LoRA r64/α128, L1 12-key-cell shape,
comparator pinning to the replay-verified baseline episodes for
best_first_add_greedy) and changes exactly: algorithm, the frozen greedy
membership ids (+sha), key cells re-derived from additive reference decision
counts (12 cheapest, frozen before outcomes), and the execution window
(schedule_doc/ledger_path pins to followup-reviewer-v1). Declared code
changes (no existing frozen gate loosened): the identity registry gains the
v3 entry with its declared algorithm; the identity check compares against
identity-declared algorithm instead of the literal "bfs"; the admission's
reference-decision basis reads the protocol's algorithm instead of hardcoded
bfs; schedule/ledger paths are protocol-overridable with the old program
constants as defaults. Qualification and probe run fresh (the v1/v2 probe
evidence measured BFS inputs; reusing it for additive inputs would be
unsound).
## Alignment update (post-review arbitration, same session)

The external arbitration accepted the reviewer's C1/C2/C3 with two sharpenings,
both now reflected in the evidence:

1. **C1 is structural, not a panel deficiency — and that is the headline.**
   The new `identity-audit` stage (cheap hygiene check over any episode
   store) shows random_valid is decision- AND expansion-identical to
   exact_reference on **48/48** additive (task, algorithm) pairs
   (`outputs/native-arms/v1/identity-audit.json`), and the structural basis
   is in the trusted runtime: every decision submits one remaining candidate,
   `finish_expansion()` requires the complete candidate set, and heap serials
   are assigned from the deterministic sorted candidate order at
   `start_expansion` — frontier evolution is submission-order invariant. Under
   this contract the policy is a candidate *enumerator*; choice quality is
   unmeasurable by construction, so no headroom panel can exist without a
   contract change. The paper framing therefore flips to
   **measurement methodology**: any VLM planning evaluation that exposes a
   grounded action menu under an enumeration contract may be measuring
   menu-reading validity, not planning — and we ship the audit (identity
   test + menu manipulation) that detects it, plus a demonstrated failure.
2. **C2's constructive probe is R1, and R2 is already decided.** The
   published-episode decomposition (CPU, `outputs/native-arms/v1/
   r2-decomposition.json`) separates the #126 confound cleanly: text-masked
   destroys copyability and 36/36 episodes terminate all-invalid (output-
   contract destruction), while copyability-preserving text-shuffled leaves
   valid operations flowing in 34/36 episodes that still fail the search —
   the information-loss signature. R1's distractor pick-rate remains the
   direct measurement of menu-reading.

**O3 redefined (pre-registered follow-through, out of this window's scope):**
not "build a headroom panel" (impossible under the enumeration contract) but
an **audit-driven contract redesign**: a choice-sensitive additive arm where
the policy selects which frontier state to expand under a binding budget
(random-valid then wastes budget, exact does not, and learned choice quality
becomes measurable). Two outcomes both publishable under the methodology
framing: learned beats random-valid (a planner emerged), or it does not (the
system was a menu-rider, revealed the moment the contract allowed choice).
Requires a new trusted-runtime variant, corpus regeneration and its own
frozen protocol/window.

## R4 — Native arms on the degraded strains

Inference-only on the frozen #129 adapters over the frozen generalization-v2
shifted-init and scale-up variant sets (5 variants each, admission-v2
membership, sha-pinned): 2 families × 5 variants × 2 arms × 2 algorithms ×
{learned_adapter, pretrained_base} = 80 GPU episodes. The published
full-scaffold learned rates on the same variants (shifted-init 19/30,
scale-up 26/30) are the reference contrast: collapse here scopes the
menu-sufficiency claim to easy saturated tasks; survival gives it teeth.

## Execution rules

Same conventions as the previous windows: frozen protocols committed before
any launch; seeded deterministic transforms with replay-exact determinism;
inference-only through the existing replay machinery with independent replay
of every episode at `stress-finalize` (expected 170 = 72 menu + 18 textmask
+ 80 variants; sb-v3 replays its own 72 + 72 comparators); complete coverage
or explicit missingness; commit/push and close only against verified
evidence. Budget: reservations staged within branch caps (reviewer_stress 6,
second_backbone 14) on the shared scheduler with the `--schedule` follow-up
override.
