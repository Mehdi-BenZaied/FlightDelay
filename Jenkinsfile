pipeline {
    agent {
        label 'linux-docker-agent'
    }

    parameters {
        booleanParam(
            name: 'PUBLISH_IMAGES',
            defaultValue: false,
            description: 'Push the backend and frontend images to Docker Hub'
        )

        booleanParam(
            name: 'DEPLOY_LOCALLY',
            defaultValue: false,
            description: 'Deploy the application locally after successful tests'
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

        // Only required when PUBLISH_IMAGES is enabled.
        REGISTRY_CREDENTIALS = 'DockerHub'

        COMPOSE_FILE = 'docker-compose.yml'

        // Name used for the persistent local deployment.
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

                echo """
==================================================
FlightDelay build information
==================================================
Branch:          ${env.SOURCE_BRANCH}
Commit:          ${env.SHORT_SHA}
Image tag:       ${env.IMAGE_TAG}
Frontend image:  ${env.FRONTEND_REF}
Backend image:   ${env.BACKEND_REF}
Compose project: ${env.CI_PROJECT}
==================================================
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

                    echo "All required files are present."
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

                    echo "Validating Docker Compose configuration..."

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

                            echo "Building frontend image: $FRONTEND_REF"

                            docker build \
                              --pull \
                              --progress=plain \
                              --target runtime \
                              --file frontend/Dockerfile \
                              --tag "$FRONTEND_REF" \
                              frontend

                            echo "Frontend image built successfully."
                        '''
                    }
                }

                stage('Build Backend') {
                    steps {
                        sh '''
                            set -eu

                            echo "Building backend image: $BACKEND_REF"

                            docker build \
                              --pull \
                              --progress=plain \
                              --target runtime \
                              --file backend/Dockerfile \
                              --tag "$BACKEND_REF" \
                              .

                            echo "Backend image built successfully."
                        '''
                    }
                }
            }
        }

        stage('Inspect Images') {
            steps {
                sh '''
                    set -eu

                    echo "Inspecting generated images..."

                    docker image inspect \
                      "$FRONTEND_REF" \
                      --format='Frontend size: {{.Size}} bytes'

                    docker image inspect \
                      "$BACKEND_REF" \
                      --format='Backend size: {{.Size}} bytes'
                '''
            }
        }

        stage('Compose Integration Test') {
            steps {
                sh '''
                    set -eu
                    set +x

                    export FRONTEND_REF
                    export BACKEND_REF

                    # Docker assigns random available host ports.
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
                    echo "Backend health test succeeded."

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
                    echo "Testing frontend React page..."

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

                    echo "Analytics dashboard test succeeded."

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
                    echo "Checking backend configuration import..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      python -c "from app.core.config import settings; print('Configuration import succeeded')"

                    echo
                    echo "Checking PredictionService import..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      python -c "from app.services.prediction_service import PredictionService; print('PredictionService import succeeded')"

                    echo
                    echo "Checking PredictionService methods..."

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      python -c "from app.services.prediction_service import PredictionService; methods = ('get_prediction', 'get_history', 'fetch_weather'); missing = [method for method in methods if not hasattr(PredictionService, method)]; assert not missing, f'Missing PredictionService methods: {missing}'; print('PredictionService methods validated successfully')"

                    echo
                    echo "=================================================="
                    echo "All integration tests succeeded."
                    echo "=================================================="
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

                        echo
                        echo "=================================================="
                        echo "Integration test failed"
                        echo "=================================================="

                        echo
                        echo "Container status:"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          ps --all || true

                        echo
                        echo "=================================================="
                        echo "Container logs"
                        echo "=================================================="

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          logs \
                          --no-color \
                          --timestamps || true

                        for service in redis backend analytics frontend
                        do
                            echo
                            echo "=================================================="
                            echo "Inspecting service: $service"
                            echo "=================================================="

                            CONTAINER_ID="$(
                                docker compose \
                                  --project-name "$CI_PROJECT" \
                                  --file "$COMPOSE_FILE" \
                                  ps --quiet "$service"
                            )"

                            if [ -n "$CONTAINER_ID" ]; then
                                docker inspect \
                                  --format='Container: {{.Name}}' \
                                  "$CONTAINER_ID" || true

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
                                echo "No container found for service: $service"
                            fi
                        done

                        echo
                        echo "=================================================="
                        echo "Frontend files"
                        echo "=================================================="

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          exec -T frontend \
                          ls -la /usr/share/nginx/html || true

                        echo
                        echo "=================================================="
                        echo "Frontend health request"
                        echo "=================================================="

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          exec -T frontend \
                          wget \
                            --server-response \
                            --output-document=- \
                            http://127.0.0.1/health || true

                        echo
                        echo "=================================================="
                        echo "Backend health request"
                        echo "=================================================="

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          exec -T backend \
                          curl \
                            --verbose \
                            http://127.0.0.1:5000/health || true
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
                            echo "Creating latest tags..."

                            docker tag \
                              "$FRONTEND_REF" \
                              "$FRONTEND_IMAGE:latest"

                            docker tag \
                              "$BACKEND_REF" \
                              "$BACKEND_IMAGE:latest"

                            docker push "$FRONTEND_IMAGE:latest"
                            docker push "$BACKEND_IMAGE:latest"
                        fi

                        echo "Docker images published successfully."
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
==================================================
FlightDelayAI deployment
==================================================
Frontend:  http://localhost:5173
Backend:   http://localhost:5000
Analytics: http://localhost:8050
Health:    http://localhost:5000/health
==================================================
"""
            }
        }
    }

    post {
        success {
            echo """
==================================================
Pipeline succeeded
==================================================
Branch: ${env.SOURCE_BRANCH}
Tag:    ${env.IMAGE_TAG}
==================================================
"""
        }

        failure {
            echo """
==================================================
Pipeline failed
==================================================
Check the failing stage and the diagnostic logs above.
==================================================
"""
        }

        aborted {
            echo 'Pipeline aborted.'
        }

        always {
            cleanWs()
        }
    }
}