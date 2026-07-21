# Project Status Assessment - 2026-07-15

## Authority and Scope

- `doc/research_proposal.md` is the study's canonical scope: test the Computational Resource Substitution Hypothesis (CRSH) across BFS, Fast Forward, Iterated Width, and Graphplan under vision, language, vision-language, and vision-language-tool conditions.
- The required research path is Blocksworld/Planimation first, then a zero-shot diagnostic, one end-to-end training/evaluation path, the P0 modality-by-algorithm sweep, and only then cross-task transfer.
- The frozen world-model interface, planner model, scratchpad runtime, SFT recipes, real VLM calls, GPU runs, and proposal-aligned evaluation are not implemented or executed.

## Completed Foundations

- Planimation validation and the 15-domain curriculum-PDDL generation pipeline are complete. The curriculum checkpoint is documented as 5,153 accepted render-validated instances, with no duplicate normalized hashes.
- The Blocksworld-only P0 benchmark slice is complete: symbolic transition loop, offline zero-shot package/scorer, step-level expert schema, four modality serializers with leakage tests, and StarVLA JSONL registry smoke integration.
- The Phase 3 local trace pipeline has replay validation, fidelity labels, schema validation, safe output-root handling, bounded worker processes, per-attempt/domain timeouts, and deterministic parent-side output writes.

## Dataset State

- The canonical `data/phase3_supervised_planning` corpus is an earlier generated snapshot: 3,600 accepted instances, 14,400 planner attempts, and 411 replay-validated supervised examples. Its FF/IW/Graphplan records were unavailable unless external executables were configured.
- Newer timestamped roots under `outputs/` are separate experimental trace collections, not yet a curated canonical training dataset. The 2026-07-10 aggregate audit records 6,816 unique replay-validated examples: train 5,690, dev 630, test 496.
- The newer collection has no duplicate examples and has render/frame paths for every emitted example. Its bounded render windows do not generally cover every plan step, so full step-aligned visual supervision would need rerendering or a per-plan render window.
- Trace-size controls are mandatory before model training. The audited full corpus has very large raw planner traces (p95 about 1.87M JSON characters; 90 examples above 5M; one above 10M). `visitall` should be treated as a separate diagnostic subset despite its later train/test recovery.

## Algorithm Fidelity and Research Risks

- Active multi-domain generation uses `gbfs`, `ff`, `iw`, and `graphplan`; `bfs` is explicitly rejected. GBFS uses unsatisfied-goal-count ranking with deterministic tie-breaking. This differs from the proposal's P0 BFS condition and must be resolved or reported as a deliberate approximation before making CRSH claims about BFS.
- Local `ff` is FF-style delete-relaxation with bounded recovery, not canonical Fast Forward. Local `graphplan` computes action-level mutexes only, not full proposition mutexes/no-good backward extraction. Recovery traces are replay-valid but marked non-exact.
- IW is configurable and defaults to IW(3). Raw IW and Graphplan traces are especially unsuitable for direct full-context prompting; future tool work should retrieve compact, decision-relevant state rather than inject full trace tables.
- Recommended current local-trace training domains are easy/medium `blocksworld`, `elevators`, `ferry`, `gripper`, `logistics`, `towers_of_hanoi`, and `visitall`, subject to trace-size filtering. Use `15puzzle` easy-only unless it is a deliberate stress test. Do not use hard instances as a broad full-trace corpus.
- `snake` and `sokoban` are unsupported by the local parser. `depot`, `driverlog`, `freecell`, `grid`, and `storage` require a stronger lifted/external backend or domain-specific work for broad coverage.

## Next Implementation Gate

1. Decide whether P0 must restore true BFS or formally revise the study matrix to GBFS. Do not conflate the two in data labels, evaluation, or paper claims.
2. Curate a training-ready corpus from the newer `outputs/` roots: deduplicate by canonical IDs, filter/bucket trace size, preserve fidelity/recovery labels, and decide how visual frames align with each supervised decision.
3. Build one planner-model plus deterministic scratchpad path and train/evaluate one algorithm-modality pilot before launching the full P0 matrix.
4. Add evaluation for action validity, algorithm-state fidelity, process/failure labels, and tool behavior before interpreting task-success scores as CRSH evidence.

## Knowledge Maintenance Rule

After each material implementation, dataset generation/audit, experimental result, design decision, or known limitation change, add or update a concise dated record in `.omo/knowledges/`. Link the relevant code, generated artifact, verification command, result, scope caveat, and the resulting next action. Update this status file when a change alters the project-wide state; retain narrower topic records rather than overwriting them.

## 2026-07-15 Planimation Pairing Update

- A sidecar Phase 3 Planimation/VLM pairing pipeline is implemented and has a validated combined manifest for all four non-deprecated trace roots. It is not a completed full image-rendering dataset yet.
- The manifest covers 6,816 examples and identifies 2,691 records eligible for the selected initial seven-domain easy/medium, unrecovered configured-method, 1M-character, and 64-action VLM pass.
- Existing VFG trajectories mismatch local planner action sequences for 4,973 examples. The pipeline therefore rerenders replay states rather than incorrectly pairing source VFG action frames to local plans.
- A real Blocksworld replay-state Planimation smoke completed successfully. See `.omo/knowledges/phase3-planimation-vlm-pairing-2026-07-15.md` for commands, caveats, and verification.
