#!/usr/bin/env bash
# One background chain; each stage gates the next and an EXIT hook seals status.
set -eo pipefail
cd "$(dirname "$0")/.."
source ~/cd_vlaplan
set -u

run_dir="outputs/matched_modalities/v5/automatic-continuation"
mkdir -p "$run_dir"
stage=starting
completion_hook() {
    result=$?
    trap - EXIT
    printf '{"stage":"%s","exit_code":%d,"finished_at":"%s"}\n' \
        "$stage" "$result" "$(date -u +%FT%TZ)" > "$run_dir/completion.json"
    exit "$result"
}
trap completion_hook EXIT
printf '%s\n' "$$" > "$run_dir/pid"
for stage in prepare qualify train verify decide; do
    printf '%s stage=%s started\n' "$(date -u +%FT%TZ)" "$stage"
    python -u scripts/run_matched_modalities.py "$stage" \
        --study configs/experiments/matched-modalities/study-v5.json \
        --workers 4 --devices 0 1 --master-ports 18775 18776 --resume \
        > "$run_dir/$stage.log" 2>&1
    printf '%s stage=%s completed\n' "$(date -u +%FT%TZ)" "$stage"
done
stage=complete
