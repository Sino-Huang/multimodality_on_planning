#!/usr/bin/env bash

set -uo pipefail

parent_pid="$1"
repo_root="/data/scratch/projects/punim0478/sukaih/multimodality_on_planning"
evidence="$repo_root/.omo/evidence/planimation-pilot-contract-and-render-recovery/task-6-planimation-pilot-contract-and-render-recovery"
pilot="outputs/phase3_planimation_frames_stratified_pilot_20260725"
full="outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800"
module="generate_planimation_vlm"

while kill -0 "$parent_pid" 2>/dev/null; do
  sleep 1
done

cd "$repo_root"

pilot_guard="${module}.*${pilot}"
full_guard="${module}.*${full}"
pgrep -af -- "$full_guard" > "$evidence/process-check-clean-shell-full-guard.txt"
full_guard_status=$?
pgrep -af -- "$pilot_guard" > "$evidence/process-check-clean-shell-pilot-guard.txt"
pilot_guard_status=$?

if [[ "$full_guard_status" -eq 0 || "$pilot_guard_status" -eq 0 ]]; then
  printf "Refusing clean-shell resume because the launcher guard still matches a process.\n" > "$evidence/resume-third-clean-shell.blocked"
  exit 17
fi

source "$HOME/cd_vlaplan"
source .venv/bin/activate
PILOT_OUTPUT_ROOT=outputs/phase3_planimation_frames_stratified_pilot_20260725 bash temp_fast_planimation_render.sh --resume > "$evidence/resume-third-clean-shell.log" 2>&1
exit_code=$?
printf "%s\n" "$exit_code" > "$evidence/resume-third-clean-shell.exit"
exit "$exit_code"
