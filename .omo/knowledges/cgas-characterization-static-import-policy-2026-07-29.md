# CGAS Characterization Static Import Policy

Date: 2026-07-29

- The characterization run contract intentionally performs AST inspection only. It never evaluates analyzed source code.
- Reachable dynamic code (`exec`, `eval`, `compile`), dynamic import functions, import-sensitive `getattr`/`vars` access, and `globals`/`locals` namespace access fail closed with stable policy reasons. The implicit `__builtins__` binding is canonicalized as `builtins`, including assignment and reflection aliases, so it cannot bypass this policy.
- Static literal reflection remains permitted when it is unrelated to import resolution, such as `getattr(os, "O_NOFOLLOW", 0)`.
- Repository-local source closure excludes standard-library and site-package modules deterministically. Product roots, contract modules, and their local AST dependencies are hashed as sorted POSIX paths.

## Verification

```bash
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests/phase3/test_cgas_characterization_contract.py
source ~/cd_vlaplan && PYTHONDONTWRITEBYTECODE=1 python -c "from pathlib import Path; from scripts.phase3.cgas_characterization_contract import build_characterization_run_contract; contract = build_characterization_run_contract(Path('data/curriculum_pddl/accepted_manifest.jsonl'), Path('.'), shard_count=1); print(contract.fingerprint)"
```
