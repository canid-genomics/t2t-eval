# t2t-eval

Evaluation of public near-T2T dog assemblies, starting with ROS_Cfam_2.0 (GCA_062019780.1 /
GCA_062019781.1). Snakemake, container-native, run on MSI's agate; finished outputs on Tier 2;
work planned in `SPEC.tsv` and done through [wg](https://github.com/graphwork/wg) task graphs, one
per person.

## Setup
```bash
git clone git@github.com:canid-genomics/t2t-eval.git && cd t2t-eval
pixi install                 # snakemake + slurm and S3 plugins (osx-arm64 and linux-64)
direnv allow                 # optional: .envrc activates the pixi env on cd
wg init                      # your own task graph (.wg/ is gitignored)
```
Interactive Claude sessions in the clone take your own rules from a settings file **outside** the
clone, passed at launch:
```bash
claude --settings ~/.config/t2t-eval/claude-interactive.json
```
It holds the `ask` for `git add` and `git commit` (CLAUDE.md, commit model) and anything else
that is yours alone. Steven's also holds the sf-lane exception's one `allow` (CLAUDE.md, "Where
work happens"); nobody else's does:
```json
{
  "permissions": {
    "ask":   ["Bash(git add:*)", "Bash(git commit:*)"],
    "allow": ["Bash(sbatch slurm/submit.slurm --ticket tickets/sf/*)"]
  }
}
```
Don't use `.claude/settings.local.json` in the clone, and don't put these rules in your global
`~/.claude/settings.json`. wg worktrees live inside the clone (`.wg-worktrees/`), so both files
reach the wg workers too, and an `ask` there stops a worker's `git commit` (LESSONS.md). A file
you pass with `--settings` reaches only the sessions you start with it.

On agate, also write `~/.config/t2t-eval/tier2.env` (`AWS_ACCESS_KEY=…`, `AWS_SECRET_KEY=…`,
`chmod 600`).

## Daily commands
```bash
pixi run snakemake -n --configfile config/config.local.yaml      # local dry run
python3 scripts/spec2wg.py --lane jc                              # SPEC rows → wg drafts (dry run)
bash slurm/submit.slurm --ticket tickets/jc/M01.md -n             # agate: dry run a ticket
sbatch slurm/submit.slurm --ticket tickets/jc/M01.md              # agate: submit (humans only)
scripts/review-before-push.sh                                     # before every push
```

See `CLAUDE.md` (identical to `AGENTS.md`) for conventions: lanes, the commit model, storage,
containers, and the collaboration protocol.
