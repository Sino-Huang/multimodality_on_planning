# CGAS Full Stored-Row Binding

- `verify_steps()` deterministically regenerates its expected rows through
  `_evaluate(source_root, alignment_root)`, which consumes the authoritative
  provenance and replay-proven alignment manifests.
- It keeps certificate comparison separate so stale certificate fields retain
  their exact invariant reasons and contribute to
  `valid_certificate_failures`. Every other emitted field, including action,
  source hash, planner, alignment, replay evidence, and counterfactual targets,
  is compared to the regenerated row and rejects as `record_mismatch:<field>`.
- JSON Schema checks, closed-model-input oracle policy, duplicate step-ID
  detection, expected-ID set comparison, and counterfactual failure counters
  remain independent diagnostics. A clean 12-row fixture verifies with every
  counter at zero; a stale stored action fails only as
  `record_mismatch:action_target`.
- Remediation-4 evidence is under
  `.omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-4/`.
