"""Assemble one M02 Tier 2 run folder: merged tables, method.txt, run_info.json, sha256s, manifest.

Run by the `sf_telomeres_publish` rule (`script:`); stdlib only, Python >= 3.11. Inputs are the
per-assembly scan tables and NCBI fetch records for one subject; outputs are what lands under
  t2t/<subject>/sf/<run-id>/
sha256sums.txt (`sha256sum -c` format) covers every file but itself and _MANIFEST.txt; the
manifest lists every file with its size and sha256, after `lane:` and `commit:` lines.
"""
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path


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
        'Tool: workflow/scripts/sf_telomere_scan.py at the commit in run_info.json',
        f"  sha256 {scan_script['sha256']}",
        f'  Python {platform.python_version()} (container image in run_info.json), stdlib only',
        '',
        'Inputs: NCBI GenBank FASTA and assembly report for each haplotype, downloaded by',
        'workflow/scripts/sf_ncbi_fetch.py and checked against NCBI md5checksums.txt (inputs.tsv).',
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
            assemblies, scan, scan_script, provenance):
    """Write every file of the run folder; `out` maps output names to local paths."""
    for p in out.values():
        Path(p).parent.mkdir(parents=True, exist_ok=True)
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
    sums = [(sha256_file(out[k]), Path(out[k]).name, Path(out[k]).stat().st_size) for k in listed]
    Path(out['sha256']).write_text(''.join(f'{h}  {name}\n' for h, name, _ in sums))
    sums.append((sha256_file(out['sha256']), Path(out['sha256']).name, Path(out['sha256']).stat().st_size))

    manifest = [
        f'run_id: {run_id}',
        f'lane: {lane}',
        f"commit: {provenance['commit']}",
        f'subject: {subject}',
        f'spec_id: {spec_id}',
        f'created_utc: {created}',
        'files (sha256, bytes, name):',
        *(f'{h}\t{size}\t{name}' for h, name, size in sums),
    ]
    Path(out['manifest']).write_text('\n'.join(manifest) + '\n')


if __name__ == '__main__' and 'snakemake' in globals():
    smk = snakemake  # noqa: F821 (injected by Snakemake's script: preamble)
    publish(scan_tables=list(smk.input.telomeres), chromosome_tables=list(smk.input.chromosomes),
            fetch_records=list(smk.input.records), out=dict(smk.output.items()),
            run_id=smk.params.run_id, lane=smk.params.lane, subject=smk.wildcards.subject,
            spec_id=smk.params.spec_id, assemblies=list(smk.params.assemblies),
            scan=dict(smk.params.scan), scan_script=dict(smk.params.scan_script),
            provenance=dict(smk.params.provenance))
