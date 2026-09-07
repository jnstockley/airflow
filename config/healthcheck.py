#!/usr/bin/env python3
"""Custom Airflow API-server healthcheck.

The Docker Hardened Images (DHI) runtime tag intentionally ships without a
shell, package manager, ``curl`` or ``jq`` to minimize attack surface, so this
check is implemented purely with the Python standard library (which the
Airflow image always provides) rather than shelling out to external tools.

Behaviour mirrors the previous bash implementation: it hits the API server's
``/monitor/health`` endpoint and verifies the metadatabase, scheduler and
triggerer are all reporting healthy.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

HOST = "localhost"
PORT = os.environ.get("AIRFLOW__API__PORT", "8080")
URL = f"http://{HOST}:{PORT}/api/v2/monitor/health"
TIMEOUT_SECONDS = 10


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Failed to reach health endpoint {URL}: {exc}")
        return 1

    checks = {
        "Metadatabase": payload.get("metadatabase", {}).get("status"),
        "Scheduler": payload.get("scheduler", {}).get("status"),
        "Triggerer": payload.get("triggerer", {}).get("status"),
    }

    healthy = True
    for name, status in checks.items():
        if (status or "unknown") != "healthy":
            print(f"{name} is not healthy: {status or 'unknown'}")
            healthy = False

    if not healthy:
        return 1

    print("All services are healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())

