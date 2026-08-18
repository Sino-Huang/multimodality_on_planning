# Current Planning Benchmark Scope Lock

### blocksworld_p0_scope_decision

The Phase 1-3 acceptance scope is `blocksworld` only and remains future-compatible.

### algorithm_matrix_decision

The exact active algorithm set is `bfs` and `iterated_width`.

### modality_matrix_decision

The modality set names `vision`, `language`, `vision_language`, and `vision_language_tool`.

### planimation_role_decision

Planimation is an offline rendering utility and not environment authority.

### frozen_world_model_decision

The frozen world model v0 is a deterministic symbolic representation. No learned encoder is used.

### artifact_policy_decision

The artifact policy says Raw PDDL files alone are not expert demonstrations.

### zero_shot_gate_decision

The zero shot gate checks go or no go conditions, parseable JSON, and whether the action is legal.
