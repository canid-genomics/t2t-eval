"""Join tidk ends.tsv files with M02's telomeres.tsv, one row per chromosome end (M02b report).

Glue only: no new measurement. M02's array columns are taken for its expected motif at that end.

    python3 workflow/scripts/jc/compare_m02.py reports/sf/M02/telomeres.tsv \
        reports/jc/M02b/ROS_Cfam_2.0_pri.ends.tsv reports/jc/M02b/ROS_Cfam_2.0_alt.ends.tsv \
        > reports/jc/M02b/compare_m02.tsv
"""
import csv
import sys
from pathlib import Path

HEADER = [
    "assembly", "haplotype", "chromosome", "seq_id", "side",
    "m02_expected_motif", "m02_array_copies", "m02_array_bp", "m02_array_dist_bp",
    "tidk_status", "tidk_telomere_length", "tidk_offset", "tidk_strand", "tidk_window_limited",
]


def read_tsv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main(m02_path: str, *ends_paths: str) -> None:
    tidk = {}
    for p in map(Path, ends_paths):
        assembly = p.name.removesuffix(".ends.tsv")
        for row in read_tsv(p):
            tidk[(assembly, row["id"], row["side"])] = row

    m02 = read_tsv(Path(m02_path))
    keys = {(r["assembly"], r["seq_id"], r["end"]) for r in m02}
    if keys != tidk.keys() or len(keys) != len(m02):
        sys.exit(f"ends differ: only M02 {sorted(keys - tidk.keys())}, "
                 f"only tidk {sorted(tidk.keys() - keys)}, M02 rows {len(m02)}")

    out = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")
    out.writerow(HEADER)
    for r in m02:
        t = tidk[(r["assembly"], r["seq_id"], r["end"])]
        motif = r["expected_motif"].lower()
        out.writerow([
            r["assembly"], r["haplotype"], r["chromosome"], r["seq_id"], r["end"],
            r["expected_motif"], r[f"{motif}_array_copies"], r[f"{motif}_array_bp"],
            r[f"{motif}_array_dist_bp"],
            t["status"], t["telomere_length"], t["offset"], t["strand"], t["window_limited"],
        ])


if __name__ == "__main__":
    main(*sys.argv[1:])
