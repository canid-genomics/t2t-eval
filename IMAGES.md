# IMAGES

Every container the workflow uses, pinned by digest. Add a row when `config/images.yaml` changes.

| Tool | Version | Image (digest) | `--version` output | Added |
|---|---|---|---|---|
| python | 3.11 | `docker://ghcr.io/canid-genomics/python@sha256:a909d1c838b9b40e4274b06b397042e6dd8d4c9b2e2ae7e11ace354268624d57` (built from branch `sf/M02` by `images` workflow run 45058770486; base `python:3.11.18-slim-trixie@sha256:07d48240…b535`) | `Python 3.11.18` | 2026-11-22 |
| gfastats | 1.3.11 | `docker://quay.io/biocontainers/gfastats@sha256:f4903ca4ed682bca6c192cac13f9b0355f149947a7cf3e53bbd2580f3a50bdd7` (public BioContainers image, tag `1.3.11--h077b44d_0`, linux/amd64; no Dockerfile here) | `gfastats v1.3.11` | 2026-11-22 |
| tidk | 0.3.3 | `docker://quay.io/biocontainers/tidk@sha256:8d5b6e6aff8adb6e6f65c6e40ae1c6f5850be0d926022b6085d3d80641678f86` (public BioContainers image, tag `0.3.3--hef77e2b_0`, linux/amd64; no Dockerfile here). Upstream https://github.com/tolkit/telomeric-identifier, MIT. Cite: Brown, Gonzalez de La Rosa, Blaxter, *Bioinformatics* 2025, btaf049, https://doi.org/10.1093/bioinformatics/btaf049. Brief: `docs/tools/tidk.md` | `tidk 0.3.3` | 2026-11-23 |
