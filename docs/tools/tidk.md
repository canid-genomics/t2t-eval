# Tool brief: tidk 0.3.3

*Approved by Jonah, 2026-11-23. Read before writing or reviewing any rule that runs tidk.*


## The tool

| | |
|---|---|
| What | Telomere Identification toolKit: finds and calls telomeric repeats in assemblies and reads |
| Version | 0.3.3 (latest release, 2026-11-23) |
| Image | BioContainers, nothing to build: `docker://quay.io/biocontainers/tidk@sha256:8d5b6e6aff8adb6e6f65c6e40ae1c6f5850be0d926022b6085d3d80641678f86` (tag `0.3.3--hef77e2b_0`, linux/amd64) |
| Upstream | https://github.com/tolkit/telomeric-identifier (Rust; Darwin Tree of Life) |
| License | MIT |
| Cite | Max R Brown, Pablo Gonzalez de La Rosa, Mark Blaxter. tidk: a toolkit to rapidly identify telomeric repeats from genomic datasets. *Bioinformatics* 2025, btaf049. https://doi.org/10.1093/bioinformatics/btaf049 |
| Sources read | `tidk <cmd> --help` for every command in the pinned image, the v0.3.3 README, and a run of `ends`, `search` and `plot` on a synthetic assembly (below) |

## What it can do, and what we use

| Command | What it does | Use? |
|---|---|---|
| **`ends`** | Calls a telomere at **both ends of each sequence** and reports which sequences are T2T. Each end gets a status: `present`, `wrong_strand`, `not_terminal` or `absent` | **Yes: the M02b measurement** |
| **`search`** | Counts a given repeat in fixed windows along every sequence | **Yes: input to the figure** |
| **`plot`** | SVG line plot of the `search` output, one panel per sequence | **Yes: the M02b figure** |
| `explore` | Discovers the repeat unit (k-mers 5–12) near sequence ends | No. The vertebrate unit TTAGGG is known; `ends` also reports the unit it used (`unit` in the JSON) |
| `caps` | Characterises what is at each end: telomere calls, end-enriched tandem repeat families, gaps near the tip, and **with `--reads`, whether long reads run past each end** | **Not now; strong candidate for the real project** (we have HiFi/ONT for these dogs) |
| `length` | Telomere length from long reads (HiFi/ONT) | Not now; real project candidate |
| `find`, `build` | Like `search`, but repeats from a clade database that must be downloaded (`build`) | No. Needs network at run time; `search --string TTAGGG` does the same |

## How `ends` decides (README + help, confirmed on synthetic data)

For each end it searches a **window** (default **10,000 bp**) for runs of the repeat at least
**`--min-length`** long (default **200 bp**). By default a run may contain sequencing errors
(substitutions and indels); `--exact` turns that off. Status per end:

- **`present`**: a telomere on the expected strand (C-rich `CCCTAA` reading along the sequence at
  the start, G-rich `TTAGGG` at the end) starting within **`--max-offset`** (default **1,000 bp**)
  of the tip. **Only `present` counts towards T2T.**
- **`not_terminal`**: right strand, but further in than `--max-offset`. Sequence beyond it needs a
  look. In the synthetic test, a telomere 2,502 bp in was flagged this way.
- **`wrong_strand`**: a telomere at the tip, but on the other strand. Often a misjoin or an
  inverted end.
- **`absent`**: none of the above, including runs shorter than `--min-length` (a 120 bp telomere
  in the test came out `absent`).
- **`window_limited = true`**: the telomere reaches the inner edge of the window, so it may be
  longer than reported.

The tool's authors define "at the end" as within 1 kb of the tip. That settles the 1 kb / 10 kb /
100 kb question from M03 with a published default instead of our choice.

## Proposed commands (one job per haplotype)

```bash
# 1. telomere calls at both ends of every chromosome
tidk ends --string TTAGGG \
    --window 10000 --min-length 200 --max-offset 1000 \
    --min-sequence-length 1000000 \
    --output {assembly} --dir {outdir} {fasta.gz}

# 2. repeat counts along every chromosome, for the figure
tidk search --string TTAGGG --window 10000 --extension tsv \
    --output {assembly} --dir {outdir} {fasta.gz}

# 3. the figure
tidk plot --tsv {outdir}/{assembly}_telomeric_repeat_windows.tsv \
    --output {outdir}/{assembly}_tidk_plot
```

- All settings except `--min-sequence-length` are the tool's defaults, written out so the run
  records them. `--min-sequence-length 1000000` skips sequences under 1 Mb. In ROS_Cfam_2.0 that
  drops only chrM (16,730 bp), leaving the 40 pri and 38 alt chromosomes, the same 156 ends as
  M02. **No custom selection script.**
- Error-tolerant runs (the default) are the tool's recommended mode. Optionally, one extra
  `tidk ends --exact` run gives a like-for-like comparison with M02's exact matching.
- `ends` and `search` read gzipped FASTA directly, so the M01 download (`jc_ncbi_fetch`) is the input.

## Outputs (exact formats, from the synthetic run)

**`{assembly}.ends.tsv`**, one row per end:
`id  sequence_length  side  status  telomere_start  telomere_end  telomere_length  offset  strand  window_limited`
(`side` = start/end; coordinates 0-based, half-open; `NA` when `absent`). `id` is the FASTA id
up to the first space, i.e. the GenBank accession, which is the same key as M01 and M02.

**`{assembly}.ends.bed`**: the telomeres found, named `<side>_<status>`.

**`{assembly}.ends.json`**: summary: `t2t` count and `t2t_ids`, `one_end`, `no_ends`, lists
of `not_terminal` and `wrong_strand` ends, plus the settings and `tidk_version`.

**`{assembly}_telomeric_repeat_windows.tsv`** (search):
`id  window  forward_repeat_number  reverse_repeat_number  telomeric_repeat`
(`window` = the window's end coordinate; forward = TTAGGG, reverse = CCCTAA).

**`{assembly}_tidk_plot.svg`**: the figure.

stderr names every `wrong_strand` and `not_terminal` end, so we keep the job log.

## Comparison with M02 (the `jc/M02b-report` step, local)

Join `ends.tsv` with `reports/sf/M02/telomeres.tsv` on (assembly, seq_id, side), giving one row per
end with M02's array copies and distance next to tidk's status, length and offset. That's a
~20-line join, or `join`/awk. **Differences are expected, and they are the point of M02b:**

| | M02 (custom) | tidk ends (defaults) |
|---|---|---|
| Matching | exact copies | error-tolerant runs |
| Minimum | ≥ 10 copies (60 bp) | ≥ 200 bp |
| "At the end" | anywhere in the terminal 100 kb | within 1 kb, else `not_terminal` |
| Search window | 100 kb | 10 kb |
| Strand check | expected motif only | also flags `wrong_strand` |

Before any data: the five M02 ends whose arrays start 1.2–3.4 kb in (pri chr8 start; alt chr16
end, chr24 start, chr29 end, chr32 start) should come out `not_terminal`. Ends whose M02 array is
under 200 bp may come out `absent`. These are expectations to check, not results.

## Pitfalls found

- **`search` windows** are counted independently: a copy that crosses a window boundary is
  counted in neither, and each sequence's last window is partial. That's fine for a plot, but
  **don't build end calls from `search`** (the first M02b ticket did; `ends` exists for this).
- `plot` only takes `search`/`find` output, not `ends`.
- `find` needs `tidk build` (network); don't use it on agate.
- The `--window` of `ends` (10 kb) is only how far in it looks; `--max-offset` (1 kb) decides
  `present` vs `not_terminal`.

## What the ticket then needs (glue budget)

- **Rules:** `jc_tidk_ends`, `jc_tidk_search`, `jc_tidk_plot`, each a `shell:` call to tidk in the
  pinned image. Publish tidk's files unchanged.
- **Our code:** none for the measurement. The shared publisher (rev 6) writes the manifest and
  checksums. The M02 join lives in the report step.
- **Validation:** `ends.tsv` has 156 rows (80 pri + 76 alt); `ends.json` `sequences` = 40 / 38;
  `tidk_version` = 0.3.3; every file traces to the Tier 2 manifest.

## Later (real project)

`tidk caps --reads <HiFi/ONT>` asks whether reads run past each assembly end and what repeat
the overhangs carry. That's a direct check of whether an end is truly finished, which no FASTA-only
method can give. `tidk length` on the same reads gives telomere lengths. Both are worth a tool
brief of their own before use.
