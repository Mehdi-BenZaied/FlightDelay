pipeline {
    agent {
        label 'linux-docker-agent'
    }

    parameters {
        booleanParam(
            name: 'PUBLISH_IMAGES',
            defaultValue: false,
            description: 'Push validated images to Docker Hub'
        )

        booleanParam(
            name: 'DEPLOY_KUBERNETES',
            defaultValue: false,
            description: 'Deploy FlightDelay to kind with Helm'
        )

        booleanParam(
            name: 'AI_FAILURE_ANALYSIS',
            defaultValue: true,
            description: 'Analyze failed pipeline logs with local Ollama'
        )

        booleanParam(
            name: 'FORCE_AI_FAILURE',
            defaultValue: false,
            description: 'Force a controlled failure to test the Ollama analysis'
        )

        string(
            name: 'OLLAMA_MODEL',
            defaultValue: 'qwen2.5-coder:3b-instruct',
            description: 'Ollama model used by the backend and integration tests'
        )

        string(
            name: 'OLLAMA_REQUEST_TIMEOUT_SECONDS',
            defaultValue: '2500',
            description: 'Maximum time to wait for the Ollama analysis response'
        )

        string(
            name: 'OLLAMA_EXTERNAL_URL',
            defaultValue: '',
            description: 'Optional external Ollama /api/chat URL used when Docker is unavailable'
        )
    }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 120, unit: 'MINUTES')
        buildDiscarder(
            logRotator(
                numToKeepStr: '15',
                artifactNumToKeepStr: '10'
            )
        )
    }

    environment {
        FRONTEND_IMAGE = 'mehdibenzaied/flight-delay-frontend'
        BACKEND_IMAGE  = 'mehdibenzaied/flight-delay-backend'

        OLLAMA_IMAGE         = 'ollama/ollama:latest'
        OLLAMA_BASE_URL      = 'http://ollama:11434'
        OLLAMA_MODEL         = 'qwen2.5-coder:3b-instruct'
        OLLAMA_MODELS_VOLUME = 'flight-delay-ollama-models'
        AI_OLLAMA_HOST_PORT   = '11435'

        AI_FALLBACK_ANALYZER_IMAGE = 'python:3.12-alpine'
        AI_SCRIPT         = 'scripts/ai/analyze_failure.py'
        AI_PUBLISH_SCRIPT = 'scripts/ai/publish_analysis.py'
        AI_OUTPUT_JSON    = 'ai-failure-analysis.json'
        AI_OUTPUT_MD      = 'ai-failure-analysis.md'
        AI_OUTPUT_RAW     = 'ai-raw-response.txt'

        AI_DASHBOARD_COMPOSE_FILE = 'ai-dashboard/docker-compose.dashboard.yml'
        AI_DASHBOARD_ENV_FILE     = 'ai-dashboard/.env'
        AI_DASHBOARD_PROJECT      = 'flight-delay-ai-dashboard'
        AI_DASHBOARD_SERVICE      = 'flightdelay-ai-dashboard'
        AI_DASHBOARD_URL          = 'http://localhost:4173'
        AI_DASHBOARD_PORT         = '4173'

        CI_LOGS_DIR = 'ci-logs'

        REGISTRY_CREDENTIALS   = 'DockerHub'
        KUBECONFIG_CREDENTIALS = 'kind-flight-delay-kubeconfig'

        // GitOps repository updated by Jenkins after publishing main images.
        GITOPS_REPO        = 'https://github.com/Mehdi-BenZaied/flight-delay-gitops.git'
        GITOPS_BRANCH      = 'main'
        GITOPS_VALUES      = 'environments/dev/values.yaml'
        GITOPS_CREDENTIALS = 'github-gitops'

        COMPOSE_FILE = 'docker-compose.yml'

        HELM_CHART   = 'deploy/helm/flight-delay'
        HELM_VALUES  = 'deploy/helm/flight-delay/values-dev.yaml'
        HELM_RELEASE = 'flight-delay-dev'

        KUBE_CONTEXT  = 'kind-flight-delay'
        K8S_NAMESPACE = 'flight-delay-helm'

        K8S_FRONTEND_URL  = 'http://localhost:8081'
        K8S_ANALYTICS_URL = 'http://localhost:8051'

        DOCKER_BUILDKIT = '1'
        LAST_STAGE = 'Pipeline initialization'
    }

    stages {
        stage('Checkout and Metadata') {
            steps {
                script { env.LAST_STAGE = 'Checkout and Metadata' }
                checkout scm

                script {
                    env.SHORT_SHA = sh(
                        script: 'git rev-parse --short=8 HEAD',
                        returnStdout: true
                    ).trim()

                    def detectedBranch = sh(
                        script: 'git branch --show-current || true',
                        returnStdout: true
                    ).trim()

                    def rawBranch =
                        env.BRANCH_NAME ?:
                        env.GIT_BRANCH ?:
                        detectedBranch ?:
                        'main'

                    rawBranch = rawBranch
                        .replaceFirst(/^\*\//, '')
                        .replaceFirst(/^origin\//, '')
                        .replaceFirst(/^refs\/heads\//, '')

                    if (!rawBranch || rawBranch == 'HEAD') {
                        rawBranch = 'main'
                    }

                    env.SOURCE_BRANCH = rawBranch
                    env.SAFE_BRANCH = rawBranch
                        .toLowerCase()
                        .replaceAll('[^a-z0-9_.-]', '-')

                    env.IMAGE_TAG =
                        "${env.SAFE_BRANCH}-${env.SHORT_SHA}-${env.BUILD_NUMBER}"

                    env.FRONTEND_REF =
                        "${env.FRONTEND_IMAGE}:${env.IMAGE_TAG}"

                    env.BACKEND_REF =
                        "${env.BACKEND_IMAGE}:${env.IMAGE_TAG}"

                    env.CI_PROJECT =
                        "flight-delay-ci-${env.BUILD_NUMBER}"

                    currentBuild.displayName =
                        "#${env.BUILD_NUMBER} ${env.IMAGE_TAG}"
                }

                echo "Branch: ${env.SOURCE_BRANCH}"
                echo "Commit: ${env.SHORT_SHA}"
                echo "Image tag: ${env.IMAGE_TAG}"
                echo "Helm release: ${env.HELM_RELEASE}"
                echo "Namespace: ${env.K8S_NAMESPACE}"
                echo "Kube context: ${env.KUBE_CONTEXT}"
            }
        }

        stage('Validate Parameters') {
            steps {
                script { env.LAST_STAGE = 'Validate Parameters' }
                script {
                    if (!params.OLLAMA_MODEL?.trim()) {
                        error('OLLAMA_MODEL cannot be empty.')
                    }

                    env.OLLAMA_MODEL = params.OLLAMA_MODEL.trim()

                    def ollamaTimeout =
                        params.OLLAMA_REQUEST_TIMEOUT_SECONDS?.trim()

                    if (!(ollamaTimeout ==~ /^\d+$/)) {
                        error(
                            'OLLAMA_REQUEST_TIMEOUT_SECONDS must be a positive integer.'
                        )
                    }

                    def ollamaTimeoutValue = ollamaTimeout.toInteger()

                    if (
                        ollamaTimeoutValue < 300 ||
                        ollamaTimeoutValue > 7200
                    ) {
                        error(
                            'OLLAMA_REQUEST_TIMEOUT_SECONDS must be between 300 and 7200.'
                        )
                    }

                    env.OLLAMA_REQUEST_TIMEOUT_SECONDS = ollamaTimeout

                    if (params.DEPLOY_KUBERNETES && !params.PUBLISH_IMAGES) {
                        error(
                            'DEPLOY_KUBERNETES requires PUBLISH_IMAGES=true.'
                        )
                    }

                    if (
                        params.DEPLOY_KUBERNETES &&
                        env.SOURCE_BRANCH != 'main'
                    ) {
                        error(
                            'Kubernetes deployment is allowed only from main.'
                        )
                    }

                    echo "Ollama image: ${env.OLLAMA_IMAGE}"
                    echo "Ollama model: ${env.OLLAMA_MODEL}"
                    echo "Ollama URL in Compose: ${env.OLLAMA_BASE_URL}"
                    echo "Ollama analysis timeout: ${env.OLLAMA_REQUEST_TIMEOUT_SECONDS} seconds"
                }
            }
        }

        stage('Validate Agent and Project') {
            steps {
                script { env.LAST_STAGE = 'Validate Agent and Project' }
                sh '''#!/usr/bin/env bash
                    set -Eeuo pipefail

                    WORKSPACE_ROOT="$(pwd -P)"
                    AI_SCRIPT_HOST="$WORKSPACE_ROOT/$AI_SCRIPT"

                    echo '===== Jenkins checkout information ====='
                    echo "WORKSPACE=${WORKSPACE:-unknown}"
                    echo "Current directory=$WORKSPACE_ROOT"
                    echo "Checked-out commit=$(git rev-parse HEAD)"
                    echo "Checked-out branch=$(git branch --show-current || true)"
                    git log -1 --oneline

                    echo '===== Required commands ====='
                    command -v git
                    command -v docker
                    docker compose version
                    command -v curl
                    command -v kubectl
                    command -v helm
                    command -v python3
                    command -v timeout

                    echo '===== AI analyzer verification ====='
                    echo "Expected relative path: $AI_SCRIPT"
                    echo "Expected absolute path: $AI_SCRIPT_HOST"

                    if ! git cat-file -e "HEAD:$AI_SCRIPT" 2>/dev/null; then
                        echo "ERROR: $AI_SCRIPT is not present in the checked-out Git commit."
                        echo 'Files tracked under scripts/ai/:'
                        git ls-tree -r --name-only HEAD |
                          grep '^scripts/ai/' || true
                        exit 1
                    fi

                    echo 'The AI analyzer is present in the checked-out Git commit.'

                    if [ ! -f "$AI_SCRIPT_HOST" ]; then
                        echo 'ERROR: AI analyzer is missing from the Jenkins workspace.'
                        echo 'Files found under scripts/:'
                        find "$WORKSPACE_ROOT/scripts" \
                          -maxdepth 4 \
                          -type f \
                          -print 2>/dev/null |
                          sort || true
                        exit 1
                    fi

                    python3 -m py_compile "$AI_SCRIPT_HOST"

                    PUBLISH_SCRIPT_HOST="$WORKSPACE_ROOT/$AI_PUBLISH_SCRIPT"

                    if [ ! -f "$PUBLISH_SCRIPT_HOST" ]; then
                        echo "ERROR: dashboard publisher is missing: $PUBLISH_SCRIPT_HOST"
                        exit 1
                    fi

                    python3 -m py_compile "$PUBLISH_SCRIPT_HOST"

                    echo '===== Project files ====='
                    test -f "$WORKSPACE_ROOT/Jenkinsfile"
                    test -f "$WORKSPACE_ROOT/$COMPOSE_FILE"

                    test -f "$WORKSPACE_ROOT/$AI_DASHBOARD_COMPOSE_FILE"
                    test -f "$WORKSPACE_ROOT/ai-dashboard/Dockerfile"
                    test -f "$WORKSPACE_ROOT/ai-dashboard/package.json"
                    test -f "$WORKSPACE_ROOT/ai-dashboard/package-lock.json"

                    test -f "$WORKSPACE_ROOT/backend/Dockerfile"
                    test -f "$WORKSPACE_ROOT/backend/requirements.txt"
                    test -f "$WORKSPACE_ROOT/backend/run.py"
                    test -f "$WORKSPACE_ROOT/backend/analytics.py"
                    test -f "$WORKSPACE_ROOT/backend/app/core/config.py"

                    test -f "$WORKSPACE_ROOT/frontend/Dockerfile"
                    test -f "$WORKSPACE_ROOT/frontend/nginx.conf"
                    test -f "$WORKSPACE_ROOT/frontend/package.json"
                    test -f "$WORKSPACE_ROOT/frontend/package-lock.json"

                    test -f "$WORKSPACE_ROOT/ml/models/v1_model.json"
                    test -f "$WORKSPACE_ROOT/data/flight_data.csv"

                    test -f "$WORKSPACE_ROOT/$HELM_CHART/Chart.yaml"
                    test -f "$WORKSPACE_ROOT/$HELM_CHART/values.yaml"
                    test -f "$WORKSPACE_ROOT/$HELM_VALUES"
                    test -d "$WORKSPACE_ROOT/$HELM_CHART/templates"

                    echo 'AI script found and Python syntax is valid.'
                    echo 'Agent and project validation succeeded.'
                '''
            }
        }

        stage('Start AI Dashboard') {
            steps {
                script { env.LAST_STAGE = 'Start AI Dashboard' }

                sh '''#!/usr/bin/env bash
                    set -Eeuo pipefail

                    WORKSPACE_ROOT="$(pwd -P)"
                    DASHBOARD_COMPOSE="$WORKSPACE_ROOT/$AI_DASHBOARD_COMPOSE_FILE"
                    DASHBOARD_ENV="$WORKSPACE_ROOT/$AI_DASHBOARD_ENV_FILE"

                    mkdir -p "$CI_LOGS_DIR"
                    mkdir -p "$(dirname "$DASHBOARD_ENV")"

                    umask 077
                    {
                        printf 'DASHBOARD_PORT=%s\n' "$AI_DASHBOARD_PORT"
                        printf 'DASHBOARD_INGEST_TOKEN=%s\n' "${AI_DASHBOARD_TOKEN:-}"
                    } > "$DASHBOARD_ENV"

                    export DASHBOARD_PORT="$AI_DASHBOARD_PORT"
                    export DASHBOARD_INGEST_TOKEN="${AI_DASHBOARD_TOKEN:-}"

                    echo '===== Starting the persistent AI dashboard ====='
                    echo "Compose file: $DASHBOARD_COMPOSE"
                    echo "Environment file: $DASHBOARD_ENV"
                    echo "Compose project: $AI_DASHBOARD_PROJECT"
                    echo "Service: $AI_DASHBOARD_SERVICE"
                    echo "URL: $AI_DASHBOARD_URL"

                    docker compose \
                      --project-name "$AI_DASHBOARD_PROJECT" \
                      --env-file "$DASHBOARD_ENV" \
                      --file "$DASHBOARD_COMPOSE" \
                      up \
                      --detach \
                      --build \
                      "$AI_DASHBOARD_SERVICE" \
                      2>&1 |
                      tee "$CI_LOGS_DIR/dashboard-start.log"

                    dashboard_ready=false

                    for attempt in $(seq 1 90); do
                        if curl \
                          --fail \
                          --silent \
                          --show-error \
                          --connect-timeout 3 \
                          --max-time 10 \
                          "$AI_DASHBOARD_URL/api/health" \
                          > "$CI_LOGS_DIR/dashboard-health.json" \
                          2> "$CI_LOGS_DIR/dashboard-health-error.log"
                        then
                            dashboard_ready=true
                            break
                        fi

                        echo "Waiting for AI dashboard: attempt $attempt/90"
                        sleep 2
                    done

                    if [ "$dashboard_ready" != true ]; then
                        echo 'ERROR: AI dashboard did not become healthy.'

                        docker compose \
                          --project-name "$AI_DASHBOARD_PROJECT" \
                          --env-file "$DASHBOARD_ENV" \
                          --file "$DASHBOARD_COMPOSE" \
                          ps --all \
                          2>&1 |
                          tee "$CI_LOGS_DIR/dashboard-ps.log" || true

                        docker compose \
                          --project-name "$AI_DASHBOARD_PROJECT" \
                          --env-file "$DASHBOARD_ENV" \
                          --file "$DASHBOARD_COMPOSE" \
                          logs \
                          --no-color \
                          --timestamps \
                          "$AI_DASHBOARD_SERVICE" \
                          2>&1 |
                          tee "$CI_LOGS_DIR/dashboard-start-failure.log" || true

                        exit 1
                    fi

                    echo '===== AI dashboard health ====='
                    cat "$CI_LOGS_DIR/dashboard-health.json"
                    echo

                    docker compose \
                      --project-name "$AI_DASHBOARD_PROJECT" \
                      --env-file "$DASHBOARD_ENV" \
                      --file "$DASHBOARD_COMPOSE" \
                      ps

                    echo 'AI dashboard is ready and will remain running after the pipeline.'
                '''
            }
        }

        stage('Validate Docker Compose') {
            steps {
                script { env.LAST_STAGE = 'Validate Docker Compose' }
                sh '''#!/usr/bin/env bash
                    set -Eeuo pipefail

                    mkdir -p "$CI_LOGS_DIR"

                    export FRONTEND_REF
                    export BACKEND_REF
                    export BACKEND_HOST_PORT=5000
                    export FRONTEND_HOST_PORT=5173
                    export ANALYTICS_HOST_PORT=8050
                    export OLLAMA_IMAGE
                    export OLLAMA_MODEL
                    export OLLAMA_MODELS_VOLUME

                    docker compose \
                      --file "$COMPOSE_FILE" \
                      config --quiet \
                      2>&1 | tee "$CI_LOGS_DIR/validate-compose.log"
                '''
            }
        }

        stage('Validate Helm Chart') {
            steps {
                script { env.LAST_STAGE = 'Validate Helm Chart' }
                sh '''
                    set -eu

                    helm lint "$HELM_CHART" \
                      --values "$HELM_VALUES"

                    helm template "$HELM_RELEASE" \
                      "$HELM_CHART" \
                      --namespace "$K8S_NAMESPACE" \
                      --values "$HELM_VALUES" \
                      --set-string frontend.image.repository="$FRONTEND_IMAGE" \
                      --set-string frontend.image.tag="$IMAGE_TAG" \
                      --set-string backend.image.repository="$BACKEND_IMAGE" \
                      --set-string backend.image.tag="$IMAGE_TAG" \
                      --set-string analytics.image.repository="$BACKEND_IMAGE" \
                      --set-string analytics.image.tag="$IMAGE_TAG" \
                      > flight-delay-rendered.yaml

                    test -s flight-delay-rendered.yaml
                    grep 'image:' flight-delay-rendered.yaml || true
                '''

                archiveArtifacts(
                    artifacts: 'flight-delay-rendered.yaml',
                    fingerprint: true
                )
            }
        }

        stage('Build Docker Images') {
            parallel {
                stage('Build Frontend') {
                    steps {
                        script { env.LAST_STAGE = 'Build Frontend' }
                        sh '''#!/usr/bin/env bash
                            set -Eeuo pipefail

                            mkdir -p "$CI_LOGS_DIR"

                            docker build \
                              --pull \
                              --progress=plain \
                              --target runtime \
                              --file frontend/Dockerfile \
                              --tag "$FRONTEND_REF" \
                              frontend \
                              2>&1 | tee "$CI_LOGS_DIR/build-frontend.log"
                        '''
                    }
                }

                stage('Build Backend') {
                    steps {
                        script { env.LAST_STAGE = 'Build Backend' }
                        sh '''#!/usr/bin/env bash
                            set -Eeuo pipefail

                            mkdir -p "$CI_LOGS_DIR"

                            docker build \
                              --pull \
                              --progress=plain \
                              --target runtime \
                              --file backend/Dockerfile \
                              --tag "$BACKEND_REF" \
                              . \
                              2>&1 | tee "$CI_LOGS_DIR/build-backend.log"
                        '''
                    }
                }
            }
        }

        stage('Inspect Docker Images') {
            steps {
                script { env.LAST_STAGE = 'Inspect Docker Images' }
                sh '''
                    set -eu

                    docker image inspect \
                      "$FRONTEND_REF" \
                      --format='Frontend size: {{.Size}} bytes'

                    docker image inspect \
                      "$BACKEND_REF" \
                      --format='Backend size: {{.Size}} bytes'
                '''
            }
        }

        stage('Docker Compose Integration Tests') {
            steps {
                script { env.LAST_STAGE = 'Docker Compose Integration Tests' }
                sh '''#!/usr/bin/env bash
                    set -Eeuo pipefail
                    set +x

                    mkdir -p "$CI_LOGS_DIR"
                    exec > >(tee "$CI_LOGS_DIR/docker-compose-integration.log") 2>&1

                    export FRONTEND_REF
                    export BACKEND_REF
                    export BACKEND_HOST_PORT=0
                    export FRONTEND_HOST_PORT=0
                    export ANALYTICS_HOST_PORT=0
                    export OLLAMA_IMAGE
                    export OLLAMA_MODEL
                    export OLLAMA_MODELS_VOLUME

                    docker volume inspect "$OLLAMA_MODELS_VOLUME" \
                      > /dev/null 2>&1 ||
                      docker volume create "$OLLAMA_MODELS_VOLUME" \
                      > /dev/null

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      up \
                      --detach \
                      --wait \
                      --wait-timeout 1800 \
                      --no-build

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      ps

                    echo 'Checking Ollama API and installed model without loading it...'

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T ollama \
                      ollama show "$OLLAMA_MODEL" \
                      > /dev/null

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec \
                      -T \
                      -e "OLLAMA_MODEL=$OLLAMA_MODEL" \
                      -e "OLLAMA_BASE_URL=$OLLAMA_BASE_URL" \
                      backend \
                      python - <<'PYTHON_OLLAMA_CHECK'
import json
import os
import urllib.request

base_url = os.environ["OLLAMA_BASE_URL"].rstrip("/")
expected = os.environ["OLLAMA_MODEL"]

with urllib.request.urlopen(
    f"{base_url}/api/tags",
    timeout=30,
) as response:
    payload = json.loads(response.read().decode("utf-8"))

models = [
    item.get("name", "")
    for item in payload.get("models", [])
]

if expected not in models:
    raise SystemExit(
        f"Expected Ollama model not found: {expected}. "
        f"Available models: {models}"
    )

print("Ollama API is reachable.")
print(f"Ollama model is installed: {expected}")
PYTHON_OLLAMA_CHECK

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T redis \
                      redis-cli ping |
                      grep --quiet '^PONG$'

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      curl \
                        --fail \
                        --silent \
                        --show-error \
                        http://127.0.0.1:5000/health

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T frontend \
                      wget \
                        --quiet \
                        --tries=1 \
                        --output-document=- \
                        http://127.0.0.1/health |
                      grep --quiet '^ok$'

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T frontend \
                      wget \
                        --quiet \
                        --tries=1 \
                        --output-document=/dev/null \
                        http://127.0.0.1/

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T analytics \
                      curl \
                        --fail \
                        --silent \
                        --show-error \
                        --output /dev/null \
                        http://127.0.0.1:8050/

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      test -f /app/ml/models/v1_model.json

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T analytics \
                      test -f /app/datasets/flight_data.csv

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      python -c "from app.services.prediction_service import PredictionService; print('PredictionService import succeeded')"
                '''
            }

            post {
                unsuccessful {
                    sh '''#!/usr/bin/env bash
                        set +e
                        set +x

                        mkdir -p "$CI_LOGS_DIR"

                        export FRONTEND_REF
                        export BACKEND_REF
                        export BACKEND_HOST_PORT=0
                        export FRONTEND_HOST_PORT=0
                        export ANALYTICS_HOST_PORT=0
                        export OLLAMA_IMAGE
                        export OLLAMA_MODEL
                        export OLLAMA_MODELS_VOLUME

                        {
                            echo '===== docker compose ps --all ====='
                            docker compose \
                              --project-name "$CI_PROJECT" \
                              --file "$COMPOSE_FILE" \
                              ps --all || true

                            echo
                            echo '===== Container state and health details ====='

                            docker ps -a \
                              --filter "label=com.docker.compose.project=$CI_PROJECT" \
                              --format '{{.Names}}' |
                            while read -r container
                            do
                                [ -n "$container" ] || continue

                                echo
                                echo "===== Container: $container ====="

                                docker inspect "$container" \
                                  --format 'Status={{.State.Status}} ExitCode={{.State.ExitCode}} Error={{.State.Error}}' \
                                  || true

                                docker inspect "$container" \
                                  --format '{{if .State.Health}}Health={{.State.Health.Status}}{{else}}Health=not-configured{{end}}' \
                                  || true

                                docker inspect "$container" \
                                  --format '{{if .State.Health}}{{range .State.Health.Log}}Started={{.Start}} ExitCode={{.ExitCode}}{{println}}{{.Output}}{{println}}{{end}}{{end}}' \
                                  || true
                            done

                            echo
                            echo '===== Ollama and backend logs ====='
                            docker compose \
                              --project-name "$CI_PROJECT" \
                              --file "$COMPOSE_FILE" \
                              logs \
                              --no-color \
                              --timestamps \
                              ollama ollama-init backend || true

                            echo
                            echo '===== All Compose logs ====='
                            docker compose \
                              --project-name "$CI_PROJECT" \
                              --file "$COMPOSE_FILE" \
                              logs \
                              --no-color \
                              --timestamps || true
                        } 2>&1 | tee "$CI_LOGS_DIR/docker-compose-failure.log"

                        {
                            echo '===== Docker Compose health summary ====='

                            docker ps -a \
                              --filter "label=com.docker.compose.project=$CI_PROJECT" \
                              --format '{{.Names}}' |
                            while read -r container
                            do
                                [ -n "$container" ] || continue

                                echo
                                echo "Container=$container"

                                docker inspect "$container" \
                                  --format 'Status={{.State.Status}} ExitCode={{.State.ExitCode}} Error={{.State.Error}}' \
                                  || true

                                docker inspect "$container" \
                                  --format '{{if .State.Health}}Health={{.State.Health.Status}}{{else}}Health=not-configured{{end}}' \
                                  || true

                                docker inspect "$container" \
                                  --format '{{if .State.Health}}{{range .State.Health.Log}}ExitCode={{.ExitCode}}{{println}}{{.Output}}{{println}}{{end}}{{end}}' \
                                  || true
                            done
                        } > "$CI_LOGS_DIR/docker-compose-health.log" 2>&1
                    '''
                }

                success {
                    sh '''
                        set +e
                        set +x

                        export FRONTEND_REF
                        export BACKEND_REF
                        export BACKEND_HOST_PORT=0
                        export FRONTEND_HOST_PORT=0
                        export ANALYTICS_HOST_PORT=0
                        export OLLAMA_IMAGE
                        export OLLAMA_MODEL
                        export OLLAMA_MODELS_VOLUME

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          down \
                          --volumes \
                          --remove-orphans || true
                    '''
                }
            }
        }

        stage('Test AI Failure Analysis') {
            when {
                expression {
                    params.FORCE_AI_FAILURE
                }
            }

            steps {
                script { env.LAST_STAGE = 'Test AI Failure Analysis' }
                sh '''#!/usr/bin/env bash
                    set -Eeuo pipefail

                    mkdir -p "$CI_LOGS_DIR"

                    {
                        echo '[Pipeline] stage'
                        echo '[Pipeline] { (Test AI Failure Analysis)'
                        echo 'ERROR: simulated backend connection failure'
                        echo 'redis.exceptions.ConnectionError: Connection refused while connecting to redis:6379'
                        echo 'Docker Compose Integration Tests failed with exit code 1'
                    } | tee "$CI_LOGS_DIR/simulated-failure.log"

                    echo 'Controlled failure triggered to validate Ollama analysis.' |
                      tee -a "$CI_LOGS_DIR/simulated-failure.log"

                    exit 1
                '''
            }
        }

        stage('Publish Docker Images') {
            when {
                expression {
                    params.PUBLISH_IMAGES &&
                    (
                        env.SOURCE_BRANCH == 'main' ||
                        env.SOURCE_BRANCH == 'develop'
                    )
                }
            }

            steps {
                script { env.LAST_STAGE = 'Publish Docker Images' }
                withCredentials([
                    usernamePassword(
                        credentialsId: env.REGISTRY_CREDENTIALS,
                        usernameVariable: 'REGISTRY_USER',
                        passwordVariable: 'REGISTRY_TOKEN'
                    )
                ]) {
                    sh '''
                        set -eu
                        set +x

                        trap 'docker logout >/dev/null 2>&1 || true' EXIT

                        echo "$REGISTRY_TOKEN" |
                          docker login \
                            --username "$REGISTRY_USER" \
                            --password-stdin

                        docker push "$FRONTEND_REF"
                        docker push "$BACKEND_REF"

                        docker tag \
                          "$FRONTEND_REF" \
                          "$FRONTEND_IMAGE:$SAFE_BRANCH-latest"

                        docker tag \
                          "$BACKEND_REF" \
                          "$BACKEND_IMAGE:$SAFE_BRANCH-latest"

                        docker push "$FRONTEND_IMAGE:$SAFE_BRANCH-latest"
                        docker push "$BACKEND_IMAGE:$SAFE_BRANCH-latest"

                        if [ "$SOURCE_BRANCH" = "main" ]; then
                            docker tag \
                              "$FRONTEND_REF" \
                              "$FRONTEND_IMAGE:latest"

                            docker tag \
                              "$BACKEND_REF" \
                              "$BACKEND_IMAGE:latest"

                            docker push "$FRONTEND_IMAGE:latest"
                            docker push "$BACKEND_IMAGE:latest"
                        fi
                    '''
                }
            }
        }

        stage('Update GitOps Repository') {
            when {
                expression {
                    params.PUBLISH_IMAGES &&
                    !params.DEPLOY_KUBERNETES &&
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                script { env.LAST_STAGE = 'Update GitOps Repository' }

                withCredentials([
                    usernamePassword(
                        credentialsId: env.GITOPS_CREDENTIALS,
                        usernameVariable: 'GITOPS_USER',
                        passwordVariable: 'GITOPS_TOKEN'
                    )
                ]) {
                    sh '''#!/usr/bin/env bash
                        set -Eeuo pipefail
                        set +x

                        command -v git > /dev/null

                        if ! command -v yq > /dev/null 2>&1; then
                            echo 'ERROR: yq is required on the Jenkins agent.'
                            echo 'Install mikefarah/yq, then run the pipeline again.'
                            exit 1
                        fi

                        WORKSPACE_ROOT="$(pwd -P)"
                        GITOPS_DIR="$WORKSPACE_ROOT/.gitops-${BUILD_NUMBER}"
                        ASKPASS_FILE="$(mktemp)"

                        cleanup() {
                            rm -f "$ASKPASS_FILE"
                            rm -rf "$GITOPS_DIR"
                        }

                        trap cleanup EXIT

                        cat > "$ASKPASS_FILE" <<'GIT_ASKPASS_SCRIPT'
#!/bin/sh
case "$1" in
    *Username*)
        printf '%s\n' "$GITOPS_USER"
        ;;
    *Password*)
        printf '%s\n' "$GITOPS_TOKEN"
        ;;
esac
GIT_ASKPASS_SCRIPT

                        chmod 700 "$ASKPASS_FILE"

                        export GIT_ASKPASS="$ASKPASS_FILE"
                        export GIT_TERMINAL_PROMPT=0
                        export FRONTEND_IMAGE
                        export BACKEND_IMAGE
                        export IMAGE_TAG

                        update_succeeded=false

                        for attempt in 1 2 3; do
                            echo "GitOps update attempt $attempt/3"

                            rm -rf "$GITOPS_DIR"

                            git clone \
                              --branch "$GITOPS_BRANCH" \
                              --single-branch \
                              "$GITOPS_REPO" \
                              "$GITOPS_DIR"

                            cd "$GITOPS_DIR"

                            if [ ! -f "$GITOPS_VALUES" ]; then
                                echo "ERROR: GitOps values file not found: $GITOPS_VALUES"
                                exit 1
                            fi

                            yq -i '
                              .frontend.image.repository = strenv(FRONTEND_IMAGE) |
                              .frontend.image.tag = strenv(IMAGE_TAG) |
                              .backend.image.repository = strenv(BACKEND_IMAGE) |
                              .backend.image.tag = strenv(IMAGE_TAG) |
                              .analytics.image.repository = strenv(BACKEND_IMAGE) |
                              .analytics.image.tag = strenv(IMAGE_TAG)
                            ' "$GITOPS_VALUES"

                            echo '===== GitOps image values ====='

                            yq '
                              {
                                "frontend": .frontend.image,
                                "backend": .backend.image,
                                "analytics": .analytics.image
                              }
                            ' "$GITOPS_VALUES"

                            git config \
                              user.name \
                              'jenkins-flight-delay'

                            git config \
                              user.email \
                              'jenkins-flight-delay@users.noreply.github.com'

                            git add "$GITOPS_VALUES"

                            if git diff --cached --quiet; then
                                echo 'GitOps already contains the requested image tag.'
                                update_succeeded=true
                                break
                            fi

                            git commit \
                              -m "deploy(dev): ${IMAGE_TAG}"

                            if git push \
                              origin \
                              "HEAD:${GITOPS_BRANCH}"
                            then
                                update_succeeded=true
                                break
                            fi

                            echo 'The GitOps branch changed during the push. Retrying from the latest remote state.'

                            cd "$WORKSPACE_ROOT"
                            sleep "$((attempt * 2))"
                        done

                        if [ "$update_succeeded" != true ]; then
                            echo 'ERROR: GitOps repository update failed after 3 attempts.'
                            exit 1
                        fi

                        echo "GitOps repository updated with image tag: $IMAGE_TAG"
                    '''
                }
            }
        }

        stage('Check Kubernetes Access') {
            when {
                expression {
                    params.DEPLOY_KUBERNETES &&
                    params.PUBLISH_IMAGES &&
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                script { env.LAST_STAGE = 'Check Kubernetes Access' }
                withCredentials([
                    file(
                        credentialsId: env.KUBECONFIG_CREDENTIALS,
                        variable: 'KUBECONFIG'
                    )
                ]) {
                    sh '''
                        set -eu

                        kubectl \
                          --context "$KUBE_CONTEXT" \
                          cluster-info

                        kubectl \
                          --context "$KUBE_CONTEXT" \
                          get nodes -o wide

                        kubectl \
                          --context "$KUBE_CONTEXT" \
                          wait \
                          --for=condition=Ready \
                          node \
                          --all \
                          --timeout=120s
                    '''
                }
            }
        }

        stage('Prepare Namespace and Registry Secret') {
            when {
                expression {
                    params.DEPLOY_KUBERNETES &&
                    params.PUBLISH_IMAGES &&
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                script { env.LAST_STAGE = 'Prepare Namespace and Registry Secret' }
                withCredentials([
                    file(
                        credentialsId: env.KUBECONFIG_CREDENTIALS,
                        variable: 'KUBECONFIG'
                    ),
                    usernamePassword(
                        credentialsId: env.REGISTRY_CREDENTIALS,
                        usernameVariable: 'REGISTRY_USER',
                        passwordVariable: 'REGISTRY_TOKEN'
                    )
                ]) {
                    sh '''
                        set -eu
                        set +x

                        if ! kubectl \
                          --context "$KUBE_CONTEXT" \
                          get namespace "$K8S_NAMESPACE" \
                          >/dev/null 2>&1
                        then
                            kubectl \
                              --context "$KUBE_CONTEXT" \
                              create namespace "$K8S_NAMESPACE"
                        fi

                        kubectl \
                          --context "$KUBE_CONTEXT" \
                          --namespace "$K8S_NAMESPACE" \
                          delete secret dockerhub-credentials \
                          --ignore-not-found=true

                        kubectl \
                          --context "$KUBE_CONTEXT" \
                          --namespace "$K8S_NAMESPACE" \
                          create secret docker-registry dockerhub-credentials \
                          --docker-server=https://index.docker.io/v1/ \
                          --docker-username="$REGISTRY_USER" \
                          --docker-password="$REGISTRY_TOKEN"
                    '''
                }
            }
        }

        stage('Deploy with Helm') {
            when {
                expression {
                    params.DEPLOY_KUBERNETES &&
                    params.PUBLISH_IMAGES &&
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                script { env.LAST_STAGE = 'Deploy with Helm' }
                withCredentials([
                    file(
                        credentialsId: env.KUBECONFIG_CREDENTIALS,
                        variable: 'KUBECONFIG'
                    )
                ]) {
                    sh '''
                        set -eu

                        helm upgrade --install "$HELM_RELEASE" \
                          "$HELM_CHART" \
                          --kube-context "$KUBE_CONTEXT" \
                          --namespace "$K8S_NAMESPACE" \
                          --create-namespace \
                          --values "$HELM_VALUES" \
                          --set-string frontend.image.repository="$FRONTEND_IMAGE" \
                          --set-string frontend.image.tag="$IMAGE_TAG" \
                          --set-string backend.image.repository="$BACKEND_IMAGE" \
                          --set-string backend.image.tag="$IMAGE_TAG" \
                          --set-string analytics.image.repository="$BACKEND_IMAGE" \
                          --set-string analytics.image.tag="$IMAGE_TAG" \
                          --history-max 10 \
                          --atomic \
                          --timeout 10m
                    '''
                }
            }

            post {
                unsuccessful {
                    withCredentials([
                        file(
                            credentialsId: env.KUBECONFIG_CREDENTIALS,
                            variable: 'KUBECONFIG'
                        )
                    ]) {
                        sh '''#!/usr/bin/env bash
                            set +e

                            mkdir -p "$CI_LOGS_DIR"

                            {
                            helm status "$HELM_RELEASE" \
                              --kube-context "$KUBE_CONTEXT" \
                              --namespace "$K8S_NAMESPACE" || true

                            kubectl \
                              --context "$KUBE_CONTEXT" \
                              --namespace "$K8S_NAMESPACE" \
                              get pods -o wide || true

                            kubectl \
                              --context "$KUBE_CONTEXT" \
                              --namespace "$K8S_NAMESPACE" \
                              get deployments,services,pvc || true

                            kubectl \
                              --context "$KUBE_CONTEXT" \
                              --namespace "$K8S_NAMESPACE" \
                              get events \
                              --sort-by=.metadata.creationTimestamp || true

                            kubectl \
                              --context "$KUBE_CONTEXT" \
                              --namespace "$K8S_NAMESPACE" \
                              logs deployment/flight-delay-dev-backend \
                              --all-containers=true \
                              --tail=150 || true

                            kubectl \
                              --context "$KUBE_CONTEXT" \
                              --namespace "$K8S_NAMESPACE" \
                              logs deployment/flight-delay-dev-frontend \
                              --all-containers=true \
                              --tail=150 || true

                            kubectl \
                              --context "$KUBE_CONTEXT" \
                              --namespace "$K8S_NAMESPACE" \
                              logs deployment/flight-delay-dev-analytics \
                              --all-containers=true \
                              --tail=150 || true
                            } 2>&1 | tee "$CI_LOGS_DIR/kubernetes-failure.log"
                        '''
                    }
                }
            }
        }

        stage('Verify Kubernetes Deployment') {
            when {
                expression {
                    params.DEPLOY_KUBERNETES &&
                    params.PUBLISH_IMAGES &&
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                script { env.LAST_STAGE = 'Verify Kubernetes Deployment' }
                withCredentials([
                    file(
                        credentialsId: env.KUBECONFIG_CREDENTIALS,
                        variable: 'KUBECONFIG'
                    )
                ]) {
                    sh '''
                        set -eu

                        helm status "$HELM_RELEASE" \
                          --kube-context "$KUBE_CONTEXT" \
                          --namespace "$K8S_NAMESPACE"

                        kubectl \
                          --context "$KUBE_CONTEXT" \
                          --namespace "$K8S_NAMESPACE" \
                          wait \
                          --for=condition=Available \
                          deployment \
                          --all \
                          --timeout=300s

                        kubectl \
                          --context "$KUBE_CONTEXT" \
                          --namespace "$K8S_NAMESPACE" \
                          get deployments,pods,services,pvc -o wide

                        kubectl \
                          --context "$KUBE_CONTEXT" \
                          --namespace "$K8S_NAMESPACE" \
                          get deployments \
                          -o custom-columns='DEPLOYMENT:.metadata.name,IMAGE:.spec.template.spec.containers[*].image'

                        kubectl \
                          --context "$KUBE_CONTEXT" \
                          --namespace "$K8S_NAMESPACE" \
                          exec deployment/flight-delay-dev-redis \
                          -- redis-cli ping |
                          grep --quiet '^PONG$'

                        kubectl \
                          --context "$KUBE_CONTEXT" \
                          --namespace "$K8S_NAMESPACE" \
                          exec deployment/flight-delay-dev-frontend \
                          -- wget \
                             --quiet \
                             --output-document=- \
                             http://backend:5000/health
                    '''
                }
            }
        }

        stage('Kubernetes Smoke Tests') {
            when {
                expression {
                    params.DEPLOY_KUBERNETES &&
                    params.PUBLISH_IMAGES &&
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                script { env.LAST_STAGE = 'Kubernetes Smoke Tests' }
                sh '''
                    set -eu

                    curl \
                      --fail \
                      --silent \
                      --show-error \
                      "$K8S_FRONTEND_URL/health" |
                      grep --quiet '^ok$'

                    curl \
                      --fail \
                      --silent \
                      --show-error \
                      --output /dev/null \
                      "$K8S_FRONTEND_URL/"

                    curl \
                      --fail \
                      --silent \
                      --show-error \
                      --output /dev/null \
                      "$K8S_ANALYTICS_URL/"

                    curl \
                      --silent \
                      --show-error \
                      --output /dev/null \
                      --write-out '%{http_code}' \
                      "$K8S_FRONTEND_URL/api/v1/predict/stats" |
                      grep --extended-regexp --quiet '^(200|401|403)$'
                '''
            }
        }

        stage('Show Deployment') {
            when {
                expression {
                    params.DEPLOY_KUBERNETES &&
                    params.PUBLISH_IMAGES &&
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                script { env.LAST_STAGE = 'Show Deployment' }
                echo "Helm release: ${env.HELM_RELEASE}"
                echo "Namespace: ${env.K8S_NAMESPACE}"
                echo "Kube context: ${env.KUBE_CONTEXT}"
                echo "Image tag: ${env.IMAGE_TAG}"
                echo "Frontend: ${env.K8S_FRONTEND_URL}"
                echo "Analytics: ${env.K8S_ANALYTICS_URL}"
            }
        }
    }

    post {
        success {
            echo "Pipeline succeeded for ${env.SOURCE_BRANCH}: ${env.IMAGE_TAG}"
        }

        failure {
            echo 'Pipeline failed. Collecting logs and running Ollama analysis.'

            script {
                if (params.AI_FAILURE_ANALYSIS) {
                    sh '''#!/usr/bin/env bash
                        set +e
                        set +x

                        WORKSPACE_ROOT="$(pwd -P)"
                        MODEL="${OLLAMA_MODEL:-qwen2.5-coder:3b-instruct}"
                        PROJECT="${CI_PROJECT:-flight-delay-ci-${BUILD_NUMBER}}"
                        AI_NETWORK="${PROJECT}-ai-network"
                        AI_OLLAMA_CONTAINER="${PROJECT}-ai-ollama"
                        AI_SCRIPT_HOST="$WORKSPACE_ROOT/$AI_SCRIPT"
                        LOGS_PATH="$WORKSPACE_ROOT/$CI_LOGS_DIR"
                        EXTERNAL_URL="${OLLAMA_EXTERNAL_URL:-}"

                        mkdir -p "$LOGS_PATH"

                        {
                            echo "Job: ${JOB_NAME:-unknown}"
                            echo "Build: ${BUILD_NUMBER:-unknown}"
                            echo "Build URL: ${BUILD_URL:-unknown}"
                            echo "Branch: ${SOURCE_BRANCH:-${BRANCH_NAME:-unknown}}"
                            echo "Commit: ${SHORT_SHA:-unknown}"
                            echo "Node: ${NODE_NAME:-unknown}"
                            echo "Jenkins workspace: ${WORKSPACE:-unknown}"
                            echo "Resolved workspace: $WORKSPACE_ROOT"
                            echo "AI script: $AI_SCRIPT_HOST"
                            echo "Ollama model: $MODEL"
                            echo "Last entered stage: ${LAST_STAGE:-unknown}"
                            echo "Build result: FAILURE"
                            echo "Force AI failure: ${FORCE_AI_FAILURE:-false}"
                        } > "$LOGS_PATH/pipeline-context.log"

                        if [ -n "${BUILD_URL:-}" ]; then
                            CONSOLE_TMP="$LOGS_PATH/jenkins-console.log.tmp"

                            if curl \
                              --fail \
                              --silent \
                              --show-error \
                              --max-time 30 \
                              "${BUILD_URL}consoleText" \
                              --output "$CONSOLE_TMP" \
                              2> /dev/null
                            then
                                mv \
                                  "$CONSOLE_TMP" \
                                  "$LOGS_PATH/jenkins-console.log"

                                echo 'Jenkins console log collected.' \
                                  >> "$LOGS_PATH/pipeline-context.log"
                            else
                                rm -f "$CONSOLE_TMP"

                                echo 'Jenkins console log could not be downloaded; using diagnostic and stage logs.' \
                                  >> "$LOGS_PATH/pipeline-context.log"
                            fi
                        fi

                        if [ ! -f "$AI_SCRIPT_HOST" ]; then
                            {
                                echo 'AI failure analysis was skipped.'
                                echo 'The analyzer script was not found in the checked-out workspace.'
                                echo "Expected file: $AI_SCRIPT_HOST"
                            } | tee "$LOGS_PATH/ai-analysis-error.log"

                            exit 0
                        fi

                        {
                            echo '===== Docker daemon diagnostic ====='
                            echo "Checked at: $(date --iso-8601=seconds)"
                            echo
                            docker version
                            echo
                            docker info
                        } > "$LOGS_PATH/docker-daemon-check.log" 2>&1

                        if docker info > /dev/null 2>&1; then
                            DOCKER_AVAILABLE=true
                            echo 'Docker daemon is available.' |
                              tee -a "$LOGS_PATH/pipeline-context.log"
                        else
                            DOCKER_AVAILABLE=false
                            {
                                echo 'Docker daemon is unavailable.'
                                echo 'The original Docker error is stored in docker-daemon-check.log.'
                                echo 'AI analysis will use an Ollama service running outside Docker.'
                            } | tee -a "$LOGS_PATH/pipeline-context.log"
                        fi

                        if [ "$DOCKER_AVAILABLE" = true ]; then
                            {
                                echo '===== Final Docker Compose state ====='
                                docker compose \
                                  --project-name "$PROJECT" \
                                  --file "$WORKSPACE_ROOT/$COMPOSE_FILE" \
                                  ps --all || true

                                echo
                                echo '===== Final Docker Compose logs ====='
                                docker compose \
                                  --project-name "$PROJECT" \
                                  --file "$WORKSPACE_ROOT/$COMPOSE_FILE" \
                                  logs \
                                  --no-color \
                                  --timestamps || true
                            } > "$LOGS_PATH/final-compose-state.log" 2>&1

                            docker compose \
                              --project-name "$PROJECT" \
                              --file "$WORKSPACE_ROOT/$COMPOSE_FILE" \
                              down \
                              --volumes \
                              --remove-orphans \
                              > /dev/null 2>&1 || true
                        else
                            {
                                echo 'Docker Compose state could not be collected.'
                                echo 'Reason: Docker daemon is unavailable.'
                            } > "$LOGS_PATH/final-compose-state.log"
                        fi

                        {
                            echo "Last entered stage: ${LAST_STAGE:-unknown}"
                            echo "Build result: FAILURE"
                            echo

                            echo '===== High-signal pipeline errors ====='

                            for log_file in "$LOGS_PATH"/*.log
                            do
                                [ -f "$log_file" ] || continue

                                case "$(basename "$log_file")" in
                                    ai-*|ollama-*)
                                        continue
                                        ;;
                                esac

                                grep \
                                  --with-filename \
                                  --line-number \
                                  --extended-regexp \
                                  --ignore-case \
                                  'failed|failure|error|fatal|exception|traceback|unhealthy|health.?check|curl:.*\\(22\\)|404|connection refused|not found|no such file|timeout|timed out|denied|forbidden|exit code [1-9]|crashloop|imagepull|back-off|cannot|could not' \
                                  "$log_file" \
                                  || true
                            done |
                              head -n 250
                        } > "$LOGS_PATH/failure-summary.log" 2>&1

                        ANALYSIS_OLLAMA_URL=''

                        if [ "$DOCKER_AVAILABLE" = true ]; then
                            docker rm -f "$AI_OLLAMA_CONTAINER" \
                              > /dev/null 2>&1 || true

                            docker network rm "$AI_NETWORK" \
                              > /dev/null 2>&1 || true

                            docker volume inspect "$OLLAMA_MODELS_VOLUME" \
                              > /dev/null 2>&1 ||
                              docker volume create "$OLLAMA_MODELS_VOLUME" \
                              > /dev/null

                            if ! docker network create "$AI_NETWORK" \
                              > /dev/null 2>&1
                            then
                                echo 'Could not create the isolated AI Docker network.' |
                                  tee "$LOGS_PATH/ai-analysis-error.log"
                                exit 0
                            fi

                            if ! docker run \
                              --detach \
                              --name "$AI_OLLAMA_CONTAINER" \
                              --network "$AI_NETWORK" \
                              --publish "127.0.0.1:${AI_OLLAMA_HOST_PORT}:11434" \
                              --env OLLAMA_HOST=0.0.0.0:11434 \
                              --env OLLAMA_KEEP_ALIVE=30m \
                              --volume "$OLLAMA_MODELS_VOLUME:/root/.ollama" \
                              "$OLLAMA_IMAGE" \
                              > /dev/null
                            then
                                echo 'Could not start the isolated Ollama container.' |
                                  tee "$LOGS_PATH/ai-analysis-error.log"
                                exit 0
                            fi

                            ollama_ready=false

                            for attempt in $(seq 1 60); do
                                if curl \
                                  --fail \
                                  --silent \
                                  --show-error \
                                  "http://127.0.0.1:${AI_OLLAMA_HOST_PORT}/api/tags" \
                                  > /dev/null 2>&1
                                then
                                    ollama_ready=true
                                    break
                                fi

                                sleep 2
                            done

                            if [ "$ollama_ready" != true ]; then
                                echo 'Ollama did not become ready for AI analysis.' |
                                  tee "$LOGS_PATH/ai-analysis-error.log"

                                docker logs "$AI_OLLAMA_CONTAINER" \
                                  >> "$LOGS_PATH/ai-analysis-error.log" \
                                  2>&1 || true

                                exit 0
                            fi

                            echo "Preparing Ollama model in Docker: $MODEL"

                            if ! docker exec "$AI_OLLAMA_CONTAINER" \
                              ollama pull "$MODEL" \
                              2>&1 |
                              tee "$LOGS_PATH/ollama-model-pull.log"
                            then
                                echo 'The Ollama model could not be prepared.' |
                                  tee "$LOGS_PATH/ai-analysis-error.log"
                                exit 0
                            fi

                            ANALYSIS_OLLAMA_URL="http://127.0.0.1:${AI_OLLAMA_HOST_PORT}/api/chat"
                        else
                            if [ -n "$EXTERNAL_URL" ]; then
                                ANALYSIS_OLLAMA_URL="$EXTERNAL_URL"
                            else
                                WINDOWS_HOST_IP="$(
                                  ip route show default 2> /dev/null |
                                  awk '/default/ {print $3; exit}'
                                )"

                                if [ -z "$WINDOWS_HOST_IP" ]; then
                                    {
                                        echo 'AI failure analysis could not run.'
                                        echo 'Docker is unavailable and the Windows host IP could not be detected.'
                                        echo 'Set OLLAMA_EXTERNAL_URL to an Ollama /api/chat endpoint.'
                                    } | tee "$LOGS_PATH/ai-analysis-error.log"

                                    exit 0
                                fi

                                ANALYSIS_OLLAMA_URL="http://${WINDOWS_HOST_IP}:11434/api/chat"
                            fi

                            echo "Using external Ollama endpoint: $ANALYSIS_OLLAMA_URL" |
                              tee -a "$LOGS_PATH/pipeline-context.log"

                            timeout "$OLLAMA_REQUEST_TIMEOUT_SECONDS" \
                              env \
                                OLLAMA_URL="$ANALYSIS_OLLAMA_URL" \
                                OLLAMA_MODEL="$MODEL" \
                                OLLAMA_REQUEST_TIMEOUT_SECONDS="$OLLAMA_REQUEST_TIMEOUT_SECONDS" \
                              python3 - <<'PYTHON_PREPARE_EXTERNAL' \
                              2>&1 | tee "$LOGS_PATH/ollama-external-check.log"
import json
import os
import urllib.request

chat_url = os.environ["OLLAMA_URL"].rstrip("/")
model = os.environ["OLLAMA_MODEL"]
timeout_seconds = int(
    os.environ["OLLAMA_REQUEST_TIMEOUT_SECONDS"]
)

if not chat_url.endswith("/api/chat"):
    raise SystemExit(
        "OLLAMA_EXTERNAL_URL must end with /api/chat"
    )

base_url = chat_url[:-len("/api/chat")]
tags_url = f"{base_url}/api/tags"
pull_url = f"{base_url}/api/pull"

print(f"Checking external Ollama: {tags_url}", flush=True)

with urllib.request.urlopen(
    tags_url,
    timeout=30,
) as response:
    tags = json.loads(response.read().decode("utf-8"))

models = {
    item.get("name", "")
    for item in tags.get("models", [])
}

if model not in models:
    print(
        f"Model {model} is not installed. Pulling it now...",
        flush=True,
    )

    request = urllib.request.Request(
        pull_url,
        data=json.dumps(
            {
                "model": model,
                "stream": False,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout_seconds,
    ) as response:
        response.read()

print(f"External Ollama model is ready: {model}", flush=True)
PYTHON_PREPARE_EXTERNAL

                            EXTERNAL_CHECK_EXIT_CODE="${PIPESTATUS[0]}"

                            if [ "$EXTERNAL_CHECK_EXIT_CODE" -ne 0 ]; then
                                {
                                    echo 'AI failure analysis could not use the external Ollama service.'
                                    echo "Endpoint: $ANALYSIS_OLLAMA_URL"
                                    echo 'Start Ollama outside Docker or set OLLAMA_EXTERNAL_URL correctly.'
                                } | tee "$LOGS_PATH/ai-analysis-error.log"

                                exit 0
                            fi
                        fi

                        echo 'Running analyze_failure.py with the collected pipeline logs...'
                        echo "Ollama URL: $ANALYSIS_OLLAMA_URL"
                        echo "Ollama analysis timeout: ${OLLAMA_REQUEST_TIMEOUT_SECONDS} seconds"

                        ANALYZER_COMMAND_TIMEOUT="$((OLLAMA_REQUEST_TIMEOUT_SECONDS + 120))"

                        timeout "$ANALYZER_COMMAND_TIMEOUT" \
                          env \
                            OLLAMA_URL="$ANALYSIS_OLLAMA_URL" \
                            OLLAMA_MODEL="$MODEL" \
                            OLLAMA_REQUEST_TIMEOUT_SECONDS="$OLLAMA_REQUEST_TIMEOUT_SECONDS" \
                            LAST_STAGE="${LAST_STAGE:-unknown}" \
                            BUILD_RESULT=FAILURE \
                            FORCE_AI_FAILURE="${FORCE_AI_FAILURE:-false}" \
                            JOB_NAME="${JOB_NAME:-unknown}" \
                            BUILD_NUMBER="${BUILD_NUMBER:-unknown}" \
                            BUILD_URL="${BUILD_URL:-unknown}" \
                            SOURCE_BRANCH="${SOURCE_BRANCH:-${BRANCH_NAME:-unknown}}" \
                            SHORT_SHA="${SHORT_SHA:-unknown}" \
                            NODE_NAME="${NODE_NAME:-unknown}" \
                            WORKSPACE="$WORKSPACE_ROOT" \
                          python3 "$AI_SCRIPT_HOST" \
                            --logs-dir "$LOGS_PATH" \
                            --output-json "$WORKSPACE_ROOT/$AI_OUTPUT_JSON" \
                            --output-markdown "$WORKSPACE_ROOT/$AI_OUTPUT_MD" \
                            --output-raw "$WORKSPACE_ROOT/$AI_OUTPUT_RAW" \
                          2>&1 |
                          tee "$LOGS_PATH/ai-analysis-run.log"

                        ANALYSIS_EXIT_CODE="${PIPESTATUS[0]}"

                        if [ "$ANALYSIS_EXIT_CODE" -ne 0 ]; then
                            echo "AI analyzer exited with code $ANALYSIS_EXIT_CODE." |
                              tee "$LOGS_PATH/ai-analysis-error.log"

                            exit 0
                        fi

                        if [ ! -s "$WORKSPACE_ROOT/$AI_OUTPUT_JSON" ] ||
                           [ ! -s "$WORKSPACE_ROOT/$AI_OUTPUT_MD" ]
                        then
                            echo 'The AI analyzer finished but did not create both reports.' |
                              tee "$LOGS_PATH/ai-analysis-error.log"

                            exit 0
                        fi

                        if ! python3 -m json.tool \
                          "$WORKSPACE_ROOT/$AI_OUTPUT_JSON" \
                          > /dev/null
                        then
                            echo 'The generated AI JSON report is invalid.' |
                              tee "$LOGS_PATH/ai-analysis-error.log"

                            exit 0
                        fi

                        echo 'AI failure analysis succeeded.' |
                          tee "$LOGS_PATH/ai-analysis-success.log"

                        exit 0
                    '''

                    script {
                        if (fileExists(env.AI_OUTPUT_JSON)) {
                            sh '''#!/usr/bin/env bash
                                set +e
                                set +x

                                WORKSPACE_ROOT="$(pwd -P)"
                                DASHBOARD_COMPOSE="$WORKSPACE_ROOT/$AI_DASHBOARD_COMPOSE_FILE"
                                DASHBOARD_ENV="$WORKSPACE_ROOT/$AI_DASHBOARD_ENV_FILE"
                                PUBLISH_SCRIPT="$WORKSPACE_ROOT/$AI_PUBLISH_SCRIPT"

                                mkdir -p "$CI_LOGS_DIR"
                                mkdir -p "$(dirname "$DASHBOARD_ENV")"

                                umask 077
                                {
                                    printf 'DASHBOARD_PORT=%s\n' "$AI_DASHBOARD_PORT"
                                    printf 'DASHBOARD_INGEST_TOKEN=%s\n' "${AI_DASHBOARD_TOKEN:-}"
                                } > "$DASHBOARD_ENV"

                                export DASHBOARD_PORT="$AI_DASHBOARD_PORT"
                                export DASHBOARD_INGEST_TOKEN="${AI_DASHBOARD_TOKEN:-}"

                                dashboard_ready=false

                                if curl \
                                  --fail \
                                  --silent \
                                  --show-error \
                                  --connect-timeout 3 \
                                  --max-time 10 \
                                  "$AI_DASHBOARD_URL/api/health" \
                                  > "$CI_LOGS_DIR/dashboard-health-before-publish.json" \
                                  2> "$CI_LOGS_DIR/dashboard-health-before-publish-error.log"
                                then
                                    dashboard_ready=true
                                else
                                    echo 'Dashboard is unavailable before publication. Restarting it.' |
                                      tee "$CI_LOGS_DIR/dashboard-restart.log"

                                    docker compose \
                                      --project-name "$AI_DASHBOARD_PROJECT" \
                                      --env-file "$DASHBOARD_ENV" \
                                      --file "$DASHBOARD_COMPOSE" \
                                      up \
                                      --detach \
                                      --build \
                                      "$AI_DASHBOARD_SERVICE" \
                                      >> "$CI_LOGS_DIR/dashboard-restart.log" \
                                      2>&1

                                    for attempt in $(seq 1 90); do
                                        if curl \
                                          --fail \
                                          --silent \
                                          --show-error \
                                          --connect-timeout 3 \
                                          --max-time 10 \
                                          "$AI_DASHBOARD_URL/api/health" \
                                          > "$CI_LOGS_DIR/dashboard-health-before-publish.json" \
                                          2> "$CI_LOGS_DIR/dashboard-health-before-publish-error.log"
                                        then
                                            dashboard_ready=true
                                            break
                                        fi

                                        sleep 2
                                    done
                                fi

                                if [ "$dashboard_ready" != true ]; then
                                    echo 'Dashboard publication skipped because the dashboard is still unreachable.' |
                                      tee "$CI_LOGS_DIR/dashboard-publish.log"

                                    docker compose \
                                      --project-name "$AI_DASHBOARD_PROJECT" \
                                      --env-file "$DASHBOARD_ENV" \
                                      --file "$DASHBOARD_COMPOSE" \
                                      logs \
                                      --no-color \
                                      --timestamps \
                                      "$AI_DASHBOARD_SERVICE" \
                                      >> "$CI_LOGS_DIR/dashboard-publish.log" \
                                      2>&1 || true

                                    exit 0
                                fi

                                if [ ! -f "$PUBLISH_SCRIPT" ]; then
                                    echo "Dashboard publisher is missing: $PUBLISH_SCRIPT" |
                                      tee "$CI_LOGS_DIR/dashboard-publish.log"
                                    exit 0
                                fi

                                BUILD_RESULT=FAILURE \
                                python3 "$PUBLISH_SCRIPT" \
                                  --report "$AI_OUTPUT_JSON" \
                                  --dashboard-url "$AI_DASHBOARD_URL" \
                                  --token "${AI_DASHBOARD_TOKEN:-}" \
                                  2>&1 |
                                  tee "$CI_LOGS_DIR/dashboard-publish.log"

                                PUBLISH_EXIT_CODE="${PIPESTATUS[0]}"

                                if [ "$PUBLISH_EXIT_CODE" -ne 0 ]; then
                                    echo "Dashboard publication failed with code $PUBLISH_EXIT_CODE."
                                    echo 'The AI report remains available as a Jenkins artifact.'
                                else
                                    echo 'AI failure analysis was published to the dashboard.'
                                fi

                                exit 0
                            '''
                        } else {
                            echo 'No valid AI JSON report was generated; dashboard publication skipped.'
                        }
                    }
                } else {
                    echo 'AI failure analysis is disabled for this build.'
                }
            }

            archiveArtifacts(
                artifacts: 'ci-logs/**/*.log, ai-failure-analysis.json, ai-failure-analysis.md, ai-raw-response.txt',
                allowEmptyArchive: true,
                fingerprint: true
            )
        }

        aborted {
            echo 'Pipeline aborted.'
        }

        cleanup {
            sh '''#!/usr/bin/env bash
                set +e
                set +x

                WORKSPACE_ROOT="$(pwd -P)"
                PROJECT="${CI_PROJECT:-flight-delay-ci-${BUILD_NUMBER}}"
                AI_NETWORK="${PROJECT}-ai-network"
                AI_OLLAMA_CONTAINER="${PROJECT}-ai-ollama"

                docker rm -f "$AI_OLLAMA_CONTAINER" \
                  > /dev/null 2>&1 || true

                docker network rm "$AI_NETWORK" \
                  > /dev/null 2>&1 || true

                export FRONTEND_REF
                export BACKEND_REF
                export BACKEND_HOST_PORT=0
                export FRONTEND_HOST_PORT=0
                export ANALYTICS_HOST_PORT=0
                export OLLAMA_IMAGE
                export OLLAMA_MODEL
                export OLLAMA_MODELS_VOLUME

                docker compose \
                  --project-name "$PROJECT" \
                  --file "$WORKSPACE_ROOT/$COMPOSE_FILE" \
                  down \
                  --volumes \
                  --remove-orphans \
                  > /dev/null 2>&1 || true
            '''

            echo 'The dedicated AI dashboard remains running on http://localhost:4173.'
            cleanWs()
        }
    }
}
