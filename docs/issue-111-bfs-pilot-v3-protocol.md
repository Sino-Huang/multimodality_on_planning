# Issue #111 BFS expansion-qualified pilot v3 protocol

This document preregisters `issue-111-bfs-expansion-qualified-pilot-v3` before qualification attempt `qualification-attempt-002`. Attempt 001 remains an immutable `VALID_STOP`; its receipt, report, empty selected manifest, and interpretation are not revised.

## Fixed scientific inputs

- Domains: the governed 15-domain set in `src/data_collect/configs/curriculum_15_domains.yaml`.
- Splits: train and dev only. Test is held out and must not be read or generated.
- Exact FIFO BFS bands: easy 1–64 expansions, medium 65–256, and hard 257–1024.
- Coverage: one train and one dev task in every domain-by-band cell, exactly 90 tasks.
- Candidate ceiling: 500 candidates per domain and split.
- Selection seed: 111.
- Selection rule: for each domain and measured band, jointly choose the lexicographically minimum train/dev pair by each candidate's selection key, normalized problem hash, and candidate ID, subject to different whole-instance identities. No split-isolated pair means the cell is missing.
- Primary model: `Qwen/Qwen3-VL-8B-Instruct` revision `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`.
- Training seeds: 17, 29, 43, 71, and 101.
- Budgets, LoRA settings, optimizer settings, frozen core libraries, statistics, and no-retuning rule: unchanged from the v1 freeze.

## Corrected candidate constructions

- 15-puzzle deterministically enumerates reachable states and partitions actual states between train and dev. Easy uses non-goal 2×2 states; medium draws from 3×3 optimal depths 7–8; hard draws from depths 9–10. Measured exact-BFS expansions, not construction depth, assign the final band.
- Elevators keeps the easy and medium profiles and uses 6 floors / 3 passengers for hard.
- Sokoban uses the supported 5×5 generator boundary for all tiers. Easy transforms its output into split-distinct one- and two-push layouts expected at 3–11 exact-BFS expansions; medium and hard retain seeded 5×5 generation.
- All other domain constructions and the tier quotas 32/64/404 are unchanged from attempt 001.

## Qualification gate

Qualification runs twice into fresh roots. `candidates.jsonl`, `selected-manifest.jsonl`, and every selected PDDL byte must match between runs. `PASS` requires all of the following:

- exactly 90 selected tasks and all 15×3×2 cells;
- no missing cell, trivial goal, test access, candidate-ceiling breach, cross-split whole-instance identity, or expansion outside the row's declared band;
- exact FIFO replay equality for every selected result, including plan, expansion count, goal status, and ordered trace records;
- repository-relative selected task paths and byte hashes that match the published files.

Any unfilled cell within the fixed ceiling produces `VALID_STOP`. Checks are never forced to pass.

## Successor freeze and authorization

Only after qualification `PASS`, publish the selected manifest and 90 domain/problem pairs under `data/bfs_pilot_v3/`, then create `bfs_phase_freeze_v3` and `bfs_phase_authorization_v3` manifests sourced from issue #111. The freeze binds the PASS receipt, qualification report, selected manifest, every selected PDDL file, unchanged model revision, five seeds, libraries, LoRA/optimizer settings, budgets, statistics, selection protocol, and stop rules.

The v3 authorization covers trace generation, process-corpus release, exact/base references, and the later #54 process-SFT sanity gate. Its downstream issue list is only #54. Operational-SFT is absent. A v1 authorization cannot authorize the v3 phase.

## Trace and corpus release

Generate exact FIFO evidence and independently replay all 90 tasks. Release a versioned process-only corpus:

- input: goal atoms, current observation, and bounded prior search memory;
- assistant target: `canonical_rationale`, `typed_operation`, and `runtime_result: null`;
- actual runtime results: retained only in trusted trace/evidence records;
- released views: process only; no operational JSONL or curriculum;
- projection: source-bound ms-swift train/dev `messages` JSONL derived from the canonical process rows.

The retained trace manifest must cover all 90 task identities. Rebuilding the process release from replay-verified evidence and repeating the ms-swift projection must reproduce the released bytes.

## Closure

Close #111 only after qualification `PASS`, 90/90 exact replay, split-isolation and held-out checks, deterministic process-corpus regeneration, and deterministic ms-swift projection. The closure record must include phase and artifact identities and explicitly retain attempt 001 as an immutable `VALID_STOP`. Comment on #54 with the v3 authorization and corpus identities and mark it unblocked. Do not run a LoRA smoke or training under #111.
