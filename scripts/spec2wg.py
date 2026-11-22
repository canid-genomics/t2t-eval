#!/usr/bin/env python3
"""SPEC.tsv -> draft wg tasks for one lane.

    python scripts/spec2wg.py --lane jc            # dry run: print the wg commands
    python scripts/spec2wg.py --lane jc --apply    # create the drafts (never publishes)
    wg publish <first-task> --wcc                  # the human releases the batch
    python scripts/spec2wg.py --lane jc --hold     # right after publishing: re-pause the holds

Rows of kind `agate` become a four-task chain:
    <lane>/<id>-ticket   worker writes the rule + tickets/<id>.md, with the dry-run output
    <lane>/<id>-run      shell task, held paused: the human submits on agate, then `wg resume`s it
    <lane>/<id>-report   worker copies the small Tier 2 outputs to reports/<id>/, with run_info.json
    <lane>/<id>-summary  worker writes a 3-line summary; a human approves it before it is a claim
Rows of kind `local` become one task, <lane>/<id>.

A dependency on another lane's row can't be a wg edge (separate graphs), so the task waits on a
`[handoff] <id>` message instead and is held paused too. Existing task ids are skipped, so the
script is safe to re-run after adding rows. Stdlib only.
"""
import argparse
import csv
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COLUMNS = ['id', 'lane', 'kind', 'title', 'after', 'outputs', 'validation']


def read_spec(path):
    lines = [l for l in path.read_text().splitlines() if l.strip() and not l.startswith('#')]
    rows = list(csv.DictReader(lines, delimiter='\t'))
    if not rows:
        return []
    missing = set(COLUMNS) - set(rows[0])
    if missing:
        sys.exit(f'{path}: missing columns {sorted(missing)}')
    for row in rows:
        if row['kind'] not in ('agate', 'local'):
            sys.exit(f"{path}: row {row['id']}: kind must be agate or local, not {row['kind']!r}")
        row['after'] = [a.strip() for a in (row['after'] or '').split(',') if a.strip()]
    return rows


def exit_task(row):
    """The task a downstream row waits on: the report (data on disk) for agate rows."""
    return f"{row['lane']}/{row['id']}-report" if row['kind'] == 'agate' else f"{row['lane']}/{row['id']}"


def validation(*items):
    return '## Validation\n' + '\n'.join(f'- [ ] {i}' for i in items if i)


def tasks_for(row, by_id):
    """Yield (task_id, title, after, description, extra_args, hold) for one SPEC row."""
    lane, rid = row['lane'], row['id']
    after, waits = [], []
    for dep in row['after']:
        if dep not in by_id:
            sys.exit(f'SPEC row {rid}: unknown dependency {dep!r}')
        (after if by_id[dep]['lane'] == lane else waits).append(dep)
    after = [exit_task(by_id[d]) for d in after]
    wait_note = ''
    if waits:
        wait_note = ('\n\n## Waits for\n' + '\n'.join(f'- `[handoff] {d}` from lane {by_id[d]["lane"]}'
                                                       for d in waits)
                     + '\nHeld paused until the handoff arrives; the human runs `wg resume`.')
    spec = f"SPEC.tsv row `{rid}` ({lane}, {row['kind']}): {row['title']}\nOutputs: {row['outputs']}"

    if row['kind'] == 'local':
        yield (f'{lane}/{rid}', row['title'], after,
               f'{spec}{wait_note}\n\n' + validation(row['validation'],
                                                     f"Outputs exist and are committed: {row['outputs']}"),
               [], bool(waits))
        return

    t, r, p, s = (f'{lane}/{rid}-{x}' for x in ('ticket', 'run', 'report', 'summary'))
    yield (t, f"{rid} ticket: {row['title']}", after,
           f'{spec}{wait_note}\n\nWrite or port the rule(s) under workflow/rules/{lane}_*.smk, writing only '
           f"tier2(..., '{lane}', subject) outputs, and write tickets/{rid}.md (commit, run_id, targets).\n\n"
           + validation('`pixi run snakemake -n --configfile config/config.local.yaml` succeeds and its '
                        'output is pasted into the ticket',
                        f'tickets/{rid}.md has commit:, run_id: and targets: lines; commit: is the commit '
                        'that holds the rule',
                        'Containers are pinned by digest in config/images.yaml'),
           [], bool(waits))
    yield (r, f'{rid} agate run (human)', [t],
           f'HUMAN STEP. No agent runs this. On agate: `git pull && sbatch slurm/submit.slurm --ticket '
           f'tickets/{rid}.md`. When the job has finished and its outputs are on Tier 2: '
           f'`wg resume {r}`. This shell task then completes and the report task follows.',
           ['--exec-mode', 'shell', '--exec', 'true'], True)
    yield (p, f'{rid} report', [r],
           f'{spec}\n\nCopy the small Tier 2 outputs for this run into reports/{rid}/ with run_info.json and '
           f'a sha256 listing. Record the run in PROVENANCE.md.\n\n'
           + validation(row['validation'], f'reports/{rid}/ holds run_info.json whose git sha matches '
                        f'tickets/{rid}.md', 'sha256 listing matches the Tier 2 objects'),
           [], False)
    yield (s, f'{rid} summary', [p],
           f'Three-line summary of reports/{rid}/ in reports/{rid}/SUMMARY.md: what was measured, the '
           f'headline numbers with their source table, and caveats. Not a claim until a human approves it.\n\n'
           + validation('Every number in SUMMARY.md appears in a reports/ table',
                        'No interpretation beyond what the tables show'),
           [], False)


def wg(*args, check=True):
    return subprocess.run(['wg', *args], cwd=REPO_ROOT, check=check,
                          capture_output=True, text=True)


def exists(task_id):
    return wg('show', task_id, check=False).returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--lane', required=True)
    ap.add_argument('--spec', type=Path, default=REPO_ROOT / 'SPEC.tsv')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='create the draft tasks')
    mode.add_argument('--hold', action='store_true', help='after publishing: pause run tasks and handoff waits')
    a = ap.parse_args()

    rows = read_spec(a.spec)
    by_id = {r['id']: r for r in rows}
    planned = [t for r in rows if r['lane'] == a.lane for t in tasks_for(r, by_id)]
    if not planned:
        sys.exit(f'no SPEC rows for lane {a.lane!r}')

    if a.hold:
        for task_id, *_, hold in planned:
            if hold:
                wg('pause', task_id)
                print(f'paused {task_id}')
        return

    for task_id, title, after, desc, extra, hold in planned:
        cmd = ['add', title, '--id', task_id, '-d', desc, '-t', a.lane, *extra]
        for dep in after:
            cmd += ['--after', dep]
        if not a.apply:
            print(f'wg add {title!r} --id {task_id}', *(f'--after {d}' for d in after), *extra,
                  '-d <description>', '(held after publish)' if hold else '')
            continue
        if exists(task_id):
            print(f'skip {task_id} (exists)')
            continue
        wg(*cmd)
        print(f'added {task_id} (draft)')

    if a.apply:
        print(f'\nReview with `wg status`, then `wg publish <first-task> --wcc` and '
              f'`python scripts/spec2wg.py --lane {a.lane} --hold`.')


if __name__ == '__main__':
    main()
