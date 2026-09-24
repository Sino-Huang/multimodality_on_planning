# #142 closeout: identity audit on LLM-First Search

**Audited: LLM-First Search (Herr et al., arXiv 2506.05213; type C). Verdict under the paper's
budget: SATURATED (predicted SATURATED). Verdict at a matched decision budget:
CHOICE_REGISTERED (predicted CHOICE_REGISTERED).** Both predictions held.

The random chooser diverges from the published controller in all 400 pairs, 380 of them at the
first decision. Under the paper's per-game token cap it wins 80/80 tasks on every seed. The
published controller wins 66/80 with the substitute model. This published evaluation therefore
gives full or better success to a controller that makes no informed choice. The failure is at
the outcome level, not at the decision level. It comes from the budget unit: a token cap never
binds a chooser that spends no tokens, and the frontier keeps every alternative, so random choice
becomes an exhaustive randomized search. Counted in decisions, the model's choices matter a
great deal. Given the reference's own number of expansions, random_valid wins 7.75% of tasks
against 82.5%.

Commits: feasibility `4f78f6b`, protocol + runner + analyzer + server spec `b09a458`
(both before any GPU launch or audit episode), Amendment A1 `e89a793` (before any audit episode).
Evidence and this closeout are in the commit that adds this file.

## Design (protocol `issue-142-protocol.md`)

- Upstream: https://github.com/NathanHerr/LLM-First-Search @ `3025bdaa3add6f41388c1d5a6d354522489d312e`
  (Apache-2.0). It is cloned untracked and imported, and the runner asserts that the checkout is
  clean at that commit. `run_countdown` / `run_sudoku` run unchanged.
- Tasks: every configuration with a published LFS-GPT-4o WinRate above 10%, i.e. Countdown 3/5/7
  and Sudoku 4x4 hard, games 0-19 each (README reproduction set). That gives 80 tasks. Sudoku
  6x6 (2.22%) is excluded by this rule.
- Budget: the README token caps (Countdown 1,000,000; Sudoku 4x4 100,000), temperature 0.0,
  `max_tokens` 16384, timeout 300 s. There is a 500,000-expansion safety guard; it never bound.
- reference: the published LFS loop, with queries answered by `Qwen/Qwen3-30B-A3B-Instruct-2507`
  @ `0d7cf239` (vLLM 0.11.0, GPU 1, ports 18850/18851/18852). One run per task.
- random_valid: the same loop with the agent's `ask` answered uniformly at random (fair-coin
  explore, U(0,1) values), so the argmax child and the popped frontier node are uniform among
  the valid options. Zero tokens. Seeds 17/5077/6131/7409/8527.
- Decision: one node expansion after the root, identified by its child-index path.
- Pair identical: equal decision sequences and equal win flag.

## Results (`outputs/external-audit/v2/lfs/identity-audit.json`)

| quantity | value | JSON key |
|---|---|---|
| tasks / pairs_checked | 80 / 400 | `tasks`, `pairs_checked` |
| pairs identical / divergent | **0** / 400 | `pairs_identical`, `pairs_divergent` |
| first_divergence_index median, min, max | 0, 0, 2 (380/400 at index 0) | `first_divergence_index` |
| **paper budget**: success reference | **0.825** (66/80) | `paper_budget.success.reference` |
| paper budget: random_valid per seed (17, 5077, 6131, 7409, 8527) | 1.0, 1.0, 1.0, 1.0, 1.0 | `paper_budget.success.random_valid_per_seed` |
| paper budget: random_valid mean | **1.000** (400/400 episodes) | `paper_budget.success.random_valid_mean` |
| paper budget: reference − random, mean per task [95% CI] | −0.175 [−0.2625, −0.100] | `paper_budget.contrast.mean_difference_reference_minus_random`, `.bootstrap_95ci` |
| paper budget: exact sign-flip p (two-sided, descriptive) | 1.22e-4 (14 tasks random better, 0 reference better, 66 tied) | `paper_budget.contrast.sign_flip_p_two_sided_exact` |
| paper budget: random/reference ratio [95% CI] | 1.212 [1.111, 1.356] | `paper_budget.contrast.random_over_reference_ratio` |
| paper budget: saturation / **verdict** | true / **SATURATED** | `paper_budget.verdict` (= headline `verdict`) |
| **matched decision budget**: random_valid per seed | 0.0625, 0.075, 0.075, 0.0875, 0.0875 | `matched_decision_budget.success.random_valid_per_seed` |
| matched: random_valid mean | **0.0775** | `matched_decision_budget.success.random_valid_mean` |
| matched: reference − random [95% CI] | +0.7475 [+0.6475, +0.8375] | `matched_decision_budget.contrast` |
| matched: exact sign-flip p (descriptive) | 3.1e-18 (66 reference better, 4 random better, 10 tied) | `matched_decision_budget.contrast.sign_flip_p_two_sided_exact` |
| matched: saturation / **verdict** | false / **CHOICE_REGISTERED** | `matched_decision_budget.verdict` |
| random_valid success at m x reference expansions, m = 1, 1.25, 1.5, 1.75, 2 | 0.078, 0.098, 0.140, 0.170, 0.190 (normalized AUC 0.135) | `matched_decision_budget.random_valid_decision_budget_curve` |
| published LFS-GPT-4o WinRate, audited configs | 0.768 | `published_model_success` |
| random_fraction_of_published | 1.301 | `random_fraction_of_published` |

Per configuration (`per_config`):

| config | reference wins | random_valid (paper budget) | random_valid (matched) | sign-flip p paper / matched | median expansions ref / random | GPT-4o LFS (paper) |
|---|---|---|---|---|---|---|
| Countdown-3 | 20/20 | 1.00 | 0.12 | 1.0 / 1.9e-6 | 4 / 15 | 100.00 |
| Sudoku 4x4 | 18/20 | 1.00 | 0.06 | 0.5 / 7.6e-6 | 23 / 97.5 | 96.84 |
| Countdown-5 | 15/20 | 1.00 | 0.11 | 0.0625 / 5.3e-4 | 102.5 / 1,303 | 63.16 |
| Countdown-7 | 13/20 | 1.00 | 0.02 | 0.0156 / 2.4e-4 | 157 / 7,358.5 | 47.37 |

All 14 reference losses ended at the token cap (su4-01, su4-05; cd5-01, -02, -04, -15, -19;
cd7-04, -05, -08, -09, -16, -17, -18). The reference used a median of 70k tokens per task
(maximum 1,300 expansions). random_valid used 0 tokens, a median of 201 expansions per episode,
and a maximum of 102,606; the 500k guard never bound. The saturation is SATURATED on every
configuration alone, and CHOICE_REGISTERED at the matched budget on every configuration. The
substitute model does better than GPT-4o on Countdown-5/7 (0.75 and 0.65 against 0.63 and
0.47); the verdict does not depend on that.

## Validation

- Replay (`replay.json`): all 80 reference episodes were re-executed through the unpatched
  upstream loop from their logged responses, with every request hash-checked. Result: 80 match,
  0 mismatch, 0 missing. All 400 random_valid episodes were re-run in a fresh process: 400
  byte-identical, 0 mismatch, 0 missing. Smoke (games 20-21, unanalysed): 8/8 reference and
  40/40 random_valid replays matched.
- `FastFrontier` (random_valid only) was byte-identical to the unpatched loop on 57/57 probe
  episodes before the protocol. Its invariants (every frontier node valued, no tie at the
  maximum) held in all 400 audit episodes: 0 `upstream_error`.

## Amendments and deviations

- **A1** (`e89a793`, 02:50 AEST, before any audit episode): the audit started once the cd3 and su4
  smoke episodes had replayed, and the cd5/cd7 smoke episodes continued concurrently. The heading
  first carried an estimated time (02:55). It was corrected to the commit time in the closeout
  commit, with no change of content. The bash wrapper of the first smoke process hit its
  3,600 s tool timeout before `cd5-20` finished. That one smoke episode was relaunched and it
  completed (8/8 smoke episodes).
- Declared deviations (protocol): the substitute model instead of GPT-4o; one reference run per
  task instead of n = 5; Sudoku 6x6 excluded; `FastFrontier` for random_valid; in-memory result
  capture instead of per-game pickles.
- The protocol order put the random_valid arm after the server stop, and it ran that way.

## Compute ledger (`outputs/external-audit/v2/budget.json`)

- Attempt 1: server start failed before readiness, 32 s (vLLM's resolver had pulled
  transformers 5.x; pinned to 4.57.1).
- Attempt 2: server up 2.88 h on GPU 1 (load, smoke, audit, idle tail).
- **Total 2.89 GPU-h of the 12 GPU-h cap**, inside the feasibility estimate of 2-4. Paid API
  spend: $0. The random arm, probes, replays and analysis ran on CPU. GPU 0 was not used.

## Limitations

- The reference model is a substitute (Qwen3-30B-A3B-Instruct-2507, non-thinking), not GPT-4o.
  Its per-configuration success differs from the paper's. The paper-budget verdict holds for any
  reference, because random_valid won 400/400; the ratio rule is met whatever the reference
  scores.
- One reference run per task, at temperature 0 on a batching server, which is not bitwise
  deterministic. The replay proves the logged decisions follow from the logged responses; it
  does not re-sample the model.
- The matched-decision reading is our analysis, not the paper's metric. The paper reports
  WinRate under a token cap and token efficiency, which does penalize tokens. It does not report
  a decision-matched or random baseline.
- The paper-budget saturation is structural. The cap binds only token-spending controllers, and
  LFS keeps every unexpanded node, so any chooser completes a randomized exhaustive search of a
  finite tree. The published efficiency metric (WinRate/tokens) is undefined for a zero-token
  controller.

## Manuscript consequence (for #131, fixed in the protocol before the outcome)

SATURATED with 0/400 identical pairs, and CHOICE_REGISTERED at the matched decision budget. The
value-anchor sentence should change, but not to say that the identity failure appears in
published practice. The per-decision identity failure (48/48 identical pairs) is still shown
only on our runtime: on LLM-First Search, random choices diverge at the first decision in 380/400
pairs. What the published LFS evaluation does show is the outcome-level counterpart. Under its
own token budget, a random-valid controller that spends no tokens solves 80/80 tasks against
66/80 for the model-guided controller. Success under that budget therefore does not measure
choice. At an equal number of decisions it does (7.75% against 82.5%). Suggested wording: "The
decision-level identity failure is shown on our runtime. On a published type-C search interface
(LLM-First Search) we find its outcome-level counterpart: under the paper's token budget a
uniform random chooser solves every audited task, because the budget does not bind a controller
that spends no tokens."

## Evidence index (sha256, first 16)

```
344ef08f6548269c  lfs/identity-audit.json
6c143d6f963ad147  lfs/replay.json
b6b74c9d91b2b6fa  lfs/tasks.json
db3aac8c3e0646c5  lfs/episodes/** (480 files)
d78363b12e7e836b  lfs-smoke/replay.json
1e10a5fd62f53f00  lfs-smoke/episodes/** (48 files)
e8eb7d8588bc1af3  lfs-probe/fast-equivalence.json
b02ae2b4dc6eb344  lfs-probe/episodes/** (100 files)
a3cc2595ec97bf6c  budget.json
c5278f1d13df185c  evidence-index.json (sha256 of all 648 files)
```

Root: `outputs/external-audit/v2/` (untracked by repo convention). A directory digest (`/**`) is
the sha256 of the sorted `path sha256` lines for that directory in `evidence-index.json`.
Tracked: `scripts/run_external_audit_v2_lfs.py`, `scripts/analyze_external_audit_v2_lfs.py`,
`configs/experiments/external-audit-v2/lfs-reference-server.json`,
`docs/experiments/external-audit/issue-142-{feasibility,protocol,closeout}.md`.

## Appendix: `identity-audit.json` (without `per_config`)

```json
{
  "benchmark": "llm-first-search",
  "first_divergence_index": {
    "max": 2,
    "median": 0,
    "min": 0,
    "pairs_diverging_at_0": 380
  },
  "interface_type": "C",
  "matched_decision_budget": {
    "contrast": {
      "bootstrap": {
        "draws": 10000,
        "interval": "percentile",
        "seed": 133,
        "unit": "task"
      },
      "bootstrap_95ci": [
        0.6475,
        0.8375
      ],
      "descriptive_only": "sign-flip p-value and intervals are descriptive; the verdict uses the fixed rule",
      "equivalence_margin": 0.05,
      "equivalent_within_margin": false,
      "mean_difference_reference_minus_random": 0.7474999999999999,
      "random_over_reference_ratio": 0.09393939393939395,
      "random_over_reference_ratio_bootstrap_95ci": [
        0.05070422535211268,
        0.14920634920634923
      ],
      "sign_flip_p_two_sided_exact": 3.0865880597946704e-18,
      "tasks_random_better": 4,
      "tasks_reference_better": 66,
      "tasks_tied": 10
    },
    "random_valid_decision_budget_curve": {
      "auc_normalized": 0.1353125,
      "multipliers": [
        1.0,
        1.25,
        1.5,
        1.75,
        2.0
      ],
      "random_valid_success": [
        0.0775,
        0.0975,
        0.14,
        0.17,
        0.19
      ],
      "reference_success_at_own_budget": 0.825
    },
    "rule": "random_valid wins only if it wins within the reference's own number of expansions on the task",
    "saturation": false,
    "success": {
      "random_valid_mean": 0.0775,
      "random_valid_per_seed": {
        "17": 0.0625,
        "5077": 0.075,
        "6131": 0.075,
        "7409": 0.0875,
        "8527": 0.0875
      },
      "reference": 0.825
    },
    "verdict": "CHOICE_REGISTERED"
  },
  "pairs_checked": 400,
  "pairs_divergent": 400,
  "pairs_identical": 0,
  "paper_budget": {
    "contrast": {
      "bootstrap": {
        "draws": 10000,
        "interval": "percentile",
        "seed": 133,
        "unit": "task"
      },
      "bootstrap_95ci": [
        -0.2625,
        -0.1
      ],
      "descriptive_only": "sign-flip p-value and intervals are descriptive; the verdict uses the fixed rule",
      "equivalence_margin": 0.05,
      "equivalent_within_margin": false,
      "mean_difference_reference_minus_random": -0.175,
      "random_over_reference_ratio": 1.2121212121212122,
      "random_over_reference_ratio_bootstrap_95ci": [
        1.1111111111111112,
        1.3559322033898304
      ],
      "sign_flip_p_two_sided_exact": 0.0001220703125,
      "tasks_random_better": 14,
      "tasks_reference_better": 0,
      "tasks_tied": 66
    },
    "saturation": true,
    "success": {
      "random_valid_mean": 1.0,
      "random_valid_per_seed": {
        "17": 1.0,
        "5077": 1.0,
        "6131": 1.0,
        "7409": 1.0,
        "8527": 1.0
      },
      "reference": 0.825
    },
    "verdict": "SATURATED"
  },
  "verdict": "SATURATED",
  "prediction": {
    "matched_decision_budget": "CHOICE_REGISTERED",
    "paper_budget": "SATURATED"
  },
  "published_model_success": {
    "source": "Herr et al. arXiv 2506.05213 Table 2, LFS with GPT-4o, WinRate averaged over the audited configurations ['cd3', 'su4', 'cd5', 'cd7'] (equal game counts); per configuration {'cd3': 100.0, 'cd5': 63.16, 'cd7': 47.37, 'su4': 96.84}",
    "value": 0.768425
  },
  "random_fraction_of_published": 1.3013631779288806,
  "replay": {
    "random_valid": {
      "episodes": 400,
      "match": 400,
      "mismatch": 0,
      "missing": 0
    },
    "reference": {
      "episodes": 80,
      "match": 80,
      "mismatch": 0,
      "missing": 0
    }
  },
  "schema_version": "external_identity_audit_v2",
  "supplementary": {
    "expansions_max": {
      "random_valid": 102606,
      "reference": 1300
    },
    "expansions_median": {
      "random_valid": 201.0,
      "random_valid_wins": 201.0,
      "reference": 29.5,
      "reference_wins": 20.0
    },
    "first_decision_options_median": 25.5,
    "terminated": {
      "random_valid": {
        "success": 400
      },
      "reference": {
        "success": 66,
        "token_limit": 14
      }
    },
    "tokens_median": {
      "random_valid": 0.0,
      "reference": 70403.5
    }
  },
  "tasks": 80,
  "upstream": {
    "commit": "3025bdaa3add6f41388c1d5a6d354522489d312e",
    "license": "Apache-2.0",
    "repo": "https://github.com/NathanHerr/LLM-First-Search"
  }
}
```
