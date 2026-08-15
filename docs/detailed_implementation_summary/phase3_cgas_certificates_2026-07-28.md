# Phase 3 CGAS Certificates

## Scope

Todo 4 adds `planning_cgas_v1` typed transition records. The builder reads only
accepted Todo 2 source rows and Todo 3 alignment rows. It emits one record per
transition with a stable ID, source hash, planner/version, split/OOD state,
task text, one aligned image, action target, certificate target, replay evidence,
and target-only counterfactuals.

The model input is closed to `domain`, `image_path`, `planner`, and `task_text`.
Route labels, memory payloads, scaffold costs, queues, novelty tables, replay
traces, final state, gold targets, and evaluation diagnostics are rejected there.

## Certificate Contract

- BFS certificates contain `frontier_head`, `frontier_order_summary`,
  `visited_delta`, and `expanded_state`.
- IW certificates contain `novelty_tuple`, `seen_feature_delta`, and
  `width_decision`.
- Every required invariant receives one deterministic target-only mutation.
  The verifier requires exactly one declared failure and classifies a two-field
  BFS mutation as `multiple_invariants_changed`.

## Commands

Run in the confirmed Conda environment:

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_certificate_contracts.py scripts/phase3/cgas_certificates.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_certificate_contracts.py scripts/phase3/cgas_certificates.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --verify --source-root <accepted-source-root> --alignment-root <accepted-alignment-root> --output-root <step-output-root>
git diff --check
```

The bounded fixture CLI report is retained in
`.omo/evidence/task-4-cgas-dataloader-and-experiment-support/certificate-verify.json`:
`invalid_schema_rows=0`, `valid_certificate_failures=0`,
`counterfactual_wrong_failure_count=0`, and
`counterfactual_multi_invariant_count=0`.

Adversarial receipts record `multiple_invariants_changed` for a two-field BFS
mutation and `oracle_field_in_input` for injected queue state. No temporary
candidate directories remain after atomic publication; the bounded fixture is
retained only as evidence.

## 2026-07-28 Schema Remediation

The emitted `_schema()` previously declared `model_input.required` and
`additionalProperties: false` without its four `properties`. Draft 2020-12
therefore rejected every generated row because each valid model-input field was
treated as additional. The handwritten verifier did not execute the emitted
JSON Schema, so a malformed model input could be accepted with
`invalid_schema_rows=0`.

`step_schema()` now owns the strict Draft 2020-12 contract for the closed
model input, planner, BFS/IW certificate variants, replay evidence, alignment,
and counterfactual structures. `_schema()` returns that contract, the checked-in
schema is identical, and `verify_steps()` runs `Draft202012Validator` on every
stored row before its existing oracle-input and certificate/counterfactual
policy checks. `invalid_schema_rows` is the number of distinct invalid rows,
not the number of individual validation errors.

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_certificates.py scripts/phase3/cgas_certificate_contracts.py tests/phase3/test_cgas_certificates.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_certificates.py scripts/phase3/cgas_certificate_contracts.py tests/phase3/test_cgas_certificates.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --source-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/planning_cgas_v1 --alignment-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/alignment --output-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation/fresh-steps
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --verify --source-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/planning_cgas_v1 --alignment-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/alignment --output-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation/fresh-steps
```

The focused suite passed `12 passed`; Basedpyright reported `0 errors, 0
warnings, 0 notes`; both CLI reports have `accepted_rows=12` and all failure
counters at zero. The RED proof, green command output, and independent
all-row JSON Schema validation are retained under
`.omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation/`.

## 2026-07-28 BFS Frontier-Order Remediation

`frontier_order_summary` was emitted and required by the BFS JSON Schema, but
was omitted from `BFS_FIELDS`. A stale order could therefore pass semantic
certificate verification and no counterfactual was generated for that
invariant. It is now part of `BFS_FIELDS`, the certificate-failure counter,
generated BFS counterfactuals, and the declared-invariant enum in both emitted
and checked-in schemas.

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_certificates.py scripts/phase3/cgas_certificate_contracts.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_certificates.py scripts/phase3/cgas_certificate_contracts.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --source-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/planning_cgas_v1 --alignment-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/alignment --output-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-2/fresh-steps
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --verify --source-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/planning_cgas_v1 --alignment-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/alignment --output-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-2/fresh-steps
```

The regression first failed because a stale order was accepted and no matching
counterfactual existed. The updated focused suite passed `13 passed`; both
fresh CLI reports accept 12 rows with all counters at zero. Receipts are under
`.omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-2/`.

## 2026-07-28 Duplicate Step-ID Remediation

`verify_steps()` compared expected and actual ID sets, which allowed an exact
duplicate output row to evade detection: 13 stored rows with one repeated ID
still had the expected 12-ID set and were accepted. Verification now separately
checks step-ID cardinality and emits `duplicate_step_id` with zero accepted rows
before retaining the independent `step_set_mismatch` check for unique-set
differences.

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_certificates.py scripts/phase3/cgas_certificate_contracts.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_certificates.py scripts/phase3/cgas_certificate_contracts.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --source-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/planning_cgas_v1 --alignment-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/alignment --output-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-3/fresh-steps
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --verify --source-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/planning_cgas_v1 --alignment-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/alignment --output-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-3/fresh-steps
```

The exact-duplicate regression first observed `accepted_rows=12`; after the
repair, the focused suite passed `14 passed`, and both fresh CLI reports accept
the correct 12 unique rows with all counters at zero. Receipts are under
`.omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-3/`.

## 2026-07-28 Full Stored-Record Binding

Schema validity and certificate-field equality alone do not prove a stored
record is the deterministic projection of its source and alignment manifests.
After the existing schema, oracle-policy, and certificate checks run,
`verify_steps()` now compares every deterministic top-level field except
`certificate` with the expected record selected by `step_id`. Certificate
comparison remains in its dedicated validator so its invariant-specific reasons
and failure counter are unchanged.

The parameterized regression verifies that stale `action_target`, `source_hash`,
`planner`, `alignment`, `replay_evidence`, and `counterfactual_targets` each
fail closed as exactly `record_mismatch:<field>`. The fresh fixture CLI still
builds and verifies 12 accepted rows; an isolated stale-action CLI output
reports zero accepted rows and `record_mismatch:action_target`.

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_provenance.py scripts/phase3/cgas_alignment.py scripts/phase3/cgas_certificate_contracts.py scripts/phase3/cgas_certificates.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_provenance.py scripts/phase3/cgas_alignment.py scripts/phase3/cgas_certificate_contracts.py scripts/phase3/cgas_certificates.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
```

Receipts, including the RED regression and fresh CLI probes, are retained at
`.omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-4/`.
