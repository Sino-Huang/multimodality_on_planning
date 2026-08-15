# Phase 3 CGAS Characterization Lifecycle CLI

## Contract

`python -m scripts.phase3.cgas_partition_characterization` exposes `fresh`, `shard`, `resume`, `finalize`, and `verify --target work|final`. Final, work, lock, and private paths are direct children of `<repository>/tmp/.cgas-characterization`; legacy direct-`tmp` roots reject without migration or adoption.

`fresh` initializes only work and calls no characterizer. `resume` validates then fills all missing rows. Progress goes to stderr as flushed canonical JSONL only after the checkpoint has been durably published; stdout carries one canonical terminal report. The supported owner-review profile is one blocking writer with `shard_count=1`.

`finalize` rejects any existing/dangling/special final entry, requires valid work with 481 checkpoints, then delegates only private three-file candidate assembly and atomic `regular_bundle_linkat_v1` publication. It neither computes rows directly nor adopts/replaces a final. `verify` is read-only; its final target is the bundle file and it verifies in memory without extraction.

The final bundle SHA-256 identifies contract-scoped provenance: it is stable across repeat and resumed histories only when the run-contract bytes and fingerprint are identical. The bundle SHA is therefore contract-scoped, including the checkpoint publication policy and fixed `shard_count=1` profile.

## Owner-Approved Production Commands

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m scripts.phase3.cgas_partition_characterization fresh --repository-root . --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --bundle-name cgas-characterization-481.cgas --private-root tmp/.cgas-characterization/private --shard-count 1
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m scripts.phase3.cgas_partition_characterization resume --repository-root . --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --bundle-name cgas-characterization-481.cgas --private-root tmp/.cgas-characterization/private --shard-count 1
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m scripts.phase3.cgas_partition_characterization verify --repository-root . --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --bundle-name cgas-characterization-481.cgas --private-root tmp/.cgas-characterization/private --target work
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m scripts.phase3.cgas_partition_characterization finalize --repository-root . --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --bundle-name cgas-characterization-481.cgas --private-root tmp/.cgas-characterization/private
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m scripts.phase3.cgas_partition_characterization verify --repository-root . --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --bundle-name cgas-characterization-481.cgas --private-root tmp/.cgas-characterization/private --target final
```

The retained synthetic 481-checkpoint fill measured 13.25 minutes. Plan 12-16 minutes for real owner review, plus finalize and final verification. The shared `tmp` parent must be current-owner, real, and not group/other writable; `fresh` descriptor-creates and pins the exact mode-0700 child, while read-only verify never creates it.

## Evidence

The new CLI tests cover synthetic 481 fresh initialization, shard dispatch, collision rejection, a real synthetic 481 finalization plus final bundle verification, read-only work/final targets, unsafe names, symlinked lifecycle paths, canonical report/progress shape, and nonzero invalid verification. The required runner/assembly/publication/verifier/checkpoint/contract/bundle/scientific suite passed twice with `177 passed` each time. The repository-local synthetic CLI QA passed `15` tests. Ruff is unavailable in `ada_vla`; Basedpyright, LSP, compileall, and `git diff --check` passed. No full real 481 production lifecycle or final publication was run.

The broad `tests/phase3` collection remains blocked by the known 19 unrelated pre-existing collection errors and was not repaired. A separate repository-local `--basetemp tmp/...` run of the broader checkpoint suite also has 20 fixture-permission failures because those tests assume a mode-0700 pytest base while pytest creates the supplied base mode-0755; the isolated repository-local CLI QA is retained under `tmp/cgas-characterization-task9-cli-qa/`.
