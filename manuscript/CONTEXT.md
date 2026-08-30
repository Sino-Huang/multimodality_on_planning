# Manuscript Domain Model

This manuscript-local glossary preserves the #38 canonical planning-research language while the paper's argument is decided. It does not supersede the project-wide glossary.

## Canonical Terms

**Search Process Policy**: A VLM policy trained to execute a declared search algorithm by emitting Typed Search Operations under a Trusted Search Runtime, rather than proposing a complete plan directly.

**Typed Search Operation**: A discrete, runtime-checkable search step, such as expanding a node, generating a successor, updating a frontier, or applying a goal test, issued by the policy within a declared algorithm.

**Search-Trace Segment**: A bounded, ordered slice of Typed Search Operations and state observations used as a training or evaluation unit.

**Search Episode Harness**: The evaluation seam into which a formal task, declared algorithm, Modality Observation adapter, policy adapter, and frozen budget enter, and from which one complete episode and evidence record leaves.

**Trusted Search Runtime**: The deterministic executor that applies Typed Search Operations, maintains algorithm state, and checks invariants, so the model does not own unbounded search bookkeeping.

**Search Memory**: The external runtime/data boundary that holds frontier, visited or best-depth, novelty, and landmark state for the runtime; it is not internal unbounded model state.

**Algorithm Invariant**: A deterministic property of the declared algorithm, such as BFS FIFO order, BFWS novelty/goal-count priority and duplicate handling, or A* frontier order under h_max or landmark-count, checked by the Trusted Search Runtime on every operation.

**Modality Observation**: A task state rendered in one declared modality (text, image, or paired) and presented to the policy under a fixed adapter contract.

**text-state**: The state and goal represented as a compact relational serialization.

**visual-state**: The same state and goal represented as a rendered state plus a partial-goal constraint image.

**multimodal-state**: The same state and goal represented by both text-state and visual-state.

## Model and Runtime Ownership

The policy must emit the operation type and every operand that determines exploration, including the selected source or frontier state and any successor, action, or insertion decision required by the declared operation. The Trusted Search Runtime may validate, apply, persist, and reject that emission, but it may not choose omitted operands, reorder candidates on the policy's behalf, silently repair an invalid emission, or substitute a default search decision. Replaying the raw policy emissions against the same task and prior Search Memory must reproduce the explored trace. This is the manuscript's test for attributing a search decision to the model rather than to runtime bookkeeping.

Stepwise validity and Algorithm Invariant compliance do not establish termination, completeness, optimality, or episode success. Those outcomes are reported separately under the declared task, heuristic, tie-breaking, and budget contract.

## Retained Infrastructure Terms

**Plan Submission**: Transmission of a particular supplied plan from the project adapter to a planning or rendering backend.

**Plan Interpretation**: Conversion of a submitted plan into the backend's ordered action representation.

**Action Sequence**: The canonical identity of a supplied plan as a normalized, ordered sequence of grounded action predicates; casing and whitespace are not part of its identity.

**Render Production**: Creation of a visualisation output and its rendered image for a planning state.

**Render Validation**: Confirmation that a produced visualisation and image satisfy declared structural and semantic checks.

**Plan Provenance**: Evidence that links a produced visualisation to the exact supplied plan that the backend interpreted.

**Integration Certification**: The complete finding that Plan Submission, Plan Interpretation, Plan Provenance, Render Production, Render Validation, and required execution-isolation checks all passed.

**Attempt**: One authorized, immutable execution with its own identity and retained outcome, whether successful or unsuccessful.

**Evidence Bundle**: The self-contained records from an Attempt that allow an independent reproducer to verify its claims offline.

## Historical CGAS Terms

Planning Certificate, Joint Action-and-Certificate SFT, Adaptive Scaffolding, Support Route, Live Memory, Verified Joint Step, and Route Label are historical CGAS terms. They may describe retained infrastructure but cannot support a current Search Process Policy efficacy claim.

## Claim Status Terms

**Demonstrated infrastructure finding**: A claim supported by committed code, focused verification, and retained Evidence Bundles. It is not an efficacy finding.

**Planned method component**: A specified mechanism without training or evaluation evidence. It must be described as proposed, not as an established result.

**Bounded empirical finding**: A comparative model result supported within one governed development panel but not licensed as a final or general efficacy conclusion. Issue #54's outcome-blind 15-task BFS v8 panel is the current example: process SFT achieved 1.0 invariant-valid success with zero invalid operations, the base model achieved 0.0, and random-valid also achieved 1.0. The zero gain over the best control produced `VALID_STOP` with `scientific_completion=false`.

**Final empirical efficacy finding**: A comparative result from the authorized final primary evaluation. None exists in the current evidence base.

**Claim boundary**: The narrowest statement directly supported by the available evidence. The manuscript must preserve this boundary.
