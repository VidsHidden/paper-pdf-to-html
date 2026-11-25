#!/usr/bin/env bash
set -euo pipefail

repo="$(cd -- "$(dirname -- "$0")/.." && pwd)"
workspace="$(dirname -- "$repo")"
cd -- "$workspace"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$workspace/.uv-cache}"

reader="$repo/scripts/reader.py"
existing_python="$HOME/Documents/deepseek-harness/default-workspace/.uv-cache/environments-v2/reader-aae8bd5c6384e717/bin/python"
if [[ -n "${PAPER_READER_PYTHON:-}" ]]; then
    run=("$PAPER_READER_PYTHON" "$reader")
elif [[ -x "$existing_python" ]] && "$existing_python" -c 'import bs4, pymupdf' 2>/dev/null; then
    run=("$existing_python" "$reader")
elif command -v uv >/dev/null 2>&1; then
    run=(uv run "$reader")
elif [[ -x "$HOME/.local/bin/uv" ]]; then
    run=("$HOME/.local/bin/uv" run "$reader")
else
    printf 'No usable Python environment found. Set PAPER_READER_PYTHON to the reader Python executable.\n' >&2
    exit 1
fi

case "${1:-}" in
    --setup)
        "${run[@]}" deepseek-setup
        exit
        ;;
    --check)
        "${run[@]}" --help >/dev/null
        ;;
    '') ;;
    *)
        printf 'Usage: %s [--setup | --check]\n' "$0" >&2
        exit 2
        ;;
esac

out="$workspace/outputs"

for paper in s41586-026-10377-y s41592-023-02007-6; do
    work="$workspace/bilingual-$paper"
    if [[ ! -f "$work/article.html" ]]; then
        printf 'Missing prepared paper source: %s\n' "$work/article.html" >&2
        exit 1
    fi
done

if [[ "${1:-}" == --check ]]; then
    printf 'Python entry point and both prepared papers are ready.\n'
    exit
fi

mkdir -p "$out"
replay="$(mktemp -d "${TMPDIR:-/tmp}/paper-deepseek-replay.XXXXXX")"
trap 'rm -rf -- "$replay"' EXIT

for paper in s41586-026-10377-y s41592-023-02007-6; do
    work="$workspace/bilingual-$paper"
    file="$out/$paper-bilingual.html"
    "${run[@]}" translate --work "$work" --translator deepseek
    "${run[@]}" render "$file" --work "$work" --mode both --translator deepseek
    "${run[@]}" verify "$file"
    "${run[@]}" review "$file" --out "$work/bilingual-review.json"
    # No credentials or network API calls are required by render with explicit translations.
    "${run[@]}" render "$replay/$paper.html" --work "$work" --mode both \
        --translations "$work/translations-deepseek.json"
    cmp "$file" "$replay/$paper.html"
    shasum -a 256 "$file"
done
