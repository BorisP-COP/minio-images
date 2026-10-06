#!/bin/sh
set -eu

product="$1"
release="$2"
architecture="$3"
sha_amd64="$4"
sha_arm64="$5"

case "$product" in minio|mc) ;; *) echo 'Unsupported product' >&2; exit 1 ;; esac
case "$architecture" in
    amd64) expected="$sha_amd64" ;;
    arm64) expected="$sha_arm64" ;;
    *) echo "Unsupported Linux architecture: $architecture" >&2; exit 1 ;;
esac
test -n "$expected"
filename="$product.linux-$architecture.$release"
mkdir -p /out
if [ -f "/binaries/$filename" ]; then
    cp "/binaries/$filename" "/out/$product"
else
    curl --fail --location --retry 3 --connect-timeout 20 --max-time 600 \
        "https://github.com/minio/$product/releases/download/$release/$filename" \
        --output "/out/$product"
fi
printf '%s  %s\n' "$expected" "/out/$product" | sha256sum -c -
chmod 755 "/out/$product"
