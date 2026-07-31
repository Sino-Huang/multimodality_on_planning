# CGAS Characterization Lifecycle CLI

Date: 2026-07-29

- `python -m scripts.phase3.cgas_partition_characterization` is the lifecycle facade for `fresh`, `shard`, `resume`, `finalize`, and `verify --target work|final`.
- Each command accepts one NFC-stable safe `--bundle-name`; it derives `<repository>/tmp/.cgas-characterization/<bundle-name>` and its `.work` sibling. Legacy direct-`tmp` roots reject without migration or adoption.
- `fresh` delegates to the runner with zero characterizer calls. `shard` and `resume` retain the runner's canonical missing-row selection. Post-publication stderr progress is canonical flushed JSONL with only `phase`, `index`, `instance_id`, `shard_index`, `shard_count`, `completed`, `total`, and `status`.
- `finalize` rejects existing final entries, requires a valid 481-checkpoint work result, then invokes only private candidate assembly and the no-replace `regular_bundle_linkat_v1` publisher. `verify` is read-only; final verification consumes the direct bundle without extraction.

## Verification

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 pytest -q --basetemp "tmp/cgas-characterization-cli-qa" tests/phase3/test_cgas_characterization_cli.py tests/phase3/test_cgas_characterization_assembly.py tests/phase3/test_cgas_characterization_final_publication.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_cli.py scripts/phase3/cgas_characterization_runner.py scripts/phase3/cgas_partition_characterization.py tests/phase3/test_cgas_characterization_cli.py tests/phase3/test_cgas_characterization_runner_resume.py
```

Repository-local synthetic 481 QA passed. No accepted-manifest lifecycle or production final bundle was run.
