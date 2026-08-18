# Manuscript Domain Model

This manuscript-local glossary preserves the #38 canonical planning-research language while the paper's argument is decided. It does not supersede the project-wide glossary.

## Canonical Terms

**Search Process Policy**: A VLM policy trained to execute a declared search algorithm by emitting Typed Search Operations under a Trusted Search Runtime, rather than proposing a complete plan directly.

**Typed Search Operation**: A discrete, runtime-checkable search step, such as expanding a node, generating a successor, updating a frontier, or applying a goal test, issued by the policy within a declared algorithm.

**Search-Trace Segment**: A bounded, ordered slice of Typed Search Operations and state observations used as a training or evaluation unit.

**Search Episode Harness**: The evaluation seam into which a formal task, declared algorithm, Modality Observation adapter, policy adapter, and frozen budget enter, and from which one complete episode and evidence record leaves.

**Trusted Search Runtime**: The deterministic executor that applies Typed Search Operations, maintains algorithm state, and checks invariants, so the model does not own unbounded search bookkeeping.

**Search Memory**: The external runtime/data boundary that holds frontier, visited or best-depth, novelty, and landmark state for the runtime; it is not internal unbounded model state.

**Algorithm Invariant**: A deterministic property of the declared algorithm, such as BFS layer order, IW novelty pruning, or A* frontier order under h_max or landmark-count, checked by the Trusted Search Runtime on every operation.

**Modality Observation**: A task state rendered in one declared modality (text, image, or paired) and presented to the policy under a fixed adapter contract.

**text-state**: The state and goal represented as a compact relational serialization.

**visual-state**: The same state and goal represented as a rendered state plus a partial-goal constraint image.

**multimodal-state**: The same state and goal represented by both text-state and visual-state.

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

**Empirical efficacy finding**: A comparative model result obtained under the preregistered evaluation protocol. None exists in the current evidence base.

**Claim boundary**: The narrowest statement directly supported by the available evidence. The manuscript must preserve this boundary.
