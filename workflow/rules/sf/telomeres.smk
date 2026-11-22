# M02 (sf): telomere-motif scan at both ends of every chromosome, ROS_Cfam_2.0 pri + alt.
# NCBI download and md5 check on sf scratch, one scan per assembly, then one Tier 2 run folder:
#   t2t/<subject>/sf/<run-id>/{telomeres,chromosomes,inputs}.tsv, method.txt, run_info.json,
#                             sha256sums.txt, _MANIFEST.txt
# Ticket target: sf_telomeres_all. Method and parameters: workflow/scripts/sf/telomere_scan.py.
import csv
import hashlib
import json
import re
import subprocess
from importlib.metadata import PackageNotFoundError, version

from snakemake import __version__ as SF_SNAKEMAKE_VERSION   # dist metadata says 0.0.0 in the pixi env

SF_M02_SPEC   = 'M02'
SF_M02_METRIC = 'telomeres'
SF_M02_RULES  = ['sf_ncbi_fetch', 'sf_telomere_scan', 'sf_telomeres_publish']
SF_M02_FILES  = ['telomeres.tsv', 'chromosomes.tsv', 'inputs.tsv', 'method.txt', 'run_info.json',
                 'sha256sums.txt', '_MANIFEST.txt']

# Scan parameters, recorded verbatim in method.txt and run_info.json.
SF_TELOMERE_SCAN = {
    'motif':      'TTAGGG',
    'windows_bp': [1_000, 10_000, 100_000],
    'search_bp':  100_000,
    'max_gap_bp': 18,
    'min_copies': 10,
}

# _MANIFEST.txt `dest:` names the bucket through this remote, as the t2t bucket's manifests do.
SF_TIER2_REMOTE = 's3Fried'

SF_SAMPLE    = samples_df.set_index('assembly').to_dict('index')
SF_SUBJECTS  = sorted(set(SUBJECT.values()))
SF_SCAN_PY   = REPO_ROOT / 'workflow/scripts/sf/telomere_scan.py'

# SLURM does not create --output/--error directories; make this lane's per-rule ones up front.
# The cwd here is the workdir (scratch on agate), where slurm_log_path() points.
for _rule in SF_M02_RULES:
    Path(f'logs/steps/{_rule}').mkdir(parents=True, exist_ok=True)


def _sf_git(*args):
    try:
        return subprocess.run(['git', '-C', str(REPO_ROOT), *args], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'


def _sf_version(dist):
    try:
        return version(dist)
    except PackageNotFoundError:
        return 'not installed'


def sf_provenance():
    """Host-side provenance for run_info.json. `commit` is the ticket's (--config ticket_commit,
    set by slurm/submit.slurm); a local run without a ticket records HEAD."""
    head = _sf_git('rev-parse', 'HEAD')
    commit = config.get('ticket_commit')
    if commit is not None and not re.fullmatch(r'[0-9a-f]{40}', str(commit)):
        raise ValueError(f'ticket_commit {commit!r} is not a full 40-hex sha')
    return {
        'commit':        str(commit or head),
        'head':          head,
        'tracked_dirty': _sf_git('status', '--porcelain', '--untracked-files=no') != '',
        'config_sha256': hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest(),
        'images':        {'python': config['images']['python']},
        'versions':      {'snakemake': SF_SNAKEMAKE_VERSION,
                          **{d: _sf_version(d) for d in ('snakemake-executor-plugin-slurm',
                                                         'snakemake-storage-plugin-s3')}},
    }


def sf_m02_run_id():
    """This run's id; refuses another metric's run-id so M02 never lands in a wrong-named folder.
    The no-ticket RUN_ID_UNSET passes, so the DAG still builds (`snakemake --unlock` builds it);
    the Snakefile's onstart and the publish script refuse it before anything is written."""
    rid = run_id()
    if rid != RUN_ID_UNSET and rid.split('.')[0] not in (SF_M02_METRIC, 'dev'):
        raise ValueError(f'run_id {rid!r} is not a {SF_M02_METRIC}.<date>.<sha7> run-id (M02)')
    return rid


def sf_m02_out(subject, name):
    return tier2(f'{sf_m02_run_id()}/{name}', 'sf', subject)


def sf_assemblies(subject):
    return [a for a in ASSEMBLIES if SUBJECT[a] == subject]


def sf_spec_describes(spec_id):
    """_MANIFEST.txt `describes:`, the SPEC.tsv row the run folder is a product of."""
    lines = [l for l in (REPO_ROOT / 'SPEC.tsv').read_text().splitlines() if l.strip() and not l.startswith('#')]
    titles = [r['title'] for r in csv.DictReader(lines, delimiter='\t') if r['id'] == spec_id]
    if len(titles) != 1:
        raise ValueError(f'SPEC.tsv has {len(titles)} rows with id {spec_id!r}, not 1')
    return f'SPEC.tsv {spec_id}: {titles[0]}'


def sf_m02_dest(subject):
    """_MANIFEST.txt `dest:`, the run folder's Tier 2 location (under tier2/ with offload off)."""
    rel = f'{subject}/sf/{sf_m02_run_id()}'
    if not config.get('offload', False):
        return f'tier2/{rel}'
    bucket = config['tier2_bucket'].removeprefix('s3://').strip('/')
    return f'{SF_TIER2_REMOTE}/{bucket}/{rel}'


rule sf_telomeres_all:
    input:
        lambda wc: [sf_m02_out(s, f) for s in SF_SUBJECTS for f in SF_M02_FILES]


rule sf_ncbi_fetch:
    output:
        fasta  = 'sf/ncbi/{assembly}/genomic.fna.gz',
        report = 'sf/ncbi/{assembly}/assembly_report.txt',
        md5s   = 'sf/ncbi/{assembly}/md5checksums.txt',
        record = 'sf/ncbi/{assembly}/fetch.tsv'
    params:
        accession = lambda wc: SF_SAMPLE[wc.assembly]['accession']
    resources:
        slurm_extra = lambda wc: slurm_log_path('sf_ncbi_fetch', wildcards_pattern=wc.assembly)
    container: config['images']['python']
    script: '../../scripts/sf/ncbi_fetch.py'


rule sf_telomere_scan:
    input:
        fasta  = 'sf/ncbi/{assembly}/genomic.fna.gz',
        report = 'sf/ncbi/{assembly}/assembly_report.txt'
    output:
        telomeres   = 'sf/{run_id}/{assembly}.telomeres.tsv',
        chromosomes = 'sf/{run_id}/{assembly}.chromosomes.tsv'
    wildcard_constraints:
        run_id = r'[^/]+'
    params:
        haplotype = lambda wc: SF_SAMPLE[wc.assembly]['haplotype'],
        accession = lambda wc: SF_SAMPLE[wc.assembly]['accession'],
        scan      = SF_TELOMERE_SCAN
    resources:
        slurm_extra = lambda wc: slurm_log_path('sf_telomere_scan', wildcards_pattern=wc.assembly)
    container: config['images']['python']
    script: '../../scripts/sf/telomere_scan.py'


rule sf_telomeres_publish:
    input:
        telomeres   = lambda wc: [f'sf/{sf_m02_run_id()}/{a}.telomeres.tsv' for a in sf_assemblies(wc.subject)],
        chromosomes = lambda wc: [f'sf/{sf_m02_run_id()}/{a}.chromosomes.tsv' for a in sf_assemblies(wc.subject)],
        records     = lambda wc: [f'sf/ncbi/{a}/fetch.tsv' for a in sf_assemblies(wc.subject)]
    output:
        telomeres   = tier2(f'{run_id()}/telomeres.tsv', 'sf', '{subject}'),
        chromosomes = tier2(f'{run_id()}/chromosomes.tsv', 'sf', '{subject}'),
        inputs      = tier2(f'{run_id()}/inputs.tsv', 'sf', '{subject}'),
        method      = tier2(f'{run_id()}/method.txt', 'sf', '{subject}'),
        run_info    = tier2(f'{run_id()}/run_info.json', 'sf', '{subject}'),
        sha256      = tier2(f'{run_id()}/sha256sums.txt', 'sf', '{subject}'),
        manifest    = tier2(f'{run_id()}/_MANIFEST.txt', 'sf', '{subject}')
    params:
        run_id      = run_id(),
        lane        = 'sf',
        spec_id     = SF_M02_SPEC,
        scan        = SF_TELOMERE_SCAN,
        assemblies  = lambda wc: [{'assembly': a, **SF_SAMPLE[a]} for a in sf_assemblies(wc.subject)],
        scan_script = {'path': 'workflow/scripts/sf/telomere_scan.py',
                       'sha256': hashlib.sha256(SF_SCAN_PY.read_bytes()).hexdigest()},
        provenance  = lambda wc: sf_provenance(),
        describes   = sf_spec_describes(SF_M02_SPEC),
        dest        = lambda wc: sf_m02_dest(wc.subject)
    resources:
        slurm_extra = lambda wc: slurm_log_path('sf_telomeres_publish', wildcards_pattern=wc.subject)
    container: config['images']['python']
    script: '../../scripts/sf/telomeres_publish.py'
