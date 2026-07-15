pipeline {
    agent {
        label 'linux && docker'
    }

    parameters {
        booleanParam(
            name: 'PUBLISH_IMAGES',
            defaultValue: false,
            description: 'Push successful images to Docker Hub'
        )

        booleanParam(
            name: 'DEPLOY_LOCALLY',
            defaultValue: false,
            description: 'Deploy the successful main branch build locally'
        )
    }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timestamps()

        timeout(
            time: 45,
            unit: 'MINUTES'
        )

        buildDiscarder(
            logRotator(
                numToKeepStr: '15'
            )
        )
    }

    environment {
        FRONTEND_IMAGE = 'mehdibenzaied/flight-delay-frontend'
        BACKEND_IMAGE  = 'mehdibenzaied/flight-delay-backend'

        REGISTRY_CREDENTIALS = 'DockerHub'

        COMPOSE_FILE = 'docker-compose.yml'
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

                    def checkedOutBranch = sh(
                        script: 'git branch --show-current || true',
                        returnStdout: true
                    ).trim()

                    def rawBranch =
                        env.BRANCH_NAME ?:
                        env.GIT_BRANCH ?:
                        checkedOutBranch ?:
                        'main'

                    rawBranch = rawBranch
                        .replaceFirst(/^\*\//, '')
                        .replaceFirst(/^origin\//, '')
                        .replaceFirst(/^refs\/heads\//, '')

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
                }

                echo """
Branch:          ${env.SOURCE_BRANCH}
Commit:          ${env.SHORT_SHA}
Image tag:       ${env.IMAGE_TAG}
Frontend image:  ${env.FRONTEND_REF}
Backend image:   ${env.BACKEND_REF}
Compose project: ${env.CI_PROJECT}
"""
            }
        }

        stage('Validate Project') {
            steps {
                sh '''
                    set -eu

                    echo "Checking required project files..."

                    test -f Jenkinsfile
                    test -f docker-compose.yml
                    test -f .dockerignore

                    test -f backend/Dockerfile
                    test -f backend/requirements.txt
                    test -f backend/run.py
                    test -f backend/analytics.py
                    test -f backend/app/core/config.py

                    test -f frontend/Dockerfile
                    test -f frontend/nginx.conf
                    test -f frontend/.dockerignore
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
                stage('Build Backend') {
                    steps {
                        sh '''
                            set -eu

                            echo "Building backend image..."

                            docker build \
                              --progress=plain \
                              --target runtime \
                              --file backend/Dockerfile \
                              --tag "$BACKEND_REF" \
                              .

                            echo "Backend image built successfully."
                        '''
                    }
                }

                stage('Build Frontend') {
                    steps {
                        sh '''
                            set -eu

                            echo "Building frontend image..."

                            docker build \
                              --progress=plain \
                              --target runtime \
                              --file frontend/Dockerfile \
                              --tag "$FRONTEND_REF" \
                              frontend

                            echo "Frontend image built successfully."
                        '''
                    }
                }
            }
        }

        stage('Inspect Images') {
            steps {
                sh '''
                    set -eu

                    docker image inspect \
                      "$BACKEND_REF" \
                      --format='Backend image: {{.RepoTags}} - {{.Size}} bytes'

                    docker image inspect \
                      "$FRONTEND_REF" \
                      --format='Frontend image: {{.RepoTags}} - {{.Size}} bytes'
                '''
            }
        }

        stage('Compose Integration Test') {
            steps {
                sh '''
                    set -eu

                    export FRONTEND_REF
                    export BACKEND_REF

                    # Docker assigns random host ports for CI.
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
                      --wait-timeout 300 \
                      --no-build

                    echo
                    echo "Container status:"

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      ps

                    echo
                    echo "Testing Redis..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T redis \
                      redis-cli ping |
                      grep --quiet '^PONG$'

                    echo "Redis test succeeded."

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
                        http://127.0.0.1:5000/health

                    echo
                    echo "Backend test succeeded."

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
                        --output /dev/null \
                        http://127.0.0.1:8050/

                    echo "Analytics test succeeded."

                    echo
                    echo "Testing frontend health endpoint..."

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

                    echo "Frontend health test succeeded."

                    echo
                    echo "Testing React application page..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T frontend \
                      wget \
                        --quiet \
                        --tries=1 \
                        --output-document=/dev/null \
                        http://127.0.0.1/

                    echo "Frontend page test succeeded."

                    echo
                    echo "Checking frontend build output..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T frontend \
                      test -f /usr/share/nginx/html/index.html

                    echo "Frontend index.html exists."

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
                    echo "Checking backend Python imports..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      python -c "
from app import create_app
from app.core.config import settings
from app.services.prediction_service import PredictionService

print('Backend imports succeeded')
"

                    echo
                    echo "All integration tests succeeded."
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
                        echo "Container logs:"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          logs \
                          --no-color \
                          --timestamps || true

                        for service in redis backend analytics frontend
                        do
                            echo
                            echo "========================================"
                            echo "$service inspection"
                            echo "========================================"

                            CONTAINER_ID="$(
                                docker compose \
                                  --project-name "$CI_PROJECT" \
                                  --file "$COMPOSE_FILE" \
                                  ps --quiet "$service"
                            )"

                            if [ -n "$CONTAINER_ID" ]; then
                                docker inspect \
                                  --format='Status: {{.State.Status}}' \
                                  "$CONTAINER_ID" || true

                                docker inspect \
                                  --format='Exit code: {{.State.ExitCode}}' \
                                  "$CONTAINER_ID" || true

                                docker inspect \
                                  --format='Health: {{json .State.Health}}' \
                                  "$CONTAINER_ID" || true
                            else
                                echo "No container was created for $service."
                            fi
                        done

                        echo
                        echo "Frontend files:"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          exec -T frontend \
                          ls -la /usr/share/nginx/html || true

                        echo
                        echo "Frontend Nginx configuration:"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          exec -T frontend \
                          nginx -T || true

                        echo
                        echo "Direct frontend health request:"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          exec -T frontend \
                          wget \
                            --server-response \
                            --output-document=- \
                            http://127.0.0.1/health || true
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

        stage('Publish Images') {
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

                        docker push "$BACKEND_REF"
                        docker push "$FRONTEND_REF"

                        docker tag \
                          "$BACKEND_REF" \
                          "$BACKEND_IMAGE:$SAFE_BRANCH-latest"

                        docker tag \
                          "$FRONTEND_REF" \
                          "$FRONTEND_IMAGE:$SAFE_BRANCH-latest"

                        docker push \
                          "$BACKEND_IMAGE:$SAFE_BRANCH-latest"

                        docker push \
                          "$FRONTEND_IMAGE:$SAFE_BRANCH-latest"

                        if [ "$SOURCE_BRANCH" = "main" ]; then
                            docker tag \
                              "$BACKEND_REF" \
                              "$BACKEND_IMAGE:latest"

                            docker tag \
                              "$FRONTEND_REF" \
                              "$FRONTEND_IMAGE:latest"

                            docker push "$BACKEND_IMAGE:latest"
                            docker push "$FRONTEND_IMAGE:latest"
                        fi
                    '''
                }
            }
        }

        stage('Deploy Locally') {
            when {
                expression {
                    params.DEPLOY_LOCALLY &&
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                sh '''
                    set -eu

                    export FRONTEND_REF
                    export BACKEND_REF

                    export BACKEND_HOST_PORT=5000
                    export FRONTEND_HOST_PORT=5173
                    export ANALYTICS_HOST_PORT=8050

                    echo "Deploying persistent local environment..."

                    docker compose \
                      --project-name "$PROD_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      up \
                      --detach \
                      --wait \
                      --wait-timeout 300 \
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

        stage('Show Deployment') {
            when {
                expression {
                    params.DEPLOY_LOCALLY &&
                    env.SOURCE_BRANCH == 'main'
                }
            }

            steps {
                echo """
FlightDelayAI is running:

Frontend:  http://localhost:5173
Backend:   http://localhost:5000
Analytics: http://localhost:8050
Health:    http://localhost:5000/health
"""
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
"""
        }

        always {
            cleanWs()
        }
    }
}