# reports/jc/M01

These are byte-for-byte copies of the 6 objects in
`s3://t2t/ROS_Cfam_2.0/jc/assembly_stats.2026-11-22.e0de057/`. They come from SPEC row M01 and
the ticket `tickets/jc/M01.md` at commit `e0de057`. The run was agate job 7865313, submitted from
`36b870d` (same tree as `e0de057` outside tickets/), and step 7867762 published the folder. Do not
edit them. Jonah's interactive Claude copied them from Tier 2 on 2026-11-23; the `jc/M01-report`
task that committed them had no Tier 2 access.

| File | What it is |
|---|---|
| `gfastats.tsv` | gfastats long format: 32 summary metrics per assembly, 10 per record (41 pri, 38 alt records; 854 rows) |
| `gaps.bed` | BED4 (`seq_id start end assembly`, 0-based half-open), every gap in both haplotypes (4 rows) |
| `inputs.tsv` | the NCBI files downloaded, with their URLs and md5 checks |
| `run_info.json` | commit, head, config hash, image digests, gfastats commands, tool versions, counts |
| `sha256sums.txt` | the run's own sha256 listing of the 4 files above |
| `_MANIFEST.txt` | the t2t bucket manifest for the run folder |
| `tier2_sha256.txt` | sha256 of all 6 copied files (`shasum -a 256 -c tier2_sha256.txt`) |

`tier2_sha256.txt` lists the 4 files in `sha256sums.txt` with the same hashes. It also lists
`sha256sums.txt` and `_MANIFEST.txt`, which the run's own listing leaves out; those two are
hashed as copied.

Checks done by `jc/M01-report` against these files (and the NCBI assembly reports as parsed in
`reports/sf/M02/chromosomes.tsv`; the M01 and M02 runs downloaded files with the same NCBI md5s):
- `inputs.tsv`: all 4 FASTA and assembly-report md5s equal NCBI's (`md5_ok yes`); the two
  `md5checksums.txt` rows are the checksum files themselves (`NA`).
- `gfastats.tsv`: the 41 pri and 38 alt record ids equal the assembly reports' GenBank
  accessions, with the reports' lengths. 40 pri records (chr1-38, X, Y) and 38 alt records
  (chr1-38) are chromosomes; the 41st pri record is the mitochondrion.
- `gaps.bed`: every gap has integer coordinates with start < end ≤ its record's length.

Status: diagnostic-only (PROVENANCE.md). Nothing here is a T2T, complete, gapless or comparison
call. `SUMMARY.md` will be written by `jc/M01-summary`, and it is not a claim until a human
approves it.
