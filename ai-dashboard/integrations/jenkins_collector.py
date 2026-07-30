#!/usr/bin/env python3
"""Poll Jenkins failure artifacts and ingest them into FlightDelay AI.

This process is intentionally independent from the Jenkinsfile and from
scripts/ai/analyze_failure.py. It only reads archived build metadata and the
existing ai-failure-analysis.json artifact.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FAILURE_RESULTS = frozenset({"FAILURE", "UNSTABLE"})
DEFAULT_ARTIFACT = "ai-failure-analysis.json"


@dataclass(frozen=True)
class Config:
    jenkins_base_url: str
    jenkins_job_path: str
    jenkins_user: str
    jenkins_api_token: str
    dashboard_url: str
    dashboard_ingest_token: str
    sites_access_token: str
    poll_interval_seconds: int
    lookback_builds: int
    artifact_path: str
    state_file: Path

    @classmethod
    def from_environment(cls) -> "Config":
        return cls(
            jenkins_base_url=os.getenv(
                "JENKINS_BASE_URL", "http://host.docker.internal:8080"
            ).rstrip("/"),
            jenkins_job_path=os.getenv(
                "JENKINS_JOB_PATH", "job/FlightDelay/job/main"
            ).strip("/"),
            jenkins_user=os.getenv("JENKINS_USER", "").strip(),
            jenkins_api_token=os.getenv("JENKINS_API_TOKEN", "").strip(),
            dashboard_url=os.getenv(
                "DASHBOARD_URL", "http://host.docker.internal:4173"
            ).rstrip("/"),
            dashboard_ingest_token=os.getenv(
                "DASHBOARD_INGEST_TOKEN", ""
            ).strip(),
            sites_access_token=os.getenv("SITES_ACCESS_TOKEN", "").strip(),
            poll_interval_seconds=max(
                15, int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
            ),
            lookback_builds=max(1, int(os.getenv("LOOKBACK_BUILDS", "25"))),
            artifact_path=os.getenv(
                "AI_ANALYSIS_ARTIFACT", DEFAULT_ARTIFACT
            ).strip(),
            state_file=Path(
                os.getenv("COLLECTOR_STATE_FILE", "/data/collector-state.json")
            ),
        )


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{timestamp} {message}", flush=True)


def authorization_header(config: Config) -> dict[str, str]:
    if not config.jenkins_user or not config.jenkins_api_token:
        return {}
    credential = base64.b64encode(
        f"{config.jenkins_user}:{config.jenkins_api_token}".encode("utf-8")
    ).decode("ascii")
    return {"Authorization": f"Basic {credential}"}


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
            **(headers or {}),
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def jenkins_api_url(config: Config) -> str:
    tree = (
        "builds[number,url,result,timestamp,duration,"
        "artifacts[fileName,relativePath],"
        "actions[parameters[name,value],lastBuiltRevision[SHA1]]]?"
    )
    tree = tree[:-1] + f"{{0,{config.lookback_builds}}}"
    query = urllib.parse.urlencode({"tree": tree})
    return (
        f"{config.jenkins_base_url}/{config.jenkins_job_path}/api/json?{query}"
    )


def find_artifact(build: dict[str, Any], configured_path: str) -> str | None:
    artifacts = build.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    configured_name = Path(configured_path).name
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        relative = artifact.get("relativePath")
        filename = artifact.get("fileName")
        if relative == configured_path or filename == configured_name:
            return str(relative or configured_path)
    return None


def build_parameters(build: dict[str, Any]) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    actions = build.get("actions")
    if not isinstance(actions, list):
        return parameters
    for action in actions:
        if not isinstance(action, dict):
            continue
        values = action.get("parameters")
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                parameters[name] = item.get("value")
    return parameters


def build_commit(build: dict[str, Any]) -> str:
    actions = build.get("actions")
    if not isinstance(actions, list):
        return "unknown"
    for action in actions:
        if not isinstance(action, dict):
            continue
        revision = action.get("lastBuiltRevision")
        if isinstance(revision, dict):
            sha = revision.get("SHA1")
            if isinstance(sha, str) and sha:
                return sha[:12]
    return "unknown"


def create_ingest_payload(
    build: dict[str, Any],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    number = int(build["number"])
    parameters = build_parameters(build)
    branch = (
        parameters.get("SOURCE_BRANCH")
        or parameters.get("BRANCH_NAME")
        or parameters.get("GIT_BRANCH")
        or "unknown"
    )
    model = parameters.get("OLLAMA_MODEL") or "unknown"
    build_url = str(build.get("url") or "")
    job_name = (
        urllib.parse.unquote(build_url.rstrip("/").split("/job/", 1)[-1])
        .replace("/job/", "/")
        .rsplit("/", 1)[0]
        or "FlightDelay"
    )
    return {
        "jenkins": {
            "source_key": f"{job_name}#{number}",
            "job_name": job_name,
            "build_number": number,
            "build_url": build_url,
            "result": str(build.get("result") or "FAILURE"),
            "timestamp": int(build.get("timestamp") or 0),
            "duration_ms": int(build.get("duration") or 0),
            "branch": str(branch),
            "commit_sha": build_commit(build),
            "model": str(model),
        },
        "analysis": analysis,
    }


def load_state(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()
    processed = payload.get("processed") if isinstance(payload, dict) else []
    return {str(item) for item in processed} if isinstance(processed, list) else set()


def save_state(path: Path, processed: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            {"processed": sorted(processed), "updated_at": int(time.time())},
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def fetch_artifact(
    config: Config,
    build: dict[str, Any],
    relative_path: str,
) -> dict[str, Any]:
    build_url = str(build.get("url") or "")
    artifact_url = (
        f"{build_url.rstrip('/')}/artifact/"
        f"{urllib.parse.quote(relative_path, safe='/')}"
    )
    return request_json(
        artifact_url,
        headers=authorization_header(config),
        timeout=45,
    )


def ingest(
    config: Config,
    payload: dict[str, Any],
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if config.dashboard_ingest_token:
        headers["Authorization"] = f"Bearer {config.dashboard_ingest_token}"
    if config.sites_access_token:
        headers["OAI-Sites-Authorization"] = (
            f"Bearer {config.sites_access_token}"
        )
    return request_json(
        f"{config.dashboard_url}/api/analyses",
        headers=headers,
        method="POST",
        payload=payload,
        timeout=45,
    )


def collect_once(config: Config) -> tuple[int, int]:
    listing = request_json(
        jenkins_api_url(config),
        headers=authorization_header(config),
        timeout=45,
    )
    builds = listing.get("builds")
    if not isinstance(builds, list):
        raise RuntimeError("Jenkins returned no builds list")

    processed = load_state(config.state_file)
    imported = 0
    considered = 0

    for build in sorted(
        (item for item in builds if isinstance(item, dict)),
        key=lambda item: int(item.get("number") or 0),
    ):
        if str(build.get("result") or "") not in FAILURE_RESULTS:
            continue
        relative_path = find_artifact(build, config.artifact_path)
        if not relative_path:
            continue
        considered += 1
        source_key = f"{config.jenkins_job_path}#{int(build['number'])}"
        if source_key in processed:
            continue
        analysis = fetch_artifact(config, build, relative_path)
        response = ingest(config, create_ingest_payload(build, analysis))
        stored = response.get("analysis")
        stored_key = (
            stored.get("sourceKey")
            if isinstance(stored, dict)
            else f"build #{build['number']}"
        )
        log(f"Imported {stored_key}")
        processed.add(source_key)
        save_state(config.state_file, processed)
        imported += 1

    return considered, imported


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect archived Jenkins AI failure analyses."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one collection pass and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = Config.from_environment()
    log(
        "Collector started "
        f"(job={config.jenkins_job_path}, interval={config.poll_interval_seconds}s)"
    )

    while True:
        try:
            considered, imported = collect_once(config)
            log(
                f"Scan complete: {considered} archived failures, "
                f"{imported} new imports"
            )
        except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError) as error:
            log(f"Scan failed: {error}")
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    sys.exit(main())

