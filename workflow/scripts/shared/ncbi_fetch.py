"""Download one NCBI GenBank assembly (FASTA, assembly report, md5checksums.txt) and verify md5s.

Run by each lane's `<lane>_ncbi_fetch` rule (`script:`), on agate scratch only; stdlib only,
Python >= 3.11.

The assembly folder is found from the accession alone: NCBI keeps every assembly at
  https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/062/019/780/GCA_062019780.1_<asm name>/
so the parent listing is read and the one sub-folder starting with `<accession>_` is used.
Each file is streamed to `<out>.part`, its md5 compared with md5checksums.txt, and only then
renamed into place; a mismatch is retried and then fails the job. The record table holds the
URL, NCBI's md5, the observed md5 and the size of every file.
"""
import csv
import hashlib
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

NCBI_ALL = 'https://ftp.ncbi.nlm.nih.gov/genomes/all'
ACCESSION_RE = re.compile(r'^(GC[AF])_(\d{3})(\d{3})(\d{3})\.(\d+)$')
RECORD_COLUMNS = ['assembly', 'accession', 'file', 'url', 'md5_ncbi', 'md5_observed', 'md5_ok',
                  'bytes', 'retrieved_utc']
TIMEOUT_S = 120
ATTEMPTS = 3


class Md5Mismatch(Exception):
    pass


def accession_parent_url(accession):
    """GCA_062019780.1 -> https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/062/019/780/"""
    m = ACCESSION_RE.match(accession)
    if not m:
        raise ValueError(f'not a GenBank/RefSeq assembly accession: {accession!r}')
    prefix, a, b, c, _ = m.groups()
    return f'{NCBI_ALL}/{prefix}/{a}/{b}/{c}/'


def resolve_assembly_dir(accession, listing_html):
    """The `<accession>_<asm name>` folder name from the parent folder's HTML listing."""
    names = set(re.findall(rf'href="({re.escape(accession)}_[^"/]+)/"', listing_html))
    if len(names) != 1:
        raise ValueError(f'expected one {accession}_* folder in the NCBI listing, found {sorted(names)}')
    return names.pop()


def parse_md5checksums(text):
    """md5checksums.txt (`<md5>  ./<path>`) -> {path: md5}."""
    sums = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        md5, _, name = line.partition(' ')
        name = name.strip()
        sums[name[2:] if name.startswith('./') else name] = md5.lower()
    return sums


def fetch_bytes(url):
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp:
        return resp.read()


def download(url, dest, expected_md5=None, attempts=ATTEMPTS, wait_s=30):
    """Stream url to dest via dest.part; check md5 if given. Returns (md5, bytes)."""
    dest = Path(dest)
    part = dest.with_name(dest.name + '.part')
    for attempt in range(1, attempts + 1):
        try:
            md5, size = hashlib.md5(), 0
            with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp, part.open('wb') as out:
                while chunk := resp.read(1 << 20):
                    md5.update(chunk)
                    out.write(chunk)
                    size += len(chunk)
            digest = md5.hexdigest()
            if expected_md5 and digest != expected_md5:
                raise Md5Mismatch(f'{url}: md5 {digest} != NCBI {expected_md5}')
            part.replace(dest)
            return digest, size
        except (OSError, Md5Mismatch) as err:  # URLError and timeouts are OSErrors
            part.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            print(f'attempt {attempt}/{attempts} failed: {err}; retrying in {wait_s}s', flush=True)
            time.sleep(wait_s)
    raise AssertionError('unreachable')


def fetch_assembly(assembly, accession, fasta_out, report_out, md5s_out, record_out,
                   parent_url=None, wait_s=30):
    parent_url = parent_url or accession_parent_url(accession)
    folder = resolve_assembly_dir(accession, fetch_bytes(parent_url).decode())
    base = f'{parent_url}{folder}/'
    now = lambda: datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')  # noqa: E731

    md5_url = f'{base}md5checksums.txt'
    md5_digest, md5_size = download(md5_url, md5s_out, wait_s=wait_s)
    sums = parse_md5checksums(Path(md5s_out).read_text())
    records = [dict(assembly=assembly, accession=accession, file='md5checksums.txt', url=md5_url,
                    md5_ncbi='NA', md5_observed=md5_digest, md5_ok='NA', bytes=md5_size,
                    retrieved_utc=now())]

    for name, dest in ((f'{folder}_assembly_report.txt', report_out), (f'{folder}_genomic.fna.gz', fasta_out)):
        if name not in sums:
            raise ValueError(f'{name} is not listed in {md5_url}')
        url = f'{base}{name}'
        digest, size = download(url, dest, expected_md5=sums[name], wait_s=wait_s)
        records.append(dict(assembly=assembly, accession=accession, file=name, url=url,
                            md5_ncbi=sums[name], md5_observed=digest, md5_ok='yes', bytes=size,
                            retrieved_utc=now()))

    with Path(record_out).open('w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=RECORD_COLUMNS, delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)
    return records


if __name__ == '__main__' and 'snakemake' in globals():
    smk = snakemake  # noqa: F821 (injected by Snakemake's script: preamble)
    for out in smk.output:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
    fetch_assembly(assembly=smk.wildcards.assembly, accession=smk.params.accession,
                   fasta_out=smk.output.fasta, report_out=smk.output.report,
                   md5s_out=smk.output.md5s, record_out=smk.output.record)
