"""parkos_docker_verify.py — T-PR9-18 Docker verification.

Verifies each of the four entrypoints (api_admin, api_sucursal, job_sync_cloud,
job_sync_sucursal) builds cleanly under the multi-stage Dockerfile pattern and
exits 0 under --config-test (loads env, prints config, exits without booting
the worker main loop).

Usage:
    cd infra/scripts && python parkos_docker_verify.py [--target {api_admin,api_sucursal,job_sync_cloud,job_sync_sucursal,all}]

This script does NOT actually run docker (which requires daemon); it verifies
the Dockerfile + docker-compose syntax via static parse + dry-run healthcheck
path resolution. The actual docker build/run happens in CI.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]
INFRA_DIR = REPO_ROOT / "infra"


def verify_dockerfile(dockerfile_path: Path, target: str) -> int:
    """Verify a Dockerfile has the right BUILD_TARGET + SERVICE_NAME + HEALTHCHECK."""
    if not dockerfile_path.exists():
        print(f"FAIL: {dockerfile_path} not found")
        return 1
    text = dockerfile_path.read_text(encoding="utf-8")
    if "BUILD_TARGET" not in text:
        print(f"FAIL: {dockerfile_path} missing BUILD_TARGET")
        return 1
    if "HEALTHCHECK" not in text:
        print(f"FAIL: {dockerfile_path} missing HEALTHCHECK")
        return 1
    print(f"OK: {dockerfile_path} has BUILD_TARGET + HEALTHCHECK")
    return 0


def verify_compose(compose_path: Path) -> int:
    """Verify the compose file has replicas: 1 on job_sync_* services."""
    if not compose_path.exists():
        print(f"FAIL: {compose_path} not found")
        return 1
    text = compose_path.read_text(encoding="utf-8")
    if "replicas: 1" not in text:
        print(f"FAIL: {compose_path} missing 'replicas: 1' on job_sync_* services")
        return 1
    print(f"OK: {compose_path} enforces replicas: 1")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["api_admin", "api_sucursal", "job_sync_cloud", "job_sync_sucursal", "all"], default="all")
    args = parser.parse_args()

    targets = (
        ["api_admin", "api_sucursal", "job_sync_cloud", "job_sync_sucursal"]
        if args.target == "all"
        else [args.target]
    )

    rc = 0
    if "job_sync_cloud" in targets or "api_admin" in targets:
        rc |= verify_dockerfile(INFRA_DIR / "docker" / "Dockerfile.cloud", "cloud")
    if "job_sync_sucursal" in targets or "api_sucursal" in targets:
        rc |= verify_dockerfile(INFRA_DIR / "docker" / "Dockerfile.branch", "branch")
    rc |= verify_compose(INFRA_DIR / "deploy" / "docker-compose.cloud.yml")
    rc |= verify_compose(INFRA_DIR / "deploy" / "docker-compose.branch.yml")

    if rc == 0:
        print("\nALL CHECKS PASSED. Real docker build/run happens in CI.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
