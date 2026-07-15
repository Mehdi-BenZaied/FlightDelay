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

        // Jenkins username/password credential for Docker Hub
        REGISTRY_CREDENTIALS = 'DockerHub'

        // Jenkins Secret Text credentials
        SECRET_KEY      = credentials('FlightDelaySecretKey')
        WEATHER_API_KEY = credentials('OpenWeatherApiKey')

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
                echo "Frontend image:  ${env.FRONTEND_REF}"
                echo "Backend image:   ${env.BACKEND_REF}"
                echo "Compose project: ${env.CI_PROJECT}"
            }
        }

        stage('Validate Project') {
            steps {
                sh '''
                    set -eu

                    test -f backend/Dockerfile
                    test -f backend/requirements.txt
                    test -f backend/run.py
                    test -f backend/analytics.py

                    test -f frontend/Dockerfile
                    test -f frontend/package.json
                    test -f frontend/package-lock.json
                    test -f frontend/nginx.conf

                    test -f ml/models/v1_model.json
                    test -f data/flight_data.csv
                    test -f "$COMPOSE_FILE"

                    echo "Required project files are present."
                '''
            }
        }

        stage('Validate Compose') {
            steps {
                sh '''
                    set +x

                    export FRONTEND_REF
                    export BACKEND_REF
                    export SECRET_KEY
                    export WEATHER_API_KEY

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

                            docker build \
                              --pull \
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

                            # The project root is the build context because
                            # the backend image requires backend/, ml/ and data/.
                            docker build \
                              --pull \
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
                    docker image inspect "$FRONTEND_REF" \
                      --format='Frontend size: {{.Size}} bytes'

                    docker image inspect "$BACKEND_REF" \
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
                    export SECRET_KEY
                    export WEATHER_API_KEY

                    # Docker assigns temporary random host ports.
                    export BACKEND_HOST_PORT=0
                    export FRONTEND_HOST_PORT=0
                    export ANALYTICS_HOST_PORT=0

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      up \
                      --detach \
                      --wait \
                      --no-build

                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      ps

                    echo "Testing backend health..."
                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      curl --fail --silent --show-error \
                      http://localhost:5000/health

                    echo
                    echo "Testing frontend..."
                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T frontend \
                      wget --quiet --output-document=- \
                      http://localhost/ > /dev/null

                    echo "Testing analytics dashboard..."
                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T analytics \
                      curl --fail --silent --show-error \
                      http://localhost:8050/ > /dev/null

                    echo "Checking prediction model..."
                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T backend \
                      test -f /app/ml/models/v1_model.json

                    echo "Checking analytics dataset..."
                    docker compose \
                      --project-name "$CI_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      exec -T analytics \
                      test -f /app/datasets/flight_data.csv

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

                    missing = [
                        name
                        for name in required_methods
                        if not hasattr(PredictionService, name)
                    ]

                    if missing:
                        raise RuntimeError(
                            f'Missing PredictionService methods: {missing}'
                        )

                    print('PredictionService validation succeeded')
                    "
                '''
            }

            post {
                unsuccessful {
                    sh '''
                        set +x

                        export FRONTEND_REF
                        export BACKEND_REF
                        export SECRET_KEY
                        export WEATHER_API_KEY

                        export BACKEND_HOST_PORT=0
                        export FRONTEND_HOST_PORT=0
                        export ANALYTICS_HOST_PORT=0

                        echo "Integration test failed. Container logs:"

                        docker compose \
                          --project-name "$CI_PROJECT" \
                          --file "$COMPOSE_FILE" \
                          logs --no-color || true
                    '''
                }

                always {
                    sh '''
                        set +x

                        export FRONTEND_REF
                        export BACKEND_REF
                        export SECRET_KEY
                        export WEATHER_API_KEY

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
                    set +x

                    export FRONTEND_REF
                    export BACKEND_REF
                    export SECRET_KEY
                    export WEATHER_API_KEY

                    export BACKEND_HOST_PORT=5000
                    export FRONTEND_HOST_PORT=5173
                    export ANALYTICS_HOST_PORT=8050

                    docker compose \
                      --project-name "$PROD_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      up \
                      --detach \
                      --wait \
                      --no-build \
                      --force-recreate \
                      --remove-orphans

                    echo
                    echo "Persistent local deployment:"

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

                        echo "$REGISTRY_TOKEN" |
                          docker login \
                            --username "$REGISTRY_USER" \
                            --password-stdin

                        # Immutable build tags
                        docker push "$FRONTEND_REF"
                        docker push "$BACKEND_REF"

                        # Branch-specific latest tags
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

                        # Global latest tags only for main
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

                        docker logout
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
                    docker compose \
                      --project-name "$PROD_PROJECT" \
                      --file "$COMPOSE_FILE" \
                      ps

                    echo
                    echo "FlightDelayAI is available at:"
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

            Check the failing stage and its container logs.
            The persistent main deployment may still be running.
            """
        }

        always {
            cleanWs()
        }
    }
}