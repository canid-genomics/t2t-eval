"""Tests for the M03 (sf) completeness table and figure, on synthetic M01/M02-format fixtures only
(tests/sf/fixture/completeness/, see its README). Stdlib unittest; the figure tests need
matplotlib and are skipped without it, so run them in the pixi `fig` environment of the main
checkout:

    pixi run --manifest-path <main checkout>/pixi.toml -e fig \\
        python -m unittest discover -s tests/sf -p 'test_*.py' -v
"""
import csv
import importlib.util
import io
import re
import struct
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / 'tests/sf/fixture/completeness'
TELOMERES, GFASTATS, GAPS = (FIXTURE / f for f in ('telomeres.tsv', 'gfastats.tsv', 'gaps.bed'))
HAS_MATPLOTLIB = importlib.util.find_spec('matplotlib') is not None
OUTPUTS = ['completeness.tsv', 'completeness.method.txt', 'completeness.pdf', 'completeness.png']


def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / f'workflow/scripts/sf/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


comp = load('completeness')

# What the fixture is built to give (README): every status, both threshold edges, a gap on a
# no-array chromosome, an unplaced M01 scaffold, and an array of the other motif at an end.
EXPECTED = {
    ('pri', 'chr1'):  ('array_both_ends_no_gaps',   'yes', 'yes', 0, 0),
    ('pri', 'chr2'):  ('array_both_ends_with_gaps', 'yes', 'yes', 2, 600),
    ('pri', 'chr10'): ('array_one_end',             'yes', 'no',  1, 200),
    ('pri', 'chrX'):  ('no_array',                  'no',  'no',  1, 10_000),
    ('pri', 'chrY'):  ('array_one_end',             'no',  'yes', 0, 0),
    ('alt', 'chr1'):  ('array_both_ends_no_gaps',   'yes', 'yes', 0, 0),
    ('alt', 'chr2'):  ('array_both_ends_with_gaps', 'yes', 'yes', 1, 100),
    ('alt', 'chr10'): ('no_array',                  'no',  'no',  0, 0),
}


def fixture_rows(**kw):
    return comp.build_table(comp.read_telomeres(TELOMERES), comp.read_gfastats(GFASTATS),
                            comp.read_gaps(GAPS), **kw)


def by_key(rows):
    return {(r['haplotype'], r['chromosome']): r for r in rows}


def edited_copy(src, dest_dir, keep=lambda line: True, edit=lambda line: line):
    """A copy of a fixture file with lines dropped or changed (header always kept)."""
    lines = src.read_text().splitlines()
    out = [lines[0], *(edit(l) for l in lines[1:] if keep(l))]
    dest = Path(dest_dir) / src.name
    dest.write_text('\n'.join(out) + '\n')
    return dest


def png_size(path):
    """(width, height) from a PNG's IHDR chunk."""
    data = Path(path).read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR'
    return struct.unpack('>II', data[16:24])


class Table(unittest.TestCase):
    def test_every_status_from_the_fixture(self):
        rows = by_key(fixture_rows())
        self.assertEqual(set(rows), set(EXPECTED))
        for key, (status, start, end, n_gaps, gap_bp) in EXPECTED.items():
            with self.subTest(key=key):
                r = rows[key]
                self.assertEqual((r['status'], r['start_array'], r['end_array'], r['n_gaps'],
                                  r['gap_bp']), (status, start, end, n_gaps, gap_bp))
        self.assertEqual({r['status'] for r in rows.values()}, set(comp.STATUSES))

    def test_order_is_pri_then_alt_and_chr1_to_38_x_y(self):
        # The fixture lists chr10 before chr2 and chrY before chrX.
        order = [(r['haplotype'], r['chromosome']) for r in fixture_rows()]
        self.assertEqual(order, [('pri', 'chr1'), ('pri', 'chr2'), ('pri', 'chr10'),
                                 ('pri', 'chrX'), ('pri', 'chrY'),
                                 ('alt', 'chr1'), ('alt', 'chr2'), ('alt', 'chr10')])
        names = [f'chr{i}' for i in range(1, 39)] + ['chrX', 'chrY']
        self.assertEqual(sorted(reversed(names), key=comp.chromosome_key), names)

    def test_columns_come_from_the_join(self):
        r = by_key(fixture_rows())[('pri', 'chr2')]
        self.assertEqual(r['seq_id'], 'TESTP002.1')
        self.assertEqual(r['length_bp'], 2_500_000)          # M01 Total path length
        self.assertEqual((r['start_motif'], r['start_array_copies'], r['start_array_dist_bp'],
                          r['start_count_10kb']), ('CCCTAA', 300, 12, 1650))
        self.assertEqual((r['end_motif'], r['end_array_copies'], r['end_array_dist_bp'],
                          r['end_count_10kb']), ('TTAGGG', 250, 0, 1500))

    def test_only_the_expected_motif_counts(self):
        # pri chr10's end has a 300-copy CCCTAA array reaching the last base, but no TTAGGG.
        r = by_key(fixture_rows())[('pri', 'chr10')]
        self.assertEqual((r['end_array_copies'], r['end_array_dist_bp'], r['end_array']),
                         (0, None, 'no'))

    def test_unscanned_m01_sequences_and_their_gaps_are_left_out(self):
        rows = fixture_rows()
        self.assertNotIn('TESTP999.1', {r['seq_id'] for r in rows})
        self.assertEqual(sum(r['n_gaps'] for r in rows), 5)   # 6 gaps in gaps.bed, 1 unplaced

    def test_threshold_edges(self):
        rows = by_key(fixture_rows())
        self.assertEqual(rows[('pri', 'chrY')]['end_array_dist_bp'], 1_000)     # <= 1,000: yes
        self.assertEqual(rows[('pri', 'chrY')]['end_array'], 'yes')
        self.assertEqual(rows[('pri', 'chrX')]['start_array_dist_bp'], 1_001)   # > 1,000: no
        self.assertEqual(rows[('pri', 'chrX')]['start_array'], 'no')

    def test_thresholds_are_parameters(self):
        rows = by_key(fixture_rows(min_copies=20))        # pri chrY end has 10 copies
        self.assertEqual(rows[('pri', 'chrY')]['status'], 'no_array')
        rows = by_key(fixture_rows(max_dist_bp=5_000))    # alt chr10 end is 5,000 bp in
        self.assertEqual(rows[('alt', 'chr10')]['status'], 'array_one_end')
        self.assertEqual(rows[('pri', 'chrX')]['status'], 'array_one_end')

    def test_has_array_rules(self):
        self.assertFalse(comp.has_array({'copies': 0, 'dist_bp': None}))
        self.assertFalse(comp.has_array({'copies': 9, 'dist_bp': 0}))
        self.assertTrue(comp.has_array({'copies': 10, 'dist_bp': 0}))
        self.assertTrue(comp.has_array({'copies': 10, 'dist_bp': 1_000}))
        self.assertFalse(comp.has_array({'copies': 4_000, 'dist_bp': 1_001}))

    def test_written_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'completeness.tsv'
            comp.write_table(fixture_rows(), path)
            with path.open(newline='') as fh:
                reader = csv.DictReader(fh, delimiter='\t')
                self.assertEqual(reader.fieldnames, comp.COLUMNS)
                rows = list(reader)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[4]['start_array_dist_bp'], 'NA')   # pri chrY start, no array


class Failures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def table(self, telomeres=TELOMERES, gfastats=GFASTATS, gaps=GAPS):
        return comp.build_table(comp.read_telomeres(telomeres), comp.read_gfastats(gfastats),
                                comp.read_gaps(gaps))

    def test_m02_chromosome_without_m01_row_fails(self):
        gf = edited_copy(GFASTATS, self.tmp.name, keep=lambda l: '\tTESTP002.1\t' not in l)
        with self.assertRaisesRegex(ValueError, r"no M01 sequence row.*'TEST_pri', 'TESTP002.1'"):
            self.table(gfastats=gf)

    def test_join_is_per_assembly(self):
        # The seq_id exists in M01 but under the other assembly: still missing.
        gf = edited_copy(GFASTATS, self.tmp.name,
                         edit=lambda l: l.replace('TEST_pri\tpri', 'TEST_alt\tpri')
                         if '\tTESTP001.1\t' in l else l)
        with self.assertRaisesRegex(ValueError, 'TESTP001.1'):
            self.table(gfastats=gf)

    def test_length_mismatch_fails(self):
        gf = edited_copy(GFASTATS, self.tmp.name,
                         edit=lambda l: l.replace('Total path length\t3000000',
                                                  'Total path length\t3000001'))
        with self.assertRaisesRegex(ValueError, 'M01 length 3000001, M02 seq_length 3000000'):
            self.table(gfastats=gf)

    def test_haplotype_mismatch_fails(self):
        gf = edited_copy(GFASTATS, self.tmp.name,
                         edit=lambda l: l.replace('TEST_alt\talt', 'TEST_alt\tpri'))
        with self.assertRaisesRegex(ValueError, 'haplotype'):
            self.table(gfastats=gf)

    def test_gap_past_the_sequence_end_fails(self):
        bed = Path(self.tmp.name) / 'gaps.bed'
        bed.write_text('TESTP001.1\t2999990\t3000010\tTEST_pri\n')
        with self.assertRaisesRegex(ValueError, 'past the sequence length'):
            self.table(gaps=bed)

    def test_gaps_bed_needs_four_columns(self):
        bed = Path(self.tmp.name) / 'gaps.bed'
        bed.write_text('TESTP001.1\t10\t20\n')
        with self.assertRaisesRegex(ValueError, 'expected 4'):
            comp.read_gaps(bed)

    def test_wrong_expected_motif_fails(self):
        tel = edited_copy(TELOMERES, self.tmp.name,
                          edit=lambda l: l.replace('\tstart\tCCCTAA\t', '\tstart\tTTAGGG\t', 1))
        with self.assertRaisesRegex(ValueError, 'expected_motif'):
            comp.read_telomeres(tel)

    def test_missing_end_row_fails(self):
        tel = edited_copy(TELOMERES, self.tmp.name,
                          keep=lambda l: not ('\tTESTA001.1\t' in l and '\tend\t' in l))
        with self.assertRaisesRegex(ValueError, 'only a start row'):
            comp.read_telomeres(tel)

    def test_missing_column_fails(self):
        gf = Path(self.tmp.name) / 'gfastats.tsv'
        gf.write_text('assembly\tseq_id\tmetric\tvalue\n')
        with self.assertRaisesRegex(ValueError, 'missing columns'):
            comp.read_gfastats(gf)


class Method(unittest.TestCase):
    def test_method_records_thresholds_rules_and_inputs_without_personal_paths(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(io.StringIO()):
            comp.main(['--telomeres', str(TELOMERES), '--gfastats', str(GFASTATS),
                       '--gaps', str(GAPS), '--out-dir', tmp, '--no-figure',
                       '--min-copies', '12', '--max-dist-bp', '2000'])
            text = (Path(tmp) / 'completeness.method.txt').read_text()
            self.assertFalse((Path(tmp) / 'completeness.png').exists())
        self.assertIn('min_copies = 12, max_dist_bp = 2,000', text)
        for status in comp.STATUSES:
            self.assertIn(status, text)
        self.assertIn('tests/sf/fixture/completeness/telomeres.tsv', text)
        self.assertIn(comp.sha256_file(GAPS), text)
        self.assertNotIn(str(Path.home()), text)
        self.assertNotIn(tmp, text)

    def test_input_outside_the_repo_is_named_by_file_name_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'telomeres.tsv'
            path.write_text('x\n')
            self.assertEqual(comp.display_path(path), 'telomeres.tsv')


@unittest.skipUnless(HAS_MATPLOTLIB, 'matplotlib not installed (use the pixi fig environment)')
class Figure(unittest.TestCase):
    def test_cli_writes_all_four_outputs(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(io.StringIO()) as err:
            self.assertEqual(comp.main(['--telomeres', str(TELOMERES), '--gfastats', str(GFASTATS),
                                        '--gaps', str(GAPS), '--out-dir', tmp]), 0)
            out = Path(tmp)
            for name in OUTPUTS:
                self.assertGreater((out / name).stat().st_size, 0, name)
            self.assertEqual((out / 'completeness.pdf').read_bytes()[:5], b'%PDF-')
            width, height = png_size(out / 'completeness.png')
            self.assertEqual(width, round(7.2 * 300))          # 7.2 in at 300 dpi
            self.assertIn('matplotlib', (out / 'completeness.method.txt').read_text())
        self.assertIn('pri\tarray_one_end\t2', err.getvalue())

    def test_pdf_is_reproducible(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for d in (a, b):
                comp.run(TELOMERES, GFASTATS, GAPS, d)
            self.assertEqual((Path(a) / 'completeness.pdf').read_bytes(),
                             (Path(b) / 'completeness.pdf').read_bytes())

    def figure(self, **kw):
        return comp.draw_figure(fixture_rows(), comp.read_gaps(GAPS), **kw)

    def test_no_forbidden_words_in_the_figure_text(self):
        texts = comp.figure_texts(self.figure())
        joined = '\n'.join(texts)
        self.assertIn('expected-motif array at the end', joined)
        self.assertIn('gap', joined)
        self.assertIn('chrY', texts)
        self.assertIn('no sequence in this assembly', texts)    # alt has no chrX, chrY
        self.assertIsNone(comp.FORBIDDEN_WORDS.search(joined), joined)
        self.assertIsNone(re.search(r'\b[pq]\s*arm\b', joined))

    def test_no_forbidden_words_in_the_rendered_svg(self):
        import matplotlib
        fig = self.figure()
        buf = io.StringIO()
        with matplotlib.rc_context(comp.SAVE_RC):           # svg.fonttype none: text stays text
            fig.savefig(buf, format='svg', metadata={'Date': None})
        svg = buf.getvalue()
        shown = re.findall(r'<text[^>]*>(.*?)</text>', svg, flags=re.S)
        self.assertIn('expected-motif arrays at chromosome ends, and gaps',
                      ' '.join(shown).replace('\n', ' '))
        self.assertIsNone(comp.FORBIDDEN_WORDS.search(svg))

    def test_forbidden_words_refuse_the_figure(self):
        for title in ('A T2T assembly', 'complete chromosomes', 'Gapless',
                      'telomere-to-telomere', 'incomplete ends'):
            with self.subTest(title=title), self.assertRaisesRegex(ValueError, 'forbidden'):
                self.figure(title=title)

    def test_legend_states_the_thresholds(self):
        joined = '\n'.join(comp.figure_texts(self.figure(min_copies=12, max_dist_bp=2_500)))
        self.assertIn('12 or more copies, within 2,500 bp', joined)

    def test_one_gap_tick_per_gap_and_two_markers_per_bar(self):
        from matplotlib.collections import LineCollection
        fig = self.figure()
        pri, alt = fig.axes[:2]
        ticks = lambda ax: sum(len(c.get_segments()) for c in ax.collections
                               if isinstance(c, LineCollection))
        self.assertEqual((ticks(pri), ticks(alt)), (4, 1))
        self.assertEqual((len(pri.lines), len(alt.lines)), (2 * 5, 2 * 3))
        filled = [l.get_markerfacecolor() != 'white' for l in pri.lines]
        self.assertEqual(filled.count(True), 6)   # start/end 'yes' in pri: 2 + 2 + 1 + 0 + 1


if __name__ == '__main__':
    unittest.main()
