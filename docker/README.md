# docker/

One image per tool version: `docker/<tool>/<version>/Dockerfile`. Images run on agate (x86_64)
via apptainer, so every Dockerfile carries the amd64 guard (from panimal):

```dockerfile
# This image only ever runs on agate, which is x86_64. Build it with:
#     docker build --platform linux/amd64 -t <tag> <this dir>
# The guard below makes a plain `docker build` on an arm64 laptop fail loudly instead
# of producing an unusable image. Do NOT pin --platform on FROM to achieve this: the
# layers come out amd64 but buildkit records the HOST platform in the pushed manifest
# list, so the index says linux/arm64 and apptainer on agate cannot select it.
ARG TARGETARCH
RUN [ "${TARGETARCH}" = "amd64" ] \
  || { echo "ERROR: got TARGETARCH=${TARGETARCH}; rebuild with --platform linux/amd64" >&2; exit 1; }
```

Build and push with the `images` workflow (Actions → images → Run workflow, with tool and
version). It pushes `ghcr.io/canid-genomics/<tool>:<version>` and `:<version>-<sha7>` and prints
the digest. Then:
1. pin it in `config/images.yaml` as `docker://ghcr.io/canid-genomics/<tool>@sha256:…` (never a tag alone;
   the `docker://` scheme is required, or Snakemake treats it as a local path);
2. add a row to `IMAGES.md` with the `--version` output.

Image changes go through a PR reviewed by the other person. On agate, Snakemake pulls into
`/projects/standard/fried255/shared/containers` (`--apptainer-prefix`); first pulls unpack in
`/dev/shm` (see `slurm/submit.slurm`).
