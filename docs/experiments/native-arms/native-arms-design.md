# Image-only state/history observation arms — frozen design (#128)

Frozen on 21 September 2026 (UTC) before any new-arm model outcome exists and
before any GPU launch of this window. Machine-readable protocol (authoritative
on key names): `configs/experiments/native-arms/native-arms-protocol.json`.
Follow-up program schedule: `docs/experiments/native-arms/schedule.json`
(`followup-native-arms-v1`, independent of expanded-nine-day-v1; no transfer
from that program's remainders is claimed or implied).

## Lineage and deliverable

#126 established, under the frozen observation contract, that the learned
Search-Process-Policy's decision-relevant information lives in the textual
search-process scaffold: language-channel corruption was catastrophic
(text-masked Δ up to −0.944, material) while visual-channel corruption was not
material (Δ ≤ 0.111) and the multimodal channel-isolation contrast was material
(−0.694 [−0.889, −0.472]). That result is well-defined because the frozen
`visual-state` arm still receives the search state and the grounded candidate
menu as text (`search_memory`, `successor_candidates`, current g/h/priority);
only state facts are image-exclusive. The question that contract cannot answer:
can a search-process VLM policy operate when **state facts and search history
are carried only by images** — or not at all? This ticket adds two strictly
additive observation arms to ask exactly that. No frozen arm, protocol or
published evidence is modified; all reused evidence stays byte-identical.

## Frozen contracts

Both arms keep the frozen page machinery of the `visual-state` arm (static
task-context pages, unlabelled 128px initial/current scenes, separate goal
pages, the unchanged one-line system message) and change only the user payload
and, for the sequence arm, the attached frames:

1. **`visual-nomem-state`** (ablation rung, recipe `visual-nomem-state-v1`):
   the payload JSON is reduced to the static interface plus an *unscored*
   candidate menu. Removed: `search_memory`, `accepted_deltas`, the current
   g/h/priority scalars and every candidate score/membership column (`g`, `h`,
   `priority`, `best_cost`, `closed`, `frontier`, `dominated`, `pruned`,
   `target_state_id`). Retained keys: `algorithm`, `current` (only
   `state_id` — the standing output contract requires the operation to echo
   the popped frontier head, so the supervised target stays learnable),
   `representation`, `schema_version`, `successor_candidates` (per-candidate
   `{name, args}` only, in the trusted grounded order), `view_legend`. State
   facts and search history have **no** channel beyond the standing images;
   this rung isolates what the textual memory itself contributes.
2. **`visual-seq-state`** (primary arm, recipe `visual-seq-state-v1`): the
   same reduced payload plus a bounded **history frame window** with K frozen
   at 8: the rendered current-state pages of the last K predecessor states on
   the current state's first-acceptance provenance path (the views registry
   parent chain; equivalently the recorded trace path for corpus records), in
   visit order, before the current-state scene, each labelled
   `Page role: history-state (visit ordinal {position})` with position the
   absolute path depth (initial state = 0). Here state facts and history are
   **image-only**; the only remaining text is the static interface and the
   unscored candidate menu.

Corpus materialization is CPU-only through the existing replay machinery: the
v5 scene-only store supplies every selected-state scene and the retained scene
catalogs' VFG vector stages supply any missing path-intermediate history state
(the same `render_vfg_to_local_png_frames(canvas_size=128, draw_labels=False)`
call the v5 preparation used — no new rendering pipeline). Structural
qualification gates assert: removed payload keys absent (the serialized user
text is scanned for every removed key marker), frame counts ≤ K, window states
strictly precede the current state in visit order, every image reference
resolves, the candidate menu equals the trusted grounded order, membership
identical to the frozen v5 512-record + diagnostic lists per algorithm,
measured input + 384 ≤ 32768, and the assistant target unchanged.

## Frozen training

One new adapter per arm × the two learned search families of #126
(`best_first_add_greedy`, `best_first_add_w3`), trained from the *same* source
traces/training tasks as the matched-modalities v5 corpus (membership sha256
`f939f864…bc23`, study sha256 `1f151846…d72b`), re-materialized under the new
contracts. Identical recipe: 512 records in frozen membership order, one
epoch, 16 optimizer updates, seed 17, LoRA r64/α128 dropout 0.05 all-linear
excluding the vision tower, lr 1e-4 cosine, warmup ratio 0.03, global batch
32 (microbatch 1 × accumulation 32), bf16, final checkpoint at update 16
only. The v5 recipe config is pinned by sha256 and referenced, not copied.

## Frozen admission feasibility gate (pre-registered)

Before any training, a bounded probe of the pretrained base (no adapter, hard
1-call cap) runs the **first decision** of each of the 9 frozen panel tasks ×
both algorithms under each arm's own contract (18 calls per arm). The gate
measure is the share of first decisions the trusted runtime accepts
(schema-valid, grounded in the unscored candidate menu, correct
`source_state_id`). The frozen minimum rate is **0.5**. At or above threshold
the rung proceeds; below, that rung declares VALID_STOP with the probe
evidence published, and `visual-seq-state` proceeds only if its own gate
passes. Minimum meaningful scope — one arm passing its gate plus its complete
clean evaluation — must fit the authorized window budget before launch, else
VALID_STOP without partial-outcome harvesting.

## Frozen budget and estimand

The user authorized this follow-up window explicitly in the execution session
("just start GPU use as I am going to AFK"), with the ticket's ~10 GPU-h
prospective envelope; the frozen window cap is **12.0 GPU-h** on a new
independent ledger (`outputs/native-arms/v1/budget.json`, branch `native_arms`),
scheduled by the declared `--schedule` extension of the shared scheduler so
the expanded-nine-day-v1 ledger, caps and cutoffs remain untouched. The frozen
admission equation prices, with a 1.25 safety factor: per-episode price =
runtime cap (2 × reference decisions for learned cells, exactly 1 call for
pretrained_base) × this protocol's own measured per-arm probe
`max_observed_call_seconds`; training = 0.3633 GPU-h per cell (the measured v5
8-cell basis) scaled for the seq arm by 1 + mean_history_frames/4; plus
4 planned worker jobs × 120 s overhead. CPU controls, reused comparators and
CPU materialization price at zero. Admission PASS requires the full frozen
scope and the minimum meaningful scope both to fit the 12 GPU-h window.
Overruns become explicit missingness; failed attempts retain their hours.

## Frozen evaluation

- **Clean:** the frozen 9-task cheapest-panel membership of #126 (membership
  sha256 `20ea888d…e854`), both arms × both algorithms ×
  {learned_adapter, pretrained_base} = 72 GPU episodes, so every new cell pairs
  whole-problem against the published frozen `visual-state` cells; greedy
  float32 decoding under the frozen rollout rules; learned cells hard-capped
  at 2 × reference decisions, pretrained_base at exactly 1 call.
- **Corruption payoff:** the frozen #126 families `visual-blank` and
  `visual-degraded` applied to `visual-seq-state` (all attached images,
  including history frames) = 72 GPU episodes. Under this contract images are
  the only state+history channel, so visual corruption **must** produce
  material degradation; a null result is itself a leak signal and is reported
  as such.
- **Controls:** random_valid on the frozen seed-17 rollouts (reused from the
  replay-verified baseline store) plus new independent CPU seeds
  {5077, 6131, 7409, 8527} (primes disjoint from every seed used by
  expanded-nine-day-v1 and #127); exact_reference reused and replayed.
  Controls are arm-invariant by construction (decisions come from the
  authoritative session, never from observations).
- **Comparators:** per (task, algorithm) the replay-verified baseline
  visual-state `process_sft` and `pretrained_base` episodes (the clean arms of
  every degradation contrast) and the text-state seed-17 `random_valid` and
  `exact_reference` episodes — 72 reused episodes, each independently
  replayed at finalize with identity fields checked.

Totals: 144 new GPU episodes, 72 new CPU control episodes, 72 reused
comparators. Every completed episode is independently replayed
(`replay_visual_episode` over read-only persisted views, inputs/page
bindings/events/results compared exactly) by the worker before writing and
again at finalize; partial coverage never satisfies the gate.

## Frozen analysis

Paired whole-problem contrasts (task × algorithm, n = 18 per contrast):
per-arm learned clean minus published frozen visual-state learned clean; the
ladder contrast learned(seq) − learned(nomem); per-family corruption
degradation on the seq arm; learned minus pretrained_base per arm; learned
versus the five-seed random-valid frequency with the #54 saturation rule; the
exact-reference oracle reported separately. Bootstrap over whole source tasks,
seed **61813** (disjoint from 17/29/71/64/1729/90717/42613/1013/2027/3041/
4001/5077/6131/7409/8527), 10,000 resamples, 95% percentile intervals,
materiality = interval excludes 0; strata with fewer than 8 paired instances
are descriptive-only. Complete coverage or explicit missingness is published
per arm, family and stratum.

## Execution contract and design gate

Versioned protocol and this design are committed before any GPU use of the
window (the probe is the first GPU launch; the admission equation, thresholds,
K, seeds and analysis constants are already frozen in the committed protocol,
and the admission artifact is recomputed only from preparation reports, probe
evidence and frozen bases — never from training or evaluation outcomes). No
outcome-selected variants, no favourable replacements, only final checkpoints
enter evaluation, every episode independently replayed, paired analysis with
tiny-strata limits, complete coverage or explicit missingness. The user
authorized GPU use for this window in advance and instructed not to wait.
Declared code changes (no frozen gate of any existing protocol is loosened):
the two new modules and runner above; `train_visual` gains an optional
`dataset_factory` hook (default path byte-identical for existing studies);
the shared scheduler gains an explicit `--schedule` override designating this
window's ledger as its own program's production ledger (behavior unchanged
without the flag). Commit/push and close only against verified evidence.

## Ordering

1. Commit this design + protocol + code (this commit).
2. CPU: validate, materialize and qualify both arms' stores; commit.
3. GPU: per-arm pretrained-base probe (18 calls each); audit; commit.
4. CPU: admission recompute; VALID_STOP or PASS; commit.
5. GPU: training (one arm per GPU); adapter audits; commit.
6. GPU+CPU: clean and corruption evaluation, controls; finalize with
   independent replay of every episode and comparator; analysis; commit.
7. Budget closeout, ticket evidence, close.
