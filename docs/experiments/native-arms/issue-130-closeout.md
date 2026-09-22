# Issue #130 closeout — reviewer blockers R1–R4 executed

All four blocking experiments executed to complete verified coverage;
independent replay of every new episode; no prior published evidence touched.

## Results summary

### R1 — Menu manipulation on the frozen #129 adapters (72 episodes)

| Family | Success | Invalid ops | Distractor picks |
| --- | ---: | ---: | ---: |
| menu-permutation (both arms) | **36/36** | 0/512 | — |
| distractor-injection (both arms) | **0/36** | 36/60 | 36/60 (0.60 overall; the first emitted operation of every episode is a distractor) |

Permutation immunity (36/36, zero invalid) rules out order-riding. Distractor
collapse (0/36; every episode's first operation picks an injected
schema-valid-but-inapplicable action) rules out state grounding: **the policy
reads menu CONTENT and pattern-matches it — it cannot verify applicability
against the scene**. This is the constructive proof the reviewer demanded:
menu-riding is now measured, not inferred.

### R2 — Text-corruption decomposition (72 published + 18 new episodes)

- Published-store decomposition: text-masked **36/36 all_invalid** (every
  emitted operation schema-invalid — pure output-contract destruction);
  copyability-preserving text-shuffled **34/36 partial_valid** (valid
  operations keep flowing; the search fails — the information-loss
  signature). The #126 "language channel carries the state" claim survives
  only in the shuffled form; the masked catastrophe was mostly copyability.
- New cross cell text-masked × visual-state: **0/18, all-invalid** — masking
  the scaffold destroys the output contract even when images are the nominal
  state channel.

### R3 — InternVL3.5-8B × best_first_add_greedy (fresh qualification, probe,
training 3 cells, 72 episodes + 72 replay-verified comparators)

**The headline positive result replicates cross-backbone on the headline
family**: process-SFT succeeds text 11/12, visual 10/12, multimodal 10/12
(base 0/36, one invalid call each; SFT invalid-operation rate 0.5–1.2%;
decision usage 164–183 of 390 allowance). The #123 "total null" is confirmed
as an algorithm confound: the same backbone, same recipe, same panel shape
that scored 0/36 on BFS scores 31/36 on the additive family. Cross-backbone
contrast vs the pinned Qwen rate (0.917): interval [−0.167, +0.083]
(descriptive; key-cell subset vs pinned full-panel aggregate).

### R4 — Native arms on the degraded strains (80 episodes)

Learned adapters: **10/10 on shifted-init and 10/10 on scale-up for BOTH
arms** (base 0/20), against the published full-scaffold rates on the same
variants (shifted-init 19/30, scale-up 26/30). The reduced contract does not
collapse where the full scaffold degraded — it sits at ceiling. Combined with
R1 this sharpens the anatomy: the scaffold's scalar/bookkeeping text was not
carrying useful signal on these tasks either (and may have been a source of
the full-scaffold failures).

## The assembled story (measurement-methodology framing)

1. **Identity audit** (tool): random_valid ≡ exact_reference decision- and
   expansion-identical on 48/48 additive pairs — structural to the
   enumeration contract (finish_expansion requires the full candidate set;
   heap serials derive from the deterministic sorted candidate order), so
   choice quality is unmeasurable by construction.
2. **Menu manipulation** (tool): the trained policy is a content-driven
   menu-reader with no state grounding — permutation-immune,
   distractor-fragile.
3. **Channel anatomy**: images irrelevant (blank/mosaic null, #129); textual
   scores/memory removable without loss (nomem 18/18, R4 at ceiling);
   scaffold masking destroys only the output contract (R2).
4. **Constructive scope**: format+enumeration IS learnable (base 0 → SFT
   18/18, cross-backbone 31/36, R3) — a real capability, distinct from
   planning.
5. **Pre-registered follow-through (O3 redefined)**: audit-driven contract
   redesign — a choice-sensitive additive arm (policy selects the next
   expansion under a binding budget) where random-valid ≠ exact by
   construction; both outcomes publishable under this framing.

## Verification & budget

- R1/R2/R4: 170/170 episodes independently replayed, zero missing
  (`stress-evaluation.json`, audit ok).
- R3: evidence PASS — 72/72 model episodes + 72/72 comparators replayed,
  complete coverage; training report PASS (3 cells × 16 updates, seed 17).
- Window spend: **7.80 GPU-h actual** (v1 ledger 3.99 + v2 ledger 3.81) of
  the 36 GPU-h authorized cap; the v1→v2 window resize (branch 14→30) was a
  pre-outcome mechanics amendment because the frozen worst-case L1 estimand
  (27.04 GPU-h incl. spent) exceeded the initial branch cap; realized cost
  landed at 29% of that conservative estimate. Failed attempt (train-0
  attempt 1, admission gate) retains its hours with resume reason recorded.
- Documentation note: the v3 admission/evidence `reduced_scope` description
  string inherited the v2 template's "bfs" wording; the actual frozen
  selection (protocol rule + task list + executed episodes) used additive
  reference decision counts — verified task-for-task identical. Code strings
  now parameterized.

Evidence: `outputs/native-arms/v1/{r2-decomposition,identity-audit,
stress-evaluation}.json`, `outputs/native-arms/v1/evaluation/episodes/
{menu,textmask,variants}/`, `outputs/expanded-study/v1/second-backbone-v3/`.
