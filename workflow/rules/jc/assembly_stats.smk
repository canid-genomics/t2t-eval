# M01 (jc): assembly statistics and gap locations, ROS_Cfam_2.0 pri + alt.
# NCBI download and md5 check on jc scratch (shared fetcher), gfastats per assembly, then one
# Tier 2 run folder:
#   t2t/<subject>/jc/<run-id>/{gfastats.tsv,gaps.bed,inputs.tsv,run_info.json,sha256sums.txt,
#                              _MANIFEST.txt}
# Ticket target: jc_assembly_stats_all. Table layout: workflow/scripts/jc/assembly_stats_publish.py.
import csv
import hashlib
import json
import re
import subprocess
from importlib.metadata import PackageNotFoundError, version

from snakemake import __version__ as JC_SNAKEMAKE_VERSION   # dist metadata says 0.0.0 in the pixi env

JC_M01_SPEC   = 'M01'
JC_M01_METRIC = 'assembly_stats'
JC_M01_RULES  = ['jc_ncbi_fetch', 'jc_gfastats', 'jc_assembly_stats_publish']
JC_M01_FILES  = ['gfastats.tsv', 'gaps.bed', 'inputs.tsv', 'run_info.json', 'sha256sums.txt',
                 '_MANIFEST.txt']

# gfastats calls, recorded verbatim in run_info.json. Summary totals, one row per scaffold
# (FASTA record), and gaps (runs of N or n) as 0-based half-open BED.
JC_GFASTATS_ARGS = {
    'summary':   '--tabular',
    'sequences': '--path-report --tabular',
    'gaps':      '--out-coord g',
}

# _MANIFEST.txt `dest:` names the bucket through this remote, as the t2t bucket's manifests do.
JC_TIER2_REMOTE = 's3Fried'

JC_SAMPLE   = samples_df.set_index('assembly').to_dict('index')
JC_SUBJECTS = sorted(set(SUBJECT.values()))

# SLURM does not create --output/--error directories; make this lane's per-rule ones up front.
# The cwd here is the workdir (scratch on agate), where slurm_log_path() points.
for _rule in JC_M01_RULES:
    Path(f'logs/steps/{_rule}').mkdir(parents=True, exist_ok=True)


def _jc_git(*args):
    try:
        return subprocess.run(['git', '-C', str(REPO_ROOT), *args], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'


def _jc_version(dist):
    try:
        return version(dist)
    except PackageNotFoundError:
        return 'not installed'


def jc_provenance():
    """Host-side provenance for run_info.json. `commit` is the ticket's (--config ticket_commit,
    set by slurm/submit.slurm); a local run without a ticket records HEAD."""
    head = _jc_git('rev-parse', 'HEAD')
    commit = config.get('ticket_commit')
    if commit is not None and not re.fullmatch(r'[0-9a-f]{40}', str(commit)):
        raise ValueError(f'ticket_commit {commit!r} is not a full 40-hex sha')
    return {
        'commit':        str(commit or head),
        'head':          head,
        'tracked_dirty': _jc_git('status', '--porcelain', '--untracked-files=no') != '',
        'config_sha256': hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest(),
        'images':        {k: config['images'][k] for k in ('python', 'gfastats')},
        'versions':      {'snakemake': JC_SNAKEMAKE_VERSION,
                          **{d: _jc_version(d) for d in ('snakemake-executor-plugin-slurm',
                                                         'snakemake-storage-plugin-s3')}},
    }


def jc_m01_run_id():
    """This run's id; refuses another metric's run-id so M01 never lands in a wrong-named folder."""
    rid = run_id()
    if rid.split('.')[0] not in (JC_M01_METRIC, 'dev'):
        raise ValueError(f'run_id {rid!r} is not a {JC_M01_METRIC}.<date>.<sha7> run-id (M01)')
    return rid


def jc_m01_out(subject, name):
    return tier2(f'{jc_m01_run_id()}/{name}', 'jc', subject)


def jc_assemblies(subject):
    return [a for a in ASSEMBLIES if SUBJECT[a] == subject]


def jc_spec_describes(spec_id):
    """_MANIFEST.txt `describes:`, the SPEC.tsv row the run folder is a product of."""
    lines = [l for l in (REPO_ROOT / 'SPEC.tsv').read_text().splitlines() if l.strip() and not l.startswith('#')]
    titles = [r['title'] for r in csv.DictReader(lines, delimiter='\t') if r['id'] == spec_id]
    if len(titles) != 1:
        raise ValueError(f'SPEC.tsv has {len(titles)} rows with id {spec_id!r}, not 1')
    return f'SPEC.tsv {spec_id}: {titles[0]}'


def jc_m01_dest(subject):
    """_MANIFEST.txt `dest:`, the run folder's Tier 2 location (under tier2/ with offload off)."""
    rel = f'{subject}/jc/{jc_m01_run_id()}'
    if not config.get('offload', False):
        return f'tier2/{rel}'
    bucket = config['tier2_bucket'].removeprefix('s3://').strip('/')
    return f'{JC_TIER2_REMOTE}/{bucket}/{rel}'


rule jc_assembly_stats_all:
    input:
        lambda wc: [jc_m01_out(s, f) for s in JC_SUBJECTS for f in JC_M01_FILES]


rule jc_ncbi_fetch:
    output:
        fasta  = 'jc/ncbi/{assembly}/genomic.fna.gz',
        report = 'jc/ncbi/{assembly}/assembly_report.txt',
        md5s   = 'jc/ncbi/{assembly}/md5checksums.txt',
        record = 'jc/ncbi/{assembly}/fetch.tsv'
    params:
        accession = lambda wc: JC_SAMPLE[wc.assembly]['accession']
    resources:
        slurm_extra = lambda wc: slurm_log_path('jc_ncbi_fetch', wildcards_pattern='{assembly}')
    container: config['images']['python']
    script: '../../scripts/shared/ncbi_fetch.py'


rule jc_gfastats:
    input:
        fasta = 'jc/ncbi/{assembly}/genomic.fna.gz'
    output:
        summary   = 'jc/{run_id}/{assembly}.gfastats.summary.tsv',
        sequences = 'jc/{run_id}/{assembly}.gfastats.sequences.tsv',
        gaps      = 'jc/{run_id}/{assembly}.gfastats.gaps.bed'
    wildcard_constraints:
        run_id = r'[^/]+'
    params:
        summary   = JC_GFASTATS_ARGS['summary'],
        sequences = JC_GFASTATS_ARGS['sequences'],
        gaps      = JC_GFASTATS_ARGS['gaps']
    threads: 4
    resources:
        slurm_extra = lambda wc: slurm_log_path('jc_gfastats', wildcards_pattern='{assembly}')
    container: config['images']['gfastats']
    shell:
        '''
        gfastats {input.fasta} -j {threads} {params.summary} > {output.summary}
        gfastats {input.fasta} -j {threads} {params.sequences} > {output.sequences}
        gfastats {input.fasta} -j {threads} {params.gaps} > {output.gaps}
        '''


rule jc_assembly_stats_publish:
    input:
        summary   = lambda wc: [f'jc/{jc_m01_run_id()}/{a}.gfastats.summary.tsv' for a in jc_assemblies(wc.subject)],
        sequences = lambda wc: [f'jc/{jc_m01_run_id()}/{a}.gfastats.sequences.tsv' for a in jc_assemblies(wc.subject)],
        gaps      = lambda wc: [f'jc/{jc_m01_run_id()}/{a}.gfastats.gaps.bed' for a in jc_assemblies(wc.subject)],
        records   = lambda wc: [f'jc/ncbi/{a}/fetch.tsv' for a in jc_assemblies(wc.subject)]
    output:
        gfastats = tier2(f'{run_id()}/gfastats.tsv', 'jc', '{subject}'),
        gaps     = tier2(f'{run_id()}/gaps.bed', 'jc', '{subject}'),
        inputs   = tier2(f'{run_id()}/inputs.tsv', 'jc', '{subject}'),
        run_info = tier2(f'{run_id()}/run_info.json', 'jc', '{subject}'),
        sha256   = tier2(f'{run_id()}/sha256sums.txt', 'jc', '{subject}'),
        manifest = tier2(f'{run_id()}/_MANIFEST.txt', 'jc', '{subject}')
    params:
        run_id     = run_id(),
        lane       = 'jc',
        spec_id    = JC_M01_SPEC,
        assemblies = lambda wc: [{'assembly': a, **JC_SAMPLE[a]} for a in jc_assemblies(wc.subject)],
        gfastats   = {name: f'gfastats <genomic.fna.gz> -j <threads> {args}' for name, args in JC_GFASTATS_ARGS.items()},
        provenance = lambda wc: jc_provenance(),
        describes  = jc_spec_describes(JC_M01_SPEC),
        dest       = lambda wc: jc_m01_dest(wc.subject)
    resources:
        slurm_extra = lambda wc: slurm_log_path('jc_assembly_stats_publish', wildcards_pattern='{subject}')
    container: config['images']['python']
    script: '../../scripts/jc/assembly_stats_publish.py'
