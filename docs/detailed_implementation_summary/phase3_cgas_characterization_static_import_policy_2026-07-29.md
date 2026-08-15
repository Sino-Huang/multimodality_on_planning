# Phase 3 CGAS Characterization Static Import Policy

## Scope

The immutable characterization run contract resolves repository-local imports from AST only. It does not execute, evaluate, or compile analyzed product source.

## Policy

- Reject direct or aliased `exec`, `eval`, `compile`, dynamic import functions, import-sensitive `getattr`, `vars`, `globals`, and `locals` access. Canonicalize Python's implicit `__builtins__` binding to `builtins` before alias propagation, closing direct and assignment-chain reflection paths to `__import__` and dynamic-code functions.
- Reject reflected access to `importlib` import functions, `sys.path`, `os.environ`, and site path injection helpers with stable typed reasons.
- Permit literal reflection unrelated to import resolution, such as platform capability constants.
- Keep standard-library and site-package modules out of the closure; bind only sorted repository-relative source files.

## Verification

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests/phase3/test_cgas_characterization_contract.py tests/phase3/test_cgas_characterization_types.py tests/phase3/test_cgas_serialization.py tests/phase3/test_cgas_partition_characterization.py tests/phase3/test_cgas_planner_performance.py tests/phase3/test_cgas_provenance.py tests/phase3/test_cgas_provenance_adversarial.py tests/phase3/test_cgas_certificates.py
source ~/cd_vlaplan && basedpyright scripts/phase3/cgas_characterization_contract.py scripts/phase3/cgas_characterization_imports.py scripts/phase3/cgas_characterization_import_policy.py tests/phase3/test_cgas_characterization_contract.py
source ~/cd_vlaplan && python -m compileall -q scripts/phase3/cgas_characterization_contract.py scripts/phase3/cgas_characterization_imports.py scripts/phase3/cgas_characterization_import_policy.py tests/phase3/test_cgas_characterization_contract.py
```
