"""Tests for the shared run-folder publisher, workflow/scripts/shared/publish.py. Stdlib unittest:

    python -m unittest discover -s tests/shared -p 'test_*.py' -v
"""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('publish', REPO / 'workflow/scripts/shared/publish.py')
pub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pub)

INFO = {'run_id': 'telomeres_tidk.2026-11-23.abcdef1', 'lane': 'jc', 'spec_id': 'M02b',
        'commit': 'a' * 40, 'images': {'tidk': 'docker://example@sha256:' + '0' * 64}}


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / 'run'
        self.run.mkdir()
        self.files = []
        for name, text in [('x.ends.tsv', 'id\tside\nchr1\tstart\n'), ('x_tidk_plot.svg', '<svg/>\n')]:
            (self.run / name).write_text(text)
            self.files.append(self.run / name)
        self.out = {k: self.run / n for k, n in
                    [('run_info', 'run_info.json'), ('sha256', 'sha256sums.txt'), ('manifest', '_MANIFEST.txt')]}

    def tearDown(self):
        self.tmp.cleanup()

    def publish(self, files=None, info=INFO, **out):
        pub.publish(files or self.files, **{**self.out, **out}, info=info,
                    describes='SPEC.tsv M02b: test', dest='s3Fried/t2t/S/jc/run', job='123')

    def test_files(self):
        self.publish()
        run_info = json.loads(self.out['run_info'].read_text())
        self.assertEqual({k: run_info[k] for k in INFO}, INFO)
        self.assertEqual(run_info['files'], ['x.ends.tsv', 'x_tidk_plot.svg'])

        # sha256sums.txt: every file but itself and the manifest, and each hash is right.
        sums = [l.split('  ') for l in self.out['sha256'].read_text().splitlines()]
        self.assertEqual([n for _, n in sums], ['x.ends.tsv', 'x_tidk_plot.svg', 'run_info.json'])
        for digest, name in sums:
            self.assertEqual(digest, hashlib.sha256((self.run / name).read_bytes()).hexdigest())

        lines = self.out['manifest'].read_text().splitlines()
        keys = [l.split(':')[0] for l in lines]
        self.assertEqual(keys, ['describes', 'source', 'dest', 'job', 'scope', 'finished', 'objects',
                                'size', 'lane', 'commit', 'run_id', 'spec_id'])
        self.assertEqual(len({l.index(' ', len('describes:')) for l in lines}), 1)  # values aligned
        fields = {l.split(':', 1)[0]: l.split(':', 1)[1].strip() for l in lines}
        self.assertEqual(fields['source'], str(self.run.resolve()))
        self.assertEqual(fields['objects'], '4')
        size = sum((self.run / n).stat().st_size for n in
                   ['x.ends.tsv', 'x_tidk_plot.svg', 'run_info.json', 'sha256sums.txt'])
        self.assertEqual(fields['size'], f'{size}B')
        self.assertEqual((fields['lane'], fields['commit'], fields['run_id'], fields['spec_id']),
                         ('jc', 'a' * 40, INFO['run_id'], 'M02b'))

    def test_refusals(self):
        with self.assertRaisesRegex(ValueError, 'lacks'):
            self.publish(info={k: v for k, v in INFO.items() if k != 'commit'})
        with self.assertRaisesRegex(ValueError, 'placeholder'):
            self.publish(info={**INFO, 'run_id': 'unset.0000-00-00.0000000'})
        other = Path(self.tmp.name) / 'elsewhere.tsv'
        other.write_text('x\n')
        with self.assertRaisesRegex(ValueError, 'folders'):
            self.publish(files=self.files + [other])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.publish(files=self.files + [self.out['run_info']])

    def test_human_size(self):
        self.assertEqual([pub.human_size(n) for n in (0, 1023, 1536, 10 * 1024, 68 * 1024 ** 3)],
                         ['0B', '1023B', '1.5KiB', '10KiB', '68GiB'])


if __name__ == '__main__':
    unittest.main()
