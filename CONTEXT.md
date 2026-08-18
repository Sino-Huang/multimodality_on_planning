# Planning Research Execution

GitHub issue #38, "Spec: Teach VLMs executable search processes across
modalities", is the single ratified authority decision for the current program,
executed through its ready-for-agent tickets #39-#108. This ratification under
issue #39 records its authority only: issue #38 remains open and its title,
body, state, and labels remain unchanged. No Search Process Policy training run
or efficacy result exists yet; nothing in this glossary or in retained evidence
constitutes such a result.

## Current terms (Search Process Policy program, issue #38)

**Search Process Policy**:
A VLM policy trained to execute a declared search algorithm by emitting its typed operations under a trusted runtime, rather than to propose a complete plan directly.
_Avoid_: Plan generator, certificate predictor

**Typed Search Operation**:
A discrete, runtime-checkable search step (for example expand, generate successor, update frontier, goal test) issued by the policy within a declared algorithm.
_Avoid_: Reasoning step, chain-of-thought

**Search-Trace Segment**:
A bounded, ordered slice of typed search operations and their state observations used as a training or evaluation unit.
_Avoid_: Full raw trace, reasoning log

**Search Episode Harness**:
The evaluation seam into which a formal task, a declared algorithm, a modality observation adapter, a policy adapter, and a frozen budget enter, and from which one complete episode and evidence record leaves.
_Avoid_: Benchmark script, evaluation wrapper

**Trusted Search Runtime**:
The deterministic executor that applies typed search operations, maintains algorithm state, and checks invariants, so the model never owns unbounded search bookkeeping.
_Avoid_: LLM-internal planner, prompt-simulated search

**Search Memory**:
The external runtime/data boundary that holds frontier, visited/best-depth, novelty, and landmark state for the runtime; it is not internal unbounded model state.
_Avoid_: Context-window contents, hidden state

**Algorithm Invariant**:
A deterministic property of the declared algorithm (for example BFS layer order, IW novelty pruning, A* frontier order under h_max or landmark-count) checked by the trusted runtime on every operation.
_Avoid_: Heuristic preference, soft constraint

**Modality Observation**:
A task state rendered in one declared modality (text, image, or paired) and presented to the policy under a fixed adapter contract.
_Avoid_: Prompt text, frame dump

### Governed downstream vocabulary

Every downstream ticket must reuse the following terms and definitions
verbatim.

**operational competence**:
Competence on local applicability, progression, validation, and transition/action tasks; it does not by itself establish executable search.

**structural/process competence**:
Competence in the model-owned decisions that determine exploration and maintain declared algorithm behavior over a full budgeted episode, evaluated with budgeted search success and mechanically checkable algorithm invariants; it is reported separately from local transition or successor prediction.

**validity**:
The trusted runtime's mechanical judgment that a typed search operation and its state effects satisfy the declared operation contract and algorithm invariants; validity is not by itself episode success or competence, and an invalid operation is charged to the episode budget without silent repair.

**stop outcome**:
One governed receipt classification from this fixed set:

- `PASS`: the applicable frozen gate criteria passed.
- `VALID_STOP`: a governed stop that produces a gated-not-run receipt.
- `INVALID`: an outcome that must never be treated as scientific completion.
- `ANCESTOR_STOP`: a downstream stop caused by a blocking ancestor gate; it produces a gated-not-run receipt.

The modality conditions use matched task content under state-plus-goal semantic
parity and a fixed search-memory interface and capacity:

**text-state**:
The state and goal represented as a compact relational serialization.

**visual-state**:
The state and goal represented as a rendered state plus a partial-goal constraint image.

**multimodal-state**:
The same state and goal represented by both text-state and visual-state.

## Retained infrastructure terms (still current)

**Plan Submission**:
Transmission of a particular supplied plan from the project adapter to a planning or rendering backend.
_Avoid_: Plan sent, request success

**Plan Interpretation**:
Conversion of a submitted plan into the backend's ordered action representation.
_Avoid_: Plan accepted, plan parsed successfully

**Action Sequence**:
The canonical identity of a supplied plan as a normalized, ordered sequence of grounded action predicates; casing and whitespace are not part of its identity.
_Avoid_: Exact plan bytes, plan text

**Render Production**:
Creation of a visualisation output and its rendered image for a planning state.
_Avoid_: Render validation, integration success

**Render Validation**:
Confirmation that a produced visualisation and image satisfy the declared structural and semantic checks.
_Avoid_: Integration validation, certification

**Plan Provenance**:
Evidence that links a produced visualisation to the exact supplied plan that the backend interpreted.
_Avoid_: Plan logging, request evidence

**Integration Certification**:
The complete finding that Plan Submission, Plan Interpretation, Plan Provenance, Render Production, Render Validation, and required execution-isolation checks all passed.
_Avoid_: Validation passed, render worked

**Attempt**:
One authorized, immutable execution with its own identity and retained outcome, whether successful or unsuccessful.
_Avoid_: Retry, renderer attempt

**Evidence Bundle**:
The self-contained records from an Attempt that allow an independent reproducer to verify its claims offline.
_Avoid_: Logs, proof report

## Historical CGAS terms (not the current target)

The terms below describe the demoted CGAS program. They are retained so that
historical evidence and retained infrastructure remain interpretable. They are
not current headline claims and are not efficacy evidence for the Search
Process Policy study.

**Planning Certificate**:
A structured symbolic record paired with a proposed action and next state, checked directly by deterministic planning invariants rather than treated as a latent representation.
_Avoid_: Latent certificate, integration certification

**Joint Action-and-Certificate SFT**:
Task-specific supervised fine-tuning that teaches one model to predict both a grounded action and its Planning Certificate.
_Avoid_: Experience distillation, in-context learning

**Adaptive Scaffolding**:
Runtime allocation of bounded certificate or memory support according to a learned, verifier-supervised route choice.
_Avoid_: Experience distillation, adaptive computation

**Support Route**:
One fixed information boundary offered to the model: direct observation, prior-certificate context, or live-memory context.
_Avoid_: Prompt variant, scaffold level

**Live Memory**:
A bounded, problem-instance-local store keyed by canonical state identity and containing only previously observed, verifier-approved action, certificate, and outcome records.
_Avoid_: Trajectory history, retrieval corpus

**Verified Joint Step**:
A prediction whose grounded action is applicable, whose Planning Certificate satisfies its invariants, and whose action and certificate describe the same transition.
_Avoid_: Exact-match step, valid certificate alone

**Route Label**:
The least-cost Support Route that produces a Verified Joint Step under counterfactual execution of the same frozen model.
_Avoid_: Failure-type label, controller prediction
