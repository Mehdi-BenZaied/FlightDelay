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
    }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 60, unit: 'MINUTES')
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
                sh '''
                    set -eu

                    export FRONTEND_REF
                    export BACKEND_REF
                    export BACKEND_HOST_PORT=5000
                    export FRONTEND_HOST_PORT=5173
                    export ANALYTICS_HOST_PORT=8050

                    docker compose \
                      --file "$COMPOSE_FILE" \
                      config --quiet
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
                        sh '''
                            set -eu

                            docker build \
                              --pull \
                              --progress=plain \
                              --target runtime \
                              --file frontend/Dockerfile \
                              --tag "$FRONTEND_REF" \
                              frontend
                        '''
                    }
                }

                stage('Build Backend') {
                    steps {
                        sh '''
                            set -eu

                            docker build \
                              --pull \
                              --progress=plain \
                              --target runtime \
                              --file backend/Dockerfile \
                              --tag "$BACKEND_REF" \
                              .
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
                sh '''
                    set -eu
                    set +x

                    export FRONTEND_REF
                    export BACKEND_REF
                    export BACKEND_HOST_PORT=0
                    export FRONTEND_HOST_PORT=0
                    export ANALYTICS_HOST_PORT=0

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      up \
                      --detach \
                      --wait \
                      --wait-timeout 300 \
                      --no-build

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      ps

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
                    sh '''
                        set +e
                        set +x

                        export FRONTEND_REF
                        export BACKEND_REF
                        export BACKEND_HOST_PORT=0
                        export FRONTEND_HOST_PORT=0
                        export ANALYTICS_HOST_PORT=0

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          ps --all || true

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          logs \
                          --no-color \
                          --timestamps || true
                    '''
                }

                cleanup {
                    sh '''
                        set +e
                        set +x

                        export FRONTEND_REF
                        export BACKEND_REF
                        export BACKEND_HOST_PORT=0
                        export FRONTEND_HOST_PORT=0
                        export ANALYTICS_HOST_PORT=0

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
                        sh '''
                            set +e

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
            echo 'Pipeline failed. Check the failing stage and diagnostic logs.'
        }

        aborted {
            echo 'Pipeline aborted.'
        }

        always {
            cleanWs()
        }
    }
}
