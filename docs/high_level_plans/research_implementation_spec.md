# CGAS Research Implementation Specification

**Status:** Confirmed design, 2026-08-17  
**Parent plan:** [`research_execution_plan.md`](./research_execution_plan.md)  
**Research proposal:** [`../research_proposal.md`](../research_proposal.md)

## Purpose

This specification records the implementation and experimental decisions needed to execute the Certificate-Guided Adaptive Scaffolding (CGAS) study. It refines the parent plan without reordering its authorization boundaries or gates.

The immediate priority is to unblock the local Planimation integration certification. The research priority is then to run the cheapest decisive direct-VLM calibration before implementing CGAS.

Canonical domain terms are defined in [`../../CONTEXT.md`](../../CONTEXT.md).

## Governing principles

- Make the smallest change that discharges the next gate.
- Do not infer scientific success from HTTP success, render completion, or certificate exact match alone.
- Keep problem instances—not individual state rows—as the split and uncertainty unit.
- Keep planning certificates, Planimation integration evidence, and model route labels as distinct contracts.
- Do not promote off-plan states to action supervision without an authoritative action-target policy.
- Do not describe certificate or memory conditioning as ICL without a frozen-weight context ablation.
- Do not describe the current method as Experience Distillation.
- Preserve all execution-authorization boundaries in the parent plan.

## Build order

1. Implement and test the Planimation evidence verifier.
2. Obtain separate authorization for a fresh 4-object localhost certification attempt.
3. Add and separately authorize the fixed 8- and 12-object production-path smokes.
4. Obtain render authorization and render the 16,822 missing pilot states.
5. Align the 790 authoritative on-plan rows and release the pilot corpus.
6. Run the three-arm direct-VLM Gate-3 calibration.
7. Continue only if failures are recurrent, reproducible, certificate-localized, and mechanism-matched to CGAS.
8. Implement live memory, counterfactual route-label generation, and the CGAS controller.
9. Freeze the method and evaluate it on a separate untouched final test set.

---

## 1. Planimation integration certification

### 1.1 Scope

The first implementation slice certifies the existing 4-object integrated path:

```text
render_missing_states
  -> render_state_with_planimation_compat
  -> render_state_with_planimation
  -> post_pddl_for_vfg
  -> pinned localhost Planimation backend
```

It must not start the 8/12-object smokes, production rendering, replay alignment, model training, or CGAS implementation.

### 1.2 Module boundary

Add:

```text
scripts/phase3/cgas_planimation_evidence.py
tests/phase3/test_cgas_planimation_evidence.py
```

Do not modify the meaning of `scripts/phase3/cgas_certificate_contracts.py`; that module remains the released BFS/IW Planning Certificate contract.

The new evidence module owns only:

- supplied-plan Action Sequence parsing;
- VFG action-stage extraction;
- ordered action-sequence comparison;
- claim-matrix construction and validation;
- offline verification of a saved attempt root;
- the verification CLI.

The existing integration harness at
`data/deprecated/2026-08-18-cgas-realignment/.claude/evidence/cgas-phase3-pilot-rendering/local_planimation_adapter_integration.py`
remains responsible for launching the backend, invoking the real adapter path, capturing artifacts, and writing `proof-report.json`.

### 1.3 Action Sequence contract

`parse_action_sequence(plan_text)` must:

- extract a non-empty sequence of balanced parenthesized actions;
- reject unbalanced parentheses, nested action forms, empty actions, and non-whitespace text outside actions;
- normalize each action with the existing `scripts.phase3.pddl.normalize_action_string()` utility;
- ignore casing and whitespace differences;
- return ordered canonical strings such as:

```json
["(move a b c)", "(pickup b1)"]
```

The scientific identity of a supplied plan is this normalized ordered Action Sequence, not its raw multipart bytes. Existing raw-text cache identity and forwarding behavior remain unchanged.

### 1.4 VFG evidence contract

The verifier must require:

- exactly one initial VFG stage;
- the initial stage is excluded from action comparison;
- every remaining stage name normalizes as one grounded action;
- the normalized VFG actions equal the submitted Action Sequence in count and order.

This predicate is named `vfg_action_sequence_match`. Its diagnostics may state that it supports Plan Interpretation and Plan Provenance under the approved pinned backend source. It must not claim a directly observed parser invocation.

The backend identity is the approved Git commit:

```text
94d82afb5ee122ce579dd11ca1953b7c85ca5824
```

No file-level integrity layer, vendored snapshot, backend patch, runtime parser monkeypatch, socket guard, `strace`, or network namespace is added.

### 1.5 Required claim matrix

`proof-report.json` gains a schema version, normalized action sequences, a `claims` object, diagnostics, and a final `certified` boolean.

Each claim has `pass`, `fail`, or `not_observed` status. `certified` is true only when all required claims pass.

The required claims are:

1. `expected_action_sequence_match` — fixture and submitted normalized actions match.
2. `loopback_plan_submission` — exactly one render POST targets the approved loopback `/upload/pddl` endpoint and contains a non-empty plan.
3. `backend_commit_match` — the recorded backend commit equals the approved pin.
4. `vfg_action_sequence_match` — submitted and VFG action sequences match exactly in count and order.
5. `render_artifacts_valid` — required VFG/PNG artifacts exist and satisfy the existing recorded artifact checks.
6. `semantic_validation_pass` — the existing semantic image receipt passes.
7. `render_counts_exact` — exactly one state is requested and succeeds, with no failure, duplicate, collision, or remaining state.
8. `no_hosted_client_request` — the project client records no hosted request.

Unsafe execution should stop immediately. Remaining safe, offline predicates should still be evaluated so the report contains a complete claim matrix.

### 1.6 Isolation claim boundary

The certification demonstrates:

- the integrated project client used one loopback render POST;
- the request included a supplied plan;
- the returned VFG contains the same normalized ordered actions under the pinned backend commit;
- the project client recorded no hosted request.

It does **not** claim OS-level proof that the backend process made no external network syscall. Reports and papers must preserve this limitation.

### 1.7 Offline CLI

Provide:

```bash
python -m scripts.phase3.cgas_planimation_evidence verify \
  --attempt-root <saved-attempt-root>
```

The command:

- reads artifacts without starting Django, rendering, or modifying the attempt;
- prints a compact JSON result;
- exits `0` when certified;
- exits `1` when the attempt is structurally readable but a required claim fails;
- exits `2` when the directory, artifact set, or report schema is malformed.

### 1.8 Hermetic tests

The first slice must cover:

- one-action and multi-action parsing;
- casing and whitespace normalization;
- empty and malformed plans;
- exact VFG match;
- wrong action order;
- missing and extra action stages;
- malformed initial-stage structure;
- claim aggregation and diagnostics;
- CLI success, failed-claim, and malformed-input exit behavior;
- unchanged raw-plan multipart forwarding and cache identity.

Regular automated tests must not start the real backend or make network requests.

### 1.9 Attempt preservation and authorization

The existing failed 4-object attempt remains immutable and uncertified. It may be inspected read-only but must not be rewritten, resumed, or retro-certified.

A real rerun requires separate authorization naming a fresh exact output root and port. Passing the new hermetic tests does not authorize that run.

---

## 2. Fixed 4/8/12-object smoke fixtures

Use one checked-in deterministic fixture for each object count under a dedicated Phase-3 fixture directory. Each fixture records:

- object count;
- state/problem identity;
- domain and problem references;
- supplied plan text;
- expected normalized Action Sequence;
- semantic render expectations.

All three smokes use the same evidence schema and required claims. They differ only in fixture data, semantic expectations, and declared resource bounds.

The 8- and 12-object smokes remain separately authorized executions. They are not implicit retries of the 4-object certification.

---

## 3. Pilot corpus completion

After the 4/8/12-object gates and explicit render authorization:

1. Render the 16,822 missing pilot states through the resumable production path.
2. Perform replay alignment for the 790 rows with authoritative on-plan actions.
3. Run the existing certificate and corpus release gates.
4. Release the pilot corpus before starting Gate-3 model training.

The 30,381 off-plan rows remain available for certificate-only analysis, verifier tests, recovery studies, or future negative examples. They are excluded from action supervision until a separate owner-approved policy defines an authoritative goal-directed action target.

---

## 4. Gate-3 direct-VLM calibration

### 4.1 Scientific question

Gate 3 asks whether a competent direct VLM still exhibits recurrent, reproducible, verifier-localized planning failures that bounded symbolic memory or certificate support could specifically repair.

Raw low accuracy alone does not justify CGAS. Failures caused mainly by rendering, parsing, output formatting, insufficient optimization, or label ambiguity must be remediated or reported separately.

### 4.2 Experimental role

The first Gate-3 run is a calibration and mechanism-localization probe, not the final paper efficacy experiment. The current 790 authoritative action-supervised rows are not treated as definitive evidence for an 8B VLM.

If learning curves show that the pilot is too small to establish model competence, expand authoritative on-plan data before making final performance claims. Do not solve the shortage by inventing off-plan action labels.

### 4.3 Data split

- Keep every state, render, and trace derived from one PDDL problem instance in one split.
- Use the existing composition-disjoint 75-train/15-held-out pilot split for calibration only.
- Do not report the calibration holdout as the final test set.
- Before production training, freeze the method and create a separate untouched problem-instance test set.
- The primary generalization claim is held-out initial/goal configurations within the same domain, predicate ontology, action vocabulary, and declared object-count regime.
- Unseen-domain and unseen-predicate transfer are out of scope unless separate contracts and data are added.

### 4.4 Model interface

Use one VLM for BFS and IW.

Input:

- current rendered observation;
- task goal/instruction;
- explicit planner-family identifier;
- the corresponding typed output schema.

The direct condition receives no prior certificate, live memory, oracle state atoms, future trace data, route label, scaffold cost, or verifier feedback before prediction.

Output:

- one normalized grounded action;
- one structured symbolic Planning Certificate for the declared planner family.

BFS and IW metrics are reported separately and pooled.

### 4.5 Training taxonomy and arms

The direct model is **Joint Action-and-Certificate SFT**: offline behavior cloning with auxiliary symbolic-certificate supervision. It is not Experience Distillation.

Gate 3 compares three no-support inference arms:

1. pretrained instruct VLM with no task-specific tuning;
2. action-only SFT;
3. joint action-and-certificate SFT.

All arms use matched observations, task instructions, action vocabulary, split, and evaluation decoder. Certificate context and live memory are introduced only in the later routing study.

The terminology analysis is recorded in
`data/deprecated/2026-08-18-cgas-realignment/.claude/knowledge/vlm-adaptation-taxonomy-cgas-2026-08-16.md`.

### 4.6 Metrics

The primary metric is **Verified Joint Step**:

- the normalized grounded action is applicable;
- the Planning Certificate passes all required invariants;
- the action and certificate describe the same transition.

Secondary metrics:

- normalized action accuracy;
- certificate fidelity;
- parse success;
- per-invariant failure frequency;
- legal-goal rollout success when rollout evaluation is available.

Gate 3 authorizes CGAS only when failures are recurrent across held-out problem instances and concentrated in mechanisms that prior-certificate context, exact-key memory, or verifier-guided routing is designed to address.

---

## 5. CGAS mechanism

### 5.1 Support routes

All routes share the same base image, goal, planner identifier, output schema, frozen joint-SFT checkpoint, and decoding configuration.

The route palette is mutually exclusive:

- `direct`: base input only;
- `certificate`: base input plus the immediately preceding verifier-approved Planning Certificate;
- `memory`: base input plus records returned from Live Memory.

The memory route does not silently receive prior-certificate context. A combined certificate-plus-memory route is not part of the approved palette.

### 5.2 Live Memory

Live Memory is:

- namespaced by problem instance and planner family;
- keyed by canonical symbolic state identity;
- populated only from information observed earlier in the current rollout;
- limited to verifier-approved action, Planning Certificate, and outcome records;
- fixed-capacity with deterministic eviction;
- empty on an unseen state;
- reset at the declared problem-instance boundary.

Similarity retrieval, cross-instance retrieval, unbounded trajectory history, future information, and gold route labels are forbidden.

The exact capacity and deterministic eviction choice are calibration configuration values. They must be selected on calibration data and frozen before final testing.

### 5.3 Counterfactual route labels

For each route-labeled state:

1. freeze the trained VLM and decoding configuration;
2. execute the same model under every permitted route;
3. verify each joint action-certificate prediction;
4. label the least-cost route that produces a Verified Joint Step;
5. emit `unsupported` when no route succeeds;
6. use a fixed declared tie rule.

One-field certificate mutations remain useful for verifier localization, but they do not substitute for empirical counterfactual route execution.

### 5.4 Cost order

Store the full support-cost vector and order verifier-valid routes lexicographically by:

1. external retrieval/tool calls;
2. added context tokens;
3. retrieved bytes;
4. measured latency as a final reported tie-breaker.

Do not learn or retune scalar weights after observing outcomes. The measurement environment and token-counting implementation must be frozen in the experiment configuration.

---

## 6. Final evaluation

### 6.1 Matched routing comparison

Freeze one joint action-and-certificate SFT checkpoint and one decoding configuration for:

- direct;
- always-certificate;
- always-memory;
- generic confidence/entropy routing;
- full CGAS;
- CGAS without certificate-derived controller inputs;
- oracle cheapest-valid route.

The untuned model and action-only SFT model are calibration controls, not alternate checkpoints for routing baselines.

### 6.2 Repetitions and uncertainty

- Run at least five fixed training/controller seeds.
- Report every seed and aggregate results.
- Use paired 95% bootstrap intervals resampled at the complete problem-instance level.
- Never treat correlated state rows from the same problem instance as independent samples.

### 6.3 Focused ablation

The required causal ablation removes certificate-derived inputs from the controller while holding the model, data, support palette, and budget fixed. Attention maps may be reported descriptively but are not causal evidence.

### 6.4 Predeclared success rule

A successful final CGAS claim requires all of:

- legal-goal rollout success at least 5 absolute percentage points above direct, with a paired 95% interval excluding zero;
- support cost at least 20% below always-memory;
- legal-goal rollout success no more than 2 absolute percentage points below always-memory.

Certificate fidelity, Verified Joint Step rate, route agreement, route distribution, and per-invariant errors remain required supporting results.

If this Pareto rule fails, report the negative result rather than weakening the thresholds after evaluation.

---

## 7. Explicit non-goals

This specification does not authorize or require:

- modifying or forking the pinned Planimation backend;
- OS-level backend network isolation;
- a new hash-manifest layer or file-level backend source hashes;
- changing renderer cache identity from raw plan text;
- action supervision for off-plan rows;
- unseen-domain generalization claims;
- Experience Distillation or an ICL claim;
- exhaustive architecture sweeps or attention-based causal claims;
- implementing the full research pipeline before Gate 3 passes.

## 8. Parameters intentionally deferred to experiment configuration

The following are not architectural decisions and must be selected on training/calibration data, recorded in versioned configuration, and frozen before final testing:

- PEFT/full-SFT optimizer details and learning rates;
- action/certificate loss normalization and weight;
- decoding temperature, sampling, and maximum output length;
- Live Memory capacity and deterministic eviction policy;
- final-test sample size and generation seed;
- resource timeouts and latency measurement environment.

None may be tuned against the untouched final test set.
