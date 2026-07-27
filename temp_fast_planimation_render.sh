#!/usr/bin/env bash

set -euo pipefail

DATASET_ROOT="outputs/reasoning_traces/curriculum/phase3_curriculum_traces_safe_no_visitall_strict_v1_1st_round"
FULL_OUTPUT_ROOT="outputs/image_frames/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800"
PILOT_OUTPUT_ROOT="${PILOT_OUTPUT_ROOT:-outputs/image_frames/phase3_planimation_frames_stratified_pilot_20260725}"
SELECTION_FILE="${FULL_OUTPUT_ROOT}/diagnostics/rollout_selection.json"
resume=false

active_generator_writes_to() {
  local output_root="$1"
  local cmdline_path
  local argument
  local output_root_argument
  local index
  local output_root_index
  local generator_argument_index
  local -a arguments

  for cmdline_path in /proc/[0-9]*/cmdline; do
    [[ -r "$cmdline_path" ]] || continue
    arguments=()
    while IFS= read -r -d '' argument; do
      arguments+=("$argument")
    done < "$cmdline_path"
    ((${#arguments[@]} > 0)) || continue

    case "${arguments[0]##*/}" in
      python|python[0-9]*)
        ;;
      *)
        continue
        ;;
    esac

    generator_argument_index=-1
    for ((index = 1; index < ${#arguments[@]}; index++)); do
      case "${arguments[index]}" in
        -c|-)
          break
          ;;
        -m)
          if ((index + 1 < ${#arguments[@]})) && [[ "${arguments[index + 1]}" == "scripts.phase3.generate_planimation_vlm" ]]; then
            generator_argument_index=$((index + 2))
          fi
          break
          ;;
        -*)
          ;;
        *)
          if [[ "${arguments[index]##*/}" == "generate_planimation_vlm.py" ]]; then
            generator_argument_index=$((index + 1))
          fi
          break
          ;;
      esac
    done
    ((generator_argument_index >= 0)) || continue

    for ((output_root_index = generator_argument_index; output_root_index < ${#arguments[@]}; output_root_index++)); do
      case "${arguments[output_root_index]}" in
        --output-root)
          if ((output_root_index + 1 < ${#arguments[@]})); then
            output_root_argument="${arguments[output_root_index + 1]}"
            [[ "$output_root_argument" == "$output_root" ]] && return 0
          fi
          ;;
        --output-root=*)
          output_root_argument="${arguments[output_root_index]#--output-root=}"
          [[ "$output_root_argument" == "$output_root" ]] && return 0
          ;;
      esac
    done
  done

  return 1
}

case "$#" in
  0)
    ;;
  1)
    if [[ "$1" != "--resume" ]]; then
      printf 'Usage: temp_fast_planimation_render.sh [--resume]\n' >&2
      exit 2
    fi
    resume=true
    ;;
  *)
    printf 'Usage: temp_fast_planimation_render.sh [--resume]\n' >&2
    exit 2
    ;;
esac

if active_generator_writes_to "$FULL_OUTPUT_ROOT"; then
  printf 'Refusing to run while the full renderer still writes to %s. Stop it first, then rerun this script.\n' "$FULL_OUTPUT_ROOT" >&2
  exit 1
fi

if active_generator_writes_to "$PILOT_OUTPUT_ROOT"; then
  printf 'Refusing to run while the pilot renderer still writes to %s. Stop it first, then rerun this script.\n' "$PILOT_OUTPUT_ROOT" >&2
  exit 1
fi

if [[ "$resume" == false ]]; then
  if [[ -e "$PILOT_OUTPUT_ROOT" ]]; then
    printf 'Refusing to overwrite existing pilot output root: %s\n' "$PILOT_OUTPUT_ROOT" >&2
    exit 1
  fi
else
  if [[ ! -d "$PILOT_OUTPUT_ROOT" ]]; then
    printf 'Resume requires existing pilot output root: %s\n' "$PILOT_OUTPUT_ROOT" >&2
    exit 1
  fi
  if [[ ! -f "$SELECTION_FILE" ]]; then
    printf 'Resume requires existing frozen selection file: %s\n' "$SELECTION_FILE" >&2
    exit 1
  fi
fi

# Conda's deactivate hook reads an unset variable under Bash nounset.
set +u
source ~/cd_vlaplan
source .venv/bin/activate
set -u

if [[ "$resume" == false ]]; then
  python - <<'PY'
from pathlib import Path

from scripts.phase3.rollout_gate_selection import prepare_selection

result = prepare_selection(
    Path("outputs/image_frames/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800"),
    "stratified-pilot",
)
print(f"Prepared {len(result['selected_pair_ids'])} selected pairs with {result['transition_count']} plan transitions.")
PY
fi

python -m scripts.phase3.generate_planimation_vlm \
  --dataset-root "$DATASET_ROOT" \
  --output-root "$PILOT_OUTPUT_ROOT" \
  --selection-file "$SELECTION_FILE" \
  --domain blocksworld \
  --domain elevators \
  --domain ferry \
  --domain gripper \
  --domain logistics \
  --domain towers_of_hanoi \
  --bucket easy \
  --bucket medium \
  --progress-every 100 \
  --request-delay-seconds 0 \
  --mode production

for verification_mode in manifest render release; do
  python scripts/phase3/verify_planimation_vlm.py \
    --output-root "$PILOT_OUTPUT_ROOT" \
    --mode "$verification_mode" \
    --selection-file "$SELECTION_FILE"
done
