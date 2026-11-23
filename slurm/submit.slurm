#!/bin/bash -l
# Submit from the repo root on agate (a git clone, kept current with `git pull`):
#   sbatch slurm/submit.slurm --ticket tickets/<lane>/<id>.md
# Dry run with the same keys and settings, on the login node:
#   bash slurm/submit.slurm --ticket tickets/<lane>/<id>.md -n
# --output/--error are evaluated against the submit cwd, not the script location.
# --rerun-incomplete: an interrupted run (walltime kill, MSI event, scancel) marks
# outputs incomplete and the next run aborts without it.
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=32gb   # a first-time container pull unpacks in /dev/shm and is charged to this job
#SBATCH --partition=msismall
#SBATCH --account=fried255
#SBATCH --job-name=submit_t2t-eval
#SBATCH --output=logs/submit/%j.submit_t2t-eval.out
#SBATCH --error=logs/submit/%j.submit_t2t-eval.err
#SBATCH --mail-type=END,FAIL   # mails your MSI account address; add --mail-user to override

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$PWD}"

# The ticket pins what runs: `commit:`, `run_id:` and `targets:` lines. Its folder,
# tickets/<lane>/, is its lane (jc, sf or shared) and points the run at that lane's scratch; an
# optional `lane:` line must agree. `commit:` is the commit holding the rule; the ticket itself is
# committed after it, so HEAD may be later. Between the two only these may differ: tickets/, the
# OTHER personal lane's folders (jc ↔ sf: reports/, workflow/rules/, workflow/scripts/, tests/),
# and the append-only logs (PROVENANCE, HANDOFFS, DECISIONS, LESSONS). None of those change what
# this ticket's run executes. Shared files and workflow/scripts/shared/ still count. Agents
# write tickets; humans submit them, apart from the sf-lane exception in CLAUDE.md ("Where work
# happens"). Remaining args pass through to snakemake, except --delete-* (below).
SCRATCH_BASE=/scratch.global/friedlab_T2TEVAL
TICKET=''
if [[ "${1:-}" == "--ticket" ]]; then
    TICKET=${2:?--ticket needs a path, e.g. tickets/jc/M01.md}
    shift 2
fi
[[ -n "$TICKET" ]] || { echo "usage: submit.slurm --ticket tickets/<lane>/<id>.md [snakemake args]" >&2; exit 1; }
# Exactly tickets/<lane>/<file>.md, relative to the repo root: no ./, no .., no absolute path.
TICKET_RE='^tickets/(jc|sf|shared)/[A-Za-z0-9._-]+\.md$'
[[ "$TICKET" =~ $TICKET_RE ]] \
    || { echo "$TICKET: give the ticket as tickets/<jc|sf|shared>/<id>.md, from the repo root" >&2; exit 1; }
LANE=${BASH_REMATCH[1]}
[[ -f "$TICKET" ]] || { echo "no ticket at $TICKET" >&2; exit 1; }
# Only a committed ticket runs: a plain file git tracks (the tracked-files check below catches
# local edits to it). The sf-lane exception keys on this path.
[[ ! -L "$TICKET" ]] || { echo "$TICKET is a symlink; a ticket is a plain file" >&2; exit 1; }
git ls-files --error-unmatch -- "$TICKET" >/dev/null 2>&1 \
    || { echo "$TICKET is not committed: commit it, then submit" >&2; exit 1; }
# Deletes on scratch and Tier 2 are human-only, and never part of a ticket run. Snakemake's
# --delete-all-output and --delete-temp-output, or any abbreviation of them, start with --delete-.
for arg in "$@"; do
    [[ "$arg" != --delete-* ]] || { echo "submit.slurm does not pass $arg: deletes are human-only" >&2; exit 1; }
done
field() { sed -n "s/^$1:[[:space:]]*//p" "$TICKET" | head -1 | sed 's/[[:space:]]*$//'; }
T_COMMIT=$(field commit); T_RUN_ID=$(field run_id); T_TARGETS=$(field targets); T_LANE=$(field lane)
[[ -z "$T_LANE" || "$T_LANE" == "$LANE" ]] \
    || { echo "$TICKET: lane: says '$T_LANE' but the ticket is in tickets/$LANE/" >&2; exit 1; }
: "${T_COMMIT:?ticket has no commit: line}" "${T_RUN_ID:?ticket has no run_id: line}" "${T_TARGETS:?ticket has no targets: line}"
T_COMMIT_SHA=$(git rev-parse --verify --quiet "${T_COMMIT}^{commit}") \
    || { echo "$TICKET pins $T_COMMIT, which is not a commit in this clone: git pull first" >&2; exit 1; }
git merge-base --is-ancestor "$T_COMMIT_SHA" HEAD \
    || { echo "$TICKET pins $T_COMMIT, which is not HEAD or an ancestor of it: git pull / checkout first" >&2; exit 1; }
# What may differ between the ticket's commit and HEAD without changing this run (see above).
IGNORE=(':!tickets' ':!PROVENANCE.md' ':!HANDOFFS.md' ':!DECISIONS.md' ':!LESSONS.md')
case "$LANE" in
    sf) OTHER=jc ;;
    jc) OTHER=sf ;;
    *)  OTHER='' ;;   # a shared-lane run may use either lane's code, so nothing more is ignored
esac
if [[ -n "$OTHER" ]]; then
    IGNORE+=(":!reports/$OTHER" ":!workflow/rules/$OTHER" ":!workflow/scripts/$OTHER" ":!tests/$OTHER")
fi
if ! git diff --quiet "$T_COMMIT_SHA" HEAD -- . "${IGNORE[@]}"; then
    echo "HEAD differs from $TICKET's commit $T_COMMIT in files this run may use; run that code or re-ticket:" >&2
    git diff --stat "$T_COMMIT_SHA" HEAD -- . "${IGNORE[@]}" >&2
    exit 1
fi
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo "tracked files are modified; commit or stash first" >&2; exit 1; }
# Everything goes in ONE --config: a second --config flag replaces the first instead of adding to it.
# ticket_commit is what run_info.json records as the run's commit (HEAD may be a later tickets/ commit).
# submit_job is this submit job's SLURM id, for _MANIFEST.txt `job:` (rule jobs only see their own
# SLURM_JOB_ID); it is empty for `bash ... -n` and other runs outside SLURM.
CONFIG=(run_id="$T_RUN_ID" ticket_commit="$T_COMMIT_SHA" workdir="$SCRATCH_BASE/$LANE"
        submit_job="${SLURM_JOB_ID:-}")

# Tier 2 keys (the shared s3Fried keys) come from this one file and nowhere else. It holds
# two lines, AWS_ACCESS_KEY=... and AWS_SECRET_KEY=..., is chmod 600, and lives outside the repo,
# so it is never synced or committed. It is parsed, not sourced: nothing in it runs.
TIER2_CREDS=${TIER2_CREDS:-$HOME/.config/t2t-eval/tier2.env}
[[ -f "$TIER2_CREDS" ]] || { echo "no Tier 2 key file at $TIER2_CREDS" >&2; exit 1; }
[[ "$(stat -c %a "$TIER2_CREDS")" == 600 ]] || { echo "$TIER2_CREDS must be chmod 600" >&2; exit 1; }
SNAKEMAKE_STORAGE_S3_ACCESS_KEY='' SNAKEMAKE_STORAGE_S3_SECRET_KEY=''
while IFS='=' read -r key val || [[ -n "$key" ]]; do
    case "$key" in
        AWS_ACCESS_KEY) SNAKEMAKE_STORAGE_S3_ACCESS_KEY=${val%$'\r'} ;;
        AWS_SECRET_KEY) SNAKEMAKE_STORAGE_S3_SECRET_KEY=${val%$'\r'} ;;
    esac
done < "$TIER2_CREDS"
: "${SNAKEMAKE_STORAGE_S3_ACCESS_KEY:?AWS_ACCESS_KEY missing from $TIER2_CREDS}"
: "${SNAKEMAKE_STORAGE_S3_SECRET_KEY:?AWS_SECRET_KEY missing from $TIER2_CREDS}"
# The S3 plugin reads these names; SLURM passes them on to every rule job. The endpoint must be here
# too, not in the profile: the plugin marks it env_var, so Snakemake leaves it off rule jobs' command
# lines, and without it the jobs send MSI keys to AWS and get 403 (panoodle test20, 2026-11-08).
export SNAKEMAKE_STORAGE_S3_ENDPOINT_URL=https://s3.msi.umn.edu
export SNAKEMAKE_STORAGE_S3_ACCESS_KEY SNAKEMAKE_STORAGE_S3_SECRET_KEY
# Shut boto3's fallback chain (AWS_* variables, ~/.aws/credentials, ~/.aws/config) so no other
# identity can be picked up, here or in any rule job.
unset AWS_ACCESS_KEY AWS_SECRET_KEY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN \
      AWS_PROFILE AWS_DEFAULT_PROFILE
export AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null

# Container pulls: unpack on the node-local RAMdisk, never on /scratch.global (multi-hour hangs;
# see the shared containers README). The layer cache is transient and can live on scratch.
export APPTAINER_TMPDIR=/dev/shm/$USER/apptainer
export APPTAINER_CACHEDIR=/scratch.global/$USER/.apptainer_cache
mkdir -p "$APPTAINER_TMPDIR" "$APPTAINER_CACHEDIR"
trap 'rm -rf "$APPTAINER_TMPDIR"' EXIT

# shellcheck disable=SC2086  # targets are a space-separated list by design
pixi run snakemake \
    --software-deployment-method apptainer \
    --apptainer-prefix /projects/standard/fried255/shared/containers \
    --configfile config/config.yaml \
    --config "${CONFIG[@]}" \
    --profile profiles/agate \
    --rerun-triggers mtime \
    --rerun-incomplete \
    --latency-wait 60 \
    --keep-going \
    "$@" \
    $T_TARGETS
