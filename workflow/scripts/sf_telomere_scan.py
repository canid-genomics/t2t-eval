"""Telomere-motif scan at both ends of every chromosome of one assembly (M02, sf lane).

Run by the `sf_telomere_scan` rule (`script:`); stdlib only, Python >= 3.11. The functions are
importable so tests/test_sf_telomeres.py can exercise them on synthetic sequence.

Which sequences: rows of the NCBI assembly report with Sequence-Role `assembled-molecule` and
Assigned-Molecule-Location/Type `Chromosome` (so chrM, unlocalized and unplaced scaffolds are
out). Every report row is written to the chromosomes table with `selected` and `reason`, and every
selected sequence must be in the FASTA with the length the report gives, or the job fails.

Method, per chromosome end (`start` = first base, `end` = last base, forward strand):
- Sequence is upper-cased (NCBI soft-masks in lower case).
- Counts: exact, non-overlapping occurrences of TTAGGG and of CCCTAA in the terminal 1, 10 and
  100 kb (the whole sequence if it is shorter). Neither motif overlaps itself, so overlapping and
  non-overlapping counts are the same.
- Arrays, per orientation, within the terminal `search_bp`: exact copies are chained into a run
  while the gap between one copy's last base and the next copy's first base is <= `max_gap_bp`
  (this bridges a few variant or damaged repeat units). Runs with >= `min_copies` copies qualify;
  the terminal array is the qualifying run nearest the sequence end. Reported: its span in bp
  (first copy's first base to last copy's last base), its number of exact copies, and its
  distance from the sequence end in bp (0 = it reaches the last base). NA if no run qualifies.
- A telomere reads CCCTAA at the start and TTAGGG at the end on the forward strand
  (`expected_motif`); both orientations are reported at both ends.

No present/absent call is made here: any call from these numbers is diagnostic-only (M03, humans).
"""
import csv
import gzip
from collections import deque
from pathlib import Path

MOTIF = 'TTAGGG'
COMPLEMENT = str.maketrans('ACGTN', 'TGCAN')

# Defaults; the rule passes the values it uses and method.txt records them.
DEFAULT_PARAMS = {
    'motif': MOTIF,
    'windows_bp': [1_000, 10_000, 100_000],
    'search_bp': 100_000,
    'max_gap_bp': 18,
    'min_copies': 10,
}

REPORT_FIELDS = {
    'Sequence-Name': 'sequence_name',
    'Sequence-Role': 'sequence_role',
    'Assigned-Molecule': 'assigned_molecule',
    'Assigned-Molecule-Location/Type': 'location_type',
    'GenBank-Accn': 'genbank_accn',
    'RefSeq-Accn': 'refseq_accn',
    'Assembly-Unit': 'assembly_unit',
    'Sequence-Length': 'report_length',
}

CHROMOSOME_COLUMNS = ['assembly', 'haplotype', 'accession', *REPORT_FIELDS.values(),
                      'fasta_length', 'selected', 'reason']


def revcomp(seq):
    return seq.translate(COMPLEMENT)[::-1]


def window_label(bp):
    return f'{bp // 1000}kb' if bp % 1000 == 0 else f'{bp}bp'


def telomere_columns(params):
    motifs = [m.lower() for m in (params['motif'], revcomp(params['motif']))]
    counts = [f'{m}_count_{window_label(w)}' for w in params['windows_bp'] for m in motifs]
    arrays = [f'{m}_array_{x}' for m in motifs for x in ('bp', 'copies', 'dist_bp')]
    return ['assembly', 'haplotype', 'accession', 'chromosome', 'seq_id', 'seq_length', 'end',
            'expected_motif', *counts, *arrays]


def parse_assembly_report(text):
    """NCBI *_assembly_report.txt -> (header dict, rows). Handles the CRLF line endings NCBI uses.

    Header lines are `# Key:  value`; the column names are the last `# Sequence-Name\t...` line.
    """
    header, columns, rows = {}, None, []
    for raw in text.splitlines():
        line = raw.rstrip('\r')
        if not line.strip():
            continue
        if line.startswith('#'):
            body = line.lstrip('#').strip()
            if body.startswith('Sequence-Name\t'):
                columns = body.split('\t')
            elif ':' in body:
                key, _, value = body.partition(':')
                header.setdefault(key.strip(), value.strip())
            continue
        if columns is None:
            raise ValueError('assembly report has data rows before its "# Sequence-Name" column line')
        values = line.split('\t')
        if len(values) != len(columns):
            raise ValueError(f'assembly report row has {len(values)} fields, expected {len(columns)}: {line!r}')
        rows.append(dict(zip(columns, values)))
    if columns is None:
        raise ValueError('assembly report has no "# Sequence-Name" column line')
    missing = set(REPORT_FIELDS) - set(columns)
    if missing:
        raise ValueError(f'assembly report lacks columns {sorted(missing)}')
    return header, rows


def select_chromosomes(rows):
    """Tag every report row with selected (yes/no) and a reason; chromosome-level molecules only."""
    out = []
    for row in rows:
        rec = {new: row[old] for old, new in REPORT_FIELDS.items()}
        if rec['sequence_role'] != 'assembled-molecule':
            rec['selected'], rec['reason'] = 'no', f"Sequence-Role is {rec['sequence_role']}"
        elif rec['location_type'] != 'Chromosome':
            rec['selected'], rec['reason'] = 'no', f"Assigned-Molecule-Location/Type is {rec['location_type']}"
        else:
            rec['selected'], rec['reason'] = 'yes', 'assembled-molecule, Chromosome'
        out.append(rec)
    return out


def open_text(path):
    path = Path(path)
    return gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()


def iter_fasta_ends(handle, keep_bp, wanted=None):
    """Yield (seq_id, length, head, tail): the first and last keep_bp bases of each record.

    Streams line by line, so memory is O(keep_bp) whatever the chromosome length. Records whose
    id is not in `wanted` (when given) are skipped without being buffered.
    """
    seq_id = None
    length = head_len = tail_len = 0
    head, tail = [], deque()

    def record():
        return seq_id, length, ''.join(head)[:keep_bp], ''.join(tail)[-keep_bp:]

    keep = False
    for line in handle:
        if line.startswith('>'):
            if seq_id is not None and keep:
                yield record()
            seq_id = line[1:].split(maxsplit=1)[0]
            keep = wanted is None or seq_id in wanted
            length = head_len = tail_len = 0
            head, tail = [], deque()
            continue
        if not keep:
            continue
        s = line.strip()
        if not s:
            continue
        length += len(s)
        if head_len < keep_bp:
            head.append(s)
            head_len += len(s)
        tail.append(s)
        tail_len += len(s)
        while tail and tail_len - len(tail[0]) >= keep_bp:
            tail_len -= len(tail.popleft())
    if seq_id is not None and keep:
        yield record()


def find_runs(seq, motif, max_gap):
    """Chain exact, non-overlapping motif copies into runs: [(start, end, copies)], 0-based half-open."""
    k = len(motif)
    runs = []
    pos = seq.find(motif)
    while pos != -1:
        if runs and pos - runs[-1][1] <= max_gap:
            start, _, copies = runs[-1]
            runs[-1] = (start, pos + k, copies + 1)
        else:
            runs.append((pos, pos + k, 1))
        pos = seq.find(motif, pos + k)
    return runs


def terminal_array(region, motif, end, max_gap, min_copies):
    """The qualifying run nearest the sequence end of a terminal region, as (bp, copies, dist_bp).

    `region` is the first (end='start') or last (end='end') stretch of the sequence, so the
    distance is measured from region[0] or region[-1] respectively. None if no run qualifies.
    """
    runs = [r for r in find_runs(region, motif, max_gap) if r[2] >= min_copies]
    if not runs:
        return None
    if end == 'start':
        start, stop, copies = runs[0]
        return stop - start, copies, start
    start, stop, copies = runs[-1]
    return stop - start, copies, len(region) - stop


def scan_end(region, end, params):
    """Count and array columns for one chromosome end. `region` is the terminal search_bp, upper case."""
    fwd = params['motif']
    motifs = (fwd, revcomp(fwd))
    row = {'end': end, 'expected_motif': revcomp(fwd) if end == 'start' else fwd}
    for w in params['windows_bp']:
        window = region[:w] if end == 'start' else region[-w:]
        for m in motifs:
            row[f'{m.lower()}_count_{window_label(w)}'] = window.count(m)
    for m in motifs:
        arr = terminal_array(region, m, end, params['max_gap_bp'], params['min_copies'])
        bp, copies, dist = arr if arr else (0, 0, 'NA')
        row[f'{m.lower()}_array_bp'] = bp
        row[f'{m.lower()}_array_copies'] = copies
        row[f'{m.lower()}_array_dist_bp'] = dist
    return row


def check_params(params):
    if params['search_bp'] < max(params['windows_bp']):
        raise ValueError('search_bp must be at least the largest window')
    if revcomp(params['motif']) == params['motif']:
        raise ValueError('motif is its own reverse complement; orientations would be indistinguishable')


def scan_assembly(fasta, report, assembly, haplotype, accession, params):
    """Scan one assembly. Returns (telomere rows, chromosome-selection rows)."""
    check_params(params)
    header, rows = parse_assembly_report(Path(report).read_text())
    report_acc = header.get('GenBank assembly accession')
    if report_acc and report_acc != accession:
        raise ValueError(f'{report} is for {report_acc}, not {accession}')

    chroms = select_chromosomes(rows)
    selected = [c for c in chroms if c['selected'] == 'yes']
    if not selected:
        raise ValueError(f'{report}: no assembled-molecule Chromosome rows')
    by_acc = {c['genbank_accn']: c for c in selected}
    if len(by_acc) != len(selected):
        raise ValueError(f'{report}: duplicate GenBank-Accn among selected chromosomes')

    found = {}
    with open_text(fasta) as handle:
        for seq_id, length, head, tail in iter_fasta_ends(handle, params['search_bp'], set(by_acc)):
            if seq_id in found:
                raise ValueError(f'{fasta}: {seq_id} appears twice')
            found[seq_id] = (length, head.upper(), tail.upper())

    missing = [a for a in by_acc if a not in found]
    if missing:
        raise ValueError(f'{fasta}: selected chromosomes missing from the FASTA: {missing}')

    telomere_rows = []
    for c in selected:
        length, head, tail = found[c['genbank_accn']]
        if str(length) != c['report_length']:
            raise ValueError(f"{c['genbank_accn']}: FASTA length {length} != report length {c['report_length']}")
        base = {'assembly': assembly, 'haplotype': haplotype, 'accession': accession,
                'chromosome': c['sequence_name'], 'seq_id': c['genbank_accn'], 'seq_length': length}
        telomere_rows.append({**base, **scan_end(head, 'start', params)})
        telomere_rows.append({**base, **scan_end(tail, 'end', params)})

    for c in chroms:
        c.update(assembly=assembly, haplotype=haplotype, accession=accession,
                 fasta_length=found.get(c['genbank_accn'], ('NA',))[0])
    return telomere_rows, chroms


def write_tsv(path, columns, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, delimiter='\t', lineterminator='\n',
                                extrasaction='raise')
        writer.writeheader()
        writer.writerows(rows)


def main(fasta, report, telomeres_out, chromosomes_out, assembly, haplotype, accession, params):
    telomere_rows, chroms = scan_assembly(fasta, report, assembly, haplotype, accession, params)
    write_tsv(telomeres_out, telomere_columns(params), telomere_rows)
    write_tsv(chromosomes_out, CHROMOSOME_COLUMNS, chroms)


if __name__ == '__main__' and 'snakemake' in globals():
    smk = snakemake  # noqa: F821 (injected by Snakemake's script: preamble)
    main(fasta=smk.input.fasta, report=smk.input.report,
         telomeres_out=smk.output.telomeres, chromosomes_out=smk.output.chromosomes,
         assembly=smk.wildcards.assembly, haplotype=smk.params.haplotype,
         accession=smk.params.accession, params=dict(smk.params.scan))
