"""Tests for the M01 (jc) assembly-stats publish script, on real gfastats output from a synthetic
FASTA (tests/jc/fixture/assembly_stats/README.md). Stdlib unittest:

    python -m unittest discover -s tests/jc -p 'test_*.py' -v
"""
import csv
import hashlib
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / 'tests/jc/fixture/assembly_stats'

_spec = importlib.util.spec_from_file_location(
    'assembly_stats_publish', REPO / 'workflow/scripts/jc/assembly_stats_publish.py')
pub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pub)


def synthetic_fasta():
    """The FASTA the fixture's gfastats output was made from."""
    seqs = {
        'chrA.1 synthetic chromosome A': 'ACGT' * 250 + 'N' * 100 + 'ACCGGT' * 100 + 'nnnnn' + 'acgt' * 50 + 'NNN',
        'chrB.1 synthetic chromosome B': 'N' * 10 + 'GATTACA' * 400,
        'chrC.1': 'TTAGGG' * 100,
    }
    lines = []
    for header, seq in seqs.items():
        lines.append(f'>{header}')
        lines += [seq[i:i + 60] for i in range(0, len(seq), 60)]
    return '\n'.join(lines) + '\n'


def n_runs(fasta_text):
    """Runs of N/n per record, 0-based half-open: the independent answer gaps.bed must match."""
    runs, seq_id, seq = [], None, []

    def flush():
        if seq_id is not None:
            runs.extend((seq_id, m.start(), m.end()) for m in re.finditer('[Nn]+', ''.join(seq)))

    for line in fasta_text.splitlines():
        if line.startswith('>'):
            flush()
            seq_id, seq = line[1:].split()[0], []
        else:
            seq.append(line.strip())
    flush()
    return runs


def fixture(name):
    return (FIXTURE / f'gfastats.{name}').read_text()


class ParseAndCheck(unittest.TestCase):
    def setUp(self):
        self.summary = pub.parse_summary(fixture('summary.tsv'))
        self.sequences = pub.parse_path_report(fixture('sequences.tsv'))
        self.gaps = pub.parse_gaps(fixture('gaps.bed'))

    def test_gaps_are_the_n_runs(self):
        self.assertEqual(self.gaps, n_runs(synthetic_fasta()))

    def test_parsed_fixture(self):
        self.assertEqual(self.summary['# scaffolds'], '3')
        self.assertEqual(self.summary['Total gap length in scaffolds'], '118')
        self.assertEqual([r['Header'] for r in self.sequences], ['chrA.1', 'chrB.1', 'chrC.1'])
        self.assertEqual(self.sequences[2]['Comment'], '')
        self.assertEqual(self.sequences[0]['Total path length'], '1908')

    def test_consistent_fixture_passes(self):
        pub.check_assembly('a', self.summary, self.sequences, self.gaps)

    def test_dropped_gap_fails(self):
        with self.assertRaisesRegex(ValueError, 'gap BED rows'):
            pub.check_assembly('a', self.summary, self.sequences, self.gaps[:-1])

    def test_gap_outside_scaffold_fails(self):
        gaps = [*self.gaps[:-1], ('chrB.1', 2800, 2811)]
        with self.assertRaisesRegex(ValueError, 'outside'):
            pub.check_assembly('a', self.summary, self.sequences, gaps)

    def test_gap_on_unknown_sequence_fails(self):
        gaps = [*self.gaps[:-1], ('chrZ.1', 0, 10)]
        with self.assertRaisesRegex(ValueError, 'not in the path report'):
            pub.check_assembly('a', self.summary, self.sequences, gaps)

    def test_moved_gap_fails_per_sequence_check(self):
        # Same count and total, but the 10 bp gap is put on chrC.1, which has none.
        gaps = [*self.gaps[:-1], ('chrC.1', 0, 10)]
        with self.assertRaisesRegex(ValueError, 'chrB.1 path - segment'):
            pub.check_assembly('a', self.summary, self.sequences, gaps)

    def test_scaffold_count_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, 'scaffolds'):
            pub.check_assembly('a', self.summary, self.sequences[:-1], self.gaps)

    def test_path_report_header_trailing_tab(self):
        # gfastats writes the header with a trailing tab (stripped in the fixture, see README).
        header, rest = fixture('sequences.tsv').split('\n', 1)
        self.assertEqual(pub.parse_path_report(f'{header}\t\n{rest}'), self.sequences)

    def test_path_report_extra_field_fails(self):
        text = fixture('sequences.tsv').replace('\tN\n', '\tN\textra\n', 1)
        with self.assertRaisesRegex(ValueError, 'fields'):
            pub.parse_path_report(text)

    def test_long_rows(self):
        sample = {'assembly': 'x_pri', 'haplotype': 'pri', 'accession': 'GCA_1.1'}
        rows = pub.gfastats_rows(sample, self.summary, self.sequences)
        per_seq = len(self.sequences[0]) - 2  # all columns but Seq and Header
        self.assertEqual(len(rows), len(self.summary) + 3 * per_seq)
        self.assertEqual(rows[0], {**sample, 'scope': 'assembly', 'seq_id': 'NA',
                                   'metric': '# scaffolds', 'value': '3'})
        self.assertIn({**sample, 'scope': 'sequence', 'seq_id': 'chrB.1',
                       'metric': 'Total path length', 'value': '2810'}, rows)


class Publish(unittest.TestCase):
    def test_run_folder(self):
        assemblies = [{'assembly': 'X_pri', 'subject': 'X', 'accession': 'GCA_000000001.1',
                       'haplotype': 'pri', 'source': 'NCBI'},
                      {'assembly': 'X_alt', 'subject': 'X', 'accession': 'GCA_000000002.1',
                       'haplotype': 'alt', 'source': 'NCBI'}]
        provenance = {'commit': 'a' * 40, 'head': 'b' * 40, 'tracked_dirty': False}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            records = []
            for a in assemblies:
                rec = tmp / f"{a['assembly']}.fetch.tsv"
                rec.write_text('assembly\taccession\tfile\n'
                               f"{a['assembly']}\t{a['accession']}\tgenomic.fna.gz\n")
                records.append(rec)
            run = tmp / 'tier2/X/jc/dev.0000-00-00.0000000'
            names = {'gfastats': 'gfastats.tsv', 'gaps': 'gaps.bed', 'inputs': 'inputs.tsv',
                     'run_info': 'run_info.json', 'sha256': 'sha256sums.txt',
                     'manifest': '_MANIFEST.txt'}
            out = {k: str(run / v) for k, v in names.items()}
            pub.publish(summaries=[FIXTURE / 'gfastats.summary.tsv'] * 2,
                        path_reports=[FIXTURE / 'gfastats.sequences.tsv'] * 2,
                        gap_beds=[FIXTURE / 'gfastats.gaps.bed'] * 2,
                        fetch_records=records, out=out, run_id='dev.0000-00-00.0000000',
                        lane='jc', subject='X', spec_id='M01', assemblies=assemblies,
                        gfastats={'summary': 'gfastats <genomic.fna.gz> -j <threads> --tabular'},
                        provenance=provenance, describes='SPEC.tsv M01: test',
                        dest='tier2/X/jc/dev.0000-00-00.0000000', job='123')

            with open(out['gfastats'], newline='') as fh:
                rows = list(csv.DictReader(fh, delimiter='\t'))
            self.assertEqual(list(rows[0]), pub.GFASTATS_COLUMNS)
            self.assertEqual({r['assembly'] for r in rows}, {'X_pri', 'X_alt'})
            self.assertEqual({r['haplotype'] for r in rows if r['assembly'] == 'X_alt'}, {'alt'})

            bed = [l.split('\t') for l in Path(out['gaps']).read_text().splitlines()]
            self.assertEqual(len(bed), 8)
            self.assertEqual(bed[0], ['chrA.1', '1000', '1100', 'X_pri'])
            self.assertEqual(bed[-1], ['chrB.1', '0', '10', 'X_alt'])

            self.assertEqual(len(Path(out['inputs']).read_text().splitlines()), 3)

            info = json.loads(Path(out['run_info']).read_text())
            self.assertEqual((info['lane'], info['commit'], info['spec_id']), ('jc', 'a' * 40, 'M01'))
            self.assertEqual(info['counts']['X_pri'], {'sequences': 3, 'gaps': 4})

            sums = dict(reversed(l.split('  ')) for l in Path(out['sha256']).read_text().splitlines())
            self.assertEqual(set(sums), {'gfastats.tsv', 'gaps.bed', 'inputs.tsv', 'run_info.json'})
            for name, digest in sums.items():
                self.assertEqual(hashlib.sha256((run / name).read_bytes()).hexdigest(), digest)

            manifest = dict(l.split(':', 1) for l in Path(out['manifest']).read_text().splitlines())
            manifest = {k: v.strip() for k, v in manifest.items()}
            self.assertEqual(list(manifest), ['describes', 'source', 'dest', 'job', 'scope', 'finished',
                                              'objects', 'size', 'lane', 'commit', 'run_id', 'spec_id'])
            self.assertEqual((manifest['lane'], manifest['commit'], manifest['objects'], manifest['job']),
                             ('jc', 'a' * 40, '5', '123'))


if __name__ == '__main__':
    unittest.main()
