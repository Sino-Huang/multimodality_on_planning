# Current project status

The characterization runner uses trace contract v3 and Gate 0b passed. The approved Phase 3 pilot
scope and deterministic source index are materialized. The current critical path is pilot rendering
before the direct-VLM Gate 3 calibration baseline.

Production rendering is blocked at the canonical Planimation PDDL/profile-to-VFG endpoint. The
hardened adapter and replay-alignment work is staged but uncommitted. Read `task_plan.md`, `notes.md`,
and `.claude/evidence/cgas-phase3-pilot-rendering/verification-20260810.md` for exact state and gates.

Standing constraints:

- Preserve both characterization roots and the released fixture digest.
- Do not create checkpoint 2, Qwen rows, or `planning_vlm/` without the decisions required by the
  research execution plan.
- Use `source ~/cd_vlaplan` for every Python command and install nothing.
- Never recursively preload `.claude/evidence/`; open only task-referenced evidence.
