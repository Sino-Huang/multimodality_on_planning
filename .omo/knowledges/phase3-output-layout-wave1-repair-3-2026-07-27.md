# Phase 3 Output-Layout Wave 1 Repair 3

Filesystem publication success must stay descriptor-bound through the final exact-tree, protected-target, and canonical-path identity checks. A pathname-only final check is insufficient because a same-permission writer can replace the namespace entry after publication. Return a held `PublishedStage`, validate through its descriptor, and compare the public pathname identity against that held identity immediately before success.

The same rule applies to idempotent verification of an already-existing view. Open and retain the existing root plus its immediate parent, verify links, repeat the exact-tree scan after the final link check, compare the canonical name to the held identity, and finish with one last descriptor-bound exact-tree scan. First publication needs the same final ordering. Pathname identity alone does not detect newly inserted extra entries.

Failed private stages should remain at their original cryptographically unique private name. Renaming a failed stage creates another namespace transition and another race window without improving the no-deletion guarantee.

Byte limits must constrain each individual read request, not only the accumulated result. Request at most `remaining + 1` bytes so the extra byte detects overflow while preventing an untrusted file implementation from returning an arbitrarily large chunk.

Verification commands:

```bash
source ~/cd_vlaplan && source .venv/bin/activate && pytest -q tests/phase3/test_output_layout_*.py
source ~/cd_vlaplan && source .venv/bin/activate && basedpyright --project .omo/evidence/output-layout/task-1-3-wave1-repair-3/pyrightconfig.json
source ~/cd_vlaplan && source .venv/bin/activate && python -m compileall -q scripts/phase3/output_layout_*.py tests/phase3/test_output_layout_*.py
GIT_MASTER=1 git diff --check
```

Observed result: the post-link and post-pathname races were red before their fixes and green after them; 213 tests passed; Basedpyright reported zero findings across every output-layout source/test; compileall, no-excuse, manual synthetic API QA, and diff-check passed. No real `outputs/` mutation occurred.

Five independent goal, QA, code-quality, security, and context reviews passed. Wave 1 Todos 1-3 are accepted; Todo 4 integration may begin, while real relocation remains blocked.
