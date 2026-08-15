# Phase 1 - Planimation All-Domain Validation Summary

## Phase Scope

This Phase 1 closeout expands the earlier five-domain smoke test into the full current actionable official Planimation sample-domain set that is materialized in the upstream `AnimationProfiles` tree.

The goal of this phase was limited to:

- collecting the official sample PDDL domain/problem/animation-profile assets into this repo,
- validating that the existing Phase 1 pipeline can exercise all supported sample-domain families,
- saving reproducible commands and result locations for future work.

This phase does **not** add planner research logic, StarVLA training integration, or any broader claim about arbitrary external PDDL domains.

---

## Final Upstream Source Used

- Upstream repository: `https://github.com/planimation/documentation/tree/master/AnimationProfiles`
- Local audit clone used for the all-domain sweep: `/tmp/opencode/planimation-documentation`
- Audited upstream commit: `09e8c8d3a08049986a7d4f698f0c1cac2d97044f`

The repo-owned source of truth for the collected actionable set is:

- `data/pddl_instances/manifest.json`
- `data/pddl_instances/README.md`

---

## Actionable Official Domain Set Collected in This Repo

The final manifest contains **23** actionable official sample-domain families:

- `15puzzle`
- `block3op`
- `blocksworld`
- `depot`
- `driverlog`
- `elevators`
- `family_and_fisherman`
- `farmer_crosses_river`
- `ferry`
- `flowfree`
- `freecell`
- `grid`
- `gripper`
- `logistics`
- `snake`
- `storage`
- `switching_soldier`
- `towers_of_hanoi`
- `visitall`
- `bloxorz`
- `lights_out`
- `sokoban`
- `traffic_rush`

The manifest also explicitly excludes six README-only legacy references that are not materialized as complete usable triples in the current upstream tree:

- `zenotravel`
- `floortile`
- `hiking`
- `nurikabe`
- `peg`
- `tpp`

---

## Repo Changes That Support the All-Domain Sweep

### Data corpus

- `data/pddl_instances/manifest.json` now defines the exact 23-domain actionable set.
- `data/pddl_instances/README.md` documents the included set, the excluded legacy references, and the core reproduction commands.

### Validation and execution code

- `scripts/planimation_phase1.py` remains the Phase 1 sync/render/verify entrypoint.
- PNG generation continues to use the local VFG-to-PNG fallback renderer when hosted raster export is unavailable.

### Tests

- `tests/test_planimation_phase1.py` now asserts the exact current actionable set.
- Final verification result for that file:

```text
8 passed
```

---

## Environment Commands Used

Per repo instruction, Planimation asset collection and image-generation commands were run with:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && <command>
```

Environment creation command used for this phase:

```bash
source ~/cd_vlaplan && uv venv .venv --python 3.10
```

Packages used for the Phase 1 Planimation workflow:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && uv pip install requests pytest pillow
```

---

## Commands Needed to Reproduce the Final Validation

### 1. Sync the collected official assets

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py sync-assets --manifest data/pddl_instances/manifest.json
```

### 2. Run the Phase 1 test file

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest tests/test_planimation_phase1.py -q
```

### 3. Hosted service preflight

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py render --manifest data/pddl_instances/manifest.json --output-dir outputs/phase1_planimation_all_domains_preflight --base-url https://planimation.planning.domains --preflight-only
```

### 4. Full 23-domain VFG attempt

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py render --manifest data/pddl_instances/manifest.json --output-dir outputs/phase1_planimation_vfg_all_domains --base-url https://planimation.planning.domains --format vfg --max-per-domain 1 --min-successes 23 --sleep-seconds 1.0 --timeout 90
```

### 5. Isolated `15puzzle` VFG retry for the transient hosted-service failure

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py render --manifest data/pddl_instances/manifest.json --output-dir outputs/phase1_planimation_vfg_15puzzle_retry --base-url https://planimation.planning.domains --format vfg --domains 15puzzle --max-per-domain 1 --min-successes 1 --sleep-seconds 0.0 --timeout 90
```

### 6. PNG generation for the 22 supported domains excluding `15puzzle`

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py render --manifest data/pddl_instances/manifest.json --output-dir outputs/phase1_planimation_png_supported_minus_15puzzle --base-url https://planimation.planning.domains --format png --domains block3op blocksworld depot driverlog elevators family_and_fisherman farmer_crosses_river ferry flowfree freecell grid gripper logistics snake storage switching_soldier towers_of_hanoi visitall bloxorz lights_out sokoban traffic_rush --max-per-domain 1 --min-successes 22 --sleep-seconds 1.0 --timeout 90
```

### 7. Isolated `15puzzle` PNG retry

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py render --manifest data/pddl_instances/manifest.json --output-dir outputs/phase1_planimation_png_15puzzle_retry --base-url https://planimation.planning.domains --format png --domains 15puzzle --max-per-domain 1 --min-successes 1 --sleep-seconds 0.0 --timeout 90
```

### 8. Verify the final output directories

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py verify-output --output-dir outputs/phase1_planimation_png_supported_minus_15puzzle
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py verify-output --output-dir outputs/phase1_planimation_png_15puzzle_retry
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py verify-output --output-dir outputs/phase1_planimation_vfg_all_domains
```

```bash
source ~/cd_vlaplan && source .venv/bin/activate && python scripts/planimation_phase1.py verify-output --output-dir outputs/phase1_planimation_vfg_15puzzle_retry
```

---

## Final Verified Results

### Hosted preflight

From `outputs/phase1_planimation_all_domains_preflight/summary.json`:

- root URL: `https://planimation.planning.domains`
- reachable: `true`
- status code: `200`

### Tests

From the final test run:

```text
8 passed in 0.18s
```

### VFG generation

From `outputs/phase1_planimation_vfg_all_domains/summary.json`:

- selected entries: `23`
- VFG files: `23`
- failure count: `1`
- transient batch failure: `15puzzle`

The failing batch item was recovered by a separate isolated retry.

From `outputs/phase1_planimation_vfg_15puzzle_retry/summary.json`:

- selected entries: `1`
- success count: `1`
- VFG files: `1`
- status for `15puzzle/15-puzzle_problem1`: `success`

### PNG generation

From `outputs/phase1_planimation_png_supported_minus_15puzzle/summary.json`:

- selected entries: `22`
- success count: `22`
- failure count: `0`
- PNG files: `86`
- result files: `22`

From `outputs/phase1_planimation_png_15puzzle_retry/summary.json`:

- selected entries: `1`
- success count: `1`
- failure count: `0`
- PNG files: `4`

### Final verification counts

From `python scripts/planimation_phase1.py verify-output ...` on the final output directories:

- `outputs/phase1_planimation_png_supported_minus_15puzzle`: `png_files=86`, `result_files=22`, `vfg_files=0`
- `outputs/phase1_planimation_png_15puzzle_retry`: `png_files=4`, `result_files=1`, `vfg_files=0`
- `outputs/phase1_planimation_vfg_all_domains`: `png_files=0`, `result_files=24`, `vfg_files=23`
- `outputs/phase1_planimation_vfg_15puzzle_retry`: `png_files=0`, `result_files=1`, `vfg_files=1`

### Combined Phase 1 conclusion

Taken together, the repo now contains successful execution evidence for **all 23 actionable official Planimation sample-domain families**:

- 22 domains succeeded in the full VFG batch,
- `15puzzle` succeeded in the isolated VFG retry,
- 22 domains succeeded in the split PNG batch,
- `15puzzle` succeeded in the isolated PNG retry.

That is the precise basis for claiming that the full current actionable official sample-domain set was collected and exercised successfully in this repo.

---

## Important Caveats That Must Remain Explicit

### 1. This is a curated official sample-set claim, not an arbitrary-domain claim

The validated scope is the 23-domain actionable set represented in `data/pddl_instances/manifest.json`, derived from the upstream `AnimationProfiles` tree at the audited commit above.

### 2. `lights_out` was validated with `problem1`

The earlier larger `lights_out/problem5x5` representative hit a hosted planner timeout. The final collected representative is `lights_out/problem1`, which succeeds and is the case counted in the final manifest and all-domain evidence.

### 3. PNG success in this repo depends on local VFG-to-PNG rendering

The live hosted upload endpoint that worked in this phase was:

```text
https://planimation.planning.domains/upload/pddl
```

The hosted raster export endpoint:

```text
https://planimation.planning.domains/downloadVisualisation
```

returned HTTP `405` for scripted client use in this environment.

Therefore, the Phase 1 PNG claim is:

> hosted PDDL/domain/problem/animation-profile submission produced VFG traces successfully, and this repo rendered those VFG traces locally into PNG frames.

This phase does **not** prove hosted raster export works for this scripted client path.

### 4. The final proof is a combined evidence set, not one pristine 23/23 batch summary

`15puzzle` failed transiently in the first full VFG batch and then succeeded in isolation. The final all-domain success claim therefore depends on the combined evidence from four summary artifacts rather than a single clean one-shot 23/23 batch output.

### 5. `outputs/phase1_planimation_vfg_all_domains` contains one stale extra `result.json`

`verify-output` reports `result_files=24` but `vfg_files=23` in `outputs/phase1_planimation_vfg_all_domains`. This is explained by a stale `lights_out/problem5x5/result.json` from the earlier failed representative attempt, while the selected final representative is `lights_out/problem1`.

---

## Output and Evidence Locations

### Data and tests

- `data/pddl_instances/manifest.json`
- `data/pddl_instances/README.md`
- `tests/test_planimation_phase1.py`

### Scripts

- `scripts/planimation_phase1.py`

### Final summary artifacts

- `outputs/phase1_planimation_all_domains_preflight/summary.json`
- `outputs/phase1_planimation_vfg_all_domains/summary.json`
- `outputs/phase1_planimation_vfg_15puzzle_retry/summary.json`
- `outputs/phase1_planimation_png_supported_minus_15puzzle/summary.json`
- `outputs/phase1_planimation_png_15puzzle_retry/summary.json`

### Earlier probe artifact relevant to the `lights_out` caveat

- `outputs/phase1_planimation_lights_out_probe/summary.json`

---

## Oracle Final Review Summary

Oracle reviewed the combined final evidence and concluded that the claim is supportable if it stays narrow and explicit.

Main conclusion:

> The combined evidence is sufficient to support the Phase 1 claim that all 23 currently actionable official Planimation sample-domain families were collected and successfully exercised in this repo.

Oracle’s required caveats were:

1. keep the claim limited to the curated 23-domain actionable set,
2. keep `lights_out/problem1` explicit as the validated representative,
3. keep the hosted `405` / local PNG-rendering caveat explicit,
4. note that the final success proof is combined from separate summary artifacts rather than a single perfect all-domain batch.

Oracle did **not** identify any remaining technical blocker to calling Phase 1 complete.

---

## Final Phase 1 Outcome

Phase 1 is complete for the all-domain validation objective.

The repo now contains:

- a curated official 23-domain Planimation Phase 1 corpus,
- tests that lock the exact actionable domain set,
- successful hosted VFG generation evidence across the full curated set,
- successful local PNG rendering evidence across the full curated set,
- and a documented reproduction path for syncing assets, generating traces, generating images, and verifying outputs.

Future work can build on this saved corpus and these output directories without needing to rediscover the current Planimation upload contract or the current official sample-domain coverage.
