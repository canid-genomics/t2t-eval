"""Finish a Tier 2 run folder whose data files are already in it: write run_info.json,
sha256sums.txt and _MANIFEST.txt beside them. Any lane; stdlib only, Python >= 3.11.

Run by a lane's publish rule (`script:`) with `input.files` (the folder's data files), outputs
`run_info`, `sha256` and `manifest`, and params `info` (a dict with at least run_id, lane, spec_id
and commit; written to run_info.json as given), `describes` and `dest`.

sha256sums.txt (`sha256sum -c` format) covers every file but itself and _MANIFEST.txt.
_MANIFEST.txt is the t2t bucket's header-only block of aligned `key: value` lines (describes,
source, dest, job, scope, finished, objects, size), then lane, commit, run_id and spec_id;
`objects:` and `size:` count the folder's other files.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ('run_id', 'lane', 'spec_id', 'commit')


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def human_size(n):
    """Bytes in binary units with no space, as the bucket's manifests write them (e.g. 68GiB)."""
    size, units = float(n), ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
    unit = units.pop(0)
    while size >= 1024 and units:
        size, unit = size / 1024, units.pop(0)
    if unit == 'B' or size >= 10:
        return f'{size:.0f}{unit}'
    return f"{f'{size:.1f}'.removesuffix('.0')}{unit}"


def manifest_text(fields):
    """`key: value` lines with the values aligned one space past the longest key's colon."""
    width = max(len(k) for k in fields) + 1
    return ''.join(f'{k + ":":<{width}} {v}\n' for k, v in fields.items())


def publish(files, run_info, sha256, manifest, info, describes, dest, job=None):
    """Write run_info.json, sha256sums.txt and _MANIFEST.txt for the folder holding `files`."""
    missing = [k for k in REQUIRED if not info.get(k)]
    if missing:
        raise ValueError(f'info lacks {missing}')
    if info['run_id'].startswith('unset.'):
        raise ValueError(f"run_id {info['run_id']!r} is the no-ticket placeholder; submit from a ticket")
    files = [Path(p) for p in files]
    outputs = [Path(run_info), Path(sha256), Path(manifest)]
    folders = {p.parent.resolve() for p in files + outputs}
    if len(folders) != 1:
        raise ValueError(f'files span {len(folders)} folders; a run folder is one: {sorted(map(str, folders))}')
    names = [p.name for p in files + outputs]
    if len(set(names)) != len(names):
        raise ValueError(f'duplicate file names: {names}')
    source = folders.pop()

    record = {**info, 'created_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
              'files': [p.name for p in files]}
    Path(run_info).write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')

    hashed = files + [Path(run_info)]
    Path(sha256).write_text(''.join(f'{sha256_file(p)}  {p.name}\n' for p in hashed))

    objects = hashed + [Path(sha256)]
    fields = {
        'describes': describes,
        'source':    source,
        'dest':      dest,
        'job':       job or 'NA',
        'scope':     'metric',
        'finished':  datetime.now().astimezone().isoformat(timespec='seconds'),
        'objects':   len(objects),
        'size':      human_size(sum(p.stat().st_size for p in objects)),
        **{k: info[k] for k in ('lane', 'commit', 'run_id', 'spec_id')},
    }
    Path(manifest).write_text(manifest_text(fields))


if __name__ == '__main__' and 'snakemake' in globals():
    smk = snakemake  # noqa: F821 (injected by Snakemake's script: preamble)
    publish(files=list(smk.input.files), run_info=smk.output.run_info, sha256=smk.output.sha256,
            manifest=smk.output.manifest, info=dict(smk.params.info), describes=smk.params.describes,
            dest=smk.params.dest, job=os.environ.get('SLURM_JOB_ID'))
