# Phase 3 CGAS Steps Manifest Binding

## Change

`planning_cgas_v1` step verification now treats `steps_manifest.json` as a required persisted trust boundary. Build and verification share one deterministic constructor for the schema version, accepted-source digest, accepted-alignment digest, and canonical steps digest. Missing, malformed, non-object, or stale manifests fail closed without suppressing row-level certificate, schema, record, or counterfactual diagnostics.

## Verification

Run the focused regression suite:

```bash
source ~/cd_vlaplan && python -m pytest -q tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_counterfactuals.py
```

Build and verify the retained bounded fixture:

```bash
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --source-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/planning_cgas_v1 --alignment-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/alignment --output-root /tmp/cgas-steps
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --verify --source-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/planning_cgas_v1 --alignment-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/alignment --output-root /tmp/cgas-steps
```

The valid fixture reports `accepted_rows=12`, an empty rejection list, and zero verification counters. Mutating only `/tmp/cgas-steps/steps_manifest.json` `steps_digest` makes `--verify` exit nonzero with `steps_manifest_mismatch`.

## Evidence

The red-to-green test receipt, static checks, fresh build/verify reports, stale-manifest CLI rejection, cleanup inventory, and DoneClaim are under `.omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-5/`.
