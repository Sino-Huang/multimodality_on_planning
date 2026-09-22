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
