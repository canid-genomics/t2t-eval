# PROVENANCE (append-only)

Every number that reaches a figure, summary or text, traced back to its run.
Status: `verdict-safe` (can support a claim) · `diagnostic-only` (internal use) · `RETRACTED` (wrong; never reuse).

| Date | Number / claim | Source table (reports/…) | Run-id | Commit | Status |
|---|---|---|---|---|---|
| 2026-11-22 | M02 run recorded: TTAGGG/CCCTAA counts and terminal arrays at both ends of the 40 pri and 38 alt chromosomes (156 rows). No number cited and no claim made | `reports/sf/M02/telomeres.tsv` (selection: `reports/sf/M02/chromosomes.tsv`) | `telomeres.2026-11-22.a88f9b4` | `a88f9b4` | diagnostic-only |
| 2026-11-22 | M02 draft summary (not human-approved; no claim made): the ends whose expected-motif array `dist_bp` is NA are listed, and the nearest expected-motif array's range at the other ends is cited (copies 10 to 4974, distance from the end 0 to 3356 bp), in `reports/sf/M02/SUMMARY.md` | `reports/sf/M02/telomeres.tsv` | `telomeres.2026-11-22.a88f9b4` | `a88f9b4` | diagnostic-only |
| 2026-11-22 | M02 SUMMARY.md approved by Steven: 147 of 156 chromosome ends have an expected-motif terminal array (≥10 exact copies within the terminal 100 kb; 10–4974 copies, 0–3356 bp from the end); no array at pri chr10 end, chr16 start, chr31 start and alt chr9 start, chr10 end, chr16 start, chr31 end, chr34 start, chr38 start; chr16 start has 0 copies of either motif in the terminal 100 kb in both haplotypes. Descriptive counts only; no present/absent, telomere, T2T or pri-vs-alt call | `reports/sf/M02/telomeres.tsv` | `telomeres.2026-11-22.a88f9b4` | `a88f9b4` | verdict-safe (counts as stated) |
| 2026-11-23 | M01 run recorded: NCBI md5 checks of the pri and alt FASTAs and assembly reports, gfastats summary and per-record metrics for every record, and gap coordinates in both haplotypes. No number cited and no claim made | `reports/jc/M01/gfastats.tsv` (gaps: `reports/jc/M01/gaps.bed`; md5s: `reports/jc/M01/inputs.tsv`) | `assembly_stats.2026-11-22.e0de057` | `e0de057` | diagnostic-only |
