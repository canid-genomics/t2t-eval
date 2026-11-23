# LESSONS (append-only)

After each scope, each side writes five bullets: what worked, friction, rounds, rough cost
(`/cost`, agate core-hours), one rule to change. The humans pick what to adopt.

## To confirm in test 2
- Interactive sessions are asked before each commit (`.claude/settings.local.json` "ask") while
  wg workers in fresh worktrees commit without a prompt (`.claude/settings.json` "allow").

## For the test 2 assessment: "ask overrides allow" also hit the workers (sf, 2026-11-22)
- Planned (protocol §8): a local `ask` for `git add`/`git commit` overrides the committed
  `allow` in interactive sessions, while wg workers, in fresh worktrees without the local file,
  commit unprompted. It came out the other way: the `ask` also hit the workers.
- Why: wg worktrees live inside the clone (`.wg-worktrees/`), so the main checkout's
  `.claude/settings.local.json` reaches them (sf side), and the global `~/.claude/settings.json`
  reaches every session on the machine (jc side: a global `ask: git commit`). An `ask` beats an
  `allow`, holds in bypassPermissions mode, and a headless worker can't answer it.
- wg 0.2.0 can't put worktrees outside the clone (`dispatcher.worktree_root`/`worktree_dir`
  don't exist).
- Fix (sf/followups): interactive rules go in a settings file outside the clone, passed with
  `claude --settings ~/.config/t2t-eval/claude-interactive.json` (README, Setup). The sf-lane
  `sbatch` allow moved out of `.claude/settings.json` into Steven's file (PR #2 review: "the
  exception should be a person's, not the repo's").
- Rule to change: no person-specific permission rule in a file a wg worker loads, which means
  neither the clone's `.claude/settings.local.json` nor `~/.claude/settings.json`.
