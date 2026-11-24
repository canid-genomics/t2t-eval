# reports/jc/M02b

Nine of the 13 objects in `s3://t2t/ROS_Cfam_2.0/jc/telomeres_tidk.2026-11-23.8774911/` are
byte-for-byte copies here, plus `compare_m02.tsv` (the join with M02) and `tier2_sha256.txt`.
They come from SPEC row M02b and the ticket `tickets/jc/M02b.md` at commit `8774911`
(`run_info.json` `commit: 87749111163795aca9680c61faba95ce06cc8cd8`). The run was agate job
7926059, COMPLETED 2026-11-23, and job 7935950 published the folder (`_MANIFEST.txt` `job:`).
`run_info.json` records `head: 304d677` and `tracked_dirty: false`. Do not edit the copies. They
were staged from Tier 2 for the `jc/M02b-report` task, which had no Tier 2 access, and checked
against the run's `sha256sums.txt` before copying.

Method, settings and output formats: `docs/tools/tidk.md`. Each haplotype ran
`tidk ends --string TTAGGG --window 10000 --min-length 200 --max-offset 1000
--min-sequence-length 1000000`, `tidk search --string TTAGGG --window 10000 --extension tsv` and
`tidk plot` (exact arguments in `run_info.json` `tidk_args`). The end calls are tidk's own; no
custom repeat scanner was run.

Images (`run_info.json` `images`):
- `tidk`: `docker://quay.io/biocontainers/tidk@sha256:8d5b6e6aff8adb6e6f65c6e40ae1c6f5850be0d926022b6085d3d80641678f86`
  (BioContainers `0.3.3--hef77e2b_0`; both `ends.json` give `tidk_version: 0.3.3`)
- `python`: `docker://ghcr.io/canid-genomics/python@sha256:a909d1c838b9b40e4274b06b397042e6dd8d4c9b2e2ae7e11ace354268624d57` (publisher only)

| File | What it is |
|---|---|
| `ROS_Cfam_2.0_{pri,alt}.ends.tsv` | `tidk ends`: one row per chromosome end (80 pri, 76 alt): status, telomere start/end/length, offset, strand, window_limited |
| `ROS_Cfam_2.0_{pri,alt}.ends.bed` | `tidk ends`: the telomere runs it found, named `<side>_<status>` (77 pri, 70 alt rows) |
| `ROS_Cfam_2.0_{pri,alt}.ends.json` | `tidk ends`: per-haplotype summary (`sequences`, `t2t`, `one_end`, `no_ends`, `not_terminal`, `wrong_strand`), settings and `tidk_version` |
| `run_info.json` | commit, head, config hash, image digests, tidk arguments, assemblies and accessions, Snakemake and plugin versions |
| `sha256sums.txt` | the run's own sha256 listing of the 10 tidk files (including the 4 not copied) and `run_info.json` |
| `_MANIFEST.txt` | the t2t bucket manifest for the run folder (`objects: 12`, i.e. every file but itself) |
| `compare_m02.tsv` | one row per chromosome end (156), M02's array next to tidk's call; see below |
| `tier2_sha256.txt` | sha256 of the 9 copied files (`shasum -a 256 -c tier2_sha256.txt`) |

`tier2_sha256.txt` lists the 7 copied files in `sha256sums.txt` with the same hashes. It also
lists `sha256sums.txt` and `_MANIFEST.txt`, which the run's own listing leaves out; those two are
hashed as copied. In this folder, `shasum -a 256 -c --ignore-missing sha256sums.txt` checks the 7.

Not copied, on Tier 2 only (sha256 from `sha256sums.txt`):

| File | sha256 |
|---|---|
| `ROS_Cfam_2.0_pri_telomeric_repeat_windows.tsv` (`tidk search`) | `be346d3036adf3543a7a0a00e5512cc5dd1b0e46185ab5b1fbe06ad73de52ba5` |
| `ROS_Cfam_2.0_pri_tidk_plot.svg` (`tidk plot`) | `ca1df6f0e6c37c8f1369912c57c82604f463cfed93e2f7af6230ea579a7232f3` |
| `ROS_Cfam_2.0_alt_telomeric_repeat_windows.tsv` (`tidk search`) | `da579538a6545842b0a29c361d664868cade0251b3b7d20b721d3987eef665a5` |
| `ROS_Cfam_2.0_alt_tidk_plot.svg` (`tidk plot`) | `ee3b344123a0d83f9ab4acaf53a1cd21833d1b31ba339c6cc503f060ff58fef4` |

## tidk status per end

From the two `ends.tsv` (and the same in `compare_m02.tsv`):

| Haplotype | Ends | `present` | `not_terminal` | `wrong_strand` | `absent` | `window_limited` true |
|---|---|---|---|---|---|---|
| pri | 80 | 76 | 1 | 0 | 3 | 64 |
| alt | 76 | 66 | 4 | 0 | 6 | 51 |

`ends.json` `sequences` is 40 pri and 38 alt (chrM, 16,730 bp, is under `--min-sequence-length`).
Its own per-sequence counts are pri `t2t` 36, `one_end` 4, `no_ends` 0 and alt 29, 8, 1. `t2t` is
tidk's field name for a sequence with `present` at both ends; it is reported here as tidk's
count, not as a claim about any chromosome.

When `window_limited` is true, `telomere_length` reaches the 10 kb window edge and is a lower bound.

tidk's "at the end" is 1 kb (`--max-offset`), M03's is 10 kb, and M02 searched 100 kb, so an array
1.2-3.4 kb in can be `not_terminal` in M02b while M03 counts it (Steven's review of #14, note 3).
All five ends predicted in `docs/tools/tidk.md` came out `not_terminal`: pri chr8 start (offset
1,434 bp), alt chr16 end (1,236 bp), alt chr24 start (1,674 bp), alt chr29 end (1,626 bp) and alt
chr32 start (3,354 bp). No other end is `not_terminal`.

The 9 `absent` ends are the 9 ends where M02 found no expected-motif array (pri chr10 end, chr16
start, chr31 start; alt chr9 start, chr10 end, chr16 start, chr31 end, chr34 start, chr38 start).
Every end with an M02 array is `present` or `not_terminal`, including the 11 whose M02 array spans
under 200 bp (`--min-length`).

## compare_m02.tsv

One row per chromosome end, in M02's row order: the two `ends.tsv` joined with
`reports/sf/M02/telomeres.tsv` on (assembly, seq_id, side), where M02's `end` column is the side
and tidk's `id` is the seq_id. It holds no new measurement and no agree/disagree column.

| Column | From |
|---|---|
| `assembly`, `haplotype`, `chromosome`, `seq_id`, `side` | M02 (`side` = M02's `end`) |
| `m02_expected_motif` | M02 `expected_motif` (CCCTAA at the start, TTAGGG at the end) |
| `m02_array_copies`, `m02_array_bp`, `m02_array_dist_bp` | M02's `<motif>_array_copies`, `_array_bp` (span), `_array_dist_bp` for the expected motif |
| `tidk_status`, `tidk_telomere_length`, `tidk_offset`, `tidk_strand`, `tidk_window_limited` | tidk `ends.tsv` `status`, `telomere_length`, `offset`, `strand`, `window_limited` |

Made with `workflow/scripts/jc/compare_m02.py` (stdlib; it exits non-zero unless both sides have
exactly the same 156 ends), from the repo root:

```bash
python3 workflow/scripts/jc/compare_m02.py reports/sf/M02/telomeres.tsv \
    reports/jc/M02b/ROS_Cfam_2.0_pri.ends.tsv reports/jc/M02b/ROS_Cfam_2.0_alt.ends.tsv \
    > reports/jc/M02b/compare_m02.tsv
```

Status: diagnostic-only (PROVENANCE.md). Nothing here is a T2T, complete, gapless, telomere or
comparison call. `SUMMARY.md` will be written by `jc/M02b-summary`, and it is not a claim until a
human approves it.
