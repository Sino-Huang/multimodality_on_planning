# CGAS Certificate Boundary

- `scripts.phase3.cgas_provenance` is the authoritative source gate and
  `scripts.phase3.cgas_alignment` is the authoritative one-image transition
  alignment gate. Todo 4 consumes their accepted JSONL outputs only.
- BFS certificate fields are projected from the trace expansion matching
  `state_before_id`; the visited delta is computed against the previous
  expansion's `visited_after` snapshot.
- IW certificate fields are projected from the unique `expand` event whose
  `state_atoms` equal the replay `state_before`. Exact IW rows exclude recovery
  traces through the upstream provenance gate.
- `model_input` is intentionally a four-field closed object. Keep all planning
  oracle state in target/evidence sections and validate injected fields before
  conversion work begins.
- The certificate CLI preserves colocated source data by atomically replacing
  only its `steps` and `schema` outputs, never the root corpus directory.
- 2026-07-28 remediation: a closed object with `additionalProperties: false`
  must explicitly declare every accepted property. The original emitted
  `model_input` omitted `properties`, causing Draft 2020-12 to reject all 12
  generated rows. Keep `step_schema()` as the shared strict source for emitted
  and checked-in schemas, and execute `Draft202012Validator` per stored row in
  `verify_steps()` before retaining the existing oracle-input checks. Count
  distinct invalid row IDs for `invalid_schema_rows`; do not infer JSON Schema
  validity from the handwritten policy validator.
- 2026-07-28 BFS order remediation: `frontier_order_summary` is a semantic BFS
  certificate invariant, not merely a schema field. Keep it in `BFS_FIELDS` so
  stale order is counted by `valid_certificate_failures` and one-invariant BFS
  counterfactual generation. The schema's `declared_invariant` enum must track
  that same tuple in both emitted and checked-in forms.
- 2026-07-28 duplicate-ID remediation: equality of expected and actual step-ID
  sets does not prove output cardinality. `verify_steps()` must reject repeated
  `step_id` values as `duplicate_step_id` before its retained
  `step_set_mismatch` comparison, so an exact duplicate cannot inflate stored
  rows while leaving the ID set unchanged.
- 2026-07-28 full-record remediation: resolve the expected record by stable
  `step_id`, then compare each non-certificate top-level field to that
  deterministic projection. Emit `record_mismatch:<field>` for stale source,
  planner, alignment, replay, target, or counterfactual content. Keep
  certificate equality in its dedicated validator so semantic reasons and
  counters remain precise.
