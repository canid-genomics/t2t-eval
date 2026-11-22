"""Assemble one M02 Tier 2 run folder: merged tables, method.txt, run_info.json, sha256s, manifest.

Run by the `sf_telomeres_publish` rule (`script:`); stdlib only, Python >= 3.11. Inputs are the
per-assembly scan tables and NCBI fetch records for one subject; outputs are what lands under
  t2t/<subject>/sf/<run-id>/
sha256sums.txt (`sha256sum -c` format) covers every file but itself and _MANIFEST.txt.
_MANIFEST.txt is the t2t bucket's header-only block of aligned `key: value` lines (describes,
source, dest, job, scope, finished, objects, size), then `lane:`, `commit:`, `run_id:` and
`spec_id:`. It has no per-file rows; `objects:` and `size:` count the run folder's other files.
"""
import hashlib
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

# workflow/scripts/utils.py RUN_ID_UNSET: run_id() without a ticket. A run folder never has it.
RUN_ID_UNSET = 'unset.0000-00-00.0000000'


def concat_tsv(paths, dest):
    """Concatenate TSVs that share one header line; refuse if the headers differ."""
    header, body = None, []
    for p in paths:
        lines = Path(p).read_text().splitlines()
        if not lines:
            raise ValueError(f'{p} is empty')
        if header is None:
            header = lines[0]
        elif lines[0] != header:
            raise ValueError(f'{p}: header differs from {paths[0]}')
        body.extend(lines[1:])
    Path(dest).write_text('\n'.join([header, *body]) + '\n')
    return len(body)


def human_size(n):
    """Bytes in binary units with no space, as the bucket's manifests write them (e.g. 68GiB)."""
    size, units = float(n), ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
    unit = units.pop(0)
    while size >= 1024 and units:
        size, unit = size / 1024, units.pop(0)
    if unit == 'B' or size >= 10:
        return f'{size:.0f}{unit}'
    return f"{f'{size:.1f}'.removesuffix('.0')}{unit}"


def manifest_text(fields):
    """`key: value` lines with the values aligned one space past the longest key's colon."""
    width = max(len(k) for k in fields) + 1
    return ''.join(f'{k + ":":<{width}} {v}\n' for k, v in fields.items())


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def method_text(run_id, subject, scan, scan_script, assemblies, n_rows):
    windows = ', '.join(f'{w:,} bp' for w in scan['windows_bp'])
    lines = [
        f'M02 telomere-motif scan, {subject}, run {run_id}',
        '',
        'Tool: workflow/scripts/sf/telomere_scan.py at the commit in run_info.json',
        f"  sha256 {scan_script['sha256']}",
        f'  Python {platform.python_version()} (container image in run_info.json), stdlib only',
        '',
        'Inputs: NCBI GenBank FASTA and assembly report for each haplotype, downloaded by',
        'workflow/scripts/sf/ncbi_fetch.py and checked against NCBI md5checksums.txt (inputs.tsv).',
    ]
    lines += [f"  {a['haplotype']}: {a['assembly']} {a['accession']}" for a in assemblies]
    lines += [
        '',
        'Sequences: rows of the NCBI assembly report with Sequence-Role = assembled-molecule and',
        'Assigned-Molecule-Location/Type = Chromosome. All report rows are in chromosomes.tsv with',
        '`selected` and `reason`; each selected GenBank-Accn was found in the FASTA with the',
        'report length. chrM, unlocalized and unplaced scaffolds are not scanned.',
        '',
        'Per chromosome end (start = first base, end = last base, forward strand), upper-cased:',
        f"  counts: exact non-overlapping {scan['motif']} and its reverse complement in the terminal",
        f'          {windows} (whole sequence if shorter)',
        f"  arrays: within the terminal {scan['search_bp']:,} bp, exact copies chained while the gap",
        f"          between copies is <= {scan['max_gap_bp']} bp; runs of >= {scan['min_copies']} copies qualify;",
        '          the qualifying run nearest the end is reported as span bp, exact copies and',
        '          distance from the sequence end (0 = reaches the last base); NA if none.',
        '  expected_motif: CCCTAA at the start, TTAGGG at the end. Both are reported at both ends.',
        '',
        f'Parameters: {json.dumps(scan, sort_keys=True)}',
        f'Rows in telomeres.tsv: {n_rows} (one per chromosome end per haplotype)',
        '',
        'Status: diagnostic-only. No present/absent or T2T call is made from these numbers here.',
    ]
    return '\n'.join(lines) + '\n'


def publish(scan_tables, chromosome_tables, fetch_records, out, run_id, lane, subject, spec_id,
            assemblies, scan, scan_script, provenance, describes, dest, job=None):
    """Write every file of the run folder; `out` maps output names to local paths, all in one
    folder (the manifest's `source:`). `dest` is the folder's Tier 2 location, `job` the SLURM job
    id (None outside SLURM). Refuses the no-ticket run_id before writing anything."""
    if run_id == RUN_ID_UNSET:
        raise ValueError(f'run_id is unset ({RUN_ID_UNSET}): a Tier 2 run folder needs a ticket '
                         'run_id (slurm/submit.slurm --ticket tickets/sf/<id>.md)')
    folders = {Path(p).parent.resolve() for p in out.values()}
    if len(folders) != 1:
        raise ValueError(f'outputs span {len(folders)} folders; a run folder is one: {sorted(map(str, folders))}')
    source = folders.pop()
    source.mkdir(parents=True, exist_ok=True)
    n_rows = concat_tsv(scan_tables, out['telomeres'])
    concat_tsv(chromosome_tables, out['chromosomes'])
    concat_tsv(fetch_records, out['inputs'])
    Path(out['method']).write_text(method_text(run_id, subject, scan, scan_script, assemblies, n_rows))

    created = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    run_info = {
        'run_id': run_id, 'spec_id': spec_id, 'lane': lane, 'subject': subject,
        'created_utc': created,
        **provenance,
        'container_python': platform.python_version(),
        'assemblies': assemblies,
        'scan_params': scan,
        'scan_script': scan_script,
    }
    Path(out['run_info']).write_text(json.dumps(run_info, indent=2, sort_keys=True) + '\n')

    listed = ['telomeres', 'chromosomes', 'inputs', 'method', 'run_info']
    Path(out['sha256']).write_text(''.join(f'{sha256_file(out[k])}  {Path(out[k]).name}\n' for k in listed))

    objects = [Path(p) for k, p in out.items() if k != 'manifest']
    fields = {
        'describes': describes,
        'source':    source,
        'dest':      dest,
        'job':       job or 'NA',
        'scope':     'metric',
        'finished':  datetime.now().astimezone().isoformat(timespec='seconds'),
        'objects':   len(objects),
        'size':      human_size(sum(p.stat().st_size for p in objects)),
        'lane':      lane,
        'commit':    provenance['commit'],
        'run_id':    run_id,
        'spec_id':   spec_id,
    }
    Path(out['manifest']).write_text(manifest_text(fields))


if __name__ == '__main__' and 'snakemake' in globals():
    smk = snakemake  # noqa: F821 (injected by Snakemake's script: preamble)
    publish(scan_tables=list(smk.input.telomeres), chromosome_tables=list(smk.input.chromosomes),
            fetch_records=list(smk.input.records), out=dict(smk.output.items()),
            run_id=smk.params.run_id, lane=smk.params.lane, subject=smk.wildcards.subject,
            spec_id=smk.params.spec_id, assemblies=list(smk.params.assemblies),
            scan=dict(smk.params.scan), scan_script=dict(smk.params.scan_script),
            provenance=dict(smk.params.provenance), describes=smk.params.describes,
            dest=smk.params.dest, job=os.environ.get('SLURM_JOB_ID'))
