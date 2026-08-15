## Phase 2 - Curriculum PDDL Generation Summary

### Scope

This phase implements and verifies the `src.data_collect` curriculum PDDL generation pipeline for the 15 selected Planimation-compatible domains.

The phase covers:

- config-driven curriculum generation under `src/data_collect/`,
- per-domain generator adapters for the selected 15 domains,
- rendering-gated acceptance using the existing Planimation Phase 1 helpers,
- deterministic metadata, rejection logging, hashing, and resumability,
- smoke/full-run command documentation and artifact locations.

This phase does **not** claim VLA training results. It is limited to dataset generation and verification.

---

### Environment Commands

Per repo instruction, all commands for this phase use:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && <command>
```

The `.venv` needed the Planimation runtime packages for the real rendering path:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && uv pip install requests pillow pytest
```

---

### What Was Implemented

- `src/data_collect/__main__.py`, `cli.py` - package entrypoint plus `generate` and `inspect-tools` commands.
- `src/data_collect/config.py` + `src/data_collect/configs/curriculum_15_domains.yaml` - 15-domain curriculum contract, split/bucket quotas, render-profile mapping, seed range, timeouts, and candidate multiplier.
- `src/data_collect/configs/generator_dependencies.yaml` - dependency groups consumed by `inspect-tools`.
- `src/data_collect/adapters/**` - adapter contract plus registry for `15puzzle`, `blocksworld`, `depot`, `driverlog`, `elevators`, `ferry`, `freecell`, `grid`, `gripper`, `logistics`, `snake`, `sokoban`, `storage`, `towers_of_hanoi`, and `visitall`.
- `src/data_collect/rendering.py` - render preflight, fake renderer test path, Planimation-backed renderer, render artifact gate.
- `src/data_collect/difficulty.py` + `selection.py` - measured difficulty assignment and deterministic stratified selection.
- `src/data_collect/metadata.py` + `hashing.py` - result schema, rejection schema, normalized PDDL hashing, duplicate detection, and resumability helpers.
- `src/data_collect/generate.py` - orchestration, staging, dedupe, selection, final manifest writing, and summary generation.
- `tests/data_collect/**` - unit/integration-style tests for config, adapters, rendering, metadata, selection, CLI, and orchestrator behavior.

---

### Built Generator Artifacts

The compiled curriculum generators were built before the real smoke/full execution path:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && for dir in modules/pddl-generators/npuzzle modules/pddl-generators/blocksworld modules/pddl-generators/depots modules/pddl-generators/driverlog modules/pddl-generators/ferry modules/pddl-generators/freecell modules/pddl-generators/gripper modules/pddl-generators/logistics modules/pddl-generators/hanoi modules/pddl-generators/visitall; do make -C "$dir"; done && make -C modules/pddl-generators/sokoban random && make -C modules/pddl-generators/storage generator
```

After the build, `inspect-tools` reported all 15 selected adapters configured and ready; the only remaining structured issue was the missing optional `validate` binary on `PATH`.

---

### Verification Commands and Observed Results

#### 1. Test suite

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m pytest tests/data_collect -q
```

Observed result:

```text
64 passed in 2.89s
```

Evidence: `.sisyphus/evidence/task-15-tests.txt`

#### 2. Tool and adapter readiness

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect inspect-tools --config src/data_collect/configs/curriculum_15_domains.yaml --json
```

Observed result summary:

```text
ready True
issues ['validator command missing: validate']
adapter_count 15
```

Evidence: `.sisyphus/evidence/task-15-inspect-tools.json`

#### 3. Smoke generation path

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect generate --config src/data_collect/configs/curriculum_15_domains.yaml --output /tmp/curriculum_pddl_smoke --domains blocksworld,gripper --splits train --quota easy=1,medium=1,hard=1 --seed 123 --max-attempts-per-bucket 10 --require-rendering
```

Observed result:

```text
Generated 6 accepted / 36 rejected to /tmp/curriculum_pddl_smoke
```

Smoke summary check:

```json
{
  "accepted_total": 6,
  "domains_completed": 2,
  "render_failed_accepted": 0,
  "duplicate_accepted_problem_hashes": 0,
  "candidate_multiplier": 2
}
```

Evidence:

- `.sisyphus/evidence/task-11-smoke.txt`
- `.sisyphus/evidence/task-11-smoke-summary.txt`

#### 4. Full generation and merged dataset path

The accepted final dataset is complete at `data/curriculum_pddl`. It was assembled from finalized per-domain shards with:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m src.data_collect merge-shards --shards-root data/curriculum_pddl_shards --output data/curriculum_pddl --force --json
```

The core command inside that environment is:

```bash
python -m src.data_collect merge-shards --shards-root data/curriculum_pddl_shards --output data/curriculum_pddl --force --json
```

Task 13 recovery history, kept concise: `storage`, `sokoban`, and `freecell` required local repair/replacement work before the final shards were merged. The accepted merged artifacts are now under `data/curriculum_pddl`.

Observed merged summary from `data/curriculum_pddl/summary.json`:

```text
accepted_total=3600
domains_completed=15
accepted_by_split={"train": 3000, "dev": 300, "test": 300}
render_failed_accepted=0
duplicate_accepted_problem_hashes=0
```

Evidence:

- `.sisyphus/evidence/task-13-merge-shards.json`
- `.sisyphus/evidence/task-13-summary-check.txt`
- `.sisyphus/evidence/task-15-merged-dataset.txt`

#### 5. Benchmark-slice reader smoke path

The Task 14 example package reads the merged dataset without modifying artifacts. The smoke command is:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python -m examples.planning_benchmark_slice --dataset data/curriculum_pddl --domain blocksworld --split dev --index 0 --json
```

The core command inside that environment is:

```bash
python -m examples.planning_benchmark_slice --dataset data/curriculum_pddl --domain blocksworld --split dev --index 0 --json
```

Expected output includes a `blocksworld` dev instance, PDDL text/paths, render frame paths, `render_trace` as a filesystem path string, and `render_trace_payload` as parsed trace JSON. This is a data-access smoke check only; it does not claim benchmark evaluation results.

Evidence:

- `.sisyphus/evidence/task-14-example-contract.txt`
- `.sisyphus/evidence/task-14-example-blocksworld.json`
- `.sisyphus/evidence/task-15-example-smoke.json`

---

### Output Layout

Accepted outputs are written under:

```text
data/curriculum_pddl/<domain_id>/<split>/<bucket>/<instance_id>/
```

Expected per-instance artifacts:

- `domain.pddl`
- `problem.pddl`
- `result.json`
- `render/trace.vfg.json`
- `render/frames/*.png`

Top-level dataset artifacts:

- `data/curriculum_pddl/accepted_manifest.jsonl`
- `data/curriculum_pddl/rejections.jsonl`
- `data/curriculum_pddl/summary.json`

---

### Metadata and Acceptance Contract

Accepted instances require all of the following:

- `render_status == "success"`
- at least one non-empty `trace.vfg.json`
- at least one PNG frame under `render/frames/`
- result metadata written for the accepted instance
- normalized PDDL hash not duplicated across accepted train/dev/test splits

The pipeline also records:

- `difficulty_target`
- `difficulty_measured`
- generator command/cwd/stdout/stderr paths
- render artifact paths
- rejection reasons for all rejected or unselected candidates

---

### Known Caveats

- The optional `validate` binary is still absent from `PATH`; `inspect-tools` reports this as a structured issue.
- Generated dataset artifacts under `data/curriculum_pddl/**` and `data/curriculum_pddl_shards/**` remain local workspace outputs and should not be committed unless the user explicitly requests it.

---

### Artifact Policy

- Do **not** commit `data/curriculum_pddl/**` generated outputs unless explicitly requested.
- Keep verification evidence under `.sisyphus/evidence/`.
- Task 15 closeout evidence is stored under `.sisyphus/evidence/task-15-*`, including tests, tool inspection, merged-count verification, example smoke output, and documentation closeout check.
