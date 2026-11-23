# M03 test fixture: synthetic M01/M02-format tables

Small hand-designed tables in the formats `workflow/scripts/sf/completeness.py` reads, for
`tests/sf/test_completeness.py`. No real sequence data and no real numbers: assemblies `TEST_pri`
(GCA_000000001.1) and `TEST_alt` (GCA_000000002.1), sequence ids `TEST….1`.

- `telomeres.tsv`: M02 format (`reports/sf/M02/telomeres.tsv`), one row per chromosome end per
  haplotype. Rows are deliberately out of order (chr10 before chr2, chrY before chrX).
- `gfastats.tsv`: M01 format (jc `assembly_stats_publish.py`), long `assembly haplotype accession
  scope seq_id metric value`, a few `scope=assembly` rows and the 10 `scope=sequence` metrics per
  record. `Total path length` equals M02's `seq_length`.
- `gaps.bed`: M01 format, `seq_id start end assembly`, 0-based half-open.

What each sequence covers, with the default thresholds (>= 10 copies, <= 1,000 bp from the end):

| haplotype | chromosome | seq_id | start array (copies, dist) | end array (copies, dist) | gaps | status |
|---|---|---|---|---|---|---|
| pri | chr1 | TESTP001.1 | 500, 0 | 400, 3 | 0 | array_both_ends_no_gaps |
| pri | chr2 | TESTP002.1 | 300, 12 | 250, 0 | 2 (600 bp) | array_both_ends_with_gaps |
| pri | chr10 | TESTP010.1 | 200, 0 | NA (a 300-copy CCCTAA array, the other motif, at dist 0) | 1 | array_one_end |
| pri | chrX | TESTP0X0.1 | 40, 1,001 (just past the threshold) | NA | 1 | no_array |
| pri | chrY | TESTP0Y0.1 | NA | 10, 1,000 (on both thresholds) | 0 | array_one_end |
| alt | chr1 | TESTA001.1 | 450, 1 | 380, 0 | 0 | array_both_ends_no_gaps |
| alt | chr2 | TESTA002.1 | 280, 2 | 260, 0 | 1 (100 bp) | array_both_ends_with_gaps |
| alt | chr10 | TESTA010.1 | NA | 12, 5,000 | 0 | no_array |

`TESTP999.1` (pri) is an unplaced scaffold: in `gfastats.tsv` and `gaps.bed` but not in
`telomeres.tsv`, so it and its gap must be left out. alt has no chrX or chrY, as in ROS_Cfam_2.0.
