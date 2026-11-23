# reports/sf/M03

SPEC row M03 (sf, local): the per-chromosome figure, pri vs alt, of expected-motif arrays at the
chromosome ends (from M02) and gaps (from M01), with its source table. The code and its tests
were built ahead of the M01 handoff on synthetic fixtures (`sf/M03-prep`, PR #9); `sf/M03` ran it
on 2026-11-23 on `reports/sf/M02/` and `reports/jc/M01/` as merged to main (`24af769`). Outputs:
`completeness.tsv`, `completeness.method.txt`, `completeness.pdf`, `completeness.png`, and the
`SUMMARY.md` (approved by Steven, 2026-11-23).

- Script: `workflow/scripts/sf/completeness.py` (stdlib + matplotlib; method in its docstring)
- Tests: `tests/sf/test_completeness.py`, fixtures in `tests/sf/fixture/completeness/`

## Inputs

| Input | From | Where |
|---|---|---|
| `telomeres.tsv` | M02 (sf), run `telomeres.2026-11-22.a88f9b4` | `reports/sf/M02/telomeres.tsv` |
| `gfastats.tsv` | M01 (jc), run `assembly_stats.<YYYY-MM-DD>.<sha7>` | `reports/jc/M01/gfastats.tsv` |
| `gaps.bed` | M01 (jc), same run | `reports/jc/M01/gaps.bed` |

Use the M01 copies in `reports/jc/M01/` once jc's report task has committed them, so that
`completeness.method.txt` records repo paths. Until then, take them from the Tier 2 folder the
`[handoff] M01` message names (`s3://t2t/ROS_Cfam_2.0/jc/assembly_stats.<YYYY-MM-DD>.<sha7>/`); the
method file then records only the file names, with their sha256. Either way, check them against
the run's own listing first:

```
cd reports/jc/M01 && shasum -a 256 -c sha256sums.txt    # or the Tier 2 folder's copy
```

## Run (local, from the repo root)

```
pixi run --manifest-path <main checkout>/pixi.toml --frozen -e fig \
    python workflow/scripts/sf/completeness.py \
        --telomeres reports/sf/M02/telomeres.tsv \
        --gfastats  reports/jc/M01/gfastats.tsv \
        --gaps      reports/jc/M01/gaps.bed \
        --out-dir   reports/sf/M03
```

In a wg worktree, never `pixi install` or `pixi run` from the worktree's own manifest. Point at
the main checkout's manifest as above, or `eval "$(pixi shell-hook --manifest-path <main
checkout>/pixi.toml -e fig)"` and then call `python`. It prints a status tally per haplotype on
stderr and writes:

| File | What it is |
|---|---|
| `completeness.tsv` | one row per haplotype x chromosome: lengths, expected-motif array copies and distance from the end, terminal-10 kb counts, gaps, `status` |
| `completeness.method.txt` | inputs with sha256, thresholds, the status rules, Python and matplotlib versions |
| `completeness.pdf`, `completeness.png` | the figure (PNG at 300 dpi; the PDF has no creation date, so a re-run gives the same bytes) |

The thresholds default to the reading in the approved M02 summary: an end has an expected-motif
array if it has >= 10 copies anywhere in the terminal 100 kb that M02 searches (`--min-copies 10`,
`--max-dist-bp 100000`), which gives 147 of 156 ends. Steven chose this on 2026-11-23 (PR #9) over
a stricter 1 kb, which would drop five ends whose arrays sit 1.2–3.4 kb in (pri chr8 start; alt
chr16 end, chr24 start, chr29 end, chr32 start). The distance of every array from the end is in
`completeness.tsv`. Change the thresholds only on both humans' say-so; the values used go into
`completeness.method.txt` and the legend.

The script fails loudly if any M02 chromosome has no M01 sequence row with the same assembly,
seq_id, haplotype, accession and length, or if a gap runs past its sequence. If it fails, fix
the inputs, not the check.

## Before committing the outputs

- Look at the figure: 40 pri rows (chr1-38, X, Y) and 38 alt rows, with alt's X and Y marked
  "no sequence in this assembly".
- The figure never says "T2T", "complete", "gapless" or "telomere-to-telomere" (AGENTS.md; the
  script refuses to save a figure whose text does).
- Status: diagnostic-only until PROVENANCE.md records otherwise. A `status` is a fixed rule on the
  M01/M02 numbers, not a call about the assembly; any claim from it waits for both humans.
