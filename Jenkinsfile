pipeline {
    agent {
        label 'linux && docker'
    }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '15'))
    }

    environment {
        // Docker Hub repositories
        FRONTEND_IMAGE = 'mehdibenzaied/flight-delay-frontend'
        BACKEND_IMAGE  = 'mehdibenzaied/flight-delay-backend'

        // Jenkins credential containing:
        // - Docker Hub username
        // - Docker Hub access token
        REGISTRY_CREDENTIALS = 'DockerHub'

        COMPOSE_FILE = 'docker-compose.yml'

        // Persistent local deployment name
        PROD_PROJECT = 'flight-delay-prod'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm

                script {
                    env.SHORT_SHA = sh(
                        script: 'git rev-parse --short=8 HEAD',
                        returnStdout: true
                    ).trim()

                    def configuredBranch = ''

                    try {
                        configuredBranch = scm.branches[0].name
                    } catch (ignored) {
                        configuredBranch = ''
                    }

                    def rawBranch =
                        env.BRANCH_NAME ?:
                        env.GIT_BRANCH ?:
                        configuredBranch ?:
                        'local'

                    rawBranch = rawBranch
                        .replaceFirst(/^\*\//, '')
                        .replaceFirst(/^origin\//, '')
                        .replaceFirst(/^refs\/heads\//, '')

                    env.SOURCE_BRANCH = rawBranch

                    env.SAFE_BRANCH = rawBranch.replaceAll(
                        '[^A-Za-z0-9_.-]',
                        '-'
                    )

                    env.IMAGE_TAG =
                        "${env.SAFE_BRANCH}-${env.SHORT_SHA}-${env.BUILD_NUMBER}"

                    env.FRONTEND_REF =
                        "${env.FRONTEND_IMAGE}:${env.IMAGE_TAG}"

                    env.BACKEND_REF =
                        "${env.BACKEND_IMAGE}:${env.IMAGE_TAG}"

                    env.CI_PROJECT =
                        "flight-delay-ci-${env.BUILD_NUMBER}"
                }

                echo "Branch:          ${env.SOURCE_BRANCH}"
                echo "Commit:          ${env.SHORT_SHA}"
                echo "Image tag:       ${env.IMAGE_TAG}"
                echo "Frontend image:  ${env.FRONTEND_REF}"
                echo "Backend image:   ${env.BACKEND_REF}"
                echo "Compose project: ${env.CI_PROJECT}"
            }
        }

        stage('Validate Project') {
            steps {
                sh '''
                    set -eu

                    echo "Checking required project files..."

                    test -f Jenkinsfile
                    test -f docker-compose.yml

                    test -f backend/Dockerfile
                    test -f backend/requirements.txt
                    test -f backend/run.py
                    test -f backend/analytics.py

                    test -f frontend/Dockerfile
                    test -f frontend/nginx.conf
                    test -f frontend/package.json
                    test -f frontend/package-lock.json

                    test -f ml/models/v1_model.json
                    test -f data/flight_data.csv

                    echo "All required project files are present."
                '''
            }
        }

        stage('Validate Compose') {
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

                    echo "Docker Compose configuration is valid."
                '''
            }
        }

        stage('Build Images') {
            parallel {
                stage('Build Frontend') {
                    steps {
                        sh '''
                            set -eu

                            echo "Building frontend image..."

                            docker build \
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

                            echo "Building backend image..."

                            # The project root is required as the build
                            # context because the image needs:
                            # - backend/
                            # - ml/
                            # - data/
                            docker build \
                              --target runtime \
                              --file backend/Dockerfile \
                              --tag "$BACKEND_REF" \
                              .
                        '''
                    }
                }
            }
        }

        stage('Inspect Images') {
            steps {
                sh '''
                    set -eu

                    echo "Built Docker images:"
                    echo

                    docker image inspect \
                      "$FRONTEND_REF" \
                      --format='Frontend: {{.RepoTags}} - {{.Size}} bytes'

                    docker image inspect \
                      "$BACKEND_REF" \
                      --format='Backend: {{.RepoTags}} - {{.Size}} bytes'
                '''
            }
        }

        stage('Compose Integration Test') {
            steps {
                sh '''
                    set -eu

                    export FRONTEND_REF
                    export BACKEND_REF

                    # Port 0 asks Docker to allocate temporary random
                    # host ports for the CI containers.
                    export BACKEND_HOST_PORT=0
                    export FRONTEND_HOST_PORT=0
                    export ANALYTICS_HOST_PORT=0

                    echo "Starting temporary integration environment..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      up \
                      --detach \
                      --wait \
                      --wait-timeout 240 \
                      --no-build

                    echo
                    echo "Container status:"

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      ps

                    echo
                    echo "Testing backend health endpoint..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      curl \
                        --fail \
                        --silent \
                        --show-error \
                        http://localhost:5000/health

                    echo
                    echo "Testing frontend..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T frontend \
                      wget \
                        --quiet \
                        --tries=1 \
                        --output-document=/dev/null \
                        http://localhost/

                    echo "Frontend test succeeded."

                    echo
                    echo "Testing analytics dashboard..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T analytics \
                      curl \
                        --fail \
                        --silent \
                        --show-error \
                        http://localhost:8050/ \
                        --output /dev/null

                    echo "Analytics test succeeded."

                    echo
                    echo "Checking prediction model..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      test -f /app/ml/models/v1_model.json

                    echo "Prediction model exists."

                    echo
                    echo "Checking analytics dataset..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T analytics \
                      test -f /app/datasets/flight_data.csv

                    echo "Analytics dataset exists."

                    echo
                    echo "Checking Python dependencies..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      python -c "
import gevent
import flask
import redis
import shap
import xgboost

print('Required Python dependencies are available')
"

                    echo
                    echo "Checking PredictionService methods..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      python -c "
from app.services.prediction_service import PredictionService

required_methods = [
    'get_prediction',
    'get_history',
    'fetch_weather',
]

missing_methods = [
    method
    for method in required_methods
    if not hasattr(PredictionService, method)
]

if missing_methods:
    raise RuntimeError(
        f'Missing PredictionService methods: {missing_methods}'
    )

print('PredictionService validation succeeded')
"

                    echo
                    echo "Integration tests succeeded."
                '''
            }

            post {
                unsuccessful {
                    sh '''
                        set +e

                        export FRONTEND_REF
                        export BACKEND_REF

                        export BACKEND_HOST_PORT=0
                        export FRONTEND_HOST_PORT=0
                        export ANALYTICS_HOST_PORT=0

                        echo
                        echo "========================================"
                        echo "Integration test failed"
                        echo "========================================"

                        echo
                        echo "Container status:"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          ps --all || true

                        echo
                        echo "========================================"
                        echo "Backend logs"
                        echo "========================================"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          logs \
                          --no-color \
                          --timestamps \
                          backend || true

                        echo
                        echo "========================================"
                        echo "Analytics logs"
                        echo "========================================"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          logs \
                          --no-color \
                          --timestamps \
                          analytics || true

                        echo
                        echo "========================================"
                        echo "Frontend logs"
                        echo "========================================"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          logs \
                          --no-color \
                          --timestamps \
                          frontend || true

                        echo
                        echo "========================================"
                        echo "Redis logs"
                        echo "========================================"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          logs \
                          --no-color \
                          --timestamps \
                          redis || true

                        echo
                        echo "========================================"
                        echo "Backend container inspection"
                        echo "========================================"

                        BACKEND_CONTAINER_ID="$(
                            docker compose \
                              --project-name "$CI_PROJECT" \
                              --file "$COMPOSE_FILE" \
                              ps --quiet backend
                        )"

                        if [ -n "$BACKEND_CONTAINER_ID" ]; then
                            docker inspect \
                              --format='Status: {{.State.Status}}' \
                              "$BACKEND_CONTAINER_ID" || true

                            docker inspect \
                              --format='Exit code: {{.State.ExitCode}}' \
                              "$BACKEND_CONTAINER_ID" || true

                            docker inspect \
                              --format='Health: {{json .State.Health}}' \
                              "$BACKEND_CONTAINER_ID" || true
                        fi
                    '''
                }

                cleanup {
                    sh '''
                        set +e

                        export FRONTEND_REF
                        export BACKEND_REF

                        export BACKEND_HOST_PORT=0
                        export FRONTEND_HOST_PORT=0
                        export ANALYTICS_HOST_PORT=0

                        echo
                        echo "Removing temporary integration environment..."

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

        stage('Deploy Locally') {
            when {
                expression {
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                script {
                    input(
                        message: "Deploy FlightDelayAI ${env.IMAGE_TAG} locally?",
                        ok: 'Deploy'
                    )
                }

                sh '''
                    set -eu

                    export FRONTEND_REF
                    export BACKEND_REF

                    export BACKEND_HOST_PORT=5000
                    export FRONTEND_HOST_PORT=5173
                    export ANALYTICS_HOST_PORT=8050

                    echo "Starting persistent local deployment..."

                    docker compose \
                      --project-name "$PROD_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      up \
                      --detach \
                      --wait \
                      --wait-timeout 240 \
                      --no-build \
                      --force-recreate \
                      --remove-orphans

                    echo
                    echo "Persistent deployment status:"

                    docker compose \
                      --project-name "$PROD_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      ps
                '''
            }
        }

        stage('Publish Images') {
            when {
                expression {
                    env.SOURCE_BRANCH == 'main' ||
                    env.SOURCE_BRANCH == 'develop'
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

                        echo "Pushing immutable image tags..."

                        docker push "$FRONTEND_REF"
                        docker push "$BACKEND_REF"

                        echo "Creating branch-specific latest tags..."

                        docker tag \
                          "$FRONTEND_REF" \
                          "$FRONTEND_IMAGE:$SAFE_BRANCH-latest"

                        docker tag \
                          "$BACKEND_REF" \
                          "$BACKEND_IMAGE:$SAFE_BRANCH-latest"

                        docker push \
                          "$FRONTEND_IMAGE:$SAFE_BRANCH-latest"

                        docker push \
                          "$BACKEND_IMAGE:$SAFE_BRANCH-latest"

                        if [ "$SOURCE_BRANCH" = "main" ]; then
                            echo "Creating global latest tags..."

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

        stage('Show Running Deployment') {
            when {
                expression {
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                sh '''
                    echo "Persistent deployment:"

                    docker compose \
                      --project-name "$PROD_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      ps

                    echo
                    echo "FlightDelayAI URLs:"
                    echo "Frontend:  http://localhost:5173"
                    echo "Backend:   http://localhost:5000"
                    echo "Analytics: http://localhost:8050"
                    echo "Health:    http://localhost:5000/health"
                '''
            }
        }
    }

    post {
        success {
            echo """
Pipeline succeeded.

Branch: ${env.SOURCE_BRANCH}
Tag:    ${env.IMAGE_TAG}
"""
        }

        failure {
            echo """
Pipeline failed.

Check the failing stage and the container logs printed above.
The persistent main deployment was not removed automatically.
"""
        }

        always {
            cleanWs()
        }
    }
}