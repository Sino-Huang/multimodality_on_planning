# Native-arms v2 amendment — corrected admission gate (#129)

Frozen on 21 September 2026 (UTC) before any trained native-arm adapter exists
and before any new GPU launch. Machine-readable protocol (authoritative):
`configs/experiments/native-arms/native-arms-v2-protocol.json`
(sha256 `37c93625…ad40`). Everything not named here is unchanged from
`native-arms-v1` (sha-pinned in the v2 protocol's `amendment` block).

## Why an amendment

#128 executed its frozen decision procedure exactly and stopped at the
pre-registered admission feasibility gate: the pretrained base emitted 0/18
schema-valid grounded first actions under each arm contract, so both rungs
declared VALID_STOP (`docs/experiments/native-arms/issue-128-closeout.md`;
probe evidence published at `outputs/native-arms/v1/probe/`). Retrospective:
that gate conditioned rung feasibility on **pretrained-base format
compliance**, but the frozen baseline evidence (0/288 first-decision invalid)
already established the base never emits the strict operation format — exactly
what process-SFT teaches (all v5 adapters were trained from this same base).
The machinery was verified sound (menu-built strict operations are accepted by
the trusted runtime under both contracts) and the budget fit; only the gate
condition fired. The user reviewed this diagnosis and selected the v2
continuation, authorizing GPU use in the remaining window (11.9074 of 12 GPU-h
unspent).

## The one change: admission adjudication moves post-training

- **v1 gate (superseded, evidence retained):** pretrained base must emit
  schema-valid grounded first actions at ≥ 0.5 on an 18-call probe → observed
  0/18 on both arms → VALID_STOP.
- **v2 gate (frozen before any trained-adapter outcome exists):** after
  training each arm's two adapters, run the learned policy on the **three
  cheapest tasks of the frozen 9-task membership** (storage-compact-919000,
  elevators-compact-914002, ferry-compact-915000) × both algorithms = 6
  episodes per arm under the clean contract (2× reference decision caps, seed
  17, greedy decoding). Gate measure: **schema-valid grounded call rate** =
  trusted-runtime-accepted model calls / total model calls across the arm's
  smoke episodes. Frozen threshold **≥ 0.5**. At or above, the arm proceeds to
  the full frozen evaluation; below, that rung VALID_STOPs with smoke evidence
  published. Corruption runs only if `visual-seq-state` passes. Gated-out
  bindings are published as `gated_out_by_smoke` — never silently dropped.
  Minimum meaningful scope unchanged: one arm passing + its complete clean
  evaluation.

This keeps the spirit of the original pre-registration (a bounded feasibility
check before the full-panel spend) while conditioning on the quantity that
actually gates it: whether the *trained* policy can emit operations under the
arm's contract at all. The threshold and subset are frozen before any
trained-arm outcome exists; success rates are never gated (that is the
scientific outcome, not an admission condition).

## v2 admission and budget

Corpus/budget admission recomputed from preparation reports, ledger spend and
frozen bases only: training basis 0.3633 GPU-h/cell (v5 measured) scaled for
the seq arm by 1 + mean_history_frames/4; per-call price = 7.0704 s (max
observed across both published v1 probe reports) × runtime caps (2× reference
decisions learned / 1 call base) for smoke + clean + corruption matrices;
×1.25 safety; 6 GPU worker jobs × 120 s overhead. Estimated ≈ 7.1 GPU-h
against the 11.9074 GPU-h remainder of the authorized
`followup-native-arms-v1` window (same ledger; expanded-nine-day-v1 remains
untouched).

## Everything else unchanged

Observation contracts and legends, K=8 history window, the frozen v5
membership and training recipe (512 records / 1 epoch / 16 updates / seed 17),
the frozen 9-task evaluation membership, clean and corruption matrices, caps,
rollout seeds {17, 5077, 6131, 7409, 8527}, reused comparators, independent
replay of every episode, paired analysis (bootstrap 61813, tiny-strata <8,
#54 saturation), missingness policy. #128's published VALID_STOP evidence is
retained untouched; this amendment is its strictly prospective continuation
under #129.

## Ordering

1. Commit this amendment + protocol + runner changes (this commit).
2. GPU: training (one arm per GPU: `na-v1-train-nomem`, `na-v1-train-seq`).
3. GPU: smoke gate per arm (`na-v1-smoke-*`); audits; commit.
4. GPU+CPU: full evaluation for passing arms + controls; finalize with
   independent replay of every episode and comparator; analysis; commit.
5. #129 closeout against verified evidence.
