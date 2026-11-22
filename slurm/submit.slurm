#!/bin/bash -l
# Submit from the repo root on agate (a git clone, kept current with `git pull`):
#   sbatch slurm/submit.slurm --ticket tickets/<id>.md
# Dry run with the same keys and settings, on the login node:
#   bash slurm/submit.slurm --ticket tickets/<id>.md -n
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

# The ticket pins what runs: `commit:`, `run_id:` and `targets:` lines, and optionally `lane:`
# (jc, sf or shared), which points the run at that lane's scratch instead of the workdir in
# config/config.yaml. `commit:` is the commit holding the rule; the ticket itself is committed after
# it, so HEAD may be later, but only tickets/ may differ between the two. Agents write tickets;
# only a human submits them. Remaining args pass through to snakemake.
SCRATCH_BASE=/scratch.global/friedlab_T2TEVAL
TICKET=''
if [[ "${1:-}" == "--ticket" ]]; then
    TICKET=${2:?--ticket needs a path, e.g. tickets/M01.md}
    shift 2
fi
[[ -n "$TICKET" ]] || { echo "usage: submit.slurm --ticket tickets/<id>.md [snakemake args]" >&2; exit 1; }
[[ -f "$TICKET" ]] || { echo "no ticket at $TICKET" >&2; exit 1; }
field() { sed -n "s/^$1:[[:space:]]*//p" "$TICKET" | head -1 | sed 's/[[:space:]]*$//'; }
T_COMMIT=$(field commit); T_RUN_ID=$(field run_id); T_TARGETS=$(field targets); T_LANE=$(field lane)
: "${T_COMMIT:?ticket has no commit: line}" "${T_RUN_ID:?ticket has no run_id: line}" "${T_TARGETS:?ticket has no targets: line}"
T_COMMIT_SHA=$(git rev-parse --verify --quiet "${T_COMMIT}^{commit}") \
    || { echo "$TICKET pins $T_COMMIT, which is not a commit in this clone: git pull first" >&2; exit 1; }
git merge-base --is-ancestor "$T_COMMIT_SHA" HEAD \
    || { echo "$TICKET pins $T_COMMIT, which is not HEAD or an ancestor of it: git pull / checkout first" >&2; exit 1; }
if ! git diff --quiet "$T_COMMIT_SHA" HEAD -- . ':!tickets'; then
    echo "HEAD differs from $TICKET's commit $T_COMMIT outside tickets/; run that code or re-ticket:" >&2
    git diff --stat "$T_COMMIT_SHA" HEAD -- . ':!tickets' >&2
    exit 1
fi
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo "tracked files are modified; commit or stash first" >&2; exit 1; }
# Everything goes in ONE --config: a second --config flag replaces the first instead of adding to it.
# ticket_commit is what run_info.json records as the run's commit (HEAD may be a later tickets/ commit).
CONFIG=(run_id="$T_RUN_ID" ticket_commit="$T_COMMIT_SHA")
if [[ -n "$T_LANE" ]]; then
    [[ "$T_LANE" =~ ^(jc|sf|shared)$ ]] || { echo "$TICKET: lane: must be jc, sf or shared, not '$T_LANE'" >&2; exit 1; }
    CONFIG+=(workdir="$SCRATCH_BASE/$T_LANE")
fi

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
