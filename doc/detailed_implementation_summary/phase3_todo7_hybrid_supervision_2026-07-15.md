# Phase 3 Todo 7: Strict Hybrid Supervision

Full and step JSONL records now use separate strict schemas. Each record carries a `supervision_mode`, relative image/VFG/derived-PDDL paths, target data, and exact pair, event, state, trace, and render provenance. Record construction validates this boundary before JSONL is written; output reload validation rejects missing or extra nested fields, duplicate record IDs, split leakage, non-relative paths, and unreconciled counts.

`--mode production` is the default and rejects `--render-limit`. `--mode bounded-smoke --render-limit N` writes `diagnostics/hybrid_output_manifest.json` with `partial: true`, selected pair/state IDs, and the limit. Production output writes `partial: false` and sets `production_complete` only when every emitted pair has complete contiguous step-zero coverage. Missing step zero remains a controlled skip and emits no full record.

Verification commands:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py -q
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright scripts/phase3/planimation_pairing.py scripts/phase3/generate_planimation_vlm.py scripts/phase3/io_utils.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/planimation_pairing.py scripts/phase3/generate_planimation_vlm.py scripts/phase3/io_utils.py tests/phase3/test_planimation_pairing.py
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/phase3/generate_planimation_vlm.py --output-root tmp/phase3_task7_production_reject --render-limit 1
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3/test_planimation_pairing.py::test_generator_bounded_smoke_cli_writes_partial_manifest -q
```

The tests use temporary fixture roots only. The bounded CLI fixture deliberately targets an unreachable loopback renderer, proving output-mode semantics without generating corpus artifacts or relying on a live rendering service. Evidence is retained in `.omo/evidence/phase3-task-7-hybrid-supervision.json`.

## Schema Correction

The initial strict schema emitted `additionalProperties: false` at the root without declaring every otherwise valid root field. The corrected full and step schemas now declare `record_id`, `split`, `domain`, `instance_id`, `planner`, `planner_approximation`, and all other valid root fields, with `step_index` declared only for step records. The root and every existing nested closed-object boundary remain strict.

The activated project environment has no `jsonschema`, `fastjsonschema`, `jsonschema-rs`, Pydantic, or JSON Schema CLI. The regression therefore evaluates the persisted Draft 2020-12 documents against emitted JSON using the exact standard object-schema keywords used by these schemas: `const`, `type`, `required`, `properties`, and `additionalProperties`. It proves valid full and step records pass and omitted or unexpected root and nested fields fail. The schema regression passed in `0.27s`; the pairing suite passed `32` tests in `1.50s`, basedpyright reported zero diagnostics, and compilation exited zero.
