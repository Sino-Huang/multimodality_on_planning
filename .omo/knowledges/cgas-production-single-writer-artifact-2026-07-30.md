# CGAS Production Single-Writer Artifact

The retained partition-selection input is:

```text
tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas
```

Its immutable companion work root is:

```text
tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas.work
```

Artifact identity:

- SHA-256: `942d7be93ad0eb0ec6580bfe380fb8f09141662140ffc3d3c98e7f09a10ddaf4`
- Regular file, mode `0600`, uid `15306`, gid `10504`, nlink `1`, size `2118813`.
- Run-contract fingerprint: `0856e76571643362abb70551ff9d4e02e2d585f7384fc3ac0adb64df240d893a`.
- Contract population: 481 Blocksworld rows, splits `dev=39`, `test=40`,
  `train=402`; object counts `4=190`, `8=198`, `12=93`.
- Source manifest SHA-256: `9a9817058e36f72468682c8b43a46c04591995bcb8fe28ee37819313f9376217`.
- Final verification: valid, complete, publishable; manifest
  `owner_approved=false`.

Read-only validation commands:

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m scripts.phase3.cgas_partition_characterization verify --repository-root . --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --bundle-name planning_cgas_v1-characterization-481.cgas --private-root tmp/.cgas-characterization/private --target work
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m scripts.phase3.cgas_partition_characterization verify --repository-root . --source-manifest data/curriculum_pddl/accepted_manifest.jsonl --bundle-name planning_cgas_v1-characterization-481.cgas --private-root tmp/.cgas-characterization/private --target final
source ~/cd_vlaplan && sha256sum tmp/.cgas-characterization/planning_cgas_v1-characterization-481.cgas
```

Do not rerun `fresh`, overwrite the final leaf, create approval markers, or
promote this artifact without the separate owner approval process.
