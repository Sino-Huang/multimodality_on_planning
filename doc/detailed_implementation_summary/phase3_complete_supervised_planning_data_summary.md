# Phase 3 Complete Supervised Planning Data Summary

## Scope

This phase implements the complete multi-domain supervised planning JSONL corpus rooted at `data/phase3_supervised_planning`. The authoritative inclusion source is `data/curriculum_pddl/accepted_manifest.jsonl`; source files under `data/curriculum_pddl` are read only and are not mutated.

`outputs/planning_artifacts/**` is smoke/prototype output from the earlier Blocksworld-only planning slice, not the final Phase 3 supervised corpus. Phase 4 training is not done, and this phase does not implement StarVLA/LeRobot tensor conversion.

## Generated status

Latest generation command emitted:

- Accepted instances accounted: `3600`
- Planner attempt records: `14400`
- Supervised JSONL examples emitted: `411`
- Split examples: `train=363`, `dev=28`, `test=20`
- Fidelity summary: `success_full_trace=411`

Planner status counts from `data/phase3_supervised_planning/summary.json`:

- BFS: `success_full_trace=411`, `skipped_resource_limit=2709`, `skipped_unsupported_pddl=480`
- FF: `skipped_planner_unavailable=3120`, `skipped_unsupported_pddl=480`
- IW: `skipped_planner_unavailable=3120`, `skipped_unsupported_pddl=480`
- Graphplan: `skipped_planner_unavailable=3120`, `skipped_unsupported_pddl=480`

Not all planner attempts succeed. Missing FF/IW/Graphplan executables and unsupported PDDL fragments are represented as diagnostics, while supervised examples are emitted only for replay-validated successful plans.

## Regeneration command

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.generate_supervised_data --input-root data/curriculum_pddl --output-root data/phase3_supervised_planning --planners gbfs ff iw graphplan --json
```

Expected signal: exits `0`, writes `generation_manifest.json`, `summary.json`, split JSONL files, schemas, diagnostics, and reports under `data/phase3_supervised_planning`.

## Verification commands

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_manifest_coverage --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --diagnostics data/phase3_supervised_planning/diagnostics/instance_accounting.jsonl
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_planner_attempts --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --planner-attempts data/phase3_supervised_planning/diagnostics/planner_attempts.jsonl --planners gbfs ff iw graphplan
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.validate_jsonl_schema --schema data/phase3_supervised_planning/schema/supervised_planning_example.schema.json --jsonl data/phase3_supervised_planning/train.jsonl --jsonl data/phase3_supervised_planning/dev.jsonl --jsonl data/phase3_supervised_planning/test.jsonl
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.validate_jsonl_schema --schema data/phase3_supervised_planning/schema/planner_attempt.schema.json --jsonl data/phase3_supervised_planning/diagnostics/planner_attempts.jsonl
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.validate_jsonl_schema --schema data/phase3_supervised_planning/schema/instance_accounting.schema.json --jsonl data/phase3_supervised_planning/diagnostics/instance_accounting.jsonl
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_replay_validated_examples --dataset-root data/phase3_supervised_planning
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_fidelity_labels --dataset-root data/phase3_supervised_planning
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_splits --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --dataset-root data/phase3_supervised_planning
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_domain_coverage --accepted-manifest data/curriculum_pddl/accepted_manifest.jsonl --dataset-root data/phase3_supervised_planning --domains 15puzzle blocksworld depot driverlog elevators ferry freecell grid gripper logistics snake sokoban storage towers_of_hanoi visitall
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_vision_assets --dataset-root data/phase3_supervised_planning
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_no_smoke_sources --dataset-root data/phase3_supervised_planning --forbidden-path outputs/planning_artifacts --forbidden-path examples/planning_benchmark_slice/experts
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m scripts.phase3.verify_determinism --dataset-root data/phase3_supervised_planning --manifest data/phase3_supervised_planning/generation_manifest.json
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/phase3 tests/planning_benchmark tests/data_collect
```

## Status taxonomy and fidelity semantics

Successful GBFS examples are labeled `success_full_trace` only when the local GBFS adapter captures heuristic/frontier/successor trace information and the generic replay validator confirms the plan. Historical generated corpora may still contain BFS-era summaries, but active regeneration uses `gbfs` and rejects the old `bfs` planner label. External planner final-plan-only successes, when configured and valid, are labeled `success_plan_replayed`; they are never labeled as full trace unless true internal traces are implemented and verified.

Current FF/IW/Graphplan attempts are diagnostic-only because planner executables were not configured with `PHASE3_FF_PLANNER`, `PHASE3_IW_PLANNER`, or `PHASE3_GRAPHPLAN_PLANNER`, and the repo-local Fast Downward fallback does not expose FF/IW-style aliases in `modules/downward/fast-downward.py --show-aliases`. Unsupported PDDL and resource-limited cases remain accounted in diagnostics rather than silently skipped.

The JSONL schema verifier reads the generated schema document and also applies the matching Phase 3 Python contract checks for supervised examples, planner attempts, or instance accounting based on the schema title. All three generated schema documents are self-consistent with their corresponding generated rows: `supervised_planning_example.schema.json` validates `train/dev/test.jsonl`, `planner_attempt.schema.json` validates `diagnostics/planner_attempts.jsonl`, and `instance_accounting.schema.json` validates `diagnostics/instance_accounting.jsonl` with `invalid_rows = 0`.
