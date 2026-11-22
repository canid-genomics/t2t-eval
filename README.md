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
Interactive sessions: create `.claude/settings.local.json` with `"ask"` for `git add` and
`git commit` (see CLAUDE.md, commit model). On agate, also write `~/.config/t2t-eval/tier2.env`
(`AWS_ACCESS_KEY=…`, `AWS_SECRET_KEY=…`, `chmod 600`).

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
