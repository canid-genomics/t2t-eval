#!/usr/bin/env python3
"""PreToolUse hook for Bash commands that run `sbatch` (settings.json: `if: Bash(sbatch *)`).

The sf-lane exception (CLAUDE.md, "Where work happens") lets Steven's Claude run exactly

    sbatch slurm/submit.slurm --ticket tickets/sf/<id>.md

Permission rules alone can't say "ask for every other sbatch": an ask rule beats a narrower allow
rule, so `ask: Bash(sbatch *)` would also stop the sf form. So .claude/settings.json allows the sf
form and denies the other lanes' ticket forms, and this hook asks a human before every other
sbatch: other scripts, the sf form with anything after the ticket path, or inside a compound
command. The sf form alone gets no answer here and falls through to the allow rule. So does a
command that doesn't contain the word sbatch: the `if` filter also fires on commands it can't
fully parse (loops, `$(...)`). Stdlib only.
"""
import json
import re
import sys

SF_SUBMIT = re.compile(r'sbatch slurm/submit\.slurm --ticket tickets/sf/[A-Za-z0-9._-]+\.md')
SBATCH = re.compile(r'\bsbatch\b')
ASK = {'hookSpecificOutput': {
    'hookEventName': 'PreToolUse',
    'permissionDecision': 'ask',
    'permissionDecisionReason': ('sbatch outside the sf-lane exception (CLAUDE.md, "Where work '
                                 'happens"): only `sbatch slurm/submit.slurm --ticket '
                                 'tickets/sf/<id>.md`, run on its own, goes without asking'),
}}


def main():
    try:
        command = json.load(sys.stdin)['tool_input']['command']
    except (ValueError, KeyError, TypeError):
        command = None
    if isinstance(command, str) and (not SBATCH.search(command) or SF_SUBMIT.fullmatch(command.strip())):
        return
    json.dump(ASK, sys.stdout)


if __name__ == '__main__':
    main()
