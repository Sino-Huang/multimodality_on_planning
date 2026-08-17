# Planning Research Execution

This context covers the evidence-bearing execution of planning, rendering, calibration, and model experiments described by the research program.

## Language

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

**Integration Certification**:
The complete finding that Plan Submission, Plan Interpretation, Plan Provenance, Render Production, Render Validation, and required execution-isolation checks all passed.
_Avoid_: Validation passed, render worked

**Attempt**:
One authorized, immutable execution with its own identity and retained outcome, whether successful or unsuccessful.
_Avoid_: Retry, renderer attempt

**Evidence Bundle**:
The self-contained records from an Attempt that allow an independent reproducer to verify its claims offline.
_Avoid_: Logs, proof report
