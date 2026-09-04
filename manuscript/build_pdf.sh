#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
texlive_bin="$script_dir/texlive/2026/bin/x86_64-linux"
tex_file="${1:-iclr2026/iclr2026_conference.tex}"
output_file="${2:-$script_dir/manuscript.pdf}"

if [[ "$tex_file" != /* ]]; then
    tex_file="$script_dir/$tex_file"
fi

if [[ ! -f "$tex_file" ]]; then
    printf 'TeX file not found: %s\n' "$tex_file" >&2
    exit 1
fi

export PATH="$texlive_bin:$PATH"

latexmk -cd -pdf -interaction=nonstopmode -halt-on-error "$tex_file"

built_pdf="${tex_file%.tex}.pdf"
pdftocairo -pdf "$built_pdf" "$output_file"
printf 'PDF written to: %s\n' "$output_file"
