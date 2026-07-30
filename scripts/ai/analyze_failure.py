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

Keep the response concise so it can run efficiently on CPU-only hardware:

- Return at most 3 secondary errors.
- Return at most 3 evidence items.
- Return at most 4 diagnostic checks.
- Return at most 4 remediation steps.
- Return at most 4 prevention items.
- Return at most 4 missing-information items.
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
        "summary": {"type": "string"},
        "failed_stage": {"type": "string"},
        "failed_component": {"type": "string"},
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
        "root_cause": {"type": "string"},
        "secondary_errors": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string"},
        },
        "evidence": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "log_file": {"type": "string"},
                    "excerpt": {"type": "string"},
                    "interpretation": {"type": "string"},
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
            "maxItems": 4,
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
                    "command": {"type": "string"},
                    "purpose": {"type": "string"},
                    "expected_result": {"type": "string"},
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
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "action": {"type": "string"},
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
            "maxItems": 4,
            "items": {"type": "string"},
        },
        "missing_information": {
            "type": "array",
            "maxItems": 4,
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


def extract_relevant_lines(lines: list[str]) -> list[str]:
    selected_indexes: set[int] = set()

    for index, line in enumerate(lines):
        if ERROR_PATTERN.search(line):
            start = max(0, index - CONTEXT_LINES)
            end = min(len(lines), index + CONTEXT_LINES + 1)

            selected_indexes.update(range(start, end))

    tail_start = max(0, len(lines) - TAIL_LINES)
    selected_indexes.update(range(tail_start, len(lines)))

    return [
        lines[index]
        for index in sorted(selected_indexes)
    ]


def collect_logs(logs_directory: Path) -> str:
    if not logs_directory.exists():
        raise FileNotFoundError(
            f"Log directory does not exist: {logs_directory}"
        )

    sections: list[str] = []

    for log_file in sorted(logs_directory.rglob("*.log")):
        raw_text = log_file.read_text(
            encoding="utf-8",
            errors="replace",
        )

        relevant = extract_relevant_lines(raw_text.splitlines())

        if not relevant:
            continue

        section = (
            f"\n===== LOG FILE: {log_file} =====\n"
            + "\n".join(relevant)
        )

        sections.append(section)

    combined = sanitize("\n".join(sections))

    if not combined.strip():
        raise RuntimeError("No useful pipeline logs were found.")

    return combined[-MAX_LOG_CHARACTERS:]


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
    }

    return f"""
Analyze the Jenkins pipeline failure below.

Pipeline metadata:

{json.dumps(metadata, indent=2)}

Instructions:

- Find the earliest meaningful root cause.
- Do not treat repeated retries as separate root causes.
- Use exact log excerpts as evidence.
- Provide commands that match this Windows + WSL environment.
- Do not output secrets.
- If the root cause cannot be proved, use
  analysis_status="insufficient_evidence".

Sanitized and reduced pipeline logs:

{log_text}
"""


def request_analysis(
    api_url: str,
    model: str,
    user_prompt: str,
) -> dict[str, Any]:
    request_body = {
        "model": model,
        "stream": False,
        "keep_alive": "30m",
        "format": OUTPUT_SCHEMA,
        "options": {
            "temperature": 0,
            "num_ctx": 4096,
            "num_predict": 600,
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

    content = payload.get("message", {}).get("content")

    if not content:
        raise RuntimeError(
            "Ollama returned no message content."
        )

    return json.loads(content)


def render_markdown(result: dict[str, Any]) -> str:
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
        "## Probable root cause",
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
        result = request_analysis(
            api_url=ollama_url(),
            model=model,
            user_prompt=build_user_prompt(logs),
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
