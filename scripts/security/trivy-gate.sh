#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-}"
shift || true

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(pwd -P)}"
TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:0.70.0}"
TRIVY_CACHE_VOLUME="${TRIVY_CACHE_VOLUME:-flight-delay-trivy-cache}"
TRIVY_REPORT_DIR="${TRIVY_REPORT_DIR:-security-reports}"
TRIVY_GATE_SEVERITY="${TRIVY_GATE_SEVERITY:-HIGH,CRITICAL}"
TRIVY_LICENSE_SEVERITY="${TRIVY_LICENSE_SEVERITY:-CRITICAL}"
TRIVY_PULL_RETRIES="${TRIVY_PULL_RETRIES:-3}"

REPORT_ROOT="$WORKSPACE_ROOT/$TRIVY_REPORT_DIR"
PUBLIC_DOCKER_CONFIG=""

declare -a GATE_FAILURES=()

usage() {
    cat <<'EOF'
Usage:
  trivy-gate.sh source
  trivy-gate.sh config <rendered-manifest>
  trivy-gate.sh images <image> [<image> ...]

Modes:
  source   Scan repository dependencies, secrets, IaC/configuration and licenses.
  config   Scan a rendered Kubernetes/Helm manifest.
  images   Scan locally built Docker images and generate CycloneDX/SPDX SBOMs.
EOF
}

fail() {
    echo "ERROR: $*" >&2
    exit 2
}

require_command() {
    command -v "$1" >/dev/null 2>&1 ||
        fail "Required command is unavailable: $1"
}

cleanup() {
    if [ -n "${PUBLIC_DOCKER_CONFIG:-}" ] &&
       [ -d "$PUBLIC_DOCKER_CONFIG" ]; then
        rm -rf "$PUBLIC_DOCKER_CONFIG"
    fi
}

trap cleanup EXIT

slugify() {
    printf '%s' "$1" |
        tr '[:upper:]' '[:lower:]' |
        sed -E 's#[^a-z0-9._-]+#-#g; s#^-+##; s#-+$##'
}

create_public_docker_config() {
    PUBLIC_DOCKER_CONFIG="$(
        mktemp -d \
            "${TMPDIR:-/tmp}/flightdelay-trivy-docker-config.XXXXXX"
    )"

    chmod 700 "$PUBLIC_DOCKER_CONFIG"

    cat > "$PUBLIC_DOCKER_CONFIG/config.json" <<'JSON'
{
  "auths": {}
}
JSON

    chmod 600 "$PUBLIC_DOCKER_CONFIG/config.json"
}

pull_trivy_image() {
    if docker image inspect "$TRIVY_IMAGE" >/dev/null 2>&1; then
        echo "Pinned Trivy image is already available locally: $TRIVY_IMAGE"
        return
    fi

    create_public_docker_config

    echo "Pulling pinned Trivy image: $TRIVY_IMAGE"
    echo "Using an isolated Docker config for this public image pull."
    echo "This avoids WSL/Docker Desktop credential-helper failures."

    local attempt
    for attempt in $(seq 1 "$TRIVY_PULL_RETRIES"); do
        echo "Trivy image pull attempt $attempt/$TRIVY_PULL_RETRIES"

        if DOCKER_CONFIG="$PUBLIC_DOCKER_CONFIG" \
            docker pull "$TRIVY_IMAGE"
        then
            break
        fi

        if [ "$attempt" -lt "$TRIVY_PULL_RETRIES" ]; then
            sleep "$((attempt * 3))"
        fi
    done

    if ! docker image inspect "$TRIVY_IMAGE" >/dev/null 2>&1; then
        fail \
            "Could not pull $TRIVY_IMAGE after $TRIVY_PULL_RETRIES attempts. " \
            "The isolated Docker configuration bypassed the desktop credential helper, " \
            "so inspect Docker daemon/network access next."
    fi
}

prepare() {
    require_command docker
    require_command mktemp
    require_command sed
    require_command seq
    require_command tr

    mkdir -p "$REPORT_ROOT"

    docker info >/dev/null 2>&1 ||
        fail \
            "Docker daemon is unavailable. " \
            "Trivy runs as a container in this project."

    docker volume inspect "$TRIVY_CACHE_VOLUME" >/dev/null 2>&1 ||
        docker volume create "$TRIVY_CACHE_VOLUME" >/dev/null

    pull_trivy_image

    echo "Trivy image: $TRIVY_IMAGE"
    echo "Gate severities: $TRIVY_GATE_SEVERITY"
    echo "License gate severities: $TRIVY_LICENSE_SEVERITY"
    echo "Report directory: $REPORT_ROOT"
}

trivy_workspace() {
    docker run \
        --rm \
        --pull never \
        --volume "$WORKSPACE_ROOT:/workspace:ro" \
        --volume "$TRIVY_CACHE_VOLUME:/root/.cache/" \
        --workdir /workspace \
        "$TRIVY_IMAGE" \
        "$@"
}

trivy_image() {
    docker run \
        --rm \
        --pull never \
        --volume "$WORKSPACE_ROOT:/workspace:ro" \
        --volume "$TRIVY_CACHE_VOLUME:/root/.cache/" \
        --volume /var/run/docker.sock:/var/run/docker.sock \
        --workdir /workspace \
        "$TRIVY_IMAGE" \
        "$@"
}

record_failure() {
    GATE_FAILURES+=("$1")
}

run_gate_with_reports() {
    local runner="$1"
    local label="$2"
    local target="$3"
    local include_sarif="$4"
    shift 4

    local report_base="$REPORT_ROOT/$label"
    local -a scan_args=("$@")
    local exit_code=0

    echo
    echo "===== Trivy scan: $label ====="
    echo "Target: $target"

    "$runner" "${scan_args[@]}" \
        --format json \
        --exit-code 0 \
        "$target" \
        > "${report_base}.json"

    if [ "$include_sarif" = "true" ]; then
        "$runner" "${scan_args[@]}" \
            --format sarif \
            --exit-code 0 \
            "$target" \
            > "${report_base}.sarif"
    fi

    set +e

    "$runner" "${scan_args[@]}" \
        --format table \
        --exit-code 1 \
        "$target" \
        2>&1 |
        tee "${report_base}.txt"

    exit_code="${PIPESTATUS[0]}"

    set -e

    if [ "$exit_code" -ne 0 ]; then
        record_failure "$label"
        echo "Gate result: FAILED ($label)"
    else
        echo "Gate result: PASSED ($label)"
    fi
}

generate_source_sboms() {
    echo
    echo "===== Generating repository SBOMs ====="

    trivy_workspace fs \
        --no-progress \
        --format cyclonedx \
        /workspace \
        > "$REPORT_ROOT/source-sbom.cdx.json"

    trivy_workspace fs \
        --no-progress \
        --format spdx-json \
        /workspace \
        > "$REPORT_ROOT/source-sbom.spdx.json"
}

scan_source() {
    local -a common_skip_args=(
        --no-progress
        --skip-dirs .git
        --skip-dirs node_modules
        --skip-dirs '*/node_modules'
        --skip-dirs .venv
        --skip-dirs '*/.venv'
        --skip-dirs venv
        --skip-dirs '*/venv'
        --skip-dirs "$TRIVY_REPORT_DIR"
        --skip-dirs ci-logs
        --skip-dirs '.gitops-*'
    )

    run_gate_with_reports \
        trivy_workspace \
        source-vulnerabilities \
        /workspace \
        true \
        fs \
        --scanners vuln \
        --severity "$TRIVY_GATE_SEVERITY" \
        --ignore-unfixed \
        "${common_skip_args[@]}"

    run_gate_with_reports \
        trivy_workspace \
        source-secrets \
        /workspace \
        true \
        fs \
        --scanners secret \
        --severity "$TRIVY_GATE_SEVERITY" \
        "${common_skip_args[@]}"

    run_gate_with_reports \
        trivy_workspace \
        source-misconfigurations \
        /workspace \
        true \
        fs \
        --scanners misconfig \
        --severity "$TRIVY_GATE_SEVERITY" \
        "${common_skip_args[@]}"

    run_gate_with_reports \
        trivy_workspace \
        source-licenses \
        /workspace \
        false \
        fs \
        --scanners license \
        --severity "$TRIVY_LICENSE_SEVERITY" \
        "${common_skip_args[@]}"

    generate_source_sboms
}

scan_config() {
    local manifest="${1:-}"

    [ -n "$manifest" ] ||
        fail "config mode requires the rendered manifest path"

    if [[ "$manifest" != /* ]]; then
        manifest="$WORKSPACE_ROOT/$manifest"
    fi

    [ -s "$manifest" ] ||
        fail "Rendered manifest does not exist or is empty: $manifest"

    local relative_manifest="${manifest#"$WORKSPACE_ROOT"/}"

    run_gate_with_reports \
        trivy_workspace \
        rendered-kubernetes-manifest \
        "/workspace/$relative_manifest" \
        true \
        config \
        --no-progress \
        --severity "$TRIVY_GATE_SEVERITY"
}

generate_image_sboms() {
    local image="$1"
    local image_slug="$2"

    echo
    echo "===== Generating image SBOMs: $image ====="

    trivy_image image \
        --image-src docker \
        --no-progress \
        --format cyclonedx \
        "$image" \
        > "$REPORT_ROOT/${image_slug}-sbom.cdx.json"

    trivy_image image \
        --image-src docker \
        --no-progress \
        --format spdx-json \
        "$image" \
        > "$REPORT_ROOT/${image_slug}-sbom.spdx.json"
}

scan_one_image() {
    local image="$1"
    local image_slug

    image_slug="$(slugify "$image")"

    [ -n "$image_slug" ] ||
        fail "Could not derive a report name from image: $image"

    docker image inspect "$image" >/dev/null 2>&1 ||
        fail "Local image does not exist: $image"

    run_gate_with_reports \
        trivy_image \
        "${image_slug}-vulnerabilities" \
        "$image" \
        true \
        image \
        --image-src docker \
        --scanners vuln \
        --severity "$TRIVY_GATE_SEVERITY" \
        --ignore-unfixed \
        --no-progress

    run_gate_with_reports \
        trivy_image \
        "${image_slug}-secrets-and-misconfigurations" \
        "$image" \
        true \
        image \
        --image-src docker \
        --scanners secret,misconfig \
        --severity "$TRIVY_GATE_SEVERITY" \
        --no-progress

    run_gate_with_reports \
        trivy_image \
        "${image_slug}-licenses" \
        "$image" \
        false \
        image \
        --image-src docker \
        --scanners license \
        --severity "$TRIVY_LICENSE_SEVERITY" \
        --no-progress

    generate_image_sboms "$image" "$image_slug"
}

scan_images() {
    [ "$#" -gt 0 ] ||
        fail "images mode requires at least one local image reference"

    local image
    for image in "$@"; do
        scan_one_image "$image"
    done
}

write_summary_and_exit() {
    local summary_file="$REPORT_ROOT/trivy-${MODE}-summary.txt"

    {
        echo "Trivy mode: $MODE"
        echo "Trivy image: $TRIVY_IMAGE"
        echo "Gate severities: $TRIVY_GATE_SEVERITY"
        echo "License gate severities: $TRIVY_LICENSE_SEVERITY"
        echo

        if [ "${#GATE_FAILURES[@]}" -eq 0 ]; then
            echo "Result: PASSED"
            echo "No blocking findings were detected."
        else
            echo "Result: FAILED"
            echo "Blocking scan groups:"
            printf '  - %s\n' "${GATE_FAILURES[@]}"
        fi
    } | tee "$summary_file"

    if [ "${#GATE_FAILURES[@]}" -ne 0 ]; then
        echo
        echo "ERROR: Trivy $MODE security gate failed."
        echo "Review the archived reports under $TRIVY_REPORT_DIR/."
        exit 1
    fi

    echo
    echo "Trivy $MODE security gate passed."
}

case "$MODE" in
    source)
        prepare
        scan_source
        ;;
    config)
        prepare
        scan_config "$@"
        ;;
    images)
        prepare
        scan_images "$@"
        ;;
    -h|--help|help|"")
        usage
        exit 0
        ;;
    *)
        usage >&2
        fail "Unknown mode: $MODE"
        ;;
esac

write_summary_and_exit
