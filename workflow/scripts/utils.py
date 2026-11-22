from pathlib import Path

# REPO_ROOT is defined in Snakefile and made available via include:.

def _abs(p):
    """Resolve repo-root-relative paths to absolute. Absolute paths pass through.

    Sheet-listed external paths in *.local.tsv are written relative to the repo
    root; with workdir: set, Snakemake would otherwise interpret them against
    the workdir. Use this whenever a helper returns a path read from a sheet.
    """
    p_str = str(p)
    if p_str.startswith('/'):
        return p_str
    return str(REPO_ROOT / p_str)


def slurm_log_path(rule_name, wildcards_pattern=None, subdir=None, extra=''):
    """Build the slurm_extra string that routes a rule's stderr/stdout to
    logs/steps/{rule_name}/{subdir}/%j.{wildcards_pattern}.{out,err}.

    This layout is what scripts/triage/parse_submit_log.py expects when it
    reconstructs per-step stderr paths from each rule's slurm_extra template.
    Don't deviate from it — the triage tooling breaks silently if you do.

    Args:
        rule_name: name of the rule (becomes the first directory under logs/steps/)
        wildcards_pattern: pattern for filename, e.g. '{sample}_{file_id}'
        subdir: optional subdirectory, e.g. '{sample}'
        extra: additional SLURM flags appended (e.g. '--gres=gpu:a100:1')
    """
    base_path = f'logs/steps/{rule_name}'

    if subdir:
        base_path += f'/{subdir}'

    if wildcards_pattern:
        result = f'--output={base_path}/%j.{wildcards_pattern}.out --error={base_path}/%j.{wildcards_pattern}.err'
    else:
        result = f'--output={base_path}/%j.out --error={base_path}/%j.err'

    if extra:
        result += f' {extra}'

    return result


def tier2(path, lane, subject=None):
    """Tier 2 location for a finished output, under the owning lane.

    With a subject (e.g. '{subject}' -> ROS_Cfam_2.0) the layout is the t2t bucket's dog-first
    one: s3://t2t/<subject>/<lane>/<path>. Rules write only under their own lane; cross-lane
    inputs are read with the other lane's name. With offload off (local and CI dry runs) the same
    path is local, under tier2/.
    """
    if lane not in config['lanes']:
        raise ValueError(f'unknown lane {lane!r}; add it to config["lanes"]')
    rel = f'{subject}/{lane}/{path}' if subject else f'{lane}/{path}'
    if config.get('offload', False):
        return storage.s3(f"{config['tier2_bucket'].rstrip('/')}/{rel}")
    return f'tier2/{rel}'


# What run_id() gives without a ticket, so the workflow still parses (`snakemake --list`, `--unlock`
# with config.yaml). Clearly fake, and nothing goes to Tier 2 under it: refuse_unset_run_id() (the
# Snakefile's onstart) stops an offload run before any job, and publish scripts refuse it too.
RUN_ID_UNSET = 'unset.0000-00-00.0000000'


def run_id():
    """This submission's run-id, <metric>.<YYYY-MM-DD>.<sha7>, from the ticket via --config, or
    RUN_ID_UNSET when no ticket set it."""
    return config.get('run_id') or RUN_ID_UNSET


def refuse_unset_run_id():
    """Refuse a run that would write Tier 2 (offload on) with no ticket run_id."""
    if config.get('offload', False) and run_id() == RUN_ID_UNSET:
        raise ValueError(f'run_id is unset ({RUN_ID_UNSET}) and offload is on: nothing may go to '
                         'Tier 2 without a ticket; submit with slurm/submit.slurm --ticket '
                         'tickets/<lane>/<id>.md')
