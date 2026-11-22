#!/usr/bin/env python3
"""Populate the local_dev/ fixture tree with touched-empty files.

Reads `config/config.local.yaml` and the `*.local.tsv` sheets it points at,
then `touch`es the leaf paths a dry-run needs to exist: raw external inputs
(reads, references, assemblies) plus any output of a toggled-OFF stage that a
toggled-ON stage consumes as input. The imported per-file fastqs are touched
because assembly_compare consumes them when the read phase is off.

Outputs produced by currently-active rules are deliberately NOT pre-touched, so
a `snakemake -n` shows those jobs. Use `snakemake -n -F` to enumerate the full
job graph regardless of what is already touched.

Idempotent. Stdlib only. Run from the repo root:

    python3 local_dev/scaffold.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path


HAPS = ['haplotype1', 'haplotype2', 'unassigned', 'disconnected']
ASM_PER_RUN = [
    'assembly.fasta',
    'assembly.scfmap',
    'assembly.homopolymer-compressed.layout',
    # graph_index / graph_align_ont in assembly_curate.smk read the sequence-
    # carrying HPC graph, not the noseq one the fillet rules use.
    'assembly.homopolymer-compressed.gfa',
] + [f'assembly.{h}.fasta' for h in HAPS]

# assembly_curate.smk only: graph_align_ont globs the verkko align stage. One
# touched shard is enough for the DAG; the rule's own `ls` guard is what catches
# a real run whose stage dirs were cleaned off scratch.
# Agate names these ont001..ont106 (three digits); match that exactly or
# the rule's input never resolves in a local dry run.
ASM_STAGE_FILES = [
    '3-align/split/ont001.fasta.gz',
    # vf_gap_evidence reads verkko's own node-to-node Hi-C link counts
    # straight out of the hic stage rather than realigning anything.
    '8-hicPipeline/hic.byread.compressed',
]


def parse_local_config(path: Path) -> dict:
    """Minimal YAML reader for flat scalars + one-deep nesting.

    Handles `key: value` and `key:\\n  nested: value`. Strips quotes/comments.
    config.local.yaml stays simple by design — bail on anything more complex.
    """
    out: dict = {}
    cur_section: dict | None = None

    for raw in path.read_text().splitlines():
        line = raw.split('#', 1)[0].rstrip()
        if not line.strip():
            continue
        m = re.match(r'^(\S+):\s*(.*)$', line)
        if m:
            key, val = m.group(1), m.group(2).strip().strip("'\"")
            if val == '':
                cur_section = {}
                out[key] = cur_section
            else:
                out[key] = val
                cur_section = None
            continue
        m = re.match(r'^\s+(\S+):\s*(.*)$', line)
        if m and cur_section is not None:
            cur_section[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


def read_tsv(path: Path) -> list[dict]:
    with path.open() as fh:
        return list(csv.DictReader(fh, delimiter='\t'))


def touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch(exist_ok=True)


def scaffold_references(repo_root: Path, ref_cfg: dict, n: list[int]) -> None:
    """References + minimap2 index (output of bam_concordance.smk:minimap2_index)."""
    for k in ('fasta', 'fasta_filtered', 'cdna'):
        if k in ref_cfg:
            touch(repo_root / ref_cfg[k])
            n[0] += 1
    if 'fasta' in ref_cfg:
        touch(repo_root / (ref_cfg['fasta'] + '.mmi'))
        n[0] += 1


def scaffold_assemblies(repo_root: Path, workdir: Path, asm_path: Path, n: list[int]) -> None:
    for r in read_tsv(asm_path):
        base = workdir / r['sample'] / 'assemblies' / r['run']
        for f in ASM_PER_RUN:
            touch(base / f)
            n[0] += 1
        # _ssphased runs genuinely have no stage dirs (verkko --paths writes
        # none), so mirror that here rather than papering over it.
        if not r['run'].endswith('_ssphased'):
            for f in ASM_STAGE_FILES:
                touch(base / f)
                n[0] += 1


def scaffold_inspector_beds(workdir: Path, asm_path: Path, n: list[int]) -> None:
    """Touch Inspector's structural_error.bed, which build_validator_mask (1.6) reads.

    It is NOT a declared output of inspector_qc -- that rule declares only
    summary_statistics (assembly_compare.smk:107) -- so snakemake treats it as an
    external input it cannot produce, and a dry-run fails with MissingInputException
    without this. Same reasoning as the toggled-off stage outputs above: pre-touch
    what the DAG cannot make for itself.
    """
    for r in read_tsv(asm_path):
        for hap in ('haplotype1', 'haplotype2'):
            d = (workdir / 'results' / r['sample'] / 'assemblies' / r['run'] / 'qc'
                 / 'inspector' / f"{r['sample']}.{r['run']}.{hap}")
            d.mkdir(parents=True, exist_ok=True)
            touch(d / 'structural_error.bed')
            n[0] += 1


def scaffold_pb(repo_root: Path, workdir: Path, pb_path: Path, n: list[int]) -> None:
    """PB raw inputs + the imported fastq (output of read_entry.smk:import_pb_reads;
    consumed by merqury / assembly_compare when the read phase is off)."""
    for r in read_tsv(pb_path):
        # input: raw reads (.bam or .fastq.gz), mirrored under local_dev/
        touch(repo_root / r['read_path'])
        n[0] += 1
        # output of read_entry.smk:import_pb_reads
        touch(workdir / 'results' / r['sample'] / 'pb' / r['file_id'] / f"{r['file_id']}.fastq.gz")
        n[0] += 1


def scaffold_ont(repo_root: Path, workdir: Path, ont_path: Path, n: list[int]) -> None:
    """ONT raw inputs + the imported per-file fastq.

    The imported fastq (output of read_entry.smk:import_ont_reads) is consumed by
    assembly_compare (align_reads_to_asm_ont) when the read phase is off, so it must
    pre-exist in that config. Read-phase OUTPUTS (corrected reads, herro
    intermediates, ONT-stats figures) are produced by the active read-side rules and
    are NOT consumed by any other tail2tail rule, so they are not pre-touched.
    The `*_corrected` columns are read only for run-vs-skip scoping — not inputs.
    """
    for r in read_tsv(ont_path):
        sample, fid = r['sample'], r['file_id']
        fid_dir = workdir / 'results' / sample / 'ont' / fid

        touch(repo_root / r['read_path'])      # raw ONT input (.bam or .fastq.gz)
        touch(fid_dir / f'{fid}.fastq.gz')     # import_ont_reads output
        n[0] += 2


def scaffold_external_reads(repo_root: Path, sheet_paths: list[Path], n: list[int]) -> None:
    """IL + Hi-C raw fastqs — touched at literal paths from the sheets."""
    for sheet_path in sheet_paths:
        for r in read_tsv(sheet_path):
            touch(repo_root / r['fastq_r1'])
            touch(repo_root / r['fastq_r2'])
            n[0] += 2


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    cfg_path = repo_root / 'config' / 'config.local.yaml'
    if not cfg_path.exists():
        sys.exit(f'config not found: {cfg_path}')
    cfg = parse_local_config(cfg_path)

    workdir = repo_root / cfg['workdir']
    n = [0]

    scaffold_references(repo_root, cfg.get('reference', {}), n)
    scaffold_assemblies(repo_root, workdir, repo_root / cfg['asm_samples'], n)
    scaffold_inspector_beds(workdir, repo_root / cfg['asm_samples'], n)
    scaffold_pb(repo_root, workdir, repo_root / cfg['pb_samples'], n)
    scaffold_ont(repo_root, workdir, repo_root / cfg['ont_samples'], n)
    scaffold_external_reads(
        repo_root,
        [repo_root / cfg['il_samples'], repo_root / cfg['hic_samples']],
        n,
    )

    print(f'scaffolded {n[0]} files under {workdir.parent}/')


if __name__ == '__main__':
    main()
