#!/usr/bin/env python3
"""Publish a Jenkins AI failure report to the FlightDelay dashboard."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RETRIES = 3
RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}

REQUIRED_ANALYSIS_FIELDS = {
    "analysis_status",
    "summary",
    "failed_stage",
    "failed_component",
    "category",
    "root_cause",
    "secondary_errors",
    "evidence",
    "checks",
    "remediation_steps",
    "prevention",
    "missing_information",
    "confidence",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish ai-failure-analysis.json to the dashboard API."
        )
    )
    parser.add_argument("--report", required=True)
    parser.add_argument("--dashboard-url", required=True)
    parser.add_argument("--token", default="")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
    )
    return parser.parse_args()


def environment(name: str, fallback: str = "unknown") -> str:
    value = os.getenv(name, "").strip()
    return value or fallback


def safe_integer(value: str, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"analysis report does not exist: {path}")

    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"analysis report is not valid JSON: {error}"
        ) from error

    if not isinstance(report, dict):
        raise RuntimeError("analysis report must be a JSON object")

    missing = sorted(REQUIRED_ANALYSIS_FIELDS - report.keys())
    if missing:
        raise RuntimeError(
            "analysis report is incomplete; missing fields: "
            + ", ".join(missing)
        )

    try:
        confidence = float(report["confidence"])
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            "analysis confidence must be numeric"
        ) from error

    if not 0 <= confidence <= 1:
        raise RuntimeError(
            "analysis confidence must be between 0 and 1"
        )

    return report


def build_payload(report: dict[str, Any]) -> dict[str, Any]:
    job_name = environment("JOB_NAME", "FlightDelay")
    build_number = safe_integer(
        environment("BUILD_NUMBER", "0"),
        0,
    )

    timestamp_ms = safe_integer(
        environment("BUILD_TIMESTAMP_MS", "0"),
        0,
    )
    if timestamp_ms <= 0:
        timestamp_ms = int(time.time() * 1000)

    duration_ms = safe_integer(
        environment("BUILD_DURATION_MS", "0"),
        0,
    )

    return {
        "jenkins": {
            "source_key": f"{job_name}#{build_number}",
            "job_name": job_name,
            "build_number": build_number,
            "build_url": environment("BUILD_URL", ""),
            "result": environment("BUILD_RESULT", "FAILURE"),
            "timestamp": timestamp_ms,
            "duration_ms": max(duration_ms, 0),
            "branch": environment(
                "SOURCE_BRANCH",
                environment("BRANCH_NAME", "unknown"),
            ),
            "commit_sha": environment(
                "SHORT_SHA",
                environment("GIT_COMMIT", "unknown"),
            ),
            "model": environment("OLLAMA_MODEL", "unknown"),
        },
        "analysis": report,
    }


def dashboard_endpoint(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")

    if not normalized:
        raise RuntimeError("dashboard URL cannot be empty")

    if not (
        normalized.startswith("http://")
        or normalized.startswith("https://")
    ):
        raise RuntimeError(
            "dashboard URL must start with http:// or https://"
        )

    return f"{normalized}/api/analyses"


def retry_delay(attempt: int) -> float:
    return min(2 ** max(attempt - 1, 0), 8)


def publish(
    *,
    endpoint: str,
    body: bytes,
    token: str,
    timeout_seconds: int,
    retries: int,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "flightdelay-jenkins-analysis-publisher/1.0",
    }

    if token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"

    attempts = max(retries, 1)

    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=max(timeout_seconds, 1),
            ) as response:
                raw_response = response.read().decode(
                    "utf-8",
                    errors="replace",
                )

                if not raw_response.strip():
                    return {}

                payload = json.loads(raw_response)

                if not isinstance(payload, dict):
                    raise RuntimeError(
                        "dashboard response must be a JSON object"
                    )

                return payload

        except urllib.error.HTTPError as error:
            details = error.read().decode(
                "utf-8",
                errors="replace",
            ).strip()

            if (
                error.code not in RETRYABLE_HTTP_CODES
                or attempt == attempts
            ):
                raise RuntimeError(
                    f"dashboard returned HTTP {error.code}: "
                    f"{details or 'no response body'}"
                ) from error

            print(
                f"Dashboard returned HTTP {error.code}; "
                f"retrying ({attempt}/{attempts})...",
                file=sys.stderr,
                flush=True,
            )

        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
        ) as error:
            if attempt == attempts:
                reason = getattr(error, "reason", error)
                raise RuntimeError(
                    f"dashboard is unreachable: {reason}"
                ) from error

            print(
                "Dashboard is temporarily unreachable; "
                f"retrying ({attempt}/{attempts})...",
                file=sys.stderr,
                flush=True,
            )

        time.sleep(retry_delay(attempt))

    raise RuntimeError("dashboard publication failed unexpectedly")


def main() -> int:
    args = parse_args()

    try:
        report = load_report(Path(args.report))
        body = json.dumps(
            build_payload(report),
            separators=(",", ":"),
        ).encode("utf-8")

        endpoint = dashboard_endpoint(args.dashboard_url)

        response_body = publish(
            endpoint=endpoint,
            body=body,
            token=args.token,
            timeout_seconds=args.timeout,
            retries=args.retries,
        )

        stored_analysis = response_body.get("analysis", {})
        source_key = (
            stored_analysis.get("sourceKey")
            if isinstance(stored_analysis, dict)
            else None
        )

        print(
            "Dashboard stored "
            f"{source_key or 'the Jenkins failure analysis'}"
        )
        return 0

    except Exception as error:
        print(
            f"Dashboard publication failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
