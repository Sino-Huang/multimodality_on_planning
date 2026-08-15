# Phase 1 - Planimation Multi-Domain Validation Summary

> Superseded for final all-domain closeout by `doc/detailed_implementation_summary/phase1_planimation_all_domains_validation_summary.md`.

This document records the earlier five-domain milestone. The final Phase 1 completion record for the 23-domain actionable official Planimation set is stored in the all-domain summary above.

## Phase Scope

This phase was limited to validating that Planimation can be used in this repo with varying PDDL domains and problem models, collecting reusable PDDL/AP assets, and producing reproducible outputs for later research work.

This phase does **not** implement the research planner, dataloaders, or StarVLA training integration yet.

---

## What Was Implemented

### 1. Repo-owned Phase 1 utility

Added `scripts/planimation_phase1.py` with three subcommands:

- `sync-assets`
- `render`
- `verify-output`

The script now does the following:

- syncs curated official Planimation assets into `data/pddl_instances/`,
- validates local domain/problem/AP triples,
- submits PDDL + problem + animation profile text fields to the live hosted Planimation upload endpoint,
- saves returned VFG traces,
- tries hosted raster export first,
- falls back to local PNG frame rendering from the returned VFG when the hosted raster export path fails,
- writes per-instance `result.json` files and top-level `summary.json` files.

### 2. Curated Phase 1 PDDL/AP corpus

Added:

- `data/pddl_instances/manifest.json`
- `data/pddl_instances/README.md`

Synced official Planimation sample assets for five domains:

- Grid
- Logistics
- Towers of Hanoi
- Driverlog
- Freecell

Each entry contains:

- domain PDDL
- problem PDDL
- animation profile PDDL
- provenance URL
- Planimation editor session ID

### 3. Tests

Added `tests/test_planimation_phase1.py`.

Covered behaviors:

- manifest loading
- unique asset download planning
- local domain/problem/AP validation
- endpoint derivation
- entry selection
- PNG archive extraction
- local VFG-to-PNG fallback rendering

---

## Environment Setup Used

Per repo instruction, all Planimation image-collection commands were run with:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && <command>
```

Environment creation command used:

```bash
source ~/cd_vlaplan && uv venv .venv --python 3.10
```

Packages installed for this phase:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && uv pip install requests pytest pillow
```

---

## Important API Finding

The old `modules/api-tools` assumptions do **not** match the currently working hosted upload contract.

### What works

The live hosted endpoint that worked in this phase was:

```text
https://planimation.planning.domains/upload/pddl
```

It expects multipart form fields containing **text content** for:

- `domain`
- `problem`
- `animation`

It returns VFG JSON.

### What did not work from the scripted client

The hosted raster export path:

```text
https://planimation.planning.domains/downloadVisualisation
```

returned HTTP 405 for scripted POST attempts in this environment.

Because of that, Phase 1 PNG success was achieved through a **local Pillow fallback renderer** that renders the Planimation-generated VFG into PNG frames.

This means the Phase 1 claim is:

> Planimation successfully converted curated multi-domain PDDL/domain/problem/AP triples into VFG traces, and those VFG traces were rendered locally into PNG frames in this repo.

This phase does **not** prove that hosted `downloadVisualisation` export works for this scripted client path.

---

## Commands Used

### Sync the curated Planimation corpus

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py sync-assets --manifest data/pddl_instances/manifest.json
```

### Hosted preflight

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py render --manifest data/pddl_instances/manifest.json --output-dir outputs/phase1_planimation_preflight --base-url https://planimation.planning.domains --preflight-only
```

### Single-domain PNG smoke test

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py render --manifest data/pddl_instances/manifest.json --output-dir outputs/phase1_planimation_png_grid --base-url https://planimation.planning.domains --format png --domains grid --max-per-domain 1 --min-successes 1 --sleep-seconds 0.0
```

### Single-domain VFG trace smoke test

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py render --manifest data/pddl_instances/manifest.json --output-dir outputs/phase1_planimation_vfg_grid --base-url https://planimation.planning.domains --format vfg --domains grid --max-per-domain 1 --min-successes 1 --sleep-seconds 0.0
```

### Multi-domain PNG generation

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py render --manifest data/pddl_instances/manifest.json --output-dir outputs/phase1_planimation_png_multidomain --base-url https://planimation.planning.domains --format png --max-per-domain 1 --min-successes 5 --sleep-seconds 1.0
```

### Multi-domain VFG / plan-trace generation

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py render --manifest data/pddl_instances/manifest.json --output-dir outputs/phase1_planimation_vfg_multidomain --base-url https://planimation.planning.domains --format vfg --max-per-domain 1 --min-successes 5 --sleep-seconds 1.0
```

### Output verification

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py verify-output --output-dir outputs/phase1_planimation_png_multidomain
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py verify-output --output-dir outputs/phase1_planimation_vfg_multidomain
```

### Unit tests

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/test_planimation_phase1.py -q
```

---

## Actual Results

### Asset sync

The sync command downloaded 15 files total:

- 5 domain PDDL files
- 5 problem PDDL files
- 5 animation profile PDDL files

All five manifest entries passed local validation.

### Preflight

Hosted root preflight succeeded:

- root URL: `https://planimation.planning.domains`
- HTTP status: `200`

### Unit tests

Final test result:

```text
7 passed
```

### Multi-domain PNG output

From `outputs/phase1_planimation_png_multidomain/summary.json`:

- `success_count: 5`
- `failure_count: 0`
- `png_files: 18`
- `result_files: 5`

Per-domain PNG frame counts:

- Grid: 4 frames
- Logistics: 4 frames
- Towers of Hanoi: 2 frames
- Driverlog: 4 frames
- Freecell: 4 frames

All five successful PNG results used:

- hosted `upload/pddl` for VFG generation
- local fallback renderer for PNG frame materialization

### Multi-domain VFG / plan-trace output

From `outputs/phase1_planimation_vfg_multidomain/summary.json`:

- `success_count: 5`
- `failure_count: 0`
- `vfg_files: 5`
- `result_files: 5`

Saved trace outputs exist for:

- `outputs/phase1_planimation_vfg_multidomain/grid/prob01/trace.vfg.json`
- `outputs/phase1_planimation_vfg_multidomain/logistics/prob01/trace.vfg.json`
- `outputs/phase1_planimation_vfg_multidomain/towers_of_hanoi/pfile1/trace.vfg.json`
- `outputs/phase1_planimation_vfg_multidomain/driverlog/problem01/trace.vfg.json`
- `outputs/phase1_planimation_vfg_multidomain/freecell/probfreecell-10-1/trace.vfg.json`

---

## Files and Output Locations

### Code

- `scripts/planimation_phase1.py`
- `scripts/__init__.py`
- `tests/test_planimation_phase1.py`

### Data

- `data/pddl_instances/manifest.json`
- `data/pddl_instances/README.md`
- `data/pddl_instances/grid/`
- `data/pddl_instances/logistics/`
- `data/pddl_instances/towers_of_hanoi/`
- `data/pddl_instances/driverlog/`
- `data/pddl_instances/freecell/`

### Outputs

- `outputs/phase1_planimation_preflight/summary.json`
- `outputs/phase1_planimation_png_grid/summary.json`
- `outputs/phase1_planimation_vfg_grid/summary.json`
- `outputs/phase1_planimation_png_multidomain/summary.json`
- `outputs/phase1_planimation_vfg_multidomain/summary.json`

### Earlier hosted-export failure evidence

The initial direct hosted export attempts failed before the local fallback was added. That evidence remains in:

- `outputs/phase1_planimation_png/summary.json`
- `outputs/phase1_planimation_vfg/summary.json`

Those earlier summaries record HTTP 405 failures for the attempted hosted export path.

---

## Oracle Review Summary

Oracle reviewed the completed implementation after smoke testing.

Main conclusion:

> The Phase 1 implementation is sound for the intended claim: multi-domain Planimation validation across five curated official domains, with successful hosted PDDL→VFG conversion and local VFG→PNG frame rendering.

Key Oracle caveats that should remain explicit:

1. This phase proves **hosted PDDL→VFG** and **local VFG→PNG**, not hosted raster export.
2. This phase does not prove arbitrary-domain generality beyond the curated five official sample domains.
3. The local Pillow renderer is a smoke-test renderer, not a fidelity-equivalent replacement for the official hosted/image-export path.
4. Asset validation checks file structure and domain naming consistency, but not full AP semantic completeness beyond successful VFG generation.

No immediate Phase 1 redesign was recommended before documenting the implementation.

---

## Phase 1 Outcome

Phase 1 is complete.

The repo now has:

- a reproducible multi-domain Planimation asset corpus,
- a tested sync/render/verify utility,
- successful hosted VFG generation across five varying domains,
- successful local PNG frame generation from those VFG traces,
- and a documented command path for generating both images and plan traces.

The next phase can build on these saved assets and outputs without needing to rediscover the Planimation contract again.
