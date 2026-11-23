# tickets/

One file per agate run, at `tickets/<lane>/<id>.md` (`jc/`, `sf/`; `<id>` is the SPEC id), written
by a wg worker (`<lane>/<id>-ticket`) and submitted by a human (sf tickets: or Steven's Claude,
under the sf-lane exception in CLAUDE.md). The lane folders belong to their lane
(`.github/CODEOWNERS`). `slurm/submit.slurm --ticket` reads these lines:

```
commit:  <full or short sha of the commit that holds the rule>
run_id:  <metric>.<YYYY-MM-DD>.<sha7>
targets: <space-separated snakemake targets or rule names>
lane:    <jc | sf | shared>   (optional; must match the ticket's folder)
```

The ticket's folder is its lane: the run uses `/scratch.global/friedlab_T2TEVAL/<lane>` as its
workdir. submit.slurm takes the path as `tickets/<lane>/<id>.md`, from the repo root, and refuses
any other form, and a ticket whose `lane:` line names another lane. It runs only committed tickets
and passes no `--delete-*` argument to Snakemake.

The ticket is committed after the rule it pins, so `commit:` need not be HEAD: it must be HEAD or
an ancestor of it. Between `commit:` and HEAD, only files that can't change this run may differ:
`tickets/`, the other personal lane's folders (for an sf ticket: `reports/jc/`,
`workflow/rules/jc/`, `workflow/scripts/jc/`, `tests/jc/`, and vice versa), and the append-only
logs (`PROVENANCE.md`, `HANDOFFS.md`, `DECISIONS.md`, `LESSONS.md`). Anything else (shared files,
`workflow/scripts/shared/`, the ticket's own lane) means re-ticket. So a merge in one lane no
longer invalidates the other lane's pending ticket. A `shared` ticket ignores only `tickets/` and
the logs. The run records `commit:` (full sha) as `ticket_commit`.

Below those lines: what the run does, expected outputs (Tier 2 paths), the dry-run output, and
resources. Anything over 500 GB of scratch or 2 days of jobs needs a `[compute-request]` first.
