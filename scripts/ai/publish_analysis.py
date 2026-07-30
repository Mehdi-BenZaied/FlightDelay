#!/usr/bin/env python3
"""Publish an existing Jenkins AI failure report to the dashboard API."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--dashboard-url", required=True)
    parser.add_argument("--token", default="")
    return parser.parse_args()


def env(name: str, fallback: str = "unknown") -> str:
    value = os.getenv(name, "").strip()
    return value or fallback


def payload(report: dict[str, Any]) -> dict[str, Any]:
    job_name = env("JOB_NAME", "FlightDelay")
    build_number = int(env("BUILD_NUMBER", "0"))
    return {
        "jenkins": {
            "source_key": f"{job_name}#{build_number}",
            "job_name": job_name,
            "build_number": build_number,
            "build_url": env("BUILD_URL", ""),
            "result": env("BUILD_RESULT", "FAILURE"),
            "timestamp": int(time.time() * 1000),
            "duration_ms": 0,
            "branch": env("SOURCE_BRANCH", env("BRANCH_NAME")),
            "commit_sha": env("GIT_COMMIT", env("SHORT_SHA")),
            "model": env("OLLAMA_MODEL"),
        },
        "analysis": report,
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    body = json.dumps(payload(report)).encode("utf-8")
    endpoint = f"{args.dashboard_url.rstrip('/')}/api/analyses"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    request = urllib.request.Request(
        endpoint,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"dashboard returned HTTP {error.code}: {details}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"dashboard is unreachable: {error.reason}") from error

    analysis = response_body.get("analysis", {})
    print(
        "Dashboard stored "
        f"{analysis.get('sourceKey', 'the Jenkins failure analysis')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
