# Scope Lock Fixture Missing World Model Decision

This is a negative test fixture for the scope lock checker.

### blocksworld_p0_scope_decision

The Phase 1-3 P0 acceptance scope is `blocksworld` only. The 15 domain curriculum remains future-compatible, but it is not Phase 1-3 acceptance scope.

### algorithm_matrix_decision

The algorithm set names `bfs`, `fast_forward`, `iterated_width`, and `graphplan`.

### modality_matrix_decision

The modality set names `vision`, `language`, `vision_language`, and `vision_language_tool`.

### planimation_role_decision

Planimation is an offline rendering utility and not environment authority.

### artifact_policy_decision

The artifact policy says Raw PDDL files alone are not expert demonstrations.

### zero_shot_gate_decision

The zero shot gate checks go or no go conditions, parseable JSON, and whether the action is legal.
