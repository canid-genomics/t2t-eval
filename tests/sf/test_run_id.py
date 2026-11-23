"""Tests for the no-ticket run_id placeholder in workflow/scripts/utils.py (run_id(), tier2(),
refuse_unset_run_id() and the Snakefile's onstart that calls it). Stdlib unittest, no Snakemake:

    python -m unittest discover -s tests/sf -p 'test_*.py' -v
"""
import importlib.util
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
RUN_ID_RE = re.compile(r'[a-z0-9_]+\.\d{4}-\d{2}-\d{2}\.[0-9a-f]{7}')
TICKET_RUN_ID = 'telomeres.2026-11-22.a88f9b4'


def utils_with(**config):
    """utils.py's names as the Snakefile's `include:` sees them, with `config` and a stand-in
    for Snakemake's `storage` injected."""
    path = REPO / 'workflow/scripts/utils.py'
    ns = {'config': {'lanes': ['jc', 'sf', 'shared'], 'tier2_bucket': 's3://t2t', **config},
          'storage': SimpleNamespace(s3=lambda query: f'storage.s3:{query}')}
    exec(compile(path.read_text(), str(path), 'exec'), ns)
    return SimpleNamespace(**{k: v for k, v in ns.items() if not k.startswith('__')})


class Placeholder(unittest.TestCase):
    def test_unset_run_id_gives_the_placeholder(self):
        for config in ({}, {'run_id': None}, {'run_id': ''}):
            u = utils_with(offload=True, **config)
            self.assertEqual(u.run_id(), u.RUN_ID_UNSET, config)
        self.assertEqual(utils_with(run_id=TICKET_RUN_ID).run_id(), TICKET_RUN_ID)

    def test_placeholder_is_run_id_shaped_and_fake(self):
        u = utils_with()
        self.assertRegex(u.RUN_ID_UNSET, RUN_ID_RE)
        self.assertTrue(u.RUN_ID_UNSET.startswith('unset.0000-00-00.'))

    def test_tier2_paths_still_build_at_parse_time(self):
        # Rules build their Tier 2 outputs from run_id() at parse time, so this must not raise.
        u = utils_with(offload=True)
        self.assertEqual(u.tier2(f'{u.run_id()}/x.tsv', 'sf', 'DOG'),
                         f'storage.s3:s3://t2t/DOG/sf/{u.RUN_ID_UNSET}/x.tsv')


class Refusal(unittest.TestCase):
    def test_offload_run_with_the_placeholder_is_refused(self):
        for config in ({}, {'run_id': None}):
            u = utils_with(offload=True, **config)
            with self.assertRaisesRegex(ValueError, 'run_id is unset .* nothing may go to Tier 2'):
                u.refuse_unset_run_id()

    def test_placeholder_given_explicitly_is_refused_too(self):
        u = utils_with(offload=True)
        with self.assertRaises(ValueError):
            utils_with(offload=True, run_id=u.RUN_ID_UNSET).refuse_unset_run_id()

    def test_ticket_run_id_or_offload_off_runs(self):
        self.assertIsNone(utils_with(offload=True, run_id=TICKET_RUN_ID).refuse_unset_run_id())
        self.assertIsNone(utils_with(offload=False).refuse_unset_run_id())   # local tier2/ only

    def test_snakefile_onstart_calls_the_refusal(self):
        text = (REPO / 'workflow/Snakefile').read_text()
        self.assertRegex(text, re.compile(r'^onstart:\n[ ]+refuse_unset_run_id\(\)$', re.M))

    def test_publish_script_refuses_the_same_placeholder(self):
        spec = importlib.util.spec_from_file_location(
            'telomeres_publish', REPO / 'workflow/scripts/sf/telomeres_publish.py')
        publish = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publish)
        self.assertEqual(publish.RUN_ID_UNSET, utils_with().RUN_ID_UNSET)


if __name__ == '__main__':
    unittest.main()
