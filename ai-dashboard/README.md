# FlightDelay AI Failure Dashboard

A React operations dashboard that stores and visualizes the JSON diagnosis
already produced by the FlightDelay Jenkins pipeline.

The integration keeps `scripts/ai/analyze_failure.py` unchanged. Jenkins
publishes the generated JSON report immediately after a failed build; an
optional read-only collector remains available for importing older artifacts.
Each Jenkins job/build pair is stored idempotently.

## Architecture

```text
Failed Jenkins build
        │
        ├─ archived ai-failure-analysis.json
        │
        ▼
Jenkins publisher (immediate) or optional collector
        │
        ├─ build metadata + analyzer JSON
        ▼
Dashboard ingestion API
        │
        ├─ normalized SQLite/D1 record
        ▼
React dashboard
```

The collector polls Jenkins every 60 seconds by default. It downloads the
existing `ai-failure-analysis.json` artifact only for failed or unstable builds,
then sends the artifact plus Jenkins metadata to `POST /api/analyses`.

## What is included

- Calm Operations React interface with Overview, Failures, Trends, and Settings.
- Durable SQLite-compatible D1 storage and committed database migration.
- Idempotent ingestion API secured by a configurable token.
- Manual JSON import for testing without waiting for another failure.
- Independent, standard-library Python Jenkins collector.
- Additive `docker-compose.dashboard.yml`; the application Compose file is left
  untouched.
- Responsive layout, keyboard-accessible chart filters, sortable tables, search,
  and diagnosis details.

## Run on localhost with Docker

From the repository root:

```bash
cp ai-dashboard/.env.example ai-dashboard/.env
docker compose \
  --env-file ai-dashboard/.env \
  -f ai-dashboard/docker-compose.dashboard.yml \
  up -d --build flightdelay-ai-dashboard
```

Open <http://localhost:4173>. Dashboard data is persisted in the
`flightdelay-ai-dashboard-data` Docker volume.

Keep `AI_DASHBOARD_URL=http://localhost:4173` when Jenkins and the dashboard
run on the same host. Localhost ingestion works without a token. For a remote
dashboard, set the same secret as `DASHBOARD_INGEST_TOKEN` in the Jenkins
environment variable `AI_DASHBOARD_TOKEN`.

The publication step is best-effort: if the dashboard is unavailable, it logs
the upload error and preserves the AI report as a Jenkins artifact without
hiding the pipeline's original failure.

## Run without Docker

Requirements:

- Node.js 22.13 or newer
- npm

Install and run:

```bash
npm ci
npm run dev
```

The dashboard uses demo data until the first analysis is stored. You can test
the complete storage contract from **Settings → Import a JSON report**.

For automated ingestion, configure a strong `DASHBOARD_INGEST_TOKEN` in the
dashboard runtime. Generate one locally, for example:

```bash
openssl rand -hex 32
```

Do not commit the generated value. The collector must receive the same value.

## Jenkins collector setup

Copy the example outside version control:

```bash
cp integrations/.env.collector.example .env.collector
```

Set these values:

```dotenv
JENKINS_BASE_URL=http://host.docker.internal:8080
JENKINS_JOB_PATH=job/FlightDelay/job/main
JENKINS_USER=jenkins-read-user
JENKINS_API_TOKEN=replace-me

DASHBOARD_URL=https://your-dashboard.example
DASHBOARD_INGEST_TOKEN=the-same-value-as-the-dashboard
```

`JENKINS_JOB_PATH` follows Jenkins’ nested job URL format. For example,
`FlightDelay/main` becomes `job/FlightDelay/job/main`.

Start only the collector:

```bash
docker compose \
  --env-file .env.collector \
  -f docker-compose.dashboard.yml \
  up -d --build
```

The collector state is stored in the named
`flightdelay-ai-collector-data` volume. Dashboard inserts are also idempotent,
so deleting that collector state does not duplicate stored builds.

If the dashboard is private behind Sites access control, also set the optional
`SITES_ACCESS_TOKEN` value accepted by that private deployment.

## Jenkins permissions

Use a dedicated read-only Jenkins account. It only needs to:

- read the selected job and build metadata;
- list archived artifacts;
- download `ai-failure-analysis.json`.

It does not need build, configure, cancel, replay, credential, or administrator
permissions.

## Ingestion contract

The collector wraps the analyzer result without modifying it:

```json
{
  "jenkins": {
    "job_name": "FlightDelay/main",
    "build_number": 24,
    "build_url": "http://jenkins/job/FlightDelay/job/main/24/",
    "result": "FAILURE",
    "timestamp": 1785400000000,
    "duration_ms": 125000,
    "branch": "main",
    "commit_sha": "de0642b4",
    "model": "qwen2.5-coder:3b-instruct"
  },
  "analysis": {
    "analysis_status": "probable",
    "summary": "Redis connection refused during backend startup",
    "failed_stage": "Compose Integration Tests",
    "failed_component": "backend",
    "category": "network",
    "root_cause": "Redis was unavailable when the backend started.",
    "secondary_errors": [],
    "evidence": [],
    "checks": [],
    "remediation_steps": [],
    "prevention": [],
    "missing_information": [],
    "confidence": 0.91
  }
}
```

The full `analysis` object follows the existing
`analyze_failure.py` output schema.

## Validation

```bash
npm run lint
python -m unittest integrations/test_jenkins_collector.py
npm run build
```

After changing `db/schema.ts`, regenerate and inspect the migration:

```bash
npm run db:generate
```

## Important files

```text
app/dashboard.tsx                 React dashboard and interactions
app/api/analyses/route.ts         Query and ingestion API
app/api/health/route.ts           Storage health endpoint
db/analysis-repository.ts         Persistent analysis repository
db/schema.ts                      Relational schema
drizzle/                          Generated migration
integrations/jenkins_collector.py Read-only Jenkins artifact collector
docker-compose.dashboard.yml      Optional collector service
```
