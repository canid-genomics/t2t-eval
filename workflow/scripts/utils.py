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


def run_id():
    """This submission's run-id, <metric>.<YYYY-MM-DD>.<sha7>, from the ticket via --config."""
    rid = config.get('run_id')
    if not rid:
        raise ValueError('run_id is unset: submit with slurm/submit.slurm --ticket tickets/<id>.md')
    return rid
