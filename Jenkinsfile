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

        string(
            name: 'OLLAMA_MODEL',
            defaultValue: 'qwen2.5-coder:7b-instruct',
            description: 'Ollama model used by the backend and integration tests'
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
        OLLAMA_MODEL         = 'qwen2.5-coder:7b-instruct'
        OLLAMA_MODELS_VOLUME = 'flight-delay-ollama-models'

        AI_ANALYZER_IMAGE = 'python:3.12-alpine'
        AI_SCRIPT         = 'scripts/ai/analyze_failure.py'
        AI_OUTPUT_JSON    = 'ai-failure-analysis.json'
        AI_OUTPUT_MD      = 'ai-failure-analysis.md'
        CI_LOGS_DIR       = 'ci-logs'

        REGISTRY_CREDENTIALS   = 'DockerHub'
        KUBECONFIG_CREDENTIALS = 'kind-flight-delay-kubeconfig'

        COMPOSE_FILE = 'docker-compose.yml'

        HELM_CHART   = 'deploy/helm/flight-delay'
        HELM_VALUES  = 'deploy/helm/flight-delay/values-dev.yaml'
        HELM_RELEASE = 'flight-delay-dev'

        KUBE_CONTEXT  = 'kind-flight-delay'
        K8S_NAMESPACE = 'flight-delay-helm'

        K8S_FRONTEND_URL  = 'http://localhost:8081'
        K8S_ANALYTICS_URL = 'http://localhost:8051'

        DOCKER_BUILDKIT = '1'
    }

    stages {
        stage('Checkout and Metadata') {
            steps {
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
                script {
                    if (!params.OLLAMA_MODEL?.trim()) {
                        error('OLLAMA_MODEL cannot be empty.')
                    }

                    env.OLLAMA_MODEL = params.OLLAMA_MODEL.trim()

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
                }
            }
        }

        stage('Validate Agent and Project') {
            steps {
                sh '''
                    set -eu

                    command -v git
                    command -v docker
                    docker compose version
                    command -v curl
                    command -v kubectl
                    command -v helm

                    test -f Jenkinsfile
                    test -f "$AI_SCRIPT"
                    test -f "$COMPOSE_FILE"

                    test -f backend/Dockerfile
                    test -f backend/requirements.txt
                    test -f backend/run.py
                    test -f backend/analytics.py
                    test -f backend/app/core/config.py

                    test -f frontend/Dockerfile
                    test -f frontend/nginx.conf
                    test -f frontend/package.json
                    test -f frontend/package-lock.json

                    test -f ml/models/v1_model.json
                    test -f data/flight_data.csv

                    test -f "$HELM_CHART/Chart.yaml"
                    test -f "$HELM_CHART/values.yaml"
                    test -f "$HELM_VALUES"
                    test -d "$HELM_CHART/templates"

                    echo "Agent and project validation succeeded."
                '''
            }
        }

        stage('Validate Docker Compose') {
            steps {
                sh '''#!/usr/bin/env bash
                    set -Eeuo pipefail

                    mkdir -p "$CI_LOGS_DIR"

                    export FRONTEND_REF
                    export BACKEND_REF
                    export BACKEND_HOST_PORT=5000
                    export FRONTEND_HOST_PORT=5173
                    export ANALYTICS_HOST_PORT=8050
                    export OLLAMA_HOST_PORT=11434
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
                    export OLLAMA_HOST_PORT=0
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

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T ollama \
                      ollama show "$OLLAMA_MODEL" \
                      > /dev/null

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      sh -eu -c '
                        response="$(
                          curl \
                            --fail \
                            --silent \
                            --show-error \
                            --max-time 600 \
                            --header "Content-Type: application/json" \
                            --data "{\"model\":\"${OLLAMA_MODEL}\",\"prompt\":\"Reply only with OK.\",\"stream\":false}" \
                            "${OLLAMA_BASE_URL}/api/generate"
                        )"

                        printf "%s" "$response" |
                          grep --quiet '"response"'
                      '

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
                        export OLLAMA_HOST_PORT=0
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
                        export OLLAMA_HOST_PORT=0
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

        stage('Check Kubernetes Access') {
            when {
                expression {
                    params.DEPLOY_KUBERNETES &&
                    params.PUBLISH_IMAGES &&
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
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

                        mkdir -p "$CI_LOGS_DIR"

                        MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b-instruct}"
                        PROJECT="${CI_PROJECT:-flight-delay-ci-${BUILD_NUMBER}}"
                        AI_NETWORK="${PROJECT}-ai-network"
                        AI_OLLAMA_CONTAINER="${PROJECT}-ai-ollama"

                        {
                            echo "Job: ${JOB_NAME:-unknown}"
                            echo "Build: ${BUILD_NUMBER:-unknown}"
                            echo "Build URL: ${BUILD_URL:-unknown}"
                            echo "Branch: ${SOURCE_BRANCH:-${BRANCH_NAME:-unknown}}"
                            echo "Commit: ${SHORT_SHA:-unknown}"
                            echo "Node: ${NODE_NAME:-unknown}"
                            echo "Workspace: ${WORKSPACE:-unknown}"
                            echo "Ollama model: $MODEL"
                        } > "$CI_LOGS_DIR/pipeline-context.log"

                        {
                            docker compose \
                              --project-name "$PROJECT" \
                              --file "$COMPOSE_FILE" \
                              ps --all || true

                            docker compose \
                              --project-name "$PROJECT" \
                              --file "$COMPOSE_FILE" \
                              logs \
                              --no-color \
                              --timestamps || true
                        } > "$CI_LOGS_DIR/final-compose-state.log" 2>&1

                        docker compose \
                          --project-name "$PROJECT" \
                          --file "$COMPOSE_FILE" \
                          down \
                          --volumes \
                          --remove-orphans \
                          > /dev/null 2>&1 || true

                        docker rm -f "$AI_OLLAMA_CONTAINER" \
                          > /dev/null 2>&1 || true
                        docker network rm "$AI_NETWORK" \
                          > /dev/null 2>&1 || true

                        docker volume inspect "$OLLAMA_MODELS_VOLUME" \
                          > /dev/null 2>&1 ||
                          docker volume create "$OLLAMA_MODELS_VOLUME" \
                          > /dev/null

                        docker network create "$AI_NETWORK" \
                          > /dev/null

                        docker run \
                          --detach \
                          --name "$AI_OLLAMA_CONTAINER" \
                          --network "$AI_NETWORK" \
                          --env OLLAMA_HOST=0.0.0.0:11434 \
                          --env OLLAMA_KEEP_ALIVE=10m \
                          --volume "$OLLAMA_MODELS_VOLUME:/root/.ollama" \
                          "$OLLAMA_IMAGE" \
                          > /dev/null

                        ollama_ready=false
                        for attempt in $(seq 1 60); do
                            if docker exec "$AI_OLLAMA_CONTAINER" \
                              ollama list > /dev/null 2>&1
                            then
                                ollama_ready=true
                                break
                            fi

                            sleep 2
                        done

                        if [ "$ollama_ready" != true ]; then
                            echo 'Ollama did not become ready for AI analysis.' |
                              tee "$CI_LOGS_DIR/ai-analysis-error.log"
                            docker logs "$AI_OLLAMA_CONTAINER" \
                              >> "$CI_LOGS_DIR/ai-analysis-error.log" 2>&1 || true
                            exit 0
                        fi

                        docker exec "$AI_OLLAMA_CONTAINER" \
                          ollama pull "$MODEL" \
                          2>&1 | tee "$CI_LOGS_DIR/ollama-model-pull.log"

                        docker run \
                          --rm \
                          --user "$(id -u):$(id -g)" \
                          --network "$AI_NETWORK" \
                          --volume "$WORKSPACE:/workspace" \
                          --workdir /workspace \
                          --env "OLLAMA_URL=http://${AI_OLLAMA_CONTAINER}:11434/api/chat" \
                          --env "OLLAMA_MODEL=$MODEL" \
                          --env "JOB_NAME=${JOB_NAME:-unknown}" \
                          --env "BUILD_NUMBER=${BUILD_NUMBER:-unknown}" \
                          --env "BUILD_URL=${BUILD_URL:-unknown}" \
                          --env "SOURCE_BRANCH=${SOURCE_BRANCH:-${BRANCH_NAME:-unknown}}" \
                          --env "SHORT_SHA=${SHORT_SHA:-unknown}" \
                          --env "NODE_NAME=${NODE_NAME:-unknown}" \
                          --env WORKSPACE=/workspace \
                          "$AI_ANALYZER_IMAGE" \
                          python "$AI_SCRIPT" \
                            --logs-dir "$CI_LOGS_DIR" \
                            --output-json "$AI_OUTPUT_JSON" \
                            --output-markdown "$AI_OUTPUT_MD" \
                          2>&1 | tee "$CI_LOGS_DIR/ai-analysis-run.log"

                        exit 0
                    '''
                } else {
                    echo 'AI failure analysis is disabled for this build.'
                }
            }

            archiveArtifacts(
                artifacts: 'ci-logs/**/*.log, ai-failure-analysis.json, ai-failure-analysis.md',
                allowEmptyArchive: true,
                fingerprint: true
            )
        }

        aborted {
            echo 'Pipeline aborted.'
        }

        always {
            sh '''#!/usr/bin/env bash
                set +e
                set +x

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
                export OLLAMA_HOST_PORT=0
                export OLLAMA_IMAGE
                export OLLAMA_MODEL
                export OLLAMA_MODELS_VOLUME

                docker compose \
                  --project-name "$PROJECT" \
                  --file "$COMPOSE_FILE" \
                  down \
                  --volumes \
                  --remove-orphans \
                  > /dev/null 2>&1 || true
            '''

            cleanWs()
        }
    }
}
