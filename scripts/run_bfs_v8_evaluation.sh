#!/usr/bin/env bash

set -o pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
cd "${repo_root}" || exit 1

# Confirmed project environment from AGENTS.md.
source ~/cd_vlaplan || exit 1
set -u
cd "${repo_root}" || exit 1

qualification="outputs/bfs_phase/issue54-v8-qualification.json"
rollout_root_0="outputs/bfs_phase/issue54-v8-rollout-shard-0"
rollout_root_1="outputs/bfs_phase/issue54-v8-rollout-shard-1"

pids=()
labels=()

manifest_field() {
    python -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2]))' "$1" "$2"
}

stop_children() {
    local signal_name="$1"
    local exit_code="$2"
    trap - INT TERM
    echo "Received ${signal_name}; asking active rollout shards to stop cleanly." >&2
    local pid
    for pid in "${pids[@]}"; do
        if kill -0 "${pid}" 2>/dev/null; then
            kill -INT "${pid}" 2>/dev/null || true
        fi
    done
    for pid in "${pids[@]}"; do
        wait "${pid}" 2>/dev/null || true
    done
    echo "Completed episodes were preserved. Run this helper again to resume." >&2
    exit "${exit_code}"
}

trap 'stop_children SIGINT 130' INT
trap 'stop_children SIGTERM 143' TERM

if [[ ! -f "${qualification}" ]]; then
    python scripts/prepare_bfs_v8_evaluation.py --output "${qualification}" || exit 1
else
    echo "Reusing the existing global-clock receipt: ${qualification}"
fi

launch_shard() {
    local shard_index="$1"
    local device="$2"
    local output_root="$3"
    local manifest="${output_root}/manifest.json"
    local resume_args=()

    if [[ -f "${manifest}" ]]; then
        local outcome
        local stop_reason
        outcome="$(manifest_field "${manifest}" outcome)" || return 1
        stop_reason="$(manifest_field "${manifest}" stop_reason)" || return 1
        if [[ "${outcome}" == "PASS" ]]; then
            echo "Shard ${shard_index} is already complete; skipping it."
            return 0
        fi
        if [[ "${stop_reason}" == "wall_clock_cutoff" ]]; then
            echo "Shard ${shard_index} reached the frozen wall-clock cutoff and cannot resume." >&2
            return 0
        fi
        resume_args=(--resume)
    elif [[ -d "${output_root}" ]]; then
        resume_args=(--resume)
    fi

    echo "Launching shard ${shard_index} on ${device}${resume_args:+ with resume}."
    python scripts/run_bfs_batched_rollout.py \
        --phase v8 \
        --qualification "${qualification}" \
        --output-root "${output_root}" \
        --attempt-id "issue-54-v8-rollout-shard-${shard_index}" \
        --device "${device}" \
        --device-shard-index "${shard_index}" \
        "${resume_args[@]}" &
    pids+=("$!")
    labels+=("shard-${shard_index}")
}

launch_shard 0 cuda:0 "${rollout_root_0}" || exit 1
launch_shard 1 cuda:1 "${rollout_root_1}" || stop_children "launch failure" 1

failed=0
for index in "${!pids[@]}"; do
    if wait "${pids[${index}]}"; then
        echo "${labels[${index}]} finished."
    else
        status="$?"
        echo "${labels[${index}]} exited with status ${status}." >&2
        failed=1
    fi
done
trap - INT TERM

if (( failed != 0 )); then
    echo "At least one rollout shard failed. Run this helper again after correcting the error." >&2
    exit 1
fi

for manifest in "${rollout_root_0}/manifest.json" "${rollout_root_1}/manifest.json"; do
    if [[ ! -f "${manifest}" ]]; then
        echo "Missing rollout manifest: ${manifest}" >&2
        exit 1
    fi
    if [[ "$(manifest_field "${manifest}" outcome)" != "PASS" ]]; then
        echo "Rollout stopped without complete coverage: ${manifest}" >&2
        echo "Run the v8 adjudication command to retain the governed stop." >&2
        exit 2
    fi
done

echo "Both v8 rollout shards completed successfully."
echo "Next: run scripts/adjudicate_bfs_batched_gate.py with the two rollout roots."
