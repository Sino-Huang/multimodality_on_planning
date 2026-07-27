#!/usr/bin/env bash

set -uo pipefail

parent_pid="$1"
repo_root="/data/scratch/projects/punim0478/sukaih/multimodality_on_planning"
evidence="$repo_root/.omo/evidence/planimation-pilot-contract-and-render-recovery/task-6-planimation-pilot-contract-and-render-recovery"
pilot="outputs/phase3_planimation_frames_stratified_pilot_20260725"
full="outputs/phase3_planimation_frames_safe_no_visitall_strict_v1_20260722_005800"
module_prefix="generate_planimation_"
module_suffix="vlm"
module="${module_prefix}${module_suffix}"

date -u +%Y-%m-%dT%H:%M:%SZ > "$evidence/resume-replacement-persistent.scheduler-started-at.txt"

while kill -0 "$parent_pid" 2>/dev/null; do
  sleep 1
done

cd "$repo_root"

full_guard="${module}.*${full}"
pilot_guard="${module}.*${pilot}"
pgrep -af -- "$full_guard" > "$evidence/process-check-replacement-full-guard.txt"
full_guard_exit=$?
pgrep -af -- "$pilot_guard" > "$evidence/process-check-replacement-pilot-guard.txt"
pilot_guard_exit=$?
printf "full_guard_exit=%s\npilot_guard_exit=%s\n" "$full_guard_exit" "$pilot_guard_exit" > "$evidence/process-check-replacement-guard-status.txt"

if [[ "$full_guard_exit" -eq 0 || "$pilot_guard_exit" -eq 0 ]]; then
  printf "blocked_at=%s\nreason=launcher raw guard matched a process\nfull_guard_exit=%s\npilot_guard_exit=%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$full_guard_exit" "$pilot_guard_exit" > "$evidence/resume-replacement-persistent.blocked"
  exit 17
fi

set +u
source "$HOME/cd_vlaplan"
cd_vlaplan_exit=$?
source .venv/bin/activate
venv_activation_exit=$?
set -u

if [[ "$cd_vlaplan_exit" -ne 0 || "$venv_activation_exit" -ne 0 ]]; then
  printf "blocked_at=%s\nreason=environment activation failed\ncd_vlaplan_exit=%s\nvenv_activation_exit=%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$cd_vlaplan_exit" "$venv_activation_exit" > "$evidence/resume-replacement-persistent.blocked"
  exit 18
fi

date -u +%Y-%m-%dT%H:%M:%SZ > "$evidence/resume-replacement-persistent.launcher-started-at.txt"
PILOT_OUTPUT_ROOT=outputs/phase3_planimation_frames_stratified_pilot_20260725 bash temp_fast_planimation_render.sh --resume > "$evidence/resume-replacement-persistent.log" 2>&1
exit_code=$?
date -u +%Y-%m-%dT%H:%M:%SZ > "$evidence/resume-replacement-persistent.launcher-ended-at.txt"
printf "%s\n" "$exit_code" > "$evidence/resume-replacement-persistent.exit"
exit "$exit_code"
