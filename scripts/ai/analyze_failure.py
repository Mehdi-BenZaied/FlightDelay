#!/usr/bin/env python3
"""Analyze current-build logs from a Jenkins Scripted Pipeline with Ollama.

The analyzer combines a constrained Ollama response with deterministic,
evidence-grounded signatures for high-risk failures such as Docker daemon
outages, Docker Compose health failures, Kubernetes probes, Helm failures,
and Helm/Argo CD managed-field conflicts.
"""

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
    "helm-deploy.log",
    "failure-summary.log",
    "pipeline-context.log",
    "docker-compose-health.log",
    "docker-daemon-check.log",
}

LOG_PRIORITY = {
    "helm-deploy.log": 0,
    "failure-summary.log": 1,
    "pipeline-context.log": 2,
    "docker-daemon-check.log": 3,
    "docker-compose-health.log": 3,
    "jenkins-console.log": 4,
    "simulated-failure.log": 4,
    "docker-compose-failure.log": 5,
    "docker-compose-integration.log": 6,
    "build-backend.log": 7,
    "build-frontend.log": 7,
    "validate-compose.log": 8,
    "kubernetes-failure.log": 9,
    "final-compose-state.log": 20,
}

DOCKER_COMPOSE_LOG_NAMES = {
    "docker-compose-health.log",
    "docker-compose-failure.log",
    "docker-compose-integration.log",
    "final-compose-state.log",
    "validate-compose.log",
}

KUBERNETES_LOG_NAMES = {
    "helm-deploy.log",
    "kubernetes-failure.log",
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
    |upgrade\s+failed
    |rollback.*failed
    |conflict\s+occurred\s+while\s+applying\s+object
    |apply\s+failed\s+with\s+\d+\s+conflict
    |conflict\s+with\s+["']?argocd-controller
    |field\s+manager
    |managedfields
    |readiness\s+probe\s+failed
    |liveness\s+probe\s+failed
    """,
    re.IGNORECASE | re.VERBOSE,
)


SYSTEM_PROMPT = """
You are a senior DevOps/SRE assistant analyzing failures from a Jenkins Scripted Pipeline.

Important Jenkins context:

- This is a Scripted Pipeline, not a Declarative Pipeline.
- Stage names are optional labels created by the Groovy script.
- Do not discuss Declarative Pipeline directives or concepts such as
  post, when, steps, stages directives, agents directives, or declarative
  lifecycle behavior.
- Describe the failure in terms of the command, scripted section, tool,
  service, or deployment operation that actually failed.

Environment:

- Jenkins controller runs on Windows.
- The Jenkins build agent runs inside Ubuntu WSL.
- Docker Desktop on Windows provides the Docker Engine to WSL.
- The Jenkins node label is linux-docker-agent.
- The application is FlightDelay.
- Frontend: Nginx on container port 80.
- Backend: Python API started by run.py on port 5000.
- Analytics: Python service started by analytics.py on port 8050.
- Redis runs on port 6379.
- Ollama runs locally and normally uses qwen2.5-coder:3b-instruct.
- Images may be built and published to Docker Hub.
- Kubernetes deployment uses kind, Helm, and may also be managed by Argo CD.

Your job:

1. Find the first meaningful error from the current Jenkins build.
2. Identify the direct cause, not an older event or a later cascading error.
3. Explain the cause in simple technical language.
4. Identify the affected command, tool, service, or deployment operation.
5. Use exact evidence copied from the supplied logs.
6. Suggest practical and safe next steps.
7. Keep the answer concise and human-friendly.
8. Do not invent evidence, filenames, service states, or command results.
9. Do not expose passwords, tokens, credentials, cookies, or authorization
   headers.
10. Do not recommend broad destructive cleanup commands.
11. Do not suggest increasing a timeout when the logs already show a concrete
    configuration, ownership, network, image, test, or application error.
12. If the evidence is incomplete, say exactly what additional log is needed.

Evidence rules:

- Prefer the stderr/stdout of the command that returned the non-zero exit code.
- Prefer helm-deploy.log for Helm deployment failures.
- Prefer docker-compose-health.log for Docker Compose health failures.
- Prefer docker-daemon-check.log for Docker daemon connection failures.
- Prefer build-specific logs over historical Kubernetes events.
- A Kubernetes readiness or liveness probe failure is not a Docker Compose
  health-check failure.
- A line containing "conflict occurred while applying object" and
  "argocd-controller" is a Kubernetes managed-field ownership conflict.
- Helm/Argo CD ownership conflicts must be classified as kubernetes, not
  docker_compose.
- Treat rollback failures as secondary when the original Helm upgrade error is
  available.
- Ignore errors generated later by AI analysis, dashboard publication, or
  cleanup unless they are the only failure in the build.
- Use last_stage only when it is meaningful. The value
  "Pipeline initialization" is a default placeholder and must not override
  direct log evidence.
- Every evidence excerpt must exist verbatim in the supplied logs.
- Confidence must be between 0 and 1.
- insufficient_evidence requires confidence below 0.5.
- When FORCE_AI_FAILURE is true and the controlled-failure marker exists,
  classify it as an intentional test failure.

Output limits for CPU-only execution:

- At most 2 secondary errors.
- At most 2 evidence items.
- At most 2 diagnostic checks.
- At most 2 remediation steps.
- At most 2 prevention items.
- At most 2 missing-information items.
- Avoid repeating the same error in multiple fields.

Return only JSON matching the supplied schema.
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


def high_signal_score(line: str) -> int:
    normalized = line.lower()
    score = 10

    strong_patterns = [
        (
            140,
            r"conflict occurred while applying object|"
            r"conflict with [\"']?argocd-controller|"
            r"apply failed with \d+ conflict",
        ),
        (130, r"\bupgrade failed\b|\brollback.*failed\b"),
        (
            120,
            r"cannot connect to the docker daemon|"
            r"failed to connect to the docker api|"
            r"docker\.sock.*no such file",
        ),
        (
            110,
            r"failed to solve|manifest unknown|"
            r"pull access denied|imagepullbackoff|errimagepull",
        ),
        (100, r"traceback|exception|syntaxerror|modulenotfounderror"),
        (90, r"exit code [1-9]|forbidden|unauthorized|denied"),
        (70, r"connection refused|timeout|timed out"),
        (45, r"readiness probe failed|liveness probe failed"),
        (40, r"\bunhealthy\b|health.?check|curl:.*\(22\)|\b404\b"),
    ]

    for candidate_score, pattern in strong_patterns:
        if re.search(pattern, normalized, re.IGNORECASE):
            score = max(score, candidate_score)

    # Kubernetes events such as "2d18h Warning Unhealthy" can describe an
    # older failure. Keep them as context, but do not rank them above the
    # current command error.
    if re.search(r"\b\d+d(?:\d+h)?\b", normalized):
        score -= 35

    if "normal" in normalized and "successful" in normalized:
        score -= 30

    return score


def high_signal_summary(log_text: str) -> str:
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    for index, line in enumerate(log_text.splitlines()):
        stripped = line.strip()

        if not stripped or stripped.startswith("===== LOG FILE:"):
            continue

        if ERROR_PATTERN.search(stripped) and stripped not in seen:
            seen.add(stripped)
            candidates.append(
                (high_signal_score(stripped), index, stripped)
            )

    if not candidates:
        return "No high-signal error line was extracted."

    candidates.sort(key=lambda item: (-item[0], item[1]))

    return "\n".join(
        f"- {line}"
        for _, _, line in candidates[:30]
    )

def build_user_prompt(log_text: str) -> str:
    metadata = {
        "job_name": os.getenv("JOB_NAME", "unknown"),
        "build_number": os.getenv("BUILD_NUMBER", "unknown"),
        "build_url": os.getenv("BUILD_URL", "unknown"),
        "branch": os.getenv(
            "SOURCE_BRANCH",
            os.getenv("BRANCH_NAME", "unknown"),
        ),
        "commit": os.getenv(
            "SHORT_SHA",
            os.getenv("GIT_COMMIT", "unknown"),
        ),
        "node": os.getenv("NODE_NAME", "unknown"),
        "last_stage": os.getenv("LAST_STAGE", "unknown"),
        "build_result": os.getenv("BUILD_RESULT", "FAILURE"),
        "force_ai_failure": os.getenv(
            "FORCE_AI_FAILURE",
            "false",
        ).lower(),
        "pipeline_style": "scripted",
    }

    return f"""
Analyze the current Jenkins Scripted Pipeline failure.

Build metadata:

{json.dumps(metadata, indent=2)}

Required behavior:

- Diagnose the command or scripted section that actually returned the failure.
- Do not reference Jenkins Declarative Pipeline syntax or lifecycle concepts.
- Prefer the earliest direct command error from the current build.
- Treat retries, rollback errors, old Kubernetes events, publication errors,
  and cleanup errors as secondary unless no earlier error exists.
- Use only exact log excerpts.
- Keep the explanation direct and understandable.
- Return confidence from 0 to 1.
- Use insufficient_evidence when the logs do not prove a cause.

Highest-priority extracted lines:

{high_signal_summary(log_text)}

Sanitized current-build logs:

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


def original_log_file_from_grep(excerpt: str) -> str | None:
    match = re.search(
        r"(?:^|[\\/])(?P<name>[^\\/:\s]+\.log):\d+:",
        excerpt,
    )

    if match:
        return match.group("name")

    match = re.match(
        r"(?P<name>[^:\s]+\.log):\d+:",
        excerpt,
    )

    return match.group("name") if match else None


def resolved_log_file(
    lines: list[str],
    index: int,
    excerpt: str,
) -> str:
    return (
        original_log_file_from_grep(excerpt)
        or current_log_file(lines, index)
    )


def is_kubernetes_evidence(
    log_file: str,
    excerpt: str,
) -> bool:
    normalized = excerpt.lower()

    return (
        log_file in KUBERNETES_LOG_NAMES
        or "kubernetes-failure.log:" in normalized
        or "helm-deploy.log:" in normalized
        or "pod/" in normalized
        or "deployment/" in normalized
        or "readiness probe" in normalized
        or "liveness probe" in normalized
        or "kubectl " in normalized
        or "helm upgrade" in normalized
        or "upgrade failed" in normalized
        or "argocd-controller" in normalized
    )


def is_docker_compose_evidence(
    log_file: str,
    excerpt: str,
) -> bool:
    normalized = excerpt.lower()

    if is_kubernetes_evidence(log_file, excerpt):
        return False

    return (
        log_file in DOCKER_COMPOSE_LOG_NAMES
        or "docker-compose-" in normalized
        or "docker compose" in normalized
        or ".state.health" in normalized
        or "container" in normalized
    )


def find_matching_evidence(
    log_text: str,
    patterns: list[re.Pattern[str]],
    predicate: Any | None = None,
) -> tuple[str, str] | None:
    lines = log_text.splitlines()

    for index, line in enumerate(lines):
        stripped = line.strip()

        if not stripped:
            continue

        if not any(pattern.search(stripped) for pattern in patterns):
            continue

        log_file = resolved_log_file(lines, index, stripped)

        if predicate is not None and not predicate(log_file, stripped):
            continue

        return log_file, stripped

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
        "checks": checks[:2],
        "remediation_steps": remediation_steps[:2],
        "prevention": [],
        "missing_information": [],
        "confidence": confidence,
    }


def deterministic_fallback(
    log_text: str,
) -> dict[str, Any] | None:
    recorded_stage = os.getenv("LAST_STAGE", "unknown")
    stage = (
        recorded_stage
        if recorded_stage not in {"unknown", "Pipeline initialization"}
        else "unknown"
    )

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

    helm_conflict = find_matching_evidence(
        log_text,
        [
            re.compile(
                r"conflict occurred while applying object",
                re.IGNORECASE,
            ),
            re.compile(
                r"apply failed with \d+ conflict",
                re.IGNORECASE,
            ),
            re.compile(
                r"conflict with [\"']?argocd-controller",
                re.IGNORECASE,
            ),
        ],
    )

    if helm_conflict:
        log_file, excerpt = helm_conflict

        return base_fallback_result(
            stage="Deploy with Helm",
            component="Helm / Argo CD field ownership",
            category="kubernetes",
            summary=(
                "The Helm upgrade failed because Argo CD already "
                "owns the Deployment image fields."
            ),
            root_cause=(
                "Helm and argocd-controller attempted to manage "
                "the same container image fields through "
                "server-side apply. Kubernetes rejected the "
                "change as a managed-field conflict."
            ),
            log_file=log_file,
            excerpt=excerpt,
            interpretation=(
                "The deployment command directly reports an "
                "apply conflict with argocd-controller."
            ),
            confidence=0.99,
            checks=[
                {
                    "platform": "Kubernetes",
                    "command": (
                        "kubectl -n flight-delay-helm get deployment "
                        "flight-delay-dev-backend "
                        "--show-managed-fields -o yaml"
                    ),
                    "purpose": (
                        "Confirm which field managers own the "
                        "backend image field."
                    ),
                    "expected_result": (
                        "managedFields shows argocd-controller "
                        "owning the container image path."
                    ),
                },
                {
                    "platform": "Kubernetes",
                    "command": (
                        "kubectl -n flight-delay-helm get deployment "
                        "flight-delay-dev-frontend "
                        "-o jsonpath='{.spec.template.spec.containers[*].image}'"
                    ),
                    "purpose": (
                        "Check which image is currently reconciled "
                        "in the cluster."
                    ),
                    "expected_result": (
                        "The image reflects the GitOps source "
                        "currently applied by Argo CD."
                    ),
                },
            ],
            remediation_steps=[
                {
                    "priority": "high",
                    "action": (
                        "Use one deployment owner. Since Argo CD "
                        "manages these Deployments, update image "
                        "tags in the GitOps repository and let "
                        "Argo CD synchronize them instead of "
                        "running a competing Helm upgrade."
                    ),
                    "command": (
                        "git diff -- deploy/helm/flight-delay/values-dev.yaml"
                    ),
                    "risk": "review_required",
                },
                {
                    "priority": "medium",
                    "action": (
                        "Remove the direct Helm deployment step "
                        "for Argo CD-managed resources, or disable "
                        "Argo CD management before intentionally "
                        "returning ownership to Helm."
                    ),
                    "command": "",
                    "risk": "review_required",
                },
            ],
        )

    helm_upgrade_failure = find_matching_evidence(
        log_text,
        [
            re.compile(r"\bupgrade failed\b", re.IGNORECASE),
            re.compile(r"\brollback.*failed\b", re.IGNORECASE),
        ],
    )

    if helm_upgrade_failure:
        log_file, excerpt = helm_upgrade_failure

        return base_fallback_result(
            stage="Deploy with Helm",
            component="Helm deployment",
            category="kubernetes",
            summary="The Helm deployment command failed.",
            root_cause=excerpt,
            log_file=log_file,
            excerpt=excerpt,
            interpretation=(
                "This is the direct Helm upgrade or rollback "
                "failure from the deployment command."
            ),
            confidence=0.94,
            checks=[
                {
                    "platform": "Kubernetes",
                    "command": (
                        "helm status flight-delay-dev "
                        "-n flight-delay-helm"
                    ),
                    "purpose": (
                        "Inspect the release state after the "
                        "failed upgrade."
                    ),
                    "expected_result": (
                        "The release status and latest failed "
                        "revision are displayed."
                    ),
                }
            ],
            remediation_steps=[],
        )

    kubernetes_probe_failure = find_matching_evidence(
        log_text,
        [
            re.compile(
                r"readiness\s+probe\s+failed",
                re.IGNORECASE,
            ),
            re.compile(
                r"liveness\s+probe\s+failed",
                re.IGNORECASE,
            ),
        ],
        predicate=is_kubernetes_evidence,
    )

    if kubernetes_probe_failure:
        log_file, excerpt = kubernetes_probe_failure

        return base_fallback_result(
            stage=(
                stage
                if stage != "unknown"
                else "Verify Kubernetes Deployment"
            ),
            component="Kubernetes Pod probe",
            category="kubernetes",
            summary=(
                "A Kubernetes Pod failed its configured probe."
            ),
            root_cause=excerpt,
            log_file=log_file,
            excerpt=excerpt,
            interpretation=(
                "This is a Kubernetes readiness or liveness "
                "probe failure, not a Docker Compose health check."
            ),
            confidence=0.86,
            checks=[
                {
                    "platform": "Kubernetes",
                    "command": (
                        "kubectl -n flight-delay-helm describe pod "
                        "<pod-name>"
                    ),
                    "purpose": (
                        "Inspect the failing probe configuration "
                        "and recent events."
                    ),
                    "expected_result": (
                        "The probe path, port, and latest failure "
                        "message are visible."
                    ),
                }
            ],
            remediation_steps=[],
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
        predicate=is_docker_compose_evidence,
    )

    if health_failure:
        log_file, excerpt = health_failure

        return base_fallback_result(
            stage=(
                stage
                if stage != "unknown"
                else "Docker Compose Integration Tests"
            ),
            component="Docker Compose service health check",
            category="docker_compose",
            summary=(
                "A Docker Compose service did not pass its "
                "configured health check."
            ),
            root_cause=(
                "The Compose health-check command or URL failed. "
                "Inspect the recorded container health output to "
                "identify the exact HTTP status or command error."
            ),
            log_file=log_file,
            excerpt=excerpt,
            interpretation=(
                "This line comes from Docker Compose container "
                "health diagnostics."
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
                    "command": "docker compose ps --all",
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
                        "Correct the failing Compose health-check "
                        "URL, port, path, or command and rerun the "
                        "integration test."
                    ),
                    "command": "docker compose config",
                    "risk": "review_required",
                }
            ],
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

    result["evidence"] = grounded_evidence[:2]

    last_stage = os.getenv("LAST_STAGE", "unknown")

    # "Pipeline initialization" is only the environment default. It must not
    # overwrite a stage inferred from a direct Helm/Kubernetes error.
    if last_stage not in {"", "unknown", "Pipeline initialization"}:
        result["failed_stage"] = last_stage

    fallback = deterministic_fallback(log_text)

    # Exact signatures are more reliable than a small model's generic
    # classification. In particular, never convert a Helm/Argo CD conflict or
    # a Kubernetes probe into a Docker Compose health-check diagnosis.
    if fallback is not None:
        fallback_component = fallback.get("failed_component", "")
        authoritative_components = {
            "Docker daemon",
            "Helm / Argo CD field ownership",
            "Helm deployment",
            "AI failure-analysis controlled test",
        }

        if fallback_component in authoritative_components:
            return fallback

        if (
            fallback.get("category") == "kubernetes"
            and result.get("category") == "docker_compose"
        ):
            return fallback

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
            missing_information[:2]
        )

    if result["analysis_status"] == "insufficient_evidence":
        result["confidence"] = min(
            result["confidence"],
            0.49,
        )

    return result

def render_markdown(result: dict[str, Any]) -> str:
    status_labels = {
        "diagnosed": "Diagnosed",
        "probable": "Probable",
        "insufficient_evidence": "Insufficient evidence",
    }

    lines = [
        "# Jenkins Failure Analysis",
        "",
        f"**Status:** {status_labels.get(result['analysis_status'], result['analysis_status'])}",
        f"**Pipeline location:** {result['failed_stage']}",
        f"**Affected component:** {result['failed_component']}",
        f"**Category:** {result['category']}",
        f"**Confidence:** {result['confidence']:.0%}",
        "",
        "## What failed",
        "",
        result["summary"],
        "",
        "## Why it failed",
        "",
        result["root_cause"],
    ]

    if result["evidence"]:
        lines.extend(["", "## Evidence", ""])

        for evidence in result["evidence"]:
            lines.extend(
                [
                    f"**{evidence['log_file']}**",
                    "",
                    "```text",
                    evidence["excerpt"],
                    "```",
                    "",
                    evidence["interpretation"],
                    "",
                ]
            )

    if result["secondary_errors"]:
        lines.extend(["## Secondary effects", ""])
        lines.extend(
            f"- {item}"
            for item in result["secondary_errors"]
        )
        lines.append("")

    if result["remediation_steps"]:
        lines.extend(["## Recommended next steps", ""])

        for index, step in enumerate(
            result["remediation_steps"],
            start=1,
        ):
            lines.append(
                f"{index}. {step['action']} "
                f"(**{step['priority']}**, {step['risk']})"
            )

            command = str(step.get("command", "")).strip()
            if command:
                lines.extend(
                    [
                        "",
                        "   Verification command:",
                        "",
                        "   ```text",
                        *[f"   {line}" for line in command.splitlines()],
                        "   ```",
                    ]
                )

        lines.append("")

    if result["checks"]:
        lines.extend(["## Useful checks", ""])

        for check in result["checks"]:
            lines.extend(
                [
                    f"- **{check['platform']} — {check['purpose']}**",
                    f"  Expected: {check['expected_result']}",
                ]
            )

            command = str(check.get("command", "")).strip()
            if command:
                lines.extend(
                    [
                        "",
                        "  ```text",
                        *[f"  {line}" for line in command.splitlines()],
                        "  ```",
                    ]
                )

        lines.append("")

    if result["prevention"]:
        lines.extend(["## Prevention", ""])
        lines.extend(f"- {item}" for item in result["prevention"])
        lines.append("")

    if result["missing_information"]:
        lines.extend(["## Missing information", ""])
        lines.extend(
            f"- {item}"
            for item in result["missing_information"]
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


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
