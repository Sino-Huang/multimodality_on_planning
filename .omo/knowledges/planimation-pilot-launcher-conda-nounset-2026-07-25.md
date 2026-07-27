# Planimation Pilot Launcher: Conda and Nounset

## Problem

`temp_fast_planimation_render.sh` enables Bash strict mode with `set -euo pipefail`.
Sourcing `~/cd_vlaplan` activates `ada_vla`; under `set -u`, Conda's
`deactivate-gcc_linux-64.sh` reads the unset
`_CONDA_PYTHON_SYSCONFIGDATA_NAME_USED` variable and exits before the pilot starts.

## Resolution

Disable only nounset while sourcing `~/cd_vlaplan` and `.venv/bin/activate`,
then restore it with `set -u`. The launcher keeps `errexit` and `pipefail`
enabled throughout, and it keeps nounset enabled for selection, rendering, and
release verification.

## Manual Launch

```bash
bash temp_fast_planimation_render.sh
PILOT_OUTPUT_ROOT=outputs/phase3_planimation_frames_stratified_pilot_20260725 bash temp_fast_planimation_render.sh --resume
```

The first command is fresh mode. It requires a new output root and refuses to
overwrite an existing one. The second command is resume mode for the existing
pilot root. It requires the root and frozen selection to exist, preserves valid
cache entries, and runs selection-bound manifest, render, and release checks.

Both modes refuse active writers for the protected full-render and pilot roots.
Todo 7 did not rerun the launcher. It used direct verifier and rollout assessment
commands against the already recovered pilot.

## Verification Signals

```bash
bash -n temp_fast_planimation_render.sh
bash -c 'set -euo pipefail; set +u; source "$HOME/cd_vlaplan"; source .venv/bin/activate; set -u; printf "conda=%s\nvenv=%s\n" "$CONDA_DEFAULT_ENV" "$VIRTUAL_ENV"'
```

Expected activation values are `conda=ada_vla` and a `.venv` path for `venv`.
