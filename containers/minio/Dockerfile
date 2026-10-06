# syntax=docker/dockerfile:1
ARG BASE_IMAGE=alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8
FROM --platform=$BUILDPLATFORM ${BASE_IMAGE} AS fetch
RUN apk add --no-cache ca-certificates curl
COPY --chmod=755 fetch-binary.sh /usr/local/bin/fetch-binary

FROM fetch AS server-binary
ARG TARGETARCH
ARG MINIO_RELEASE
ARG MINIO_SHA_AMD64
ARG MINIO_SHA_ARM64
RUN --mount=type=bind,from=binaries,target=/binaries \
    fetch-binary minio "$MINIO_RELEASE" "$TARGETARCH" "$MINIO_SHA_AMD64" "$MINIO_SHA_ARM64"

FROM fetch AS client-binary
ARG TARGETARCH
ARG MC_RELEASE
ARG MC_SHA_AMD64
ARG MC_SHA_ARM64
RUN --mount=type=bind,from=binaries,target=/binaries \
    fetch-binary mc "$MC_RELEASE" "$TARGETARCH" "$MC_SHA_AMD64" "$MC_SHA_ARM64"

FROM ${BASE_IMAGE} AS runtime
RUN apk add --no-cache ca-certificates curl
ARG IMAGE_SOURCE=https://github.com/BorisP-COP/minio-images
LABEL org.opencontainers.image.source="$IMAGE_SOURCE" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.vendor="Phoenix Platform"
COPY --from=client-binary /out/mc /usr/local/bin/mc
COPY LICENSE /usr/share/licenses/minio/LICENSE

FROM runtime AS client
ARG MC_RELEASE
LABEL org.opencontainers.image.title="MinIO Client" \
      org.opencontainers.image.version="$MC_RELEASE" \
      org.opencontainers.image.documentation="https://github.com/minio/mc"
ENTRYPOINT ["mc"]
CMD ["--help"]

FROM runtime AS server
ARG MINIO_RELEASE
LABEL org.opencontainers.image.title="MinIO Server" \
      org.opencontainers.image.version="$MINIO_RELEASE" \
      org.opencontainers.image.documentation="https://github.com/minio/minio"
COPY --from=server-binary /out/minio /usr/local/bin/minio
COPY --chmod=755 entrypoint.sh /usr/local/bin/minio-entrypoint
EXPOSE 9000 9001
ENTRYPOINT ["minio-entrypoint"]
CMD ["server", "/data", "--console-address", ":9001"]
