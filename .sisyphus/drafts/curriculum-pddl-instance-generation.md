# Curriculum PDDL Instance Generation Draft

Confirmed requirements captured before implementation:

- Build reusable scripts under `src/data_collect`.
- Generate a 15-domain curriculum from `modules/pddl-generators`.
- Target counts per domain: `train=200`, `dev=20`, `test=20`.
- Train buckets: `easy=70`, `medium=80`, `hard=50`.
- Dev buckets: `easy=7`, `medium=8`, `hard=5`.
- Test buckets: `easy=5`, `medium=7`, `hard=8`.
- Rendering is required for accepted instances.
- Accepted instances must pass generator normalization plus Planimation rendering checks.
- Record complete metadata and structured rejection reasons.
- Keep generation resumable and config-driven.
- Do not edit `modules/pddl-generators`.
- Do not commit generated dataset artifacts unless explicitly requested.
