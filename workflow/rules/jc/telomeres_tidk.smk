# M02b (jc): telomeres at both ends of every chromosome with tidk 0.3.3, ROS_Cfam_2.0 pri + alt.
# Method, settings and output formats: docs/tools/tidk.md. tidk writes its files straight into
# one Tier 2 run folder, unchanged; the shared publisher then adds the provenance files:
#   t2t/<subject>/jc/<run-id>/{<assembly>.ends.{tsv,bed,json},
#                              <assembly>_telomeric_repeat_windows.tsv, <assembly>_tidk_plot.svg,
#                              run_info.json, sha256sums.txt, _MANIFEST.txt}
# Input: jc_ncbi_fetch's md5-checked FASTA (M01's rule). Ticket target: jc_telomeres_tidk_all.
# The comparison with M02 is jc/M02b-report, not here.

JC_M02B_SPEC   = 'M02b'
JC_M02B_METRIC = 'telomeres_tidk'
JC_M02B_RULES  = ['jc_tidk_ends', 'jc_tidk_search', 'jc_tidk_plot', 'jc_telomeres_tidk_publish']
JC_M02B_RUN    = r'telomeres_tidk\.[^/]+'

# tidk settings, recorded verbatim in run_info.json (plot runs on its defaults). All are tidk
# 0.3.3's defaults written out, except --min-sequence-length, which skips sequences under 1 Mb (chrM).
JC_TIDK_ARGS = {
    'ends':   '--string TTAGGG --window 10000 --min-length 200 --max-offset 1000 --min-sequence-length 1000000',
    'search': '--string TTAGGG --window 10000 --extension tsv',
}

# Per assembly, the files tidk writes (named as tidk names them).
JC_TIDK_FILES = ['{a}.ends.tsv', '{a}.ends.bed', '{a}.ends.json',
                 '{a}_telomeric_repeat_windows.tsv', '{a}_tidk_plot.svg']

for _rule in JC_M02B_RULES:
    Path(f'logs/steps/{_rule}').mkdir(parents=True, exist_ok=True)


def jc_m02b_run():
    """The run folder: the ticket's run-id, which must be telomeres_tidk.<date>.<sha7>. The local
    dev run-id (dev.<date>.<sha7>) becomes telomeres_tidk.<date>.<sha7>, so a local `all` does not
    put M02b's run_info.json and _MANIFEST.txt in M01's dev folder."""
    metric, _, rest = run_id().partition('.')
    if metric == 'dev':
        return f'{JC_M02B_METRIC}.{rest}'
    if metric != JC_M02B_METRIC:
        raise ValueError(f'run_id {run_id()!r} is not a {JC_M02B_METRIC}.<date>.<sha7> run-id (M02b)')
    return run_id()


def jc_m02b_files(subject, run):
    return [tier2(f'{run}/{f.format(a=a)}', 'jc', subject) for a in jc_assemblies(subject) for f in JC_TIDK_FILES]


def jc_m02b_dest(subject):
    """_MANIFEST.txt `dest:`, the run folder's Tier 2 location (under tier2/ with offload off)."""
    rel = f'{subject}/jc/{jc_m02b_run()}'
    if not config.get('offload', False):
        return f'tier2/{rel}'
    bucket = config['tier2_bucket'].removeprefix('s3://').strip('/')
    return f'{JC_TIER2_REMOTE}/{bucket}/{rel}'


rule jc_telomeres_tidk_all:
    input:
        lambda wc: [tier2(f'{jc_m02b_run()}/{f}', 'jc', s)
                    for s in JC_SUBJECTS for f in ['run_info.json', 'sha256sums.txt', '_MANIFEST.txt']]


rule jc_tidk_ends:
    input:
        fasta = 'jc/ncbi/{assembly}/genomic.fna.gz'
    output:
        tsv  = tier2('{jc_m02b_run}/{assembly}.ends.tsv', 'jc', '{subject}'),
        bed  = tier2('{jc_m02b_run}/{assembly}.ends.bed', 'jc', '{subject}'),
        json = tier2('{jc_m02b_run}/{assembly}.ends.json', 'jc', '{subject}')
    wildcard_constraints:
        jc_m02b_run = JC_M02B_RUN
    params:
        args = JC_TIDK_ARGS['ends']
    resources:
        slurm_extra = lambda wc: slurm_log_path('jc_tidk_ends', wildcards_pattern=wc.assembly)
    container: config['images']['tidk']
    shell:
        '''
        tidk ends {params.args} \
            --output {wildcards.assembly} --dir "$(dirname {output.tsv})" {input.fasta}
        '''


rule jc_tidk_search:
    input:
        fasta = 'jc/ncbi/{assembly}/genomic.fna.gz'
    output:
        tsv = tier2('{jc_m02b_run}/{assembly}_telomeric_repeat_windows.tsv', 'jc', '{subject}')
    wildcard_constraints:
        jc_m02b_run = JC_M02B_RUN
    params:
        args = JC_TIDK_ARGS['search']
    resources:
        slurm_extra = lambda wc: slurm_log_path('jc_tidk_search', wildcards_pattern=wc.assembly)
    container: config['images']['tidk']
    shell:
        '''
        tidk search {params.args} \
            --output {wildcards.assembly} --dir "$(dirname {output.tsv})" {input.fasta}
        '''


rule jc_tidk_plot:
    input:
        tsv = tier2('{jc_m02b_run}/{assembly}_telomeric_repeat_windows.tsv', 'jc', '{subject}')
    output:
        svg = tier2('{jc_m02b_run}/{assembly}_tidk_plot.svg', 'jc', '{subject}')
    wildcard_constraints:
        jc_m02b_run = JC_M02B_RUN
    resources:
        slurm_extra = lambda wc: slurm_log_path('jc_tidk_plot', wildcards_pattern=wc.assembly)
    container: config['images']['tidk']
    shell:
        '''
        tidk plot --tsv {input.tsv} \
            --output "$(dirname {output.svg})/{wildcards.assembly}_tidk_plot"
        '''


rule jc_telomeres_tidk_publish:
    input:
        files = lambda wc: jc_m02b_files(wc.subject, wc.jc_m02b_run)
    output:
        run_info = tier2('{jc_m02b_run}/run_info.json', 'jc', '{subject}'),
        sha256   = tier2('{jc_m02b_run}/sha256sums.txt', 'jc', '{subject}'),
        manifest = tier2('{jc_m02b_run}/_MANIFEST.txt', 'jc', '{subject}')
    wildcard_constraints:
        jc_m02b_run = JC_M02B_RUN
    params:
        info      = lambda wc: {
            **jc_provenance(),
            'images':     {k: config['images'][k] for k in ('python', 'tidk')},
            'run_id':     wc.jc_m02b_run,
            'lane':       'jc',
            'spec_id':    JC_M02B_SPEC,
            'subject':    wc.subject,
            'assemblies': [{'assembly': a, **JC_SAMPLE[a]} for a in jc_assemblies(wc.subject)],
            'tidk_args':  JC_TIDK_ARGS,
        },
        describes = jc_spec_describes(JC_M02B_SPEC),
        dest      = lambda wc: jc_m02b_dest(wc.subject)
    resources:
        slurm_extra = lambda wc: slurm_log_path('jc_telomeres_tidk_publish', wildcards_pattern=wc.subject)
    container: config['images']['python']
    script: '../../scripts/shared/publish.py'
