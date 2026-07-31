# CGAS Steps Manifest Binding

- `scripts.phase3.cgas_certificates._steps_manifest()` is the single deterministic constructor for the persisted certificate manifest. It binds `schema_version`, the aggregate accepted-source digest, the aggregate accepted-alignment digest, and the canonical generated-step digest.
- `verify_steps()` loads `steps_manifest.json` after the step files and schema. It rejects a missing file as `missing_steps_manifest`, invalid JSON or a non-object as `malformed_steps_manifest`, and any exact-object difference as `steps_manifest_mismatch`.
- Manifest failures are additive to the existing record/certificate/schema diagnostics rather than replacing them. A fresh fixture remains 12 accepted rows with zero counters; a stale manifest digest fails closed.
- Remediation evidence is retained under `.omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-5/`.
