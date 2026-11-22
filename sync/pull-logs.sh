#!/usr/bin/env bash
set -euo pipefail

LOCAL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/"
# TODO: set REMOTE to your agate clone, e.g. 'agate:projects/t2t-eval/'
REMOTE=''
if [[ -z "$REMOTE" ]]; then
    echo "pull-logs.sh: REMOTE is unset — edit this script and set it to your agate clone." >&2
    exit 1
fi

usage() {
    cat <<'EOF'
Usage: pull-logs.sh [-n|--dry-run] [MODE]

Options:
  -n, --dry-run  Preview the rsync transfer without writing anything.
                 Must precede MODE. Prints --stats plus the first few
                 candidate files; the rest are summarized as "... and N more".

Modes:
  (no args)      Pull logs/, benchmarks/, and *.bm.txt under results/.
  --submit       Pull only logs/submit/ from the remote.
  --from FILE    Pull only the repo-relative paths listed in FILE.
                 Use FILE='-' to read paths from stdin.
  -h, --help     Show this help.
EOF
}

DRYRUN=()
banner_printed=0
if [[ "${1:-}" == "-n" || "${1:-}" == "--dry-run" ]]; then
    DRYRUN=(-n)
    shift
fi

die() {
    echo "pull-logs.sh: $1" >&2
    exit 2
}

# Trim rsync's verbose file list to the first few entries, keep the --stats
# block intact. Triggered only in dry-run mode.
dryrun_filter() {
    awk -v sample=5 '
        NR == 1 { print; next }
        /^$/ && !seen_blank {
            if (extras > 0) printf "  ... and %d more\n", extras
            seen_blank = 1
            print
            next
        }
        seen_blank { print; next }
        { count++; if (count <= sample) print; else extras++ }
    '
}

# Wrapper: pass through in normal mode; in dry-run mode inject -n --stats and
# filter the file listing.
rsync_w() {
    if [[ ${#DRYRUN[@]} -eq 0 ]]; then
        rsync "$@"
    else
        if [[ $banner_printed -eq 0 ]]; then
            echo "== DRY RUN — no files will be written =="
            banner_printed=1
        fi
        rsync "$@" -n --stats | dryrun_filter
    fi
}

pull_default() {
    rsync_w -avz "${REMOTE}logs/"       "${LOCAL}logs/"       || echo "(no logs on agate yet)"
    rsync_w -avz "${REMOTE}benchmarks/" "${LOCAL}benchmarks/" || echo "(no benchmarks on agate yet)"
    rsync_w -avz --prune-empty-dirs \
        --include='*/' \
        --include='*.bm.txt' \
        --exclude='*' \
        "${REMOTE}results/" "${LOCAL}results/" || echo "(no results on agate yet)"
}

pull_submit() {
    rsync_w -avz "${REMOTE}logs/submit/" "${LOCAL}logs/submit/" || echo "(no submit logs on agate yet)"
}

pull_from() {
    local file="$1"
    if [[ "$file" != "-" && ! -f "$file" ]]; then
        die "--from FILE: '$file' is not a regular file (use '-' for stdin)"
    fi
    rsync_w -avz --files-from="$file" "$REMOTE" "$LOCAL"
}

case "${1:-}" in
    "")
        pull_default
        ;;
    --submit)
        [[ $# -gt 1 ]] && die "--submit takes no arguments"
        pull_submit
        ;;
    --from)
        [[ $# -lt 2 ]] && die "--from requires a FILE argument (use '-' for stdin)"
        [[ $# -gt 2 ]] && die "--from takes exactly one argument"
        pull_from "$2"
        ;;
    -h|--help)
        usage
        ;;
    *)
        echo "pull-logs.sh: unknown option: $1" >&2
        usage >&2
        exit 2
        ;;
esac
