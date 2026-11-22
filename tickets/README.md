# tickets/

One file per agate run, written by a wg worker (`<lane>/<id>-ticket`) and submitted only by a
human. `slurm/submit.slurm --ticket` reads these lines and refuses to run if `commit:` isn't HEAD:

```
commit:  <full or short sha the run must use>
run_id:  <metric>.<YYYY-MM-DD>.<sha7>
targets: <space-separated snakemake targets or rule names>
lane:    <jc | sf | shared>   (optional: run in /scratch.global/friedlab_T2TEVAL/<lane>)
```

Without `lane:` the run uses the `workdir:` in `config/config.yaml`.

Below those lines: what the run does, expected outputs (Tier 2 paths), the dry-run output, and
resources. Anything over 500 GB of scratch or 2 days of jobs needs a `[compute-request]` first.
