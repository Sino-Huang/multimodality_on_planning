# Issues

## 2026-06-24 Start Work
- Need verify whether existing tests assume local `data/curriculum_pddl/**`; plan requires fresh-checkout fixtures or clear skips.
- Need avoid modality leakage in Vision-only and Language-only serializers.
- Need keep generated large artifacts uncommitted unless user explicitly requests otherwise.

## 2026-06-24 Task 2 Blocksworld Core
- Empty-goal local curriculum examples still exist for the legacy slice smoke path; Task 2 validation rejects them via explicit validator/fixtures without changing the old smoke test expectations.

## 2026-06-24 Task 3 Zero-Shot Diagnostic
- The non-trivial fixture does not include render artifacts, so vision-bearing prompt packages use empty `render_paths` placeholders rather than generating or requiring images; real VLM/image calls stay outside acceptance.
- `validate_fixture` summaries do not carry `instance_id`; zero-shot package building reloads the fixture payload after validation to preserve deterministic fixture-based package names.

## 2026-06-24 Task 4 Benchmark Loop
- The invalid-action fixture intentionally starts with `stack(a,b)`, which is syntactically valid but illegal in the initial state. This verifies graceful loop failure without relying on malformed action parsing.

## 2026-06-24 Task 5 Unified Expert Trajectory Schema
- While generating invalid evidence, `zsh` rejected a wrapper variable named `status` because it is read-only; reran the wrapper with `rc` and verified the validator itself exited nonzero with `bfs.frontier_before` in the evidence.

## 2026-06-24 Task 7 Fast Forward-Style Expert
- Existing Task 6 CLI test expected `fast_forward` to be unsupported; Task 7 changes that contract, so the negative case now uses `graphplan`, which remains unimplemented until Task 8.

## 2026-06-24 Task 8 Graphplan Expert
- Existing Task 6 generator test treated `graphplan` as unimplemented; Task 8 changes that contract, so the negative CLI case now uses truly unsupported `astar`.

## 2026-06-24 Task 10 StarVLA Registry
- The required `.venv` initially could not import `starVLA.dataloader.gr00t_lerobot.registry` because package/base registry imports eagerly required optional training dependencies (`accelerate`, then `torch`). Minimal lazy/skip guards were needed before the registry smoke could reach the new planning config.

## 2026-06-24 Task 11 Documentation Closeout
- Initial write attempt hit shell heredoc quoting because the summary includes a nested `python - <<'PY'` command block. Retried with a different outer delimiter and kept the exact registry smoke command in the docs.

## 2026-06-24 F2 Registry Rejection Fix
- F2 rejected broad `ModuleNotFoundError` catches in registry-only smoke paths because they could hide internal/project import bugs. The fix restricts skips to an explicit optional dependency allowlist (`accelerate`, `numpy`, `pandas`, `pydantic`, `torch`, `tqdm`) and re-raises all other missing imports, with regression tests covering artificial internal missing modules.
