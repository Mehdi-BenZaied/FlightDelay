import type {
  AnalysisStatus,
  DiagnosticCheck,
  EvidenceItem,
  FailureAnalysis,
  RemediationStep,
} from "./analysis";

type UnknownRecord = Record<string, unknown>;

const allowedStatuses = new Set<AnalysisStatus>([
  "diagnosed",
  "probable",
  "insufficient_evidence",
]);

function record(value: unknown, label: string): UnknownRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be a JSON object`);
  }
  return value as UnknownRecord;
}

function requiredString(value: unknown, label: string) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} is required`);
  }
  return value.trim();
}

function optionalString(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function finiteNumber(value: unknown, label: string) {
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) throw new Error(`${label} must be a number`);
  return number;
}

function stringArray(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function evidenceArray(value: unknown): EvidenceItem[] {
  if (!Array.isArray(value)) return [];
  return value.map((item, index) => {
    const entry = record(item, `analysis.evidence[${index}]`);
    return {
      logFile: requiredString(entry.log_file, `analysis.evidence[${index}].log_file`),
      excerpt: requiredString(entry.excerpt, `analysis.evidence[${index}].excerpt`),
      interpretation: requiredString(
        entry.interpretation,
        `analysis.evidence[${index}].interpretation`,
      ),
    };
  });
}

function checksArray(value: unknown): DiagnosticCheck[] {
  if (!Array.isArray(value)) return [];
  return value.map((item, index) => {
    const entry = record(item, `analysis.checks[${index}]`);
    return {
      platform: requiredString(
        entry.platform,
        `analysis.checks[${index}].platform`,
      ),
      command: requiredString(
        entry.command,
        `analysis.checks[${index}].command`,
      ),
      purpose: requiredString(
        entry.purpose,
        `analysis.checks[${index}].purpose`,
      ),
      expectedResult: requiredString(
        entry.expected_result,
        `analysis.checks[${index}].expected_result`,
      ),
    };
  });
}

function remediationArray(value: unknown): RemediationStep[] {
  if (!Array.isArray(value)) return [];
  return value.map((item, index) => {
    const entry = record(item, `analysis.remediation_steps[${index}]`);
    const priority = requiredString(
      entry.priority,
      `analysis.remediation_steps[${index}].priority`,
    );
    const risk = requiredString(
      entry.risk,
      `analysis.remediation_steps[${index}].risk`,
    );
    if (!["high", "medium", "low"].includes(priority)) {
      throw new Error(`analysis.remediation_steps[${index}].priority is invalid`);
    }
    if (!["safe", "review_required", "destructive"].includes(risk)) {
      throw new Error(`analysis.remediation_steps[${index}].risk is invalid`);
    }
    return {
      priority: priority as RemediationStep["priority"],
      action: requiredString(
        entry.action,
        `analysis.remediation_steps[${index}].action`,
      ),
      command: optionalString(entry.command, ""),
      risk: risk as RemediationStep["risk"],
    };
  });
}

function timestampFrom(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Date(value).toISOString();
  }
  const candidate = optionalString(value, new Date().toISOString());
  const parsed = new Date(candidate);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("jenkins.timestamp must be an ISO timestamp or epoch milliseconds");
  }
  return parsed.toISOString();
}

export type IngestedAnalysis = {
  analysis: FailureAnalysis;
  rawJson: string;
};

export function normalizeIngestPayload(payload: unknown): IngestedAnalysis {
  const envelope = record(payload, "payload");
  const analysisPayload = record(
    envelope.analysis ?? envelope,
    "analysis",
  );
  const jenkins = record(envelope.jenkins ?? {}, "jenkins");

  const status = requiredString(
    analysisPayload.analysis_status,
    "analysis.analysis_status",
  );
  if (!allowedStatuses.has(status as AnalysisStatus)) {
    throw new Error("analysis.analysis_status is invalid");
  }

  const confidence = finiteNumber(
    analysisPayload.confidence,
    "analysis.confidence",
  );
  if (confidence < 0 || confidence > 1) {
    throw new Error("analysis.confidence must be between 0 and 1");
  }

  const buildNumber = Math.trunc(
    finiteNumber(jenkins.build_number ?? jenkins.buildNumber, "jenkins.build_number"),
  );
  if (buildNumber < 0) {
    throw new Error("jenkins.build_number must be zero or greater");
  }

  const jobName = optionalString(
    jenkins.job_name ?? jenkins.jobName,
    "FlightDelay",
  );
  const sourceKey = optionalString(
    jenkins.source_key ?? jenkins.sourceKey,
    `${jobName}#${buildNumber}`,
  );
  const importedAt = new Date().toISOString();

  const normalized: FailureAnalysis = {
    id: sourceKey,
    sourceKey,
    jobName,
    buildNumber,
    buildUrl: optionalString(jenkins.build_url ?? jenkins.buildUrl, ""),
    buildResult: optionalString(
      jenkins.result ?? jenkins.build_result ?? jenkins.buildResult,
      "FAILURE",
    ),
    timestamp: timestampFrom(jenkins.timestamp),
    durationMs: Math.max(
      0,
      Math.trunc(
        finiteNumber(
          jenkins.duration_ms ?? jenkins.durationMs ?? 0,
          "jenkins.duration_ms",
        ),
      ),
    ),
    branch: optionalString(jenkins.branch, "unknown"),
    commitSha: optionalString(
      jenkins.commit_sha ?? jenkins.commitSha,
      "unknown",
    ),
    model: optionalString(jenkins.model, "unknown"),
    analysisStatus: status as AnalysisStatus,
    summary: requiredString(analysisPayload.summary, "analysis.summary"),
    failedStage: requiredString(
      analysisPayload.failed_stage,
      "analysis.failed_stage",
    ),
    failedComponent: requiredString(
      analysisPayload.failed_component,
      "analysis.failed_component",
    ),
    category: requiredString(analysisPayload.category, "analysis.category"),
    rootCause: requiredString(
      analysisPayload.root_cause,
      "analysis.root_cause",
    ),
    secondaryErrors: stringArray(analysisPayload.secondary_errors),
    evidence: evidenceArray(analysisPayload.evidence),
    checks: checksArray(analysisPayload.checks),
    remediationSteps: remediationArray(analysisPayload.remediation_steps),
    prevention: stringArray(analysisPayload.prevention),
    missingInformation: stringArray(analysisPayload.missing_information),
    confidence,
    importedAt,
  };

  return { analysis: normalized, rawJson: JSON.stringify(analysisPayload) };
}

