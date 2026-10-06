#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
    set -- minio --help
elif [ "$1" != minio ]; then
    set -- minio "$@"
fi
exec "$@"
