
## Deferred Todo 8 Concern

- `verify_planimation_vlm.py` currently reports zero full/step VLM records when those files are absent from a manifest-only output. This is a later Todo 8 release-verification concern and was intentionally not changed in Todo 1.

## Todo 5 Scope Observation

- The known broad `tests/phase3` generator timeout remains independent of this traversal-only change. Todo 5 used focused fast regressions and module CLIs; it did not run or alter corpus generation.

## Todo 7 Stable Interface

- Todo 7 introduces `diagnostics/hybrid_output_manifest.json` and `validate_vlm_output` as stable inputs for Todo 8. Release-mode requirements, missing-artifact policy, and broader corpus promotion remain intentionally deferred to Todo 8 and Todo 9.

## Todo 7 Schema Validator Constraint

- The activated environment contains no third-party JSON Schema validator or CLI. The regression uses a dependency-free evaluator for the exact Draft 2020-12 object-schema keywords emitted by Todo 7 and validates the persisted schemas against emitted JSON; no dependency was added. Atlas retains independent verification responsibility.

## Todo 8 Resolved

- Required release JSONL paths are checked before parsing because `read_jsonl()` intentionally treats missing files as empty lists for generator workflows. Release now distinguishes absent artifacts from valid zero-count dev/test split files through manifest reconciliation.

## Todo 9 Promotion Status

- Frozen full selection remains blocked. The first active source-root changed-canary cannot start until strict v1 provenance exists; Todo 9 intentionally does not backfill legacy rows or bypass trace-contract exclusion.

## Todo 10 Final Documentation Boundary

- Documentation is complete for the implemented hybrid format and temporary fixture evidence. Corpus promotion is not complete. Final verification must preserve the missing strict-v1 active-source blocker and the independent broad generator timeout rather than treating the fixture receipt as a corpus release.

## F1 Production Boundary

- The output/source overlap guard covers equality and output-under-source paths at the manifest write boundary. It intentionally does not reinterpret active legacy traces or create a compatibility path for them.

## F3 Final Manual QA Refresh (2026-07-16T01:55:10Z)

- Active-source promotion remains unavailable, not ambiguous: all 688 active pairs are excluded before rendering because strict `trace_contract_version` provenance is absent. The fixture approval cannot be interpreted as an active-corpus approval.
