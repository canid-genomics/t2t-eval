# Python 3.11 for the workflow's stdlib-only `script:` rules (first used by M02, sf_telomeres.smk).
# 3.11 matches the linux-64 pixi env that runs Snakemake on agate: for a Python `script:` Snakemake
# binds its own package into the container and the container's `python` imports it.
#
# This image only ever runs on agate, which is x86_64. Build it with:
#     docker build --platform linux/amd64 -t <tag> <this dir>
# The guard below makes a plain `docker build` on an arm64 laptop fail loudly instead
# of producing an unusable image. Do NOT pin --platform on FROM to achieve this: the
# layers come out amd64 but buildkit records the HOST platform in the pushed manifest
# list, so the index says linux/arm64 and apptainer on agate cannot select it.
FROM docker.io/library/python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535

ARG TARGETARCH
RUN [ "${TARGETARCH}" = "amd64" ] \
  || { echo "ERROR: got TARGETARCH=${TARGETARCH}; rebuild with --platform linux/amd64" >&2; exit 1; }

# No packages beyond the base image: the scripts use the standard library only.
RUN python --version
