#!/usr/bin/env bash
# What landed on local main since the last push, grouped by wg task, before a human pushes.
# Flags changes to shared files: those go up as a PR branch, not straight to main:
#   git push origin main:<lane>/<topic>
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)
RANGE=${UPSTREAM:+$UPSTREAM..main}
RANGE=${RANGE:-main}   # nothing pushed yet: review everything
# The shared files of CLAUDE.md ("Lanes and file ownership"); \.github/ covers .github/CODEOWNERS.
SHARED='^(workflow/Snakefile|config/|docker/|\.github/|pixi\.(toml|lock)|AGENTS\.md|CLAUDE\.md|\.claude/settings\.json|\.claude/hooks/|SPEC\.tsv)'

echo "Commits in $RANGE:"
git log --reverse --format='%h %s' "$RANGE"
echo

echo "By wg task (ids in commit messages):"
for task in $(git log --format='%s%n%b' "$RANGE" | grep -oE '\b(jc|sf|shared)/[A-Za-z0-9._-]+' | sort -u); do
    echo "== $task"
    wg show "$task" 2>/dev/null | head -15 || echo "   (not in this graph)"
done
echo

shared=$(git diff --name-only "${UPSTREAM:-$(git hash-object -t tree /dev/null)}" main | grep -E "$SHARED" || true)
if [[ -n "$shared" ]]; then
    echo "SHARED FILES CHANGED (push these as a PR branch, not to main):"
    echo "$shared" | sed 's/^/  /'
else
    echo "No shared files changed."
fi
echo
echo "If anything is wrong: git revert <sha>. Then push (humans only)."
