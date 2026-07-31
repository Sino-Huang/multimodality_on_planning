# Phase 3 CGAS Certificate Publication Transaction

## Scope

`planning_cgas_v1` certificate publication now treats `steps/`, `schema/`, and
`steps_manifest.json` as one bounded in-process transaction. It preserves
colocated `source/` and `alignment/` directories by never replacing the output
root.

## Failure Contract

The publisher stages all candidate artifacts under a sibling private directory.
For each owned path it moves the current artifact to one private backup, then
installs the candidate. It retains completed backups until the final manifest
transition succeeds. An `OSError` reverses installed candidate artifacts,
restores exact prior artifacts, removes the private backup, and re-raises the
original failure. The outer build cleanup removes the candidate tree.

The regression suite injects failures at all three first-publication candidate
replacements and all six update backup/candidate replacements. Every failed
build preserves an exact byte snapshot and leaves neither candidate nor backup
paths. Successful update publication replaces all three owned artifacts while
retaining test `source/` and `alignment/` companions.

## Commands

```bash
source ~/cd_vlaplan && pytest -q tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_certificates_publication.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_provenance.py scripts/phase3/cgas_alignment.py scripts/phase3/cgas_certificate_contracts.py scripts/phase3/cgas_certificate_publication.py scripts/phase3/cgas_certificates.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_alignment.py tests/phase3/test_cgas_certificates.py tests/phase3/test_cgas_certificates_publication.py tests/phase3/test_cgas_counterfactuals.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_certificate_publication.py scripts/phase3/cgas_certificates.py tests/phase3/test_cgas_certificates_publication.py
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --source-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/planning_cgas_v1 --alignment-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/alignment --output-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-6/fresh-steps
source ~/cd_vlaplan && python -m scripts.phase3.cgas_certificates --verify --source-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/planning_cgas_v1 --alignment-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/fixture/alignment --output-root .omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-6/fresh-steps
git diff --check
```

Results: the focused suite passed `43` tests; basedpyright reported zero errors,
warnings, and notes; compileall and diff checks succeeded. Fresh build and
verification each accept 12 rows with zero failure counters. Evidence is in
`.omo/evidence/task-4-cgas-dataloader-and-experiment-support/remediation-6/`.
