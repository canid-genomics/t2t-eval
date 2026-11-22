# M01 test fixture: real gfastats output on a synthetic FASTA

`gfastats.{summary.tsv,sequences.tsv,gaps.bed}` are the output of the three `jc_gfastats`
commands (`workflow/rules/jc/assembly_stats.smk`), run with the pinned image
`quay.io/biocontainers/gfastats@sha256:f4903ca4…bdd7` (gfastats v1.3.11) on the FASTA that
`synthetic_fasta()` in `tests/jc/test_assembly_stats.py` writes (gzipped as `synthetic.fna.gz`):

```
gfastats synthetic.fna.gz -j 4 --tabular              > gfastats.summary.tsv
gfastats synthetic.fna.gz -j 4 --path-report --tabular > gfastats.sequences.tsv
gfastats synthetic.fna.gz -j 4 --out-coord g          > gfastats.gaps.bed
```

Three records: `chrA.1` with an internal 100 bp N run, an internal 5 bp `n` run and a terminal
3 bp N run; `chrB.1` with a leading 10 bp N run; `chrC.1` with no gaps and no header comment.
No real sequence data.

gfastats ends the path report's header line with a tab; it is removed here (`git diff --check`
flags trailing whitespace), and the test puts it back to check both forms parse the same.
