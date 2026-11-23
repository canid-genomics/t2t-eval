# reports/sf/M02

These are byte-for-byte copies of the 7 objects in
`s3://t2t/ROS_Cfam_2.0/sf/telomeres.2026-11-22.a88f9b4/`. They come from SPEC row M02 and the
ticket `tickets/sf/M02.md` at commit `a88f9b4`. The run was agate job 7853288, and step 7853394
published the folder. Do not edit them. Steven's Claude copied them from Tier 2 on 2026-11-22;
the `sf/M02-report` task that committed them had no Tier 2 access.

| File | What it is |
|---|---|
| `telomeres.tsv` | one row per chromosome end per haplotype (156 rows) |
| `chromosomes.tsv` | every assembly-report row, with `selected` and `reason` |
| `inputs.tsv` | the NCBI files downloaded, with their URLs and md5 checks |
| `method.txt` | how the scan was done and its parameters |
| `run_info.json` | commit, config hash, image digest, tool versions |
| `sha256sums.txt` | the run's own sha256 listing of the 5 files above |
| `_MANIFEST.txt` | the t2t bucket manifest for the run folder |
| `tier2_sha256.txt` | sha256 of all 7 copied files (`shasum -a 256 -c tier2_sha256.txt`) |

`tier2_sha256.txt` lists the 5 files in `sha256sums.txt` with the same hashes. It also lists
`sha256sums.txt` and `_MANIFEST.txt`, which the run's own listing leaves out; those two are
hashed as copied.

Status: diagnostic-only (PROVENANCE.md). Nothing here is a present/absent, T2T or comparison
call. `SUMMARY.md` will be written by `sf/M02-summary`, and it is not a claim until a human
approves it.
