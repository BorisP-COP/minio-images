#!/usr/bin/env python3
"""Build shared MinIO images. Architecture selection is handled centrally."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

CONTEXT = Path(__file__).resolve().parent
CONFIG = json.loads((CONTEXT / "releases.json").read_text())
PLATFORMS = "linux/amd64,linux/arm64"


def run(command, *, dry_run=False):
    print("+ " + shlex.join(command), flush=True)
    if not dry_run:
        subprocess.run(command, check=True)


def verify_local(directory):
    found = 0
    artifacts = {"minio": CONFIG["servers"], "mc": {
        CONFIG["client"]["release"]: CONFIG["client"]["sha256"]
    }}
    for product, releases in artifacts.items():
        for release, architectures in releases.items():
            for arch, expected in architectures.items():
                path = directory / f"{product}.linux-{arch}.{release}"
                if not path.is_file():
                    continue
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected:
                    raise ValueError(f"SHA-256 mismatch: {path}")
                found += 1
                print(f"SHA-256 OK: {path.name}")
    if not found:
        raise ValueError(f"No known Linux MinIO/mc binaries in {directory}")


def verify_manifest(image):
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", "--raw", image],
        check=True, capture_output=True, text=True,
    )
    manifest = json.loads(result.stdout)
    platforms = {
        f"{item.get('platform', {}).get('os')}/{item.get('platform', {}).get('architecture')}"
        for item in manifest.get("manifests", [])
    }
    missing = set(PLATFORMS.split(",")) - platforms
    if missing:
        raise ValueError(f"{image} is missing: {', '.join(sorted(missing))}")
    print(f"Registry platforms OK: {image}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--push", action="store_true", help="Publish both architectures to a registry")
    mode.add_argument("--load", action="store_true", help="Load the host architecture into local Docker (default)")
    mode.add_argument("--verify-local", type=Path, metavar="DIRECTORY", help="Check downloaded binaries only")
    parser.add_argument("--all", action="store_true", help="Build every pinned server version and mc")
    parser.add_argument("--release", choices=tuple(CONFIG["servers"]), default=CONFIG["default_server"])
    parser.add_argument("--namespace", default=CONFIG["namespace"], help="Registry namespace, e.g. ghcr.io/borisp-cop/minio-images")
    parser.add_argument("--local-binaries", type=Path, help="Optional external binary cache; files are never copied into Git")
    parser.add_argument("--dry-run", action="store_true", help="Show build commands without building or publishing")
    args = parser.parse_args()
    if args.verify_local:
        verify_local(args.verify_local.resolve())
        return
    namespace = args.namespace.rstrip("/").lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._:/-]*", namespace) or "/" not in namespace:
        parser.error("namespace must be a registry path without a protocol, tag or credentials")
    if "//" in namespace or ":" in namespace.split("/", 1)[1]:
        parser.error("namespace must not contain a protocol or image tag")
    binaries = (args.local_binaries or CONTEXT / "empty").resolve()
    if not binaries.is_dir():
        parser.error(f"Binary cache directory does not exist: {binaries}")
    if args.local_binaries:
        verify_local(binaries)
    client = CONFIG["client"]
    # A fork or standalone GHCR repository must own its package source label.
    namespace_parts = namespace.split("/")
    source_url = (
        f"https://github.com/{namespace_parts[1]}/{namespace_parts[2]}"
        if namespace_parts[0] == "ghcr.io" and len(namespace_parts) == 3
        else "https://github.com/BorisP-COP/minio-images"
    )
    targets = [("server", release) for release in (CONFIG["servers"] if args.all else [args.release])]
    targets.append(("client", client["release"]))
    for target, release in targets:
        product = "minio" if target == "server" else "mc"
        image = f"{namespace}/{product}:{release}"
        command = ["docker", "buildx", "build", "--target", target,
                   "--tag", image, "--build-context", f"binaries={binaries}"]
        build_args = {
            "BASE_IMAGE": CONFIG["base_image"], "IMAGE_SOURCE": source_url,
            "MC_RELEASE": client["release"],
            "MC_SHA_AMD64": client["sha256"]["amd64"], "MC_SHA_ARM64": client["sha256"]["arm64"],
        }
        if target == "server":
            hashes = CONFIG["servers"][release]
            build_args.update(MINIO_RELEASE=release, MINIO_SHA_AMD64=hashes["amd64"], MINIO_SHA_ARM64=hashes["arm64"])
        for key, value in build_args.items():
            command.extend(["--build-arg", f"{key}={value}"])
        if args.push:
            command.extend(["--platform", PLATFORMS, "--push"])
        else:
            # BuildKit selects the Docker host architecture; callers need no --platform.
            command.append("--load")
        command.append(str(CONTEXT))
        run(command, dry_run=args.dry_run)
        if args.push and not args.dry_run:
            verify_manifest(image)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
