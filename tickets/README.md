# tickets/

One file per agate run, written by a wg worker (`<lane>/<id>-ticket`) and submitted only by a
human. `slurm/submit.slurm --ticket` reads these lines:

```
commit:  <full or short sha of the commit that holds the rule>
run_id:  <metric>.<YYYY-MM-DD>.<sha7>
targets: <space-separated snakemake targets or rule names>
lane:    <jc | sf | shared>   (optional: run in /scratch.global/friedlab_T2TEVAL/<lane>)
```

The ticket is committed after the rule it pins, so `commit:` need not be HEAD: it must be HEAD or
an ancestor of it, and nothing outside `tickets/` may differ between `commit:` and HEAD. The run
records `commit:` (full sha) as `ticket_commit`. Without `lane:` the run uses the `workdir:` in
`config/config.yaml`.

Below those lines: what the run does, expected outputs (Tier 2 paths), the dry-run output, and
resources. Anything over 500 GB of scratch or 2 days of jobs needs a `[compute-request]` first.
