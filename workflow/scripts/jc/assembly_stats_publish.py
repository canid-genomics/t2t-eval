"""Assemble one M01 Tier 2 run folder from per-assembly gfastats output (jc lane).

Run by the `jc_assembly_stats_publish` rule (`script:`); stdlib only, Python >= 3.11. The
functions are importable so tests/jc/test_assembly_stats.py can exercise them. Outputs land under
  t2t/<subject>/jc/<run-id>/

gfastats.tsv is long format, one value per row:
  assembly, haplotype, accession, scope, seq_id, metric, value
scope `assembly` rows are gfastats' summary (`--tabular`; seq_id NA); scope `sequence` rows are
its per-scaffold report (`--path-report --tabular`; one scaffold = one FASTA record, seq_id = its
FASTA id, `Comment` = the rest of its header line). Metric names and values are gfastats' own.
gaps.bed is gfastats' gap coordinates (`--out-coord g`: runs of N or n, 0-based half-open) with
the assembly as the BED name column.

Before writing, each assembly's three gfastats outputs are checked against each other: scaffold
count and total length, gap count and total gap length, per-scaffold gap bp, and every gap within
its scaffold. Any disagreement fails the job.

sha256sums.txt (`sha256sum -c` format) covers every file but itself and _MANIFEST.txt.
_MANIFEST.txt is the t2t bucket's header-only block of aligned `key: value` lines (describes,
source, dest, job, scope, finished, objects, size), then `lane:`, `commit:`, `run_id:` and
`spec_id:`; `objects:` and `size:` count the run folder's other files.
"""
import csv
import hashlib
import json
import os
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

GFASTATS_COLUMNS = ['assembly', 'haplotype', 'accession', 'scope', 'seq_id', 'metric', 'value']


def parse_summary(text):
    """gfastats --tabular -> {metric: value}, values as gfastats printed them."""
    summary = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        metric, sep, value = line.partition('\t')
        if not sep:
            raise ValueError(f'gfastats summary line has no tab: {line!r}')
        if metric in summary:
            raise ValueError(f'gfastats summary repeats {metric!r}')
        summary[metric] = value.strip()
    return summary


def parse_path_report(text):
    """gfastats --path-report --tabular -> rows keyed by its header (trailing empty column dropped)."""
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        raise ValueError('gfastats path report is empty')
    columns = lines[0].rstrip('\t').split('\t')
    if 'Header' not in columns or 'Total path length' not in columns:
        raise ValueError(f'gfastats path report header lacks Header/Total path length: {columns}')
    rows = []
    for line in lines[1:]:
        values = line.split('\t')
        if len(values) < len(columns) or any(values[len(columns):]):
            raise ValueError(f'gfastats path report row has {len(values)} fields, expected {len(columns)}: {line!r}')
        rows.append(dict(zip(columns, values)))
    return rows


def parse_gaps(text):
    """gfastats --out-coord g -> [(seq_id, start, end)], 0-based half-open."""
    gaps = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split('\t')
        if len(fields) != 3:
            raise ValueError(f'gap BED line has {len(fields)} fields, expected 3: {line!r}')
        gaps.append((fields[0], int(fields[1]), int(fields[2])))
    return gaps


def check_assembly(assembly, summary, sequences, gaps):
    """Cross-check one assembly's three gfastats outputs; raise on any disagreement."""
    def total(metric):
        if metric not in summary:
            raise ValueError(f'{assembly}: gfastats summary lacks {metric!r}')
        return int(summary[metric])

    lengths = {}
    for row in sequences:
        if row['Header'] in lengths:
            raise ValueError(f"{assembly}: {row['Header']} appears twice in the path report")
        lengths[row['Header']] = int(row['Total path length'])
    if len(lengths) != total('# scaffolds'):
        raise ValueError(f"{assembly}: path report has {len(lengths)} scaffolds, summary {total('# scaffolds')}")
    if sum(lengths.values()) != total('Total scaffold length'):
        raise ValueError(f'{assembly}: path report lengths do not sum to Total scaffold length')

    gap_bp = Counter()
    for seq_id, start, end in gaps:
        if seq_id not in lengths:
            raise ValueError(f'{assembly}: gap on {seq_id}, which is not in the path report')
        if not 0 <= start < end <= lengths[seq_id]:
            raise ValueError(f'{assembly}: gap {seq_id}:{start}-{end} is outside 0-{lengths[seq_id]}')
        gap_bp[seq_id] += end - start
    if len(gaps) != total('# gaps in scaffolds'):
        raise ValueError(f"{assembly}: {len(gaps)} gap BED rows, summary {total('# gaps in scaffolds')}")
    if sum(gap_bp.values()) != total('Total gap length in scaffolds'):
        raise ValueError(f'{assembly}: gap BED bp do not sum to Total gap length in scaffolds')
    for row in sequences:
        seq_id = row['Header']
        if lengths[seq_id] - int(row['Total segment length']) != gap_bp[seq_id]:
            raise ValueError(f'{assembly}: {seq_id} path - segment length != its gap BED bp')


def gfastats_rows(sample, summary, sequences):
    """Long-format rows for one assembly: summary first, then each scaffold in FASTA order."""
    base = {k: sample[k] for k in ('assembly', 'haplotype', 'accession')}
    rows = [{**base, 'scope': 'assembly', 'seq_id': 'NA', 'metric': m, 'value': v}
            for m, v in summary.items()]
    for seq in sequences:
        rows += [{**base, 'scope': 'sequence', 'seq_id': seq['Header'], 'metric': m, 'value': v}
                 for m, v in seq.items() if m not in ('Seq', 'Header')]
    return rows


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


def publish(summaries, path_reports, gap_beds, fetch_records, out, run_id, lane, subject, spec_id,
            assemblies, gfastats, provenance, describes, dest, job=None):
    """Write every file of the run folder. The first three lists are per-assembly gfastats outputs
    in `assemblies` order; `out` maps output names to local paths, all in one folder (the
    manifest's `source:`). `dest` is the folder's Tier 2 location, `job` the SLURM job id."""
    if not len(summaries) == len(path_reports) == len(gap_beds) == len(assemblies):
        raise ValueError('need one gfastats summary, path report and gap BED per assembly')
    folders = {Path(p).parent.resolve() for p in out.values()}
    if len(folders) != 1:
        raise ValueError(f'outputs span {len(folders)} folders; a run folder is one: {sorted(map(str, folders))}')
    source = folders.pop()
    source.mkdir(parents=True, exist_ok=True)

    stat_rows, bed_lines, counts = [], [], {}
    for sample, s_path, p_path, g_path in zip(assemblies, summaries, path_reports, gap_beds):
        summary = parse_summary(Path(s_path).read_text())
        sequences = parse_path_report(Path(p_path).read_text())
        gaps = parse_gaps(Path(g_path).read_text())
        check_assembly(sample['assembly'], summary, sequences, gaps)
        stat_rows += gfastats_rows(sample, summary, sequences)
        bed_lines += [f"{seq_id}\t{start}\t{end}\t{sample['assembly']}" for seq_id, start, end in gaps]
        counts[sample['assembly']] = {'sequences': len(sequences), 'gaps': len(gaps)}

    with Path(out['gfastats']).open('w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=GFASTATS_COLUMNS, delimiter='\t', lineterminator='\n',
                                extrasaction='raise')
        writer.writeheader()
        writer.writerows(stat_rows)
    Path(out['gaps']).write_text(''.join(f'{l}\n' for l in bed_lines))
    concat_tsv(fetch_records, out['inputs'])

    run_info = {
        'run_id': run_id, 'spec_id': spec_id, 'lane': lane, 'subject': subject,
        'created_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        **provenance,
        'container_python': platform.python_version(),
        'assemblies': assemblies,
        'gfastats_commands': gfastats,
        'counts': counts,
    }
    Path(out['run_info']).write_text(json.dumps(run_info, indent=2, sort_keys=True) + '\n')

    listed = ['gfastats', 'gaps', 'inputs', 'run_info']
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
    publish(summaries=list(smk.input.summary), path_reports=list(smk.input.sequences),
            gap_beds=list(smk.input.gaps), fetch_records=list(smk.input.records),
            out=dict(smk.output.items()), run_id=smk.params.run_id, lane=smk.params.lane,
            subject=smk.wildcards.subject, spec_id=smk.params.spec_id,
            assemblies=list(smk.params.assemblies), gfastats=dict(smk.params.gfastats),
            provenance=dict(smk.params.provenance), describes=smk.params.describes,
            dest=smk.params.dest, job=os.environ.get('SLURM_JOB_ID'))
