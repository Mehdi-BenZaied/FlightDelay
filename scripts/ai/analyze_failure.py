#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "qwen2.5-coder:3b-instruct"
MAX_LOG_CHARACTERS = 15_000
CONTEXT_LINES = 3
TAIL_LINES = 50
OLLAMA_REQUEST_TIMEOUT_SECONDS = int(
    os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "2500")
)

PER_LOG_CHARACTER_LIMIT = 4_000

IGNORED_ANALYSIS_LOGS = {
    "ai-analysis-run.log",
    "ai-analysis-error.log",
    "ai-analysis-success.log",
    "ai-model-preflight.log",
    "ollama-model-pull.log",
    "ollama-external-check.log",
}

ALWAYS_INCLUDE_LOGS = {
    "failure-summary.log",
    "pipeline-context.log",
    "docker-compose-health.log",
    "docker-daemon-check.log",
}

LOG_PRIORITY = {
    "failure-summary.log": 0,
    "pipeline-context.log": 1,
    "docker-daemon-check.log": 2,
    "docker-compose-health.log": 2,
    "jenkins-console.log": 3,
    "simulated-failure.log": 3,
    "docker-compose-failure.log": 4,
    "docker-compose-integration.log": 5,
    "build-backend.log": 6,
    "build-frontend.log": 6,
    "validate-compose.log": 7,
    "kubernetes-failure.log": 8,
    "final-compose-state.log": 20,
}


ERROR_PATTERN = re.compile(
    r"""
    error
    |failed
    |failure
    |fatal
    |exception
    |traceback
    |denied
    |unauthorized
    |forbidden
    |timeout
    |timed\s*out
    |connection\s*refused
    |not\s*found
    |no\s*such\s*file
    |unhealthy
    |exit\s*code
    |crashloop
    |imagepull
    |back-off
    |cannot
    |could\s*not
    |unhealthy
    |health\s*check
    |healthcheck
    |http\s*404
    |\b404\b
    |curl:\s*\(22\)
    |manifest\s*unknown
    |pull\s*access\s*denied
    |failed\s*to\s*solve
    |syntaxerror
    |modulenotfounderror
    |importerror
    |crashloopbackoff
    |imagepullbackoff
    |errimagepull
    """,
    re.IGNORECASE | re.VERBOSE,
)


SYSTEM_PROMPT = """
You are a senior DevOps/SRE CI/CD failure-triage assistant.

Environment you are analyzing:

- Jenkins controller runs on Windows.
- Jenkins build agent runs inside Ubuntu WSL.
- Docker Desktop on Windows provides the Docker Engine to WSL.
- The Jenkins agent label is "linux-docker-agent".
- The application is FlightDelay, a containerized full-stack application.
- Frontend: web application served by Nginx, container port 80.
- Backend: Python API started by run.py, container port 5000.
- Analytics: Python analytics service started by analytics.py, port 8050.
- Cache: Redis 7, port 6379.
- Local database: SQLite stored in /app/data/flight_delay.db.
- Machine-learning files include ml/models/v1_model.json and
  data/flight_data.csv.
- Ollama runs as a Docker Compose service on port 11434.
- The default Ollama model is qwen2.5-coder:3b-instruct.
- Docker Compose starts Redis, Ollama, backend, analytics, and frontend.
- Images are built by Jenkins and may be pushed to Docker Hub.
- Kubernetes deployment is optional and uses kind plus Helm.
- Important pipeline stages include:
  1. Checkout and Metadata
  2. Validate Parameters
  3. Validate Agent and Project
  4. Validate Docker Compose
  5. Validate Helm Chart
  6. Build Docker Images
  7. Docker Compose Integration Tests
  8. Publish Docker Images
  9. Optional Kubernetes deployment and smoke tests

Your task is to diagnose a failed pipeline using only the supplied evidence.

Analysis requirements:

1. Identify the first meaningful root-cause error.
2. Separate the primary root cause from secondary or cascading errors.
3. Identify the likely failed stage and affected component.
4. Quote exact evidence from the provided logs.
5. Do not claim certainty when evidence is incomplete.
6. Prefer safe diagnostic checks before suggesting changes.
7. Tailor commands to the correct platform:
   - bash for Ubuntu WSL / Jenkins agent
   - PowerShell for Windows / Jenkins controller / Docker Desktop
8. Never expose, repeat, or reconstruct passwords, tokens, SSH keys,
   Jenkins secrets, Docker credentials, cookies, or authorization headers.
9. Never recommend dangerous commands such as:
   - chmod 777
   - rm -rf on broad directories
   - docker system prune -a
   - deleting databases or volumes
   unless clearly marked as destructive and absolutely necessary.
10. Do not recommend increasing timeouts when the logs show a real
    application, networking, credential, image, or configuration problem.
11. Explain why each diagnostic command is useful and what result is expected.
12. If the evidence is insufficient, list the exact additional logs or
    commands required.
13. Do not automatically execute any remediation.
14. Keep the diagnosis technical, direct, and actionable.

Common environment-specific failures to recognize include:

- Docker Desktop is not running.
- /var/run/docker.sock is missing inside WSL.
- Docker Desktop WSL integration is disabled.
- Jenkins agent is offline or has no executor.
- Jenkins is using the wrong WSL home directory.
- Docker Hub credentials are invalid or image push is denied.
- Docker image or tag does not exist.
- Docker Compose configuration is invalid.
- Docker Compose health checks fail.
- Redis is unhealthy or unreachable from the backend.
- The backend cannot find its model, dataset, or SQLite path.
- Ollama is unreachable, the model pull fails, or memory is insufficient.
- The backend uses the wrong Ollama URL or model name.
- The frontend cannot reach the backend service.
- Helm rendering fails because a value or template is invalid.
- Kubernetes Service selectors do not match Pod labels.
- Kubernetes probes use the wrong port or path.
- Disk space, memory, or Docker build cache is exhausted.

Analyze failures from every pipeline area, including:

- checkout and source control
- Jenkins agent and WSL
- Docker and Docker Compose
- frontend, backend, analytics, Redis, SQLite, and Ollama
- tests and health checks
- Docker Hub authentication and image publication
- Helm rendering and Kubernetes deployment
- network, credentials, configuration, timeout, disk, RAM, and CPU issues

Evidence and consistency requirements:

- Use the metadata field last_stage as the failed stage unless stronger log
  evidence proves another stage failed first.
- Every evidence excerpt must appear verbatim in the supplied logs.
- Never invent a log filename, error message, command result, or service state.
- The root cause must be supported by at least one evidence excerpt.
- Do not use evidence describing an unrelated or older failure.
- Confidence must be a number from 0 to 1, for example 0.75, never 75.
- When analysis_status is insufficient_evidence, confidence must be below 0.5.
- If force_ai_failure is true and the logs contain
  "Controlled failure triggered to validate Ollama analysis.", classify it as
  test_failure and explain that Jenkins intentionally exited with code 1.
- Do not report the simulated Redis or backend message as a real outage when
  force_ai_failure is true.
- Distinguish the original pipeline failure from errors produced later by the
  AI-analysis or cleanup process.

Keep the response concise so it can run efficiently on CPU-only hardware:

- Return at most 2 secondary errors.
- Return at most 2 evidence items.
- Return at most 2 diagnostic checks.
- Return at most 2 remediation steps.
- Return at most 2 prevention items.
- Return at most 2 missing-information items.
- Avoid repeating the same error, explanation, or command.
- Keep each explanation direct and brief.

Return only structured JSON that follows the supplied JSON schema.
"""


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "analysis_status": {
            "type": "string",
            "enum": [
                "diagnosed",
                "probable",
                "insufficient_evidence",
            ],
        },
        "summary": {"type": "string", "maxLength": 350},
        "failed_stage": {"type": "string", "maxLength": 160},
        "failed_component": {"type": "string", "maxLength": 160},
        "category": {
            "type": "string",
            "enum": [
                "source_control",
                "jenkins_agent",
                "docker",
                "docker_compose",
                "frontend",
                "backend",
                "database",
                "network",
                "credentials",
                "registry",
                "kubernetes",
                "resource_exhaustion",
                "configuration",
                "test_failure",
                "unknown",
            ],
        },
        "root_cause": {"type": "string", "maxLength": 600},
        "secondary_errors": {
            "type": "array",
            "maxItems": 2,
            "items": {"type": "string"},
        },
        "evidence": {
            "type": "array",
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "log_file": {"type": "string", "maxLength": 260},
                    "excerpt": {"type": "string", "maxLength": 600},
                    "interpretation": {"type": "string", "maxLength": 300},
                },
                "required": [
                    "log_file",
                    "excerpt",
                    "interpretation",
                ],
            },
        },
        "checks": {
            "type": "array",
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "enum": [
                            "WSL",
                            "Windows PowerShell",
                            "Jenkins UI",
                            "Docker",
                            "Kubernetes",
                        ],
                    },
                    "command": {"type": "string", "maxLength": 400},
                    "purpose": {"type": "string", "maxLength": 250},
                    "expected_result": {"type": "string", "maxLength": 250},
                },
                "required": [
                    "platform",
                    "command",
                    "purpose",
                    "expected_result",
                ],
            },
        },
        "remediation_steps": {
            "type": "array",
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "action": {"type": "string", "maxLength": 300},
                    "command": {"type": "string"},
                    "risk": {
                        "type": "string",
                        "enum": [
                            "safe",
                            "review_required",
                            "destructive",
                        ],
                    },
                },
                "required": [
                    "priority",
                    "action",
                    "command",
                    "risk",
                ],
            },
        },
        "prevention": {
            "type": "array",
            "maxItems": 2,
            "items": {"type": "string"},
        },
        "missing_information": {
            "type": "array",
            "maxItems": 2,
            "items": {"type": "string"},
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
    },
    "required": [
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
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze Jenkins failure logs with local Ollama."
    )
    parser.add_argument(
        "--logs-dir",
        default="ci-logs",
        help="Directory containing pipeline log files.",
    )
    parser.add_argument(
        "--output-json",
        default="ai-failure-analysis.json",
    )
    parser.add_argument(
        "--output-markdown",
        default="ai-failure-analysis.md",
    )
    parser.add_argument(
        "--output-raw",
        default="ai-raw-response.txt",
        help="File used to preserve the raw Ollama response.",
    )
    return parser.parse_args()


def windows_host_ip() -> str:
    completed = subprocess.run(
        ["ip", "route", "show", "default"],
        check=True,
        capture_output=True,
        text=True,
    )

    fields = completed.stdout.strip().split()

    if "via" not in fields:
        raise RuntimeError(
            "Could not determine the Windows host IP from WSL."
        )

    return fields[fields.index("via") + 1]


def ollama_url() -> str:
    configured = os.getenv("OLLAMA_URL")

    if configured:
        return configured.rstrip("/")

    return f"http://{windows_host_ip()}:11434/api/chat"


def sanitize(text: str) -> str:
    patterns = [
        (
            re.compile(
                r"(?i)(password|passwd|token|secret|api[_-]?key)"
                r"\s*[:=]\s*[^\s]+"
            ),
            r"\1=[REDACTED]",
        ),
        (
            re.compile(r"(?i)authorization:\s*bearer\s+\S+"),
            "Authorization: Bearer [REDACTED]",
        ),
        (
            re.compile(r"(?i)--password(?:-stdin)?\s+\S+"),
            "--password [REDACTED]",
        ),
        (
            re.compile(r"(?i)-secret\s+[a-f0-9]{32,}"),
            "-secret [REDACTED]",
        ),
        (
            re.compile(r"(?i)glpat-[A-Za-z0-9_-]+"),
            "[REDACTED_GITLAB_TOKEN]",
        ),
    ]

    sanitized = text

    for pattern, replacement in patterns:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def extract_relevant_lines(
    lines: list[str],
    include_tail_when_no_error: bool = False,
) -> list[str]:
    selected_indexes: set[int] = set()

    for index, line in enumerate(lines):
        if ERROR_PATTERN.search(line):
            start = max(0, index - CONTEXT_LINES)
            end = min(
                len(lines),
                index + CONTEXT_LINES + 1,
            )
            selected_indexes.update(range(start, end))

    if not selected_indexes and include_tail_when_no_error:
        tail_start = max(0, len(lines) - TAIL_LINES)
        selected_indexes.update(
            range(tail_start, len(lines))
        )

    return [
        lines[index]
        for index in sorted(selected_indexes)
    ]


def collect_logs(logs_directory: Path) -> str:
    if not logs_directory.exists():
        raise FileNotFoundError(
            f"Log directory does not exist: {logs_directory}"
        )

    log_files = [
        path
        for path in logs_directory.rglob("*.log")
        if path.name not in IGNORED_ANALYSIS_LOGS
    ]

    log_files.sort(
        key=lambda path: (
            LOG_PRIORITY.get(path.name, 100),
            -path.stat().st_mtime,
            str(path),
        )
    )

    sections: list[str] = []
    remaining_characters = MAX_LOG_CHARACTERS

    for log_file in log_files:
        raw_text = log_file.read_text(
            encoding="utf-8",
            errors="replace",
        )

        if log_file.name in ALWAYS_INCLUDE_LOGS:
            relevant = raw_text.splitlines()
        else:
            relevant = extract_relevant_lines(
                raw_text.splitlines(),
                include_tail_when_no_error=False,
            )

        if not relevant:
            continue

        relative_name = log_file.relative_to(
            logs_directory
        )

        section = (
            f"\n===== LOG FILE: {relative_name} =====\n"
            + "\n".join(relevant)
        )

        section = sanitize(section)

        if len(section) > PER_LOG_CHARACTER_LIMIT:
            header, separator, content = section.partition("\n")

            if separator:
                allowed_content = (
                    PER_LOG_CHARACTER_LIMIT
                    - len(header)
                    - len(separator)
                )
                section = (
                    header
                    + separator
                    + content[-max(0, allowed_content):]
                )
            else:
                section = section[-PER_LOG_CHARACTER_LIMIT:]

        if len(section) > remaining_characters:
            section = section[:remaining_characters]

        if not section.strip():
            continue

        sections.append(section)
        remaining_characters -= len(section)

        if remaining_characters <= 0:
            break

    combined = "\n".join(sections)

    if not combined.strip():
        raise RuntimeError(
            "No useful pipeline failure logs were found."
        )

    return combined


def high_signal_summary(log_text: str) -> str:
    selected: list[str] = []

    for line in log_text.splitlines():
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("===== LOG FILE:"):
            continue

        if ERROR_PATTERN.search(stripped):
            if stripped not in selected:
                selected.append(stripped)

        if len(selected) >= 30:
            break

    if not selected:
        return "No high-signal error line was extracted."

    return "\n".join(f"- {line}" for line in selected)


def build_user_prompt(log_text: str) -> str:
    metadata = {
        "job_name": os.getenv("JOB_NAME", "unknown"),
        "build_number": os.getenv("BUILD_NUMBER", "unknown"),
        "build_url": os.getenv("BUILD_URL", "unknown"),
        "branch": os.getenv(
            "SOURCE_BRANCH",
            os.getenv("BRANCH_NAME", "unknown"),
        ),
        "commit": os.getenv("SHORT_SHA", "unknown"),
        "node_name": os.getenv("NODE_NAME", "unknown"),
        "workspace": os.getenv("WORKSPACE", "unknown"),
        "last_stage": os.getenv("LAST_STAGE", "unknown"),
        "build_result": os.getenv("BUILD_RESULT", "FAILURE"),
        "force_ai_failure": os.getenv(
            "FORCE_AI_FAILURE",
            "false",
        ).lower(),
    }

    return f"""
Analyze the Jenkins pipeline failure below.

Pipeline metadata:

{json.dumps(metadata, indent=2)}

Instructions:

- Find the earliest meaningful root cause of the current build failure.
- Use last_stage to identify where Jenkins was executing when it failed.
- Do not treat repeated retries or cleanup errors as separate root causes.
- Use only exact log excerpts as evidence.
- Never invent evidence or a log filename.
- Make sure the root cause and evidence describe the same failure.
- Provide commands that match this Windows + WSL environment.
- Do not output secrets.
- Return confidence as a number between 0 and 1.
- If the root cause cannot be proved, use
  analysis_status="insufficient_evidence" and confidence below 0.5.

Pre-extracted high-signal error lines:

{high_signal_summary(log_text)}

Sanitized and reduced pipeline logs:

{log_text}
"""


def request_analysis(
    api_url: str,
    model: str,
    user_prompt: str,
    raw_output_path: Path,
) -> dict[str, Any]:
    request_body = {
        "model": model,
        "stream": False,
        "keep_alive": "30m",
        "format": OUTPUT_SCHEMA,
        "options": {
            "temperature": 0,
            "num_ctx": 6144,
            "num_predict": 2000,
        },
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    }

    request = urllib.request.Request(
        api_url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(
        "Ollama request timeout: "
        f"{OLLAMA_REQUEST_TIMEOUT_SECONDS} seconds",
        flush=True,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_REQUEST_TIMEOUT_SECONDS,
        ) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Could not reach Ollama at {api_url}: {error}"
        ) from error

    content = payload.get("message", {}).get("content", "")
    done_reason = payload.get("done_reason", "unknown")
    prompt_eval_count = payload.get(
        "prompt_eval_count",
        "unknown",
    )
    eval_count = payload.get("eval_count", "unknown")

    print(f"Ollama done reason: {done_reason}", flush=True)
    print(
        f"Ollama prompt tokens: {prompt_eval_count}",
        flush=True,
    )
    print(
        f"Ollama generated tokens: {eval_count}",
        flush=True,
    )

    raw_output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    raw_output_path.write_text(
        content,
        encoding="utf-8",
    )

    if not content.strip():
        raise RuntimeError(
            "Ollama returned no message content. "
            f"Raw response saved to {raw_output_path}."
        )

    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        print(
            "WARNING: Ollama returned invalid or truncated JSON. "
            "The grounded local fallback will analyze the collected "
            "pipeline errors instead.",
            file=sys.stderr,
            flush=True,
        )
        print(
            f"Ollama JSON details: done_reason={done_reason}, "
            f"eval_count={eval_count}, error={error}",
            file=sys.stderr,
            flush=True,
        )
        print(
            f"Raw Ollama response saved to {raw_output_path}.",
            file=sys.stderr,
            flush=True,
        )

        return {
            "analysis_status": "insufficient_evidence",
            "summary": (
                "The Ollama response could not be parsed as complete "
                "JSON. A grounded local fallback will use the collected "
                "pipeline logs."
            ),
            "failed_stage": os.getenv(
                "LAST_STAGE",
                "unknown",
            ),
            "failed_component": "pipeline",
            "category": "unknown",
            "root_cause": (
                "The model response was truncated or malformed."
            ),
            "secondary_errors": [],
            "evidence": [],
            "checks": [],
            "remediation_steps": [],
            "prevention": [],
            "missing_information": [
                "The Ollama JSON response was incomplete."
            ],
            "confidence": 0.0,
        }


def normalize_confidence(value: Any) -> float:
    try:
        if isinstance(value, str):
            normalized = value.strip().rstrip("%")
            confidence = float(normalized)
        else:
            confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    if 1 < confidence <= 100:
        confidence /= 100

    return max(0.0, min(confidence, 1.0))


def normalize_for_match(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value.strip().lower(),
    )


def excerpt_is_grounded(excerpt: str, log_text: str) -> bool:
    normalized_log = normalize_for_match(log_text)

    meaningful_lines = [
        normalize_for_match(line)
        for line in excerpt.splitlines()
        if len(line.strip()) >= 8
    ]

    if not meaningful_lines:
        return False

    return any(
        line in normalized_log
        for line in meaningful_lines
    )


def current_log_file(
    lines: list[str],
    index: int,
) -> str:
    for previous in range(index, -1, -1):
        line = lines[previous].strip()

        if (
            line.startswith("===== LOG FILE:")
            and line.endswith("=====")
        ):
            return (
                line
                .removeprefix("===== LOG FILE:")
                .removesuffix("=====")
                .strip()
            )

    return "pipeline logs"


def find_matching_evidence(
    log_text: str,
    patterns: list[re.Pattern[str]],
) -> tuple[str, str] | None:
    lines = log_text.splitlines()

    for index, line in enumerate(lines):
        stripped = line.strip()

        if not stripped:
            continue

        if any(pattern.search(stripped) for pattern in patterns):
            return current_log_file(lines, index), stripped

    return None


def base_fallback_result(
    *,
    stage: str,
    component: str,
    category: str,
    summary: str,
    root_cause: str,
    log_file: str,
    excerpt: str,
    interpretation: str,
    confidence: float,
    checks: list[dict[str, str]],
    remediation_steps: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "analysis_status": "diagnosed",
        "summary": summary,
        "failed_stage": stage,
        "failed_component": component,
        "category": category,
        "root_cause": root_cause,
        "secondary_errors": [],
        "evidence": [
            {
                "log_file": log_file,
                "excerpt": excerpt,
                "interpretation": interpretation,
            }
        ],
        "checks": checks[:4],
        "remediation_steps": remediation_steps[:4],
        "prevention": [],
        "missing_information": [],
        "confidence": confidence,
    }


def deterministic_fallback(
    log_text: str,
) -> dict[str, Any] | None:
    stage = os.getenv("LAST_STAGE", "unknown")

    docker_daemon = find_matching_evidence(
        log_text,
        [
            re.compile(
                r"failed to connect to the docker api",
                re.IGNORECASE,
            ),
            re.compile(
                r"cannot connect to the docker daemon",
                re.IGNORECASE,
            ),
            re.compile(
                r"docker\.sock.*no such file",
                re.IGNORECASE,
            ),
        ],
    )

    if docker_daemon:
        log_file, excerpt = docker_daemon

        return base_fallback_result(
            stage=stage,
            component="Docker daemon",
            category="docker",
            summary=(
                "The pipeline could not communicate with the "
                "Docker daemon."
            ),
            root_cause=(
                "Docker Desktop or its WSL integration was not "
                "available, so the Docker socket could not be used."
            ),
            log_file=log_file,
            excerpt=excerpt,
            interpretation=(
                "This is the direct Docker API connection error "
                "that caused the stage to fail."
            ),
            confidence=0.99,
            checks=[
                {
                    "platform": "WSL",
                    "command": "docker info",
                    "purpose": (
                        "Verify that the Jenkins WSL agent can "
                        "reach the Docker daemon."
                    ),
                    "expected_result": (
                        "Docker server information is returned "
                        "without a socket connection error."
                    ),
                },
                {
                    "platform": "Windows PowerShell",
                    "command": "docker version",
                    "purpose": (
                        "Verify that Docker Desktop is running "
                        "on Windows."
                    ),
                    "expected_result": (
                        "Both client and server versions are shown."
                    ),
                },
            ],
            remediation_steps=[
                {
                    "priority": "high",
                    "action": (
                        "Start Docker Desktop and verify that WSL "
                        "integration is enabled for the Jenkins "
                        "Ubuntu distribution."
                    ),
                    "command": "docker info",
                    "risk": "safe",
                }
            ],
        )

    health_failure = find_matching_evidence(
        log_text,
        [
            re.compile(r"\bunhealthy\b", re.IGNORECASE),
            re.compile(r"curl:\s*\(22\)", re.IGNORECASE),
            re.compile(r"\b404\b", re.IGNORECASE),
            re.compile(
                r"health\s*check.*fail",
                re.IGNORECASE,
            ),
        ],
    )

    if health_failure:
        log_file, excerpt = health_failure

        return base_fallback_result(
            stage=stage,
            component="Docker Compose service health check",
            category="docker_compose",
            summary=(
                "A Docker Compose service did not pass its "
                "configured health check."
            ),
            root_cause=(
                "The service health-check command or URL failed. "
                "Inspect the recorded container health output to "
                "identify the exact HTTP status or command error."
            ),
            log_file=log_file,
            excerpt=excerpt,
            interpretation=(
                "This line directly shows the service health "
                "failure observed by Docker Compose."
            ),
            confidence=0.90,
            checks=[
                {
                    "platform": "Docker",
                    "command": (
                        "docker inspect <container> "
                        "--format '{{json .State.Health}}'"
                    ),
                    "purpose": (
                        "Read the exact health-check commands, "
                        "exit codes, and output."
                    ),
                    "expected_result": (
                        "The failing URL or command is visible in "
                        "the latest health-check entry."
                    ),
                },
                {
                    "platform": "WSL",
                    "command": (
                        "docker compose ps --all"
                    ),
                    "purpose": (
                        "Identify which Compose service is "
                        "unhealthy."
                    ),
                    "expected_result": (
                        "The affected service is marked unhealthy."
                    ),
                },
            ],
            remediation_steps=[
                {
                    "priority": "high",
                    "action": (
                        "Correct the failing health-check URL, "
                        "port, path, or command and rerun the "
                        "integration test."
                    ),
                    "command": (
                        "docker compose config"
                    ),
                    "risk": "review_required",
                }
            ],
        )

    controlled_marker = (
        "Controlled failure triggered to validate "
        "Ollama analysis."
    )

    if (
        os.getenv("FORCE_AI_FAILURE", "false").lower()
        == "true"
        and controlled_marker in log_text
    ):
        return base_fallback_result(
            stage="Test AI Failure Analysis",
            component="AI failure-analysis controlled test",
            category="test_failure",
            summary=(
                "Jenkins intentionally generated a controlled "
                "failure to validate the Ollama analysis."
            ),
            root_cause=(
                "FORCE_AI_FAILURE was enabled and the test stage "
                "intentionally exited with code 1."
            ),
            log_file="simulated-failure.log",
            excerpt=controlled_marker,
            interpretation=(
                "This marker confirms that the failure was "
                "intentional."
            ),
            confidence=1.0,
            checks=[],
            remediation_steps=[],
        )

    generic_patterns = [
        re.compile(r"\berror\b", re.IGNORECASE),
        re.compile(r"\bfailed\b", re.IGNORECASE),
        re.compile(r"\bexception\b", re.IGNORECASE),
        re.compile(r"traceback", re.IGNORECASE),
        re.compile(r"exit\s*code\s*[1-9]", re.IGNORECASE),
        re.compile(r"connection\s*refused", re.IGNORECASE),
        re.compile(r"not\s*found", re.IGNORECASE),
    ]

    generic_failure = find_matching_evidence(
        log_text,
        generic_patterns,
    )

    if generic_failure:
        log_file, excerpt = generic_failure

        return base_fallback_result(
            stage=stage,
            component="Pipeline command",
            category="unknown",
            summary=(
                "The pipeline failed while executing the last "
                "recorded stage."
            ),
            root_cause=excerpt,
            log_file=log_file,
            excerpt=excerpt,
            interpretation=(
                "This is the first grounded high-signal failure "
                "line available in the collected logs."
            ),
            confidence=0.70,
            checks=[
                {
                    "platform": "Jenkins UI",
                    "command": (
                        "Open the failed stage console output."
                    ),
                    "purpose": (
                        "Review the lines immediately before the "
                        "reported failure."
                    ),
                    "expected_result": (
                        "The failing command and its complete "
                        "stderr output are visible."
                    ),
                }
            ],
            remediation_steps=[],
        )

    return None


def normalize_result(
    result: dict[str, Any],
    log_text: str,
) -> dict[str, Any]:
    required_fields = set(OUTPUT_SCHEMA["required"])
    missing_fields = required_fields - result.keys()

    if missing_fields:
        raise RuntimeError(
            "Ollama returned an incomplete analysis. "
            f"Missing fields: {sorted(missing_fields)}"
        )

    result["confidence"] = normalize_confidence(
        result.get("confidence", 0)
    )

    grounded_evidence: list[dict[str, str]] = []

    for evidence in result.get("evidence", []):
        if not isinstance(evidence, dict):
            continue

        excerpt = str(evidence.get("excerpt", "")).strip()

        if excerpt_is_grounded(excerpt, log_text):
            grounded_evidence.append(
                {
                    "log_file": str(
                        evidence.get("log_file", "unknown")
                    ),
                    "excerpt": excerpt,
                    "interpretation": str(
                        evidence.get(
                            "interpretation",
                            "No interpretation provided.",
                        )
                    ),
                }
            )

    result["evidence"] = grounded_evidence[:3]

    last_stage = os.getenv("LAST_STAGE", "unknown")

    if last_stage and last_stage != "unknown":
        result["failed_stage"] = last_stage

    fallback = deterministic_fallback(log_text)

    if (
        result.get("analysis_status")
        == "insufficient_evidence"
        or not result["evidence"]
    ):
        if fallback is not None:
            return fallback

        result["analysis_status"] = "insufficient_evidence"
        result["confidence"] = min(
            result["confidence"],
            0.49,
        )

        missing_information = list(
            result.get("missing_information", [])
        )

        message = (
            "No grounded high-signal error could be extracted "
            "from the supplied logs."
        )

        if message not in missing_information:
            missing_information.append(message)

        result["missing_information"] = (
            missing_information[:4]
        )

    if result["analysis_status"] == "insufficient_evidence":
        result["confidence"] = min(
            result["confidence"],
            0.49,
        )

    return result


def render_markdown(result: dict[str, Any]) -> str:
    status = result["analysis_status"]

    if status == "diagnosed":
        root_cause_heading = "## Root cause"
    elif status == "probable":
        root_cause_heading = "## Probable root cause"
    else:
        root_cause_heading = "## Unconfirmed hypothesis"

    lines = [
        "# AI Pipeline Failure Analysis",
        "",
        f"**Status:** {result['analysis_status']}",
        f"**Failed stage:** {result['failed_stage']}",
        f"**Component:** {result['failed_component']}",
        f"**Category:** {result['category']}",
        f"**Confidence:** {result['confidence']:.0%}",
        "",
        "## Summary",
        "",
        result["summary"],
        "",
        root_cause_heading,
        "",
        result["root_cause"],
        "",
        "## Evidence",
        "",
    ]

    for evidence in result["evidence"]:
        lines.extend(
            [
                f"### {evidence['log_file']}",
                "",
                "```text",
                evidence["excerpt"],
                "```",
                "",
                evidence["interpretation"],
                "",
            ]
        )

    lines.extend(["## Checks", ""])

    for check in result["checks"]:
        lines.extend(
            [
                f"### {check['platform']}",
                "",
                f"Purpose: {check['purpose']}",
                "",
                "```text",
                check["command"],
                "```",
                "",
                f"Expected: {check['expected_result']}",
                "",
            ]
        )

    lines.extend(["## Remediation", ""])

    for step in result["remediation_steps"]:
        lines.extend(
            [
                (
                    f"- **{step['priority'].upper()}** "
                    f"[{step['risk']}]: {step['action']}"
                ),
                "",
                "```text",
                step["command"],
                "```",
                "",
            ]
        )

    lines.extend(["## Prevention", ""])

    for item in result["prevention"]:
        lines.append(f"- {item}")

    if result["missing_information"]:
        lines.extend(["", "## Missing information", ""])

        for item in result["missing_information"]:
            lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()

    try:
        logs = collect_logs(Path(args.logs_dir))
        model = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)

        print(f"Ollama model: {model}", flush=True)
        print(
            f"Reduced pipeline logs: {len(logs):,} characters",
            flush=True,
        )
        raw_output_path = Path(args.output_raw)

        result = request_analysis(
            api_url=ollama_url(),
            model=model,
            user_prompt=build_user_prompt(logs),
            raw_output_path=raw_output_path,
        )

        result = normalize_result(
            result=result,
            log_text=logs,
        )

        Path(args.output_json).write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )

        markdown = render_markdown(result)

        Path(args.output_markdown).write_text(
            markdown,
            encoding="utf-8",
        )

        print(markdown)
        return 0

    except Exception as error:
        print(
            f"AI failure analysis could not run: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
