# IMAGES

Every container the workflow uses, pinned by digest. Add a row when `config/images.yaml` changes.

| Tool | Version | Image (digest) | `--version` output | Added |
|---|---|---|---|---|
| python | 3.11 | `ghcr.io/canid-genomics/python@sha256:a909d1c838b9b40e4274b06b397042e6dd8d4c9b2e2ae7e11ace354268624d57` (built from branch `sf/M02` by `images` workflow run 45058770486; base `python:3.11.18-slim-trixie@sha256:07d48240…b535`) | `Python 3.11.18` | 2026-11-22 |
| gfastats | 1.3.11 | `quay.io/biocontainers/gfastats@sha256:f4903ca4ed682bca6c192cac13f9b0355f149947a7cf3e53bbd2580f3a50bdd7` (public BioContainers image, tag `1.3.11--h077b44d_0`, linux/amd64; no Dockerfile here) | `gfastats v1.3.11` | 2026-11-22 |
