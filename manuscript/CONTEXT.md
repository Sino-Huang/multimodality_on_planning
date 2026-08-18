# Manuscript Domain Model

This manuscript-local glossary preserves the canonical planning-research language while the paper's argument is decided. It does not supersede the project-wide glossary.

## Canonical Terms

**Plan Submission**: Transmission of a particular supplied plan from the project adapter to a planning or rendering backend.

**Plan Interpretation**: Conversion of a submitted plan into the backend's ordered action representation.

**Action Sequence**: The canonical identity of a supplied plan as a normalized, ordered sequence of grounded action predicates; casing and whitespace are not part of its identity.

**Render Production**: Creation of a visualisation output and its rendered image for a planning state.

**Render Validation**: Confirmation that a produced visualisation and image satisfy the declared structural and semantic checks.

**Plan Provenance**: Evidence that links a produced visualisation to the exact supplied plan that the backend interpreted.

**Planning Certificate**: A structured symbolic record paired with a proposed action and next state, checked directly by deterministic planning invariants rather than treated as a latent representation.

**Joint Action-and-Certificate SFT**: Task-specific supervised fine-tuning that teaches one model to predict both a grounded action and its Planning Certificate.

**Adaptive Scaffolding**: Runtime allocation of bounded certificate or memory support according to a learned, verifier-supervised route choice.

**Support Route**: One fixed information boundary offered to the model: direct observation, prior-certificate context, or live-memory context.

**Live Memory**: A bounded, problem-instance-local store keyed by canonical state identity and containing only previously observed, verifier-approved action, certificate, and outcome records.

**Verified Joint Step**: A prediction whose grounded action is applicable, whose Planning Certificate satisfies its invariants, and whose action and certificate describe the same transition.

**Route Label**: The least-cost Support Route that produces a Verified Joint Step under counterfactual execution of the same frozen model.

**Integration Certification**: The complete finding that Plan Submission, Plan Interpretation, Plan Provenance, Render Production, Render Validation, and required execution-isolation checks all passed.

**Attempt**: One authorized, immutable execution with its own identity and retained outcome, whether successful or unsuccessful.

**Evidence Bundle**: The self-contained records from an Attempt that allow an independent reproducer to verify its claims offline.

## Claim Status Terms

**Demonstrated infrastructure finding**: A claim supported by committed code, focused verification, and retained Evidence Bundles. It is not an efficacy finding.

**Planned method component**: A specified mechanism without training or evaluation evidence. It must be described as proposed, not as an established result.

**Empirical efficacy finding**: A comparative model result obtained under the preregistered evaluation protocol. None exists in the current evidence base.

**Claim boundary**: The narrowest statement directly supported by the available evidence. The manuscript must preserve this boundary.
