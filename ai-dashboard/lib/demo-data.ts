import type { AnalysisStatus, FailureAnalysis } from "./analysis";

type DemoSeed = {
  build: number;
  day: string;
  time: string;
  stage: string;
  component: string;
  category: string;
  status: AnalysisStatus;
  confidence: number;
  summary: string;
  rootCause: string;
};

const seeds: DemoSeed[] = [
  {
    build: 24,
    day: "2026-07-30",
    time: "09:16:00",
    stage: "Compose Integration Tests",
    component: "backend",
    category: "network",
    status: "probable",
    confidence: 0.91,
    summary: "Redis connection refused during backend startup",
    rootCause:
      "The backend attempted to connect before Redis was reachable on the Compose network.",
  },
  {
    build: 23,
    day: "2026-07-30",
    time: "07:42:00",
    stage: "Unit Tests",
    component: "backend",
    category: "test_failure",
    status: "diagnosed",
    confidence: 0.88,
    summary: "Prediction contract test returned an unexpected payload",
    rootCause:
      "A response field changed without updating the backend contract test.",
  },
  {
    build: 22,
    day: "2026-07-29",
    time: "16:08:00",
    stage: "Build Docker Images",
    component: "frontend",
    category: "docker",
    status: "insufficient_evidence",
    confidence: 0.68,
    summary: "Frontend image build stopped during dependency installation",
    rootCause:
      "The available log excerpt ends before the package manager reports the underlying error.",
  },
  {
    build: 21,
    day: "2026-07-28",
    time: "14:31:00",
    stage: "Validate Helm Chart",
    component: "helm",
    category: "configuration",
    status: "diagnosed",
    confidence: 0.95,
    summary: "Helm rendering failed on a missing backend image tag",
    rootCause:
      "The development values file omitted the required backend image tag.",
  },
  {
    build: 20,
    day: "2026-07-28",
    time: "11:07:00",
    stage: "Docker Compose Integration Tests",
    component: "analytics",
    category: "resource_exhaustion",
    status: "probable",
    confidence: 0.84,
    summary: "Analytics health check timed out while the model loaded",
    rootCause:
      "Model initialization likely exhausted the memory available to Docker Desktop.",
  },
  {
    build: 19,
    day: "2026-07-28",
    time: "08:55:00",
    stage: "Publish Docker Images",
    component: "registry",
    category: "credentials",
    status: "diagnosed",
    confidence: 0.97,
    summary: "Docker Hub rejected the image push",
    rootCause: "The Jenkins Docker Hub credential was no longer valid.",
  },
  {
    build: 18,
    day: "2026-07-28",
    time: "07:23:00",
    stage: "Compose Integration Tests",
    component: "ollama",
    category: "resource_exhaustion",
    status: "insufficient_evidence",
    confidence: 0.7,
    summary: "Ollama stopped before returning a complete analysis",
    rootCause:
      "The logs show an interrupted response but do not include container resource metrics.",
  },
  {
    build: 17,
    day: "2026-07-27",
    time: "18:12:00",
    stage: "Validate Agent and Project",
    component: "jenkins-agent",
    category: "jenkins_agent",
    status: "diagnosed",
    confidence: 0.93,
    summary: "The Jenkins agent could not access the Docker daemon",
    rootCause:
      "Docker Desktop integration was disabled for the Ubuntu WSL distribution.",
  },
  {
    build: 16,
    day: "2026-07-27",
    time: "15:40:00",
    stage: "Compose Integration Tests",
    component: "frontend",
    category: "network",
    status: "probable",
    confidence: 0.82,
    summary: "Frontend health check could not reach the backend",
    rootCause:
      "The frontend used a host-only backend address from inside the Compose network.",
  },
  {
    build: 15,
    day: "2026-07-27",
    time: "10:18:00",
    stage: "Build Docker Images",
    component: "backend",
    category: "configuration",
    status: "diagnosed",
    confidence: 0.9,
    summary: "Backend image could not locate the model artifact",
    rootCause:
      "The Docker build context excluded the model directory required at runtime.",
  },
  {
    build: 14,
    day: "2026-07-26",
    time: "17:03:00",
    stage: "Optional Kubernetes Deployment",
    component: "backend",
    category: "kubernetes",
    status: "insufficient_evidence",
    confidence: 0.65,
    summary: "Backend Pod did not become ready before the smoke test",
    rootCause:
      "Pod events and readiness-probe output were not included in the archived logs.",
  },
  {
    build: 13,
    day: "2026-07-25",
    time: "13:27:00",
    stage: "Docker Compose Integration Tests",
    component: "database",
    category: "database",
    status: "diagnosed",
    confidence: 0.94,
    summary: "SQLite database directory was not writable",
    rootCause:
      "The mounted data directory was owned by a different host user.",
  },
  {
    build: 12,
    day: "2026-07-25",
    time: "09:02:00",
    stage: "Checkout and Metadata",
    component: "source",
    category: "source_control",
    status: "diagnosed",
    confidence: 0.87,
    summary: "Git checkout failed while resolving the requested revision",
    rootCause:
      "The pipeline referenced a branch that had already been deleted remotely.",
  },
  {
    build: 11,
    day: "2026-07-24",
    time: "16:46:00",
    stage: "Compose Integration Tests",
    component: "backend",
    category: "backend",
    status: "insufficient_evidence",
    confidence: 0.66,
    summary: "Backend process exited before exposing its health endpoint",
    rootCause:
      "The archived excerpt does not contain the Python traceback needed to isolate the failure.",
  },
];

export const demoAnalyses: FailureAnalysis[] = seeds.map((seed) => ({
  id: `demo-${seed.build}`,
  sourceKey: `FlightDelay/main#${seed.build}`,
  jobName: "FlightDelay/main",
  buildNumber: seed.build,
  buildUrl: `http://localhost:8080/job/FlightDelay/job/main/${seed.build}/`,
  buildResult: "FAILURE",
  timestamp: `${seed.day}T${seed.time}+02:00`,
  durationMs: 322_000 + seed.build * 7_500,
  branch: "main",
  commitSha: `de0642${seed.build.toString(16).padStart(2, "0")}`,
  model: "qwen2.5-coder:3b-instruct",
  analysisStatus: seed.status,
  summary: seed.summary,
  failedStage: seed.stage,
  failedComponent: seed.component,
  category: seed.category,
  rootCause: seed.rootCause,
  secondaryErrors:
    seed.build === 24
      ? ["Backend health check failed after Redis became unavailable."]
      : [],
  evidence: [
    {
      logFile: "ci-logs/compose-tests.log",
      excerpt:
        seed.build === 24
          ? "redis.exceptions.ConnectionError: Error 111 connecting to redis:6379. Connection refused."
          : seed.summary,
      interpretation: seed.rootCause,
    },
  ],
  checks: [
    {
      platform: "WSL",
      command: "docker compose ps && docker compose logs --tail=80",
      purpose: "Verify the failing service and the first relevant error.",
      expectedResult: "The affected service and its dependency state are visible.",
    },
  ],
  remediationSteps: [
    {
      priority: "high",
      action: "Confirm the dependency is healthy before retrying the application.",
      command: "docker compose ps redis",
      risk: "safe",
    },
  ],
  prevention: ["Keep dependency health checks as pipeline gates."],
  missingInformation:
    seed.status === "insufficient_evidence"
      ? ["Complete component logs from the first failure window."]
      : [],
  confidence: seed.confidence,
  importedAt: `${seed.day}T${seed.time}+02:00`,
}));

