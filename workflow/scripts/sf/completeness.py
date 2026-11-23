"""Per-chromosome table and figure of expected-motif arrays at the ends and gaps (M03, sf lane).

Joins M02 (sf) `telomeres.tsv` with M01 (jc) `gfastats.tsv` and `gaps.bed` and writes, into
--out-dir:
  completeness.tsv          one row per haplotype x chromosome (columns: COLUMNS below)
  completeness.method.txt   inputs with sha256, thresholds, status rules, versions
  completeness.pdf / .png   the figure (PNG at 300 dpi)

Local, no sequence data. Python >= 3.11; the table needs only the stdlib, the figure needs
matplotlib (the pixi `fig` environment), imported only when the figure is drawn:
  pixi run --manifest-path <main checkout>/pixi.toml -e fig python \\
      workflow/scripts/sf/completeness.py --telomeres ... --gfastats ... --gaps ... --out-dir ...

Inputs:
- telomeres.tsv (M02): one row per chromosome end per haplotype; `expected_motif` is CCCTAA at
  `start` and TTAGGG at `end`. Per end, only the expected motif's columns are used:
  `<motif>_array_copies`, `<motif>_array_dist_bp` (NA when no qualifying array) and
  `<motif>_count_10kb`.
- gfastats.tsv (M01): long format `assembly haplotype accession scope seq_id metric value`; the
  `scope=sequence` rows give each FASTA record's `Total path length`.
- gaps.bed (M01): `seq_id start end assembly`, 0-based half-open runs of N/n.
Rows join on (assembly, seq_id): both come from the same NCBI FASTA. Every M02 chromosome must have
an M01 sequence row with the same haplotype, accession and length, or this fails. M01 sequences
that M02 did not scan (unplaced scaffolds, chrM) and their gaps are left out.

An end has an expected-motif array if its array has >= `min_copies` exact copies and lies
<= `max_dist_bp` from the sequence end (dist_bp 0 = reaches the last base; NA = none). Status:
  array_both_ends_no_gaps    arrays at both ends, no gap in the sequence
  array_both_ends_with_gaps  arrays at both ends, >= 1 gap
  array_one_end              an array at exactly one end (any number of gaps)
  no_array                   an array at neither end (any number of gaps)
The status is a fixed rule on these numbers, not a call about the assembly.

The figure's words are checked against FORBIDDEN_WORDS before it is saved.
"""
import argparse
import csv
import hashlib
import platform
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

DEFAULT_MIN_COPIES = 10
# 10 kb, one of M02's own windows: an array counts only if it starts within 10 kb of the end, so an
# interstitial array further in never counts as terminal. On ROS_Cfam_2.0 any cutoff >= 3,356 bp
# gives the approved M02 reading (147/156 ends). Jonah proposed it, Steven agreed, 2026-11-23
# (replacing 100 kb, M02's whole search window, PR #9).
DEFAULT_MAX_DIST_BP = 10_000

EXPECTED_MOTIF = {'start': 'CCCTAA', 'end': 'TTAGGG'}
HAPLOTYPE_ORDER = ['pri', 'alt']

STATUSES = ['array_both_ends_no_gaps', 'array_both_ends_with_gaps', 'array_one_end', 'no_array']

COLUMNS = ['assembly', 'haplotype', 'accession', 'chromosome', 'seq_id', 'length_bp',
           'start_motif', 'start_array_copies', 'start_array_dist_bp', 'start_count_10kb',
           'start_array',
           'end_motif', 'end_array_copies', 'end_array_dist_bp', 'end_count_10kb', 'end_array',
           'n_gaps', 'gap_bp', 'status']

TELOMERE_COLUMNS = ['assembly', 'haplotype', 'accession', 'chromosome', 'seq_id', 'seq_length',
                    'end', 'expected_motif',
                    *(f'{m}_{k}' for m in ('ttaggg', 'ccctaa')
                      for k in ('count_10kb', 'array_copies', 'array_dist_bp'))]
GFASTATS_COLUMNS = ['assembly', 'haplotype', 'accession', 'scope', 'seq_id', 'metric', 'value']
LENGTH_METRIC = 'Total path length'

# AGENTS.md never-claim list: none of these may appear in the figure's text.
FORBIDDEN_WORDS = re.compile(r't2t|complete|gapless|telomere-to-telomere', re.IGNORECASE)

# Okabe-Ito colours (colour-blind safe). Present and absent also differ in fill, so the figure
# reads in greyscale.
COLOURS = {'array': '#0072B2', 'no_array': '#D55E00', 'bar': '#D9D9D9', 'gap': '#000000',
           'muted': '#666666'}

# Read at save time, not draw time: TrueType (editable) text in the PDF, and text kept as text in
# an SVG (the tests grep one).
SAVE_RC = {'pdf.fonttype': 42, 'svg.fonttype': 'none'}


def read_tsv(path, required):
    """Rows of a tab-separated file with a header, as dicts; refuse if a column is missing."""
    with Path(path).open(newline='') as fh:
        reader = csv.DictReader(fh, delimiter='\t')
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f'{path}: missing columns {missing}')
        return list(reader)


def as_int(value, what):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{what}: expected an integer, got {value!r}') from None


def as_dist(value, what):
    """dist_bp: an integer, or None for NA (no qualifying array)."""
    return None if value == 'NA' else as_int(value, what)


def read_telomeres(path):
    """M02 telomeres.tsv -> {(assembly, seq_id): {'start': row, 'end': row}}, one start and one end
    row per sequence, each with its expected motif, one chromosome name and one length."""
    ends = defaultdict(dict)
    for row in read_tsv(path, TELOMERE_COLUMNS):
        key = (row['assembly'], row['seq_id'])
        end = row['end']
        if end not in EXPECTED_MOTIF:
            raise ValueError(f'{path}: {key}: end {end!r} is not start or end')
        if row['expected_motif'] != EXPECTED_MOTIF[end]:
            raise ValueError(f"{path}: {key} {end}: expected_motif {row['expected_motif']!r}, "
                             f'not {EXPECTED_MOTIF[end]}')
        if end in ends[key]:
            raise ValueError(f'{path}: {key} has two {end} rows')
        ends[key][end] = row
    for key, pair in ends.items():
        if set(pair) != set(EXPECTED_MOTIF):
            raise ValueError(f'{path}: {key} has only a {next(iter(pair))} row')
        for field in ('haplotype', 'accession', 'chromosome', 'seq_length'):
            if pair['start'][field] != pair['end'][field]:
                raise ValueError(f'{path}: {key}: start and end rows differ in {field}')
    return dict(ends)


def read_gfastats(path):
    """M01 gfastats.tsv -> {(assembly, seq_id): {'haplotype', 'accession', metric: value, ...}}
    from its scope=sequence rows."""
    sequences = {}
    for row in read_tsv(path, GFASTATS_COLUMNS):
        if row['scope'] == 'assembly':
            continue
        if row['scope'] != 'sequence':
            raise ValueError(f"{path}: scope {row['scope']!r} is not assembly or sequence")
        key = (row['assembly'], row['seq_id'])
        seq = sequences.setdefault(key, {'haplotype': row['haplotype'],
                                         'accession': row['accession']})
        if (seq['haplotype'], seq['accession']) != (row['haplotype'], row['accession']):
            raise ValueError(f'{path}: {key} rows disagree on haplotype or accession')
        if row['metric'] in seq:
            raise ValueError(f"{path}: {key} repeats metric {row['metric']!r}")
        seq[row['metric']] = row['value']
    return sequences


def read_gaps(path):
    """M01 gaps.bed (seq_id, start, end, assembly) -> {(assembly, seq_id): [(start, end), ...]}."""
    gaps = defaultdict(list)
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split('\t')
        if len(fields) != 4:
            raise ValueError(f'{path}:{n}: {len(fields)} fields, expected 4 (seq_id start end assembly)')
        seq_id, start, end, assembly = fields
        start, end = as_int(start, f'{path}:{n} start'), as_int(end, f'{path}:{n} end')
        if not 0 <= start < end:
            raise ValueError(f'{path}:{n}: gap {seq_id}:{start}-{end} is empty or negative')
        gaps[(assembly, seq_id)].append((start, end))
    return {k: sorted(v) for k, v in gaps.items()}


def end_values(row):
    """The expected motif's array copies, dist_bp and terminal 10 kb count at one end."""
    motif = row['expected_motif'].lower()
    what = f"{row['assembly']} {row['seq_id']} {row['end']}"
    return {
        'motif':       row['expected_motif'],
        'copies':      as_int(row[f'{motif}_array_copies'], f'{what} {motif}_array_copies'),
        'dist_bp':     as_dist(row[f'{motif}_array_dist_bp'], f'{what} {motif}_array_dist_bp'),
        'count_10kb':  as_int(row[f'{motif}_count_10kb'], f'{what} {motif}_count_10kb'),
    }


def has_array(values, min_copies=DEFAULT_MIN_COPIES, max_dist_bp=DEFAULT_MAX_DIST_BP):
    """True if the end's expected-motif array has >= min_copies copies and is <= max_dist_bp from
    the end. dist_bp None (NA) is no array."""
    return (values['dist_bp'] is not None and values['copies'] >= min_copies
            and values['dist_bp'] <= max_dist_bp)


def status(start_array, end_array, n_gaps):
    if start_array and end_array:
        return 'array_both_ends_no_gaps' if n_gaps == 0 else 'array_both_ends_with_gaps'
    if start_array or end_array:
        return 'array_one_end'
    return 'no_array'


def chromosome_key(name):
    """chr1..chr38 numerically, then chrX, chrY, then anything else by name."""
    bare = name.removeprefix('chr')
    if bare.isdigit():
        return (0, int(bare), '')
    return (1, {'X': 0, 'Y': 1}.get(bare, 2), bare)


def haplotype_key(haplotype):
    return (HAPLOTYPE_ORDER.index(haplotype) if haplotype in HAPLOTYPE_ORDER else len(HAPLOTYPE_ORDER),
            haplotype)


def build_table(telomeres, sequences, gaps, min_copies=DEFAULT_MIN_COPIES,
                max_dist_bp=DEFAULT_MAX_DIST_BP):
    """One row per haplotype x chromosome (COLUMNS), haplotypes pri then alt, chromosomes
    chr1-38, X, Y. Raises if an M02 sequence has no M01 sequence row or the two disagree."""
    missing = sorted(k for k in telomeres if k not in sequences)
    if missing:
        raise ValueError(f'{len(missing)} M02 chromosome(s) have no M01 sequence row '
                         f'(assembly, seq_id): {missing}')
    rows = []
    for key, pair in telomeres.items():
        first, seq = pair['start'], sequences[key]
        for field in ('haplotype', 'accession'):
            if first[field] != seq[field]:
                raise ValueError(f'{key}: M02 {field} {first[field]!r}, M01 {seq[field]!r}')
        if LENGTH_METRIC not in seq:
            raise ValueError(f'{key}: M01 has no {LENGTH_METRIC!r} row')
        length = as_int(seq[LENGTH_METRIC], f'{key} M01 {LENGTH_METRIC}')
        if length != as_int(first['seq_length'], f'{key} M02 seq_length'):
            raise ValueError(f"{key}: M01 length {length}, M02 seq_length {first['seq_length']}")
        seq_gaps = gaps.get(key, [])
        outside = [g for g in seq_gaps if g[1] > length]
        if outside:
            raise ValueError(f'{key}: gaps past the sequence length {length}: {outside}')
        start, end = end_values(pair['start']), end_values(pair['end'])
        start_array = has_array(start, min_copies, max_dist_bp)
        end_array = has_array(end, min_copies, max_dist_bp)
        rows.append({
            'assembly': key[0], 'haplotype': first['haplotype'], 'accession': first['accession'],
            'chromosome': first['chromosome'], 'seq_id': key[1], 'length_bp': length,
            **{f'start_{k}': v for k, v in (('motif', start['motif']),
                                            ('array_copies', start['copies']),
                                            ('array_dist_bp', start['dist_bp']),
                                            ('count_10kb', start['count_10kb']))},
            'start_array': 'yes' if start_array else 'no',
            **{f'end_{k}': v for k, v in (('motif', end['motif']),
                                          ('array_copies', end['copies']),
                                          ('array_dist_bp', end['dist_bp']),
                                          ('count_10kb', end['count_10kb']))},
            'end_array': 'yes' if end_array else 'no',
            'n_gaps': len(seq_gaps), 'gap_bp': sum(e - s for s, e in seq_gaps),
            'status': status(start_array, end_array, len(seq_gaps)),
        })
    seen = Counter((r['haplotype'], r['chromosome']) for r in rows)
    twice = sorted(k for k, n in seen.items() if n > 1)
    if twice:
        raise ValueError(f'(haplotype, chromosome) on more than one sequence: {twice}')
    rows.sort(key=lambda r: (haplotype_key(r['haplotype']), chromosome_key(r['chromosome'])))
    return rows


def write_table(rows, path):
    with Path(path).open('w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter='\t', lineterminator='\n',
                                extrasaction='raise')
        writer.writeheader()
        writer.writerows({k: 'NA' if v is None else v for k, v in r.items()} for r in rows)


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def display_path(path):
    """Repo-relative if inside this repo, else the file name only: no personal paths in outputs."""
    path = Path(path).resolve()
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return path.name


def method_text(inputs, rows, min_copies, max_dist_bp, matplotlib_version, figure=True):
    by_hap = Counter(r['haplotype'] for r in rows)
    lines = [
        'M03 per-chromosome table and figure: expected-motif arrays at the ends, and gaps',
        '',
        f'Tool: workflow/scripts/sf/completeness.py, sha256 {sha256_file(__file__)}',
        f'  Python {platform.python_version()}, matplotlib {matplotlib_version}',
        '',
        'Inputs (sha256):',
        *(f'  {label}: {display_path(p)}  {sha256_file(p)}' for label, p in inputs.items()),
        '',
        'Join: M02 rows to M01 scope=sequence rows on (assembly, seq_id); every M02 chromosome',
        f'must have an M01 row with the same haplotype, accession and length ({LENGTH_METRIC!r}',
        '= M02 seq_length). M01 sequences M02 did not scan, and their gaps, are left out.',
        '',
        'Per end, only the expected motif is used: CCCTAA at start (first base), TTAGGG at end',
        '(last base), forward strand. start_/end_ columns: that motif\'s terminal array as M02',
        'reports it (the qualifying run nearest that end; method in M02\'s method.txt), as',
        'array_copies and array_dist_bp (0 = the array reaches the terminal base, NA = no',
        'qualifying array), and its exact count in the terminal 10 kb (count_10kb).',
        '',
        f'Thresholds: min_copies = {min_copies}, max_dist_bp = {max_dist_bp:,}',
        f'  start_array / end_array = yes if array_copies >= {min_copies} and array_dist_bp <= '
        f'{max_dist_bp:,}; NA is no.',
        'Gaps: n_gaps and gap_bp count gaps.bed rows (runs of N/n) on that sequence.',
        'Status, a fixed rule on the columns above:',
        '  array_both_ends_no_gaps    start_array and end_array yes, n_gaps = 0',
        '  array_both_ends_with_gaps  start_array and end_array yes, n_gaps >= 1',
        '  array_one_end              exactly one of start_array, end_array yes',
        '  no_array                   neither yes',
        '',
        f"Rows in completeness.tsv: {len(rows)} ("
        + ', '.join(f'{h}: {by_hap[h]}' for h in sorted(by_hap, key=haplotype_key)) + ')',
        *(['Figure: completeness.pdf, completeness.png (300 dpi). One bar per chromosome, scaled',
           'to length; a filled marker at an end with start_array/end_array yes, an open one',
           'otherwise; a tick at each gap\'s midpoint.'] if figure else
          ['Figure: not drawn (--no-figure).']),
        '',
        'Status: diagnostic-only until recorded otherwise in PROVENANCE.md.',
    ]
    return '\n'.join(lines) + '\n'


def subject_name(rows):
    """The assembly name the haplotypes share (ROS_Cfam_2.0 from ROS_Cfam_2.0_pri/_alt)."""
    names = {r['assembly'].removesuffix(f"_{r['haplotype']}") for r in rows}
    return names.pop() if len(names) == 1 else ', '.join(sorted({r['assembly'] for r in rows}))


def figure_texts(fig):
    """Every string drawn in the figure (titles, labels, ticks, legend, annotations). Lays the
    figure out first so tick labels exist."""
    from matplotlib.text import Text
    fig.draw_without_rendering()
    return [t.get_text() for t in fig.findobj(Text) if t.get_text()]


def check_words(fig):
    """Refuse a figure whose text has any FORBIDDEN_WORDS (case-insensitive)."""
    bad = sorted({m.group(0) for text in figure_texts(fig) for m in FORBIDDEN_WORDS.finditer(text)})
    if bad:
        raise ValueError(f'figure text contains forbidden words {bad} (AGENTS.md never-claim list)')


def draw_figure(rows, gaps, min_copies=DEFAULT_MIN_COPIES, max_dist_bp=DEFAULT_MAX_DIST_BP,
                title=None):
    """A matplotlib Figure (no pyplot, so no GUI backend): one panel per haplotype, one bar per
    chromosome on a shared Mb scale, end markers and gap ticks. `gaps` is read_gaps() output."""
    import matplotlib
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D

    haplotypes = sorted({r['haplotype'] for r in rows}, key=haplotype_key)
    chromosomes = sorted({r['chromosome'] for r in rows}, key=chromosome_key)
    by_key = {(r['haplotype'], r['chromosome']): r for r in rows}
    max_mb = max(r['length_bp'] for r in rows) / 1e6
    y = {c: i for i, c in enumerate(chromosomes)}
    bar_h, tick_h, marker = 0.56, 0.78, 3.6
    font = {'axes.titlesize': 8, 'axes.labelsize': 7, 'xtick.labelsize': 6.5,
            'ytick.labelsize': 6.5, 'legend.fontsize': 6.5, 'font.size': 7}

    with matplotlib.rc_context({**font, 'axes.spines.top': False, 'axes.spines.right': False}):
        height = 1.3 + 0.13 * len(chromosomes)
        fig = Figure(figsize=(7.2, height), layout='constrained')
        axes = fig.subplots(1, len(haplotypes), sharex=True, sharey=True, squeeze=False)[0]
        for ax, hap in zip(axes, haplotypes):
            accessions = sorted({r['accession'] for r in rows if r['haplotype'] == hap})
            assemblies = sorted({r['assembly'] for r in rows if r['haplotype'] == hap})
            ax.set_title(f"{hap}: {', '.join(assemblies)} ({', '.join(accessions)})", loc='left')
            for chrom in chromosomes:
                r = by_key.get((hap, chrom))
                if r is None:
                    ax.text(0, y[chrom], 'no sequence in this assembly', va='center', ha='left',
                            fontsize=5.5, style='italic', color=COLOURS['muted'])
                    continue
                mb = r['length_bp'] / 1e6
                ax.barh(y[chrom], mb, height=bar_h, left=0, color=COLOURS['bar'], linewidth=0,
                        zorder=1)
                mids = [(s + e) / 2e6 for s, e in gaps.get((r['assembly'], r['seq_id']), [])]
                if mids:
                    ax.vlines(mids, y[chrom] - tick_h / 2, y[chrom] + tick_h / 2,
                              color=COLOURS['gap'], linewidth=0.7, zorder=2)
                for x, flag in ((0, r['start_array']), (mb, r['end_array'])):
                    present = flag == 'yes'
                    colour = COLOURS['array'] if present else COLOURS['no_array']
                    ax.plot([x], [y[chrom]], marker='o', markersize=marker, linestyle='none',
                            markerfacecolor=colour if present else 'white',
                            markeredgecolor=colour, markeredgewidth=0.9, zorder=3, clip_on=False)
            top = by_key.get((hap, chromosomes[0]))
            if top is not None:
                for x, label, ha in ((0, 'start', 'left'), (top['length_bp'] / 1e6, 'end', 'right')):
                    ax.annotate(label, (x, -0.55), xytext=(0, 2), textcoords='offset points',
                                ha=ha, va='bottom', fontsize=5.5, color=COLOURS['muted'],
                                annotation_clip=False)
            ax.set_xlabel('Position from the first base (Mb)')
            ax.tick_params(axis='y', length=0)
            ax.grid(axis='x', color='#EEEEEE', linewidth=0.5, zorder=0)
            ax.set_axisbelow(True)
        axes[0].set_yticks(range(len(chromosomes)), chromosomes)
        axes[0].set_ylim(len(chromosomes) - 0.4, -0.9)
        axes[0].set_xlim(-0.02 * max_mb, 1.03 * max_mb)

        handles = [
            Line2D([], [], marker='o', linestyle='none', markersize=marker + 0.6,
                   markerfacecolor=COLOURS['array'], markeredgecolor=COLOURS['array'],
                   label=f'expected-motif array at the end: CCCTAA at the start, TTAGGG at '
                         f'the end; {min_copies:,} or more copies, within {max_dist_bp:,} bp'),
            Line2D([], [], marker='o', linestyle='none', markersize=marker + 0.6,
                   markerfacecolor='white', markeredgecolor=COLOURS['no_array'],
                   markeredgewidth=0.9, label='no such array at the end'),
            Line2D([], [], marker='|', linestyle='none', markersize=7, markeredgewidth=0.9,
                   color=COLOURS['gap'], label='gap (run of N)'),
        ]
        fig.legend(handles=handles, loc='outside lower center', ncols=1, frameon=False,
                   handletextpad=0.3, columnspacing=1.2)
        fig.suptitle(title or f'{subject_name(rows)}: expected-motif arrays at chromosome ends, '
                              f'and gaps', fontsize=8.5)
    check_words(fig)
    return fig


def save_figure(fig, out_dir):
    """completeness.pdf and completeness.png (300 dpi), without creation dates so re-runs on the
    same inputs give the same bytes."""
    import matplotlib
    out_dir = Path(out_dir)
    pdf, png = out_dir / 'completeness.pdf', out_dir / 'completeness.png'
    with matplotlib.rc_context(SAVE_RC):
        fig.savefig(pdf, metadata={'CreationDate': None, 'ModDate': None})
        fig.savefig(png, dpi=300)
    return pdf, png


def run(telomeres, gfastats, gaps, out_dir, min_copies=DEFAULT_MIN_COPIES,
        max_dist_bp=DEFAULT_MAX_DIST_BP, title=None, figure=True):
    """Build the table, method and (if `figure`) the figure in out_dir; returns the table rows."""
    gap_map = read_gaps(gaps)
    rows = build_table(read_telomeres(telomeres), read_gfastats(gfastats), gap_map,
                       min_copies, max_dist_bp)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_table(rows, out_dir / 'completeness.tsv')
    mpl_version = 'not used (--no-figure)'
    if figure:
        import matplotlib
        mpl_version = matplotlib.__version__
        save_figure(draw_figure(rows, gap_map, min_copies, max_dist_bp, title), out_dir)
    inputs = {'telomeres (M02)': telomeres, 'gfastats (M01)': gfastats, 'gaps (M01)': gaps}
    (out_dir / 'completeness.method.txt').write_text(
        method_text(inputs, rows, min_copies, max_dist_bp, mpl_version, figure))
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--telomeres', required=True, help='M02 telomeres.tsv')
    p.add_argument('--gfastats', required=True, help='M01 gfastats.tsv (long format)')
    p.add_argument('--gaps', required=True, help='M01 gaps.bed (seq_id start end assembly)')
    p.add_argument('--out-dir', required=True, help='folder for completeness.{tsv,method.txt,pdf,png}')
    p.add_argument('--min-copies', type=int, default=DEFAULT_MIN_COPIES,
                   help=f'array copies needed at an end (default {DEFAULT_MIN_COPIES})')
    p.add_argument('--max-dist-bp', type=int, default=DEFAULT_MAX_DIST_BP,
                   help=f'largest array distance from the end, bp (default {DEFAULT_MAX_DIST_BP})')
    p.add_argument('--title', help='figure title (default names the assembly)')
    p.add_argument('--no-figure', action='store_true', help='table and method only (no matplotlib)')
    args = p.parse_args(argv)
    rows = run(args.telomeres, args.gfastats, args.gaps, args.out_dir, args.min_copies,
               args.max_dist_bp, args.title, figure=not args.no_figure)
    tally = Counter((r['haplotype'], r['status']) for r in rows)
    for (hap, st), n in sorted(tally.items(), key=lambda kv: (haplotype_key(kv[0][0]), kv[0][1])):
        print(f'{hap}\t{st}\t{n}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
