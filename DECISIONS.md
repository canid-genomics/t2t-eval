# DECISIONS (append-only)

`<date> · <who> · <decision> · <why> · <link>`

- 2026-11-22 · Jonah + Steven · Repo `canid-genomics/t2t-eval` is public (Alfie is public data); our own unpublished dogs get a separate private repo. · protocol rev 5 §8
- 2026-11-22 · Jonah + Steven · Tier 2 is the existing `s3Fried/t2t` bucket, dog-first: `t2t/<assembly>/{jc,sf,shared}/<run-id>/`, with lane and commit in each `_MANIFEST.txt`. · protocol rev 5 §4
- 2026-11-22 · Jonah + Steven · wg workers: Opus; wg bookkeeping roles: Sonnet. Revisit at the test 2 retrospective with /cost numbers. · protocol rev 5 §9
- 2026-11-22 · Jonah + Steven · Lane files live in per-lane folders (`tickets/<lane>/`, `reports/<lane>/`, `workflow/rules/<lane>/`, `workflow/scripts/<lane>/`), owned per `.github/CODEOWNERS`; everything else is owned by both. · Clear ownership before git automation is switched on · WG msg 18; PR `sf/lane-rules`
- 2026-11-22 · Steven (noted by Jonah) · sf-lane agate exception for test 2: Steven's Claude may `sbatch`/`scancel` sf-lane tickets only (`tickets/sf/*.md`, through `slurm/submit.slurm --ticket`), within ≤2 days walltime per job, ≤500 GB scratch and ≤2,000 core-hours in total, with a note to Steven after each job. Deletes stay human-only; the jc lane stays human-only. · His lane, his fried255 account · WG msg 18; protocol rev 6, assessed at the end of test 2
