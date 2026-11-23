"""Tests for the M02 (sf) telomere-scan scripts, on synthetic sequence only. Stdlib unittest:

    pixi run python -m unittest discover -s tests/sf -p 'test_*.py' -v
"""
import gzip
import hashlib
import importlib.util
import json
import random
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / 'tests/sf/fixture/telomeres'


def load(name, lane='sf'):
    spec = importlib.util.spec_from_file_location(name, REPO / f'workflow/scripts/{lane}/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scan = load('telomere_scan')
fetch = load('ncbi_fetch', 'shared')
publish = load('telomeres_publish')

PARAMS = dict(scan.DEFAULT_PARAMS)
FWD, REV = 'TTAGGG', 'CCCTAA'


def background(n, rng):
    """Sequence that cannot contain either motif (no T, no G), so expected counts are exact."""
    return ''.join(rng.choice('AC') for _ in range(n))


def place(seq, pos, insert):
    return seq[:pos] + insert + seq[pos + len(insert):]


def synthetic_chromosomes():
    """Sequences matching the lengths in tests/sf/fixture/telomeres/assembly_report.txt."""
    rng = random.Random(2)
    # chr1: CCCTAA x500 at the start with one variant unit; an inward TTAGGG x12 at 5 kb; a
    # soft-masked TTAGGG x300 that stops 7 bp short of the end.
    start_array = REV * 250 + 'CCCTGA' + REV * 249
    chr1 = background(60_000, rng)
    chr1 = place(chr1, 0, start_array)
    chr1 = place(chr1, 5_000, FWD * 12)
    chr1 = place(chr1, 60_000 - 7 - 1_800, (FWD * 300).lower())
    # chr2: nothing at the start; CCCTAA x50 120 kb from both ends (outside the search region);
    # TTAGGG x400, 30 N, TTAGGG x600 at the very end.
    chr2 = background(250_000, rng)
    chr2 = place(chr2, 120_000, REV * 50)
    end = FWD * 400 + 'N' * 30 + FWD * 600
    chr2 = place(chr2, 250_000 - len(end), end)
    # chrX: shorter than the 10 kb window; 20 copies at each end.
    chrx = place(place(background(3_000, rng), 0, REV * 20), 3_000 - 120, FWD * 20)
    return {'TEST0001.1': chr1, 'TEST0002.1': chr2, 'TEST0003.1': chrx,
            'TEST0004.1': background(500, rng), 'TEST0005.1': background(800, rng)}


def write_fasta(path, seqs, width=80):
    with gzip.open(path, 'wt') as fh:
        for i, (name, seq) in enumerate(seqs.items()):
            w = width if i % 2 == 0 else 61   # mixed line widths
            fh.write(f'>{name} synthetic sequence {i}\n')
            fh.writelines(seq[j:j + w] + '\n' for j in range(0, len(seq), w))


def crlf_copy(src, dest):
    dest.write_bytes(src.read_text().replace('\n', '\r\n').encode())
    return dest


class MotifRuns(unittest.TestCase):
    def test_revcomp(self):
        self.assertEqual(scan.revcomp(FWD), REV)

    def test_runs_chain_across_small_gaps_only(self):
        seq = 'AC' + FWD * 5 + 'A' * 18 + FWD * 3 + 'A' * 19 + FWD * 2
        runs = scan.find_runs(seq, FWD, max_gap=18)
        self.assertEqual(runs, [(2, 2 + 30 + 18 + 18, 8), (2 + 66 + 19, 2 + 66 + 19 + 12, 2)])

    def test_runs_match_a_naive_scan(self):
        rng = random.Random(7)
        seq = ''.join(rng.choice('ACGT') for _ in range(20_000))
        seq = place(seq, 3_000, FWD * 40 + 'ACG' + FWD * 10)
        hits = [i for i in range(len(seq) - 5) if seq[i:i + 6] == FWD]
        naive = []
        for h in hits:
            if naive and h - naive[-1][1] <= 18:
                naive[-1] = (naive[-1][0], h + 6, naive[-1][2] + 1)
            else:
                naive.append((h, h + 6, 1))
        self.assertEqual(scan.find_runs(seq, FWD, 18), naive)
        self.assertEqual(seq.count(FWD), len(hits))

    def test_terminal_array_is_the_qualifying_run_nearest_the_end(self):
        region = 'A' * 5 + FWD * 9 + 'A' * 100 + FWD * 10 + 'A' * 50 + FWD * 30 + 'A' * 3
        self.assertEqual(scan.terminal_array(region, FWD, 'start', 18, 10), (60, 10, 5 + 54 + 100))
        self.assertEqual(scan.terminal_array(region, FWD, 'end', 18, 10), (180, 30, 3))
        self.assertIsNone(scan.terminal_array(region, REV, 'end', 18, 10))


class FastaEnds(unittest.TestCase):
    def test_head_and_tail_match_slicing(self):
        rng = random.Random(3)
        seqs = {f's{i}': ''.join(rng.choice('ACGT') for _ in range(n))
                for i, n in enumerate([1, 49, 50, 51, 777, 5_000])}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'x.fa.gz'
            write_fasta(path, seqs, width=13)
            with scan.open_text(path) as fh:
                got = {sid: (n, h, t) for sid, n, h, t in scan.iter_fasta_ends(fh, 50)}
            with scan.open_text(path) as fh:
                only = [sid for sid, *_ in scan.iter_fasta_ends(fh, 50, wanted={'s4'})]
        for sid, seq in seqs.items():
            self.assertEqual(got[sid], (len(seq), seq[:50], seq[-50:]), sid)
        self.assertEqual(only, ['s4'])


class AssemblyReport(unittest.TestCase):
    def test_crlf_report_and_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = crlf_copy(FIXTURE / 'assembly_report.txt', Path(tmp) / 'r.txt')
            text = report.read_bytes().decode()   # keep the \r (read_text() would translate it)
            self.assertIn('\r\n', text)
            header, rows = scan.parse_assembly_report(text)
        self.assertEqual(header['GenBank assembly accession'], 'GCA_000000001.1')
        chroms = scan.select_chromosomes(rows)
        self.assertEqual([c['sequence_name'] for c in chroms if c['selected'] == 'yes'],
                         ['chr1', 'chr2', 'chrX'])
        reasons = {c['sequence_name']: c['reason'] for c in chroms if c['selected'] == 'no'}
        self.assertIn('Mitochondrion', reasons['chrM'])
        self.assertIn('unplaced-scaffold', reasons['scaf1'])
        self.assertTrue(all(not v.endswith('\r') for r in rows for v in r.values()))


class ScanAssembly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.seqs = synthetic_chromosomes()
        self.fasta = self.dir / 'genomic.fna.gz'
        write_fasta(self.fasta, self.seqs)
        self.report = crlf_copy(FIXTURE / 'assembly_report.txt', self.dir / 'report.txt')

    def tearDown(self):
        self.tmp.cleanup()

    def run_scan(self, fasta=None, report=None, accession='GCA_000000001.1'):
        return scan.scan_assembly(fasta or self.fasta, report or self.report, 'TEST_pri', 'pri',
                                  accession, PARAMS)

    def test_rows_and_values(self):
        rows, chroms = self.run_scan()
        self.assertEqual(len(rows), 6)   # 3 chromosomes x 2 ends
        by = {(r['chromosome'], r['end']): r for r in rows}

        r = by['chr1', 'start']
        self.assertEqual(r['expected_motif'], REV)
        self.assertEqual((r['ccctaa_count_1kb'], r['ccctaa_count_10kb'], r['ccctaa_count_100kb']), (166, 499, 499))
        self.assertEqual((r['ttaggg_count_1kb'], r['ttaggg_count_10kb'], r['ttaggg_count_100kb']), (0, 12, 312))
        self.assertEqual((r['ccctaa_array_bp'], r['ccctaa_array_copies'], r['ccctaa_array_dist_bp']), (3_000, 499, 0))
        self.assertEqual((r['ttaggg_array_bp'], r['ttaggg_array_copies'], r['ttaggg_array_dist_bp']), (72, 12, 5_000))

        r = by['chr1', 'end']
        self.assertEqual(r['expected_motif'], FWD)
        self.assertEqual((r['ttaggg_array_bp'], r['ttaggg_array_copies'], r['ttaggg_array_dist_bp']), (1_800, 300, 7))
        self.assertEqual(r['ccctaa_array_dist_bp'], 60_000 - 3_000)

        r = by['chr2', 'start']
        self.assertEqual((r['ccctaa_count_100kb'], r['ttaggg_count_100kb']), (0, 0))
        self.assertEqual((r['ccctaa_array_bp'], r['ccctaa_array_copies'], r['ccctaa_array_dist_bp']), (0, 0, 'NA'))
        r = by['chr2', 'end']
        self.assertEqual((r['ttaggg_count_1kb'], r['ttaggg_count_10kb'], r['ccctaa_count_100kb']), (166, 1_000, 0))
        self.assertEqual((r['ttaggg_array_bp'], r['ttaggg_array_copies'], r['ttaggg_array_dist_bp']), (3_600, 600, 0))

        r = by['chrX', 'start']   # shorter than the 10 kb window: it covers the whole sequence
        self.assertEqual((r['ccctaa_count_1kb'], r['ccctaa_count_10kb'], r['ttaggg_count_10kb']), (20, 20, 20))
        self.assertEqual((r['ttaggg_array_copies'], r['ttaggg_array_dist_bp']), (20, 2_880))

        self.assertEqual({r['seq_length'] for r in rows if r['chromosome'] == 'chr2'}, {250_000})
        self.assertEqual(sorted(c['genbank_accn'] for c in chroms), [f'TEST000{i}.1' for i in range(1, 6)])

    def test_main_writes_the_declared_columns(self):
        out_t, out_c = self.dir / 'out/t.tsv', self.dir / 'out/c.tsv'
        scan.main(self.fasta, self.report, out_t, out_c, 'TEST_pri', 'pri', 'GCA_000000001.1', PARAMS)
        lines = out_t.read_text().splitlines()
        self.assertEqual(lines[0].split('\t'), scan.telomere_columns(PARAMS))
        self.assertEqual(len(lines), 7)
        self.assertEqual(out_c.read_text().splitlines()[0].split('\t'), scan.CHROMOSOME_COLUMNS)

    def test_length_mismatch_fails(self):
        report = self.dir / 'bad.txt'
        report.write_text(self.report.read_text().replace('\t60000\t', '\t60001\t'))
        with self.assertRaisesRegex(ValueError, 'FASTA length 60000 != report length 60001'):
            self.run_scan(report=report)

    def test_missing_chromosome_fails(self):
        seqs = dict(self.seqs)
        del seqs['TEST0002.1']
        fasta = self.dir / 'short.fna.gz'
        write_fasta(fasta, seqs)
        with self.assertRaisesRegex(ValueError, 'missing from the FASTA'):
            self.run_scan(fasta=fasta)

    def test_wrong_accession_fails(self):
        with self.assertRaisesRegex(ValueError, 'not GCA_000000002.1'):
            self.run_scan(accession='GCA_000000002.1')


LISTING = ('<a href="/genomes/all/GCA/000/000/">Parent</a>\n'
           '<a href="GCA_000000001.1_TEST_pri/">GCA_000000001.1_TEST_pri/</a>\n'
           '<a href="https://www.example.org/policy.html">policy</a>\n')


class NcbiFetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        folder = self.dir / 'ncbi/GCA_000000001.1_TEST_pri'
        folder.mkdir(parents=True)
        self.files = {
            'GCA_000000001.1_TEST_pri_assembly_report.txt': (FIXTURE / 'assembly_report.txt').read_bytes(),
            'GCA_000000001.1_TEST_pri_genomic.fna.gz': gzip.compress(b'>TEST0001.1\nACGT\n'),
        }
        sums = []
        for name, data in self.files.items():
            (folder / name).write_bytes(data)
            sums.append(f'{hashlib.md5(data).hexdigest()}  ./{name}\n')
        sums.append('0123456789abcdef0123456789abcdef  ./other/file.txt\n')
        (folder / 'md5checksums.txt').write_text(''.join(sums))
        self.folder = folder
        self.parent = (self.dir / 'ncbi').as_uri() + '/'
        self.out = {k: self.dir / 'out' / k for k in ('fasta', 'report', 'md5s', 'record')}
        (self.dir / 'out').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self):
        with mock.patch.object(fetch, 'fetch_bytes', return_value=LISTING.encode()):
            return fetch.fetch_assembly('TEST_pri', 'GCA_000000001.1', self.out['fasta'],
                                        self.out['report'], self.out['md5s'], self.out['record'],
                                        parent_url=self.parent, wait_s=0)

    def test_parent_url_and_folder(self):
        self.assertEqual(fetch.accession_parent_url('GCA_062019780.1'),
                         'https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/062/019/780/')
        self.assertEqual(fetch.resolve_assembly_dir('GCA_000000001.1', LISTING), 'GCA_000000001.1_TEST_pri')
        with self.assertRaises(ValueError):
            fetch.resolve_assembly_dir('GCA_000000001.1', LISTING + '<a href="GCA_000000001.1_other/">')
        with self.assertRaises(ValueError):
            fetch.accession_parent_url('ROS_Cfam_2.0')

    def test_download_verifies_md5(self):
        records = self.fetch()
        self.assertEqual(self.out['fasta'].read_bytes(), self.files['GCA_000000001.1_TEST_pri_genomic.fna.gz'])
        self.assertEqual([r['md5_ok'] for r in records], ['NA', 'yes', 'yes'])
        lines = self.out['record'].read_text().splitlines()
        self.assertEqual(lines[0].split('\t'), fetch.RECORD_COLUMNS)
        self.assertEqual(len(lines), 4)

    def test_md5_mismatch_fails_and_leaves_nothing(self):
        (self.folder / 'GCA_000000001.1_TEST_pri_genomic.fna.gz').write_bytes(b'corrupted')
        with self.assertRaises(fetch.Md5Mismatch):
            self.fetch()
        self.assertFalse(self.out['fasta'].exists())
        self.assertEqual(list((self.dir / 'out').glob('*.part')), [])


MANIFEST_KEYS = ['describes', 'source', 'dest', 'job', 'scope', 'finished', 'objects', 'size',
                 'lane', 'commit', 'run_id', 'spec_id']


class Publish(unittest.TestCase):
    NAMES = {'telomeres': 'telomeres.tsv', 'chromosomes': 'chromosomes.tsv', 'inputs': 'inputs.tsv',
             'method': 'method.txt', 'run_info': 'run_info.json', 'sha256': 'sha256sums.txt',
             'manifest': '_MANIFEST.txt'}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.dir = Path(self.tmp.name)
        cols = scan.telomere_columns(PARAMS)
        for hap in ('pri', 'alt'):
            scan.write_tsv(d / f'{hap}.t.tsv', cols, [])
            scan.write_tsv(d / f'{hap}.c.tsv', scan.CHROMOSOME_COLUMNS, [])
            scan.write_tsv(d / f'{hap}.f.tsv', fetch.RECORD_COLUMNS, [])
        (d / 'pri.t.tsv').write_text((d / 'pri.t.tsv').read_text() + '\t'.join(['x'] * len(cols)) + '\n')

    def tearDown(self):
        self.tmp.cleanup()

    def publish(self, out, job='12345678'):
        d = self.dir
        prov = {'commit': 'a' * 40, 'head': 'b' * 40, 'images': {'python': 'img@sha256:x'}}
        publish.publish([d / 'pri.t.tsv', d / 'alt.t.tsv'], [d / 'pri.c.tsv', d / 'alt.c.tsv'],
                        [d / 'pri.f.tsv', d / 'alt.f.tsv'], out, 'telomeres.2026-11-22.aaaaaaa', 'sf',
                        'TEST', 'M02', [{'assembly': 'TEST_pri', 'haplotype': 'pri', 'accession': 'GCA_1'}],
                        PARAMS, {'path': 'x.py', 'sha256': 'c' * 64}, prov,
                        describes='SPEC.tsv M02: TEST pri+alt: telomere-motif scan',
                        dest='s3Fried/t2t/TEST/sf/telomeres.2026-11-22.aaaaaaa', job=job)

    def manifest(self, out):
        """_MANIFEST.txt as {key: value}, after checking every line is an aligned `key: value`."""
        lines = out['manifest'].read_text().splitlines()
        pairs = [re.fullmatch(r'([a-z_]+):( +)(\S.*)', l) for l in lines]
        self.assertTrue(all(pairs), lines)
        value_cols = {len(m[1]) + 1 + len(m[2]) for m in pairs}
        self.assertEqual(value_cols, {len('describes: ')}, 'values are not aligned')
        return {m[1]: m[3] for m in pairs}

    def test_run_folder(self):
        out = {k: self.dir / 'run' / v for k, v in self.NAMES.items()}
        self.publish(out)
        self.assertEqual(len(out['telomeres'].read_text().splitlines()), 2)
        sums = out['sha256'].read_text().splitlines()
        self.assertEqual(len(sums), 5)
        for line in sums:
            digest, name = line.split('  ')
            self.assertEqual(digest, hashlib.sha256((self.dir / 'run' / name).read_bytes()).hexdigest())
        info = json.loads(out['run_info'].read_text())
        self.assertEqual((info['commit'], info['lane'], info['run_id']), ('a' * 40, 'sf', 'telomeres.2026-11-22.aaaaaaa'))
        self.assertIn('"max_gap_bp": 18', out['method'].read_text())

    def test_manifest_is_the_bucket_header_block(self):
        out = {k: self.dir / 'run' / v for k, v in self.NAMES.items()}
        self.publish(out)
        text = out['manifest'].read_text()
        self.assertNotIn('\t', text)   # no per-object rows: sha256sums.txt holds those
        m = self.manifest(out)
        self.assertEqual(list(m), MANIFEST_KEYS)
        self.assertEqual(m['describes'], 'SPEC.tsv M02: TEST pri+alt: telomere-motif scan')
        self.assertEqual(m['source'], str((self.dir / 'run').resolve()))
        self.assertEqual(m['dest'], 's3Fried/t2t/TEST/sf/telomeres.2026-11-22.aaaaaaa')
        self.assertEqual((m['job'], m['scope']), ('12345678', 'metric'))
        self.assertIsNotNone(datetime.fromisoformat(m['finished']).utcoffset())
        others = [p for p in (self.dir / 'run').iterdir() if p.name != '_MANIFEST.txt']
        self.assertEqual(int(m['objects']), len(others))
        self.assertEqual(m['size'], publish.human_size(sum(p.stat().st_size for p in others)))
        self.assertEqual((m['lane'], m['commit']), ('sf', 'a' * 40))
        self.assertEqual((m['run_id'], m['spec_id']), ('telomeres.2026-11-22.aaaaaaa', 'M02'))

    def test_manifest_job_outside_slurm(self):
        out = {k: self.dir / 'run' / v for k, v in self.NAMES.items()}
        self.publish(out, job=None)
        self.assertEqual(self.manifest(out)['job'], 'NA')

    def test_outputs_in_two_folders_fail(self):
        out = {k: self.dir / 'run' / v for k, v in self.NAMES.items()}
        out['manifest'] = self.dir / 'elsewhere' / '_MANIFEST.txt'
        with self.assertRaisesRegex(ValueError, 'span 2 folders'):
            self.publish(out)

    def test_human_size(self):
        cases = {0: '0B', 1023: '1023B', 1024: '1KiB', 1536: '1.5KiB', 10 * 1024 - 1: '10KiB',
                 62_700: '61KiB', 1_500_000_000: '1.4GiB', 68 * 1024 ** 3: '68GiB', 3 * 1024 ** 4: '3TiB'}
        self.assertEqual({n: publish.human_size(n) for n in cases}, cases)

    def test_header_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a', Path(tmp) / 'b'
            a.write_text('x\ty\n1\t2\n')
            b.write_text('x\tz\n1\t2\n')
            with self.assertRaises(ValueError):
                publish.concat_tsv([a, b], Path(tmp) / 'c')


if __name__ == '__main__':
    unittest.main()
