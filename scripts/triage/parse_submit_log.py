#!/usr/bin/env python3
"""
parse_submit_log.py — deterministic Snakemake failure rollup

Parses a top-level Snakemake submit log (the .err file from the Snakemake
master process) and emits a structured failure rollup. Used by the
snakemake-log-triage Claude Code subagent to decide which per-step stderr
files are worth reading.

Usage:
    parse_submit_log.py LOG_PATH [--json] [--out PATH]

Without --json, emits a compact text summary suitable for piping to an LLM.
With --json, emits the full schema for programmatic consumption.

What it handles:
  * Two-emission deduplication. Snakemake reports each failed job twice
    (once with the SLURM status, once with the shell command). We dedupe
    by Snakemake jobid and merge.
  * Two jobid namespaces. Snakemake's internal jobid != SLURM's external
    jobid. We track both.
  * Wildcard recovery. Wildcards live in the *submission* block, not the
    error block. We index submissions by jobid and cross-reference.
  * stderr path reconstruction. Each rule's `slurm_extra` carries an
    `--error=...` template with `%j`. We fill in the SLURM jobid to get
    the canonical per-step stderr path.
  * Status × completeness classification (see CLASSIFY below).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Regexes match Snakemake 7.x / 8.x submit-log conventions.
TS_RE         = re.compile(r'^\[(?P<ts>[A-Z][a-z]{2} [A-Z][a-z]{2} +\d+ \d+:\d+:\d+ \d{4})\]\s*$')
SUBMIT_RE     = re.compile(r'^rule (?P<rule>[A-Za-z_][A-Za-z0-9_]*):\s*$')
ERROR_RE      = re.compile(r'^Error in rule (?P<rule>[A-Za-z_][A-Za-z0-9_]*):\s*$')
JOBID_RE      = re.compile(r'^\s{4}jobid:\s+(?P<jid>\d+)\s*$')
WILDCARDS_RE  = re.compile(r'^\s{4}wildcards:\s+(?P<wc>.+)\s*$')
STDERR_TPL_RE = re.compile(r'--error=(?P<err>\S+)')
SLURM_STAT_RE = re.compile(r"SLURM-job '(?P<sjid>\d+)'.*status is: '(?P<status>[A-Z_]+)'")
EXTERNAL_RE   = re.compile(r'^\s{4}external_jobid:\s+(?P<sjid>\d+)\s*$')


@dataclass
class Submission:
    rule: str
    jobid: int = -1
    wildcards: dict[str, str] = field(default_factory=dict)
    submitted_at: str | None = None
    stderr_template: str | None = None


@dataclass
class Failure:
    rule: str
    jobid: int = -1
    slurm_jobid: str | None = None
    slurm_status: str | None = None
    failed_at: str | None = None
    stderr_path: str | None = None


def parse_wildcards(s: str) -> dict[str, str]:
    out = {}
    for part in s.split(','):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def parse_job_stats(lines: list[str]) -> dict[str, int]:
    """Find the 'Job stats:' table and extract {rule: total_count}."""
    stats = {}
    for i, line in enumerate(lines):
        if line.strip() == 'Job stats:':
            # header + dashes are i+1, i+2; rows start at i+3
            for row in lines[i + 3:]:
                row = row.rstrip()
                if not row:
                    break
                parts = row.split()
                if len(parts) < 2 or parts[0] == 'total':
                    if parts and parts[0] == 'total':
                        break
                    continue
                try:
                    stats[parts[0]] = int(parts[-1])
                except ValueError:
                    pass
            break
    return stats


def parse_log(path: Path) -> dict[str, Any]:
    lines = path.read_text(errors='replace').splitlines()
    job_stats = parse_job_stats(lines)

    submissions: dict[int, Submission] = {}
    failures_raw: list[Failure] = []

    last_ts: str | None = None
    sub: Submission | None = None
    fail: Failure | None = None

    def flush():
        nonlocal sub, fail
        if sub is not None and sub.jobid >= 0:
            submissions[sub.jobid] = sub
        sub = None
        if fail is not None and fail.jobid >= 0:
            failures_raw.append(fail)
        fail = None

    for line in lines:
        m_ts = TS_RE.match(line)
        if m_ts:
            flush()
            last_ts = m_ts.group('ts')
            continue

        m_sub = SUBMIT_RE.match(line)
        if m_sub:
            flush()
            sub = Submission(rule=m_sub.group('rule'), submitted_at=last_ts)
            continue

        m_err = ERROR_RE.match(line)
        if m_err:
            flush()
            fail = Failure(rule=m_err.group('rule'), failed_at=last_ts)
            continue

        if sub is not None:
            if m := JOBID_RE.match(line):
                sub.jobid = int(m.group('jid'))
            elif m := WILDCARDS_RE.match(line):
                sub.wildcards = parse_wildcards(m.group('wc'))
            elif m := STDERR_TPL_RE.search(line):
                sub.stderr_template = m.group('err')

        if fail is not None:
            if m := JOBID_RE.match(line):
                fail.jobid = int(m.group('jid'))
            if m := SLURM_STAT_RE.search(line):
                fail.slurm_jobid = m.group('sjid')
                fail.slurm_status = m.group('status')
            elif m := EXTERNAL_RE.match(line):
                fail.slurm_jobid = m.group('sjid')

    flush()

    # Dedupe failures by snakemake jobid; merge non-null fields.
    merged: dict[int, Failure] = {}
    for f in failures_raw:
        e = merged.get(f.jobid)
        if e is None:
            merged[f.jobid] = f
            continue
        for k, v in asdict(f).items():
            if v and not getattr(e, k):
                setattr(e, k, v)
    failures = list(merged.values())

    # Reconstruct per-step stderr path from the rule's slurm_extra template.
    for f in failures:
        s = submissions.get(f.jobid)
        if s and s.stderr_template and f.slurm_jobid:
            f.stderr_path = s.stderr_template.replace('%j', f.slurm_jobid)

    # Rollup per rule.
    rollup: dict[str, dict] = {}
    for r, total in job_stats.items():
        rollup[r] = {
            'total': total, 'failed': 0,
            'by_status': defaultdict(int), 'failed_jobs': [],
        }
    for f in failures:
        b = rollup.setdefault(f.rule, {
            'total': 0, 'failed': 0,
            'by_status': defaultdict(int), 'failed_jobs': [],
        })
        b['failed'] += 1
        b['by_status'][f.slurm_status or 'UNKNOWN'] += 1
        s = submissions.get(f.jobid)
        b['failed_jobs'].append({
            'jobid': f.jobid,
            'slurm_jobid': f.slurm_jobid,
            'status': f.slurm_status or 'UNKNOWN',
            'wildcards': s.wildcards if s else {},
            'stderr': f.stderr_path,
            'failed_at': f.failed_at,
            'submitted_at': s.submitted_at if s else None,
        })

    # Classify per the status × completeness matrix.
    def classify(b):
        total, failed = b['total'], b['failed']
        if failed == 0:
            return 'ok'
        rate = failed / total if total else 1.0
        statuses = {k for k, v in b['by_status'].items() if v > 0}
        only_to = statuses == {'TIMEOUT'}
        only_fa = statuses == {'FAILED'}
        if rate >= 0.999:
            if only_to: return 'rule_timeout_cap'
            if only_fa: return 'rule_bug'
            return 'rule_bug_plus_timeout'
        if only_to: return 'sample_size_correlated'
        if only_fa: return 'sample_data'
        return 'partial_mixed'

    def choose_logs(b, cls):
        wcs = b['failed_jobs']
        if cls in ('rule_timeout_cap', 'sample_size_correlated'):
            return []
        if cls in ('rule_bug', 'sample_data'):
            for w in wcs:
                if w['stderr']:
                    return [w['stderr']]
            return []
        if cls in ('rule_bug_plus_timeout', 'partial_mixed'):
            picks: dict[str, str] = {}
            for w in wcs:
                if w['stderr'] and w['status'] not in picks:
                    picks[w['status']] = w['stderr']
            return list(picks.values())
        return []

    out_rollup = {}
    for r, b in rollup.items():
        cls = classify(b)
        out_rollup[r] = {
            'total': b['total'],
            'failed': b['failed'],
            'rate': round(b['failed'] / b['total'], 3) if b['total'] else 0.0,
            'by_status': dict(b['by_status']),
            'classification': cls,
            'logs_to_read': choose_logs(b, cls),
            'failed_jobs': b['failed_jobs'],
        }

    return {
        'log_path': str(path),
        'job_stats': job_stats,
        'total_jobs': sum(job_stats.values()),
        'total_failures': len(failures),
        'rollup': out_rollup,
    }


def format_text(report: dict) -> str:
    out: list[str] = []
    out.append(f"# Triage rollup: {report['log_path']}")
    out.append(f"Total jobs: {report['total_jobs']}  |  Failed: {report['total_failures']}"
               f"  ({report['total_failures'] / max(report['total_jobs'], 1):.1%})")
    out.append("")
    out.append(f"{'rule':<28} {'tot':>4} {'fail':>5} {'rate':>6}  {'status':<28} classification")
    out.append('-' * 105)
    for rule, r in sorted(report['rollup'].items(), key=lambda x: -x[1]['failed']):
        if r['failed'] == 0:
            continue
        sb = ', '.join(f"{k}={v}" for k, v in r['by_status'].items())
        out.append(f"{rule:<28} {r['total']:>4} {r['failed']:>5} {r['rate']:>6.1%}  "
                   f"{sb:<28} {r['classification']}")
    out.append("")
    out.append("# Per-step stderr to read:")
    any_logs = False
    for rule, r in sorted(report['rollup'].items()):
        if r['logs_to_read']:
            any_logs = True
            out.append(f"  {rule}:")
            for p in r['logs_to_read']:
                out.append(f"    {p}")
    if not any_logs:
        out.append("  (none — all classifications are resource-only)")
    out.append("")
    out.append("# Wildcards of failed jobs (per rule):")
    for rule, r in sorted(report['rollup'].items()):
        if r['failed'] == 0:
            continue
        wcs = [j['wildcards'] for j in r['failed_jobs']]
        keys = sorted({k for w in wcs for k in w})
        if not keys:
            continue
        out.append(f"  {rule}:")
        for k in keys:
            vals = sorted({w.get(k, '<missing>') for w in wcs})
            out.append(f"    {k}: {', '.join(vals)}")
    return '\n'.join(out)


def format_logs_only(report: dict) -> str:
    """Just the recommended stderr paths, one per line. No header, no commentary.
    Designed for piping: into xargs, rsync --files-from, or `Read` calls.
    """
    paths: list[str] = []
    for _, r in sorted(report['rollup'].items()):
        for p in r['logs_to_read']:
            if p and p not in paths:  # preserve order, dedupe
                paths.append(p)
    return '\n'.join(paths)


def main():
    ap = argparse.ArgumentParser(
        description='Parse a Snakemake submit log into a failure rollup.',
    )
    ap.add_argument('log', type=Path, help='path to submit .err log')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--json', action='store_true',
                      help='emit full structured JSON')
    mode.add_argument('--logs-only', action='store_true',
                      help='emit only newline-separated stderr paths')
    ap.add_argument('--out', type=Path,
                    help='write to file instead of stdout')
    args = ap.parse_args()

    report = parse_log(args.log)
    if args.json:
        text = json.dumps(report, indent=2, default=str)
    elif args.logs_only:
        text = format_logs_only(report)
    else:
        text = format_text(report)

    if args.out:
        args.out.write_text(text + ('\n' if not text.endswith('\n') else ''))
    else:
        print(text)



if __name__ == '__main__':
    # Die cleanly when piped to head/less/etc.
    try:
        main()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
