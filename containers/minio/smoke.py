#!/usr/bin/env python3
"""Check health and S3 round trips in disposable containers, without host ports or volumes."""

import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid

CONFIG = json.loads((Path(__file__).parent / "releases.json").read_text())


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, **kwargs)


def check(server_image, client_image, platform=None):
    name = "shared-minio-smoke-" + uuid.uuid4().hex[:12]
    platform_args = ["--platform", platform] if platform else []
    created = False
    docker("network", "create", name)
    try:
        docker("run", "--detach", "--rm", *platform_args, "--name", name,
               "--network", name, "--tmpfs", "/data",
               "--env", "MINIO_ROOT_USER=smoke",
               "--env", "MINIO_ROOT_PASSWORD=smoke-password-for-disposable-test",
               server_image, "server", "/data", "--console-address", ":9001")
        created = True
        deadline = time.monotonic() + 45
        while True:
            health = subprocess.run(["docker", "exec", name, "curl", "--fail", "--silent",
                                     "http://localhost:9000/minio/health/ready"], capture_output=True)
            if health.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f"MinIO readiness failed: {server_image}")
            time.sleep(0.5)
        version = docker("exec", name, "minio", "--version").stdout.splitlines()[0]
        # Existing MindPlaces/Reports Compose files use this healthcheck.
        docker("exec", name, "mc", "ready", "local", timeout=15)
        script = """set -eu
mc mb smoke/roundtrip >/dev/null
printf 'shared MinIO S3 roundtrip\n' >/tmp/source
mc cp /tmp/source smoke/roundtrip/object >/dev/null
mc cp smoke/roundtrip/object /tmp/result >/dev/null
cmp /tmp/source /tmp/result
mc rm smoke/roundtrip/object >/dev/null
mc rb smoke/roundtrip >/dev/null
"""
        docker("run", "--rm", "--network", name, "--entrypoint", "/bin/sh",
               "--env", f"MC_HOST_smoke=http://smoke:smoke-password-for-disposable-test@{name}:9000",
               client_image, "-ec", script)
        print(f"PASS: {server_image} health + upload/download/delete; {version}", flush=True)
    finally:
        if created:
            subprocess.run(["docker", "rm", "--force", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", name], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default=CONFIG["namespace"])
    parser.add_argument("--server-image", help="Check one image instead of all pinned versions")
    parser.add_argument("--platform", help="Optional explicit platform for cross-architecture verification")
    args = parser.parse_args()
    namespace = args.namespace.rstrip("/").lower()
    client = f"{namespace}/mc:{CONFIG['client']['release']}"
    servers = [args.server_image] if args.server_image else [
        f"{namespace}/minio:{release}" for release in CONFIG["servers"]
    ]
    for image in servers:
        check(image, client, args.platform)


if __name__ == "__main__":
    main()
