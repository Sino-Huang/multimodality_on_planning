#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

max_knowledge_files=6
max_knowledge_bytes=25600
max_orientation_bytes=25600

knowledge_files=$(find .claude/knowledge .omo/knowledges -type f -name '*.md' | wc -l)
knowledge_bytes=$(find .claude/knowledge .omo/knowledges -type f -name '*.md' -printf '%s\n' |
    awk '{sum += $1} END {print sum + 0}')
orientation_bytes=$(find .claude/knowledge .claude/plans .omo/knowledges -type f -printf '%s\n' |
    awk '{sum += $1} END {print sum + 0}')
orientation_bytes=$((
    orientation_bytes
    + $(wc -c < .claude/README.md)
    + $(wc -c < .claude/ledger.jsonl)
    + $(wc -c < .claude/production-p0-status.md)
))

if ((knowledge_files > max_knowledge_files)); then
    printf 'agent context budget exceeded: %d knowledge files > %d\n' "$knowledge_files" "$max_knowledge_files" >&2
    exit 1
fi
if ((knowledge_bytes > max_knowledge_bytes)); then
    printf 'agent context budget exceeded: %d knowledge bytes > %d\n' "$knowledge_bytes" "$max_knowledge_bytes" >&2
    exit 1
fi
if ((orientation_bytes > max_orientation_bytes)); then
    printf 'agent context budget exceeded: %d orientation bytes > %d\n' "$orientation_bytes" "$max_orientation_bytes" >&2
    exit 1
fi

for retired_root in .claude/logs .omo/evidence .omo/ulw-loop; do
    first_retired_file=""
    if [[ -d "$retired_root" ]]; then
        first_retired_file=$(find "$retired_root" -type f -print -quit)
    fi
    if [[ -n "$first_retired_file" ]]; then
        printf 'retired hot context root contains files: %s\n' "$retired_root" >&2
        exit 1
    fi
done

archive=.claude/archive/context-hot-snapshot-2026-08-10.tar.gz
expected_archive_sha256=8b16b0231fd4d2eda359da80b3fdc16563a43eaa58828cc55d4456bb22ca45fc
if [[ -f "$archive" ]]; then
    actual_archive_sha256=$(sha256sum "$archive" | awk '{print $1}')
    if [[ "$actual_archive_sha256" != "$expected_archive_sha256" ]]; then
        printf 'context recovery archive digest mismatch: %s\n' "$archive" >&2
        exit 1
    fi
fi

supplemental_archive=.claude/archive/session-logs-2026-08-10-to-2026-08-11.tar.gz
expected_supplemental_sha256=61da47e64015cde758aaa8c82a13c4a2b5670236d7a16b880e99cc261e6bbd97
if [[ -f "$supplemental_archive" ]]; then
    actual_supplemental_sha256=$(sha256sum "$supplemental_archive" | awk '{print $1}')
    if [[ "$actual_supplemental_sha256" != "$expected_supplemental_sha256" ]]; then
        printf 'context recovery archive digest mismatch: %s\n' "$supplemental_archive" >&2
        exit 1
    fi
fi

printf 'agent context budget OK: files=%d knowledge_bytes=%d orientation_bytes=%d\n' \
    "$knowledge_files" "$knowledge_bytes" "$orientation_bytes"
