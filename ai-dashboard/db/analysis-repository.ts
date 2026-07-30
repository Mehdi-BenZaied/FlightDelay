import type { FailureAnalysis } from "../lib/analysis";
import type { IngestedAnalysis } from "../lib/ingest";
import { ensureDatabase } from "./runtime";

type AnalysisRow = {
  id: number;
  source_key: string;
  job_name: string;
  build_number: number;
  build_url: string;
  build_result: string;
  build_timestamp: string;
  duration_ms: number;
  branch: string;
  commit_sha: string;
  model: string;
  analysis_status: FailureAnalysis["analysisStatus"];
  summary: string;
  failed_stage: string;
  failed_component: string;
  category: string;
  root_cause: string;
  secondary_errors_json: string;
  evidence_json: string;
  checks_json: string;
  remediation_steps_json: string;
  prevention_json: string;
  missing_information_json: string;
  confidence: number;
  imported_at: string;
};

function parseJson<T>(value: string, fallback: T): T {
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function toAnalysis(row: AnalysisRow): FailureAnalysis {
  return {
    id: String(row.id),
    sourceKey: row.source_key,
    jobName: row.job_name,
    buildNumber: row.build_number,
    buildUrl: row.build_url,
    buildResult: row.build_result,
    timestamp: row.build_timestamp,
    durationMs: row.duration_ms,
    branch: row.branch,
    commitSha: row.commit_sha,
    model: row.model,
    analysisStatus: row.analysis_status,
    summary: row.summary,
    failedStage: row.failed_stage,
    failedComponent: row.failed_component,
    category: row.category,
    rootCause: row.root_cause,
    secondaryErrors: parseJson(row.secondary_errors_json, []),
    evidence: parseJson(row.evidence_json, []),
    checks: parseJson(row.checks_json, []),
    remediationSteps: parseJson(row.remediation_steps_json, []),
    prevention: parseJson(row.prevention_json, []),
    missingInformation: parseJson(row.missing_information_json, []),
    confidence: row.confidence,
    importedAt: row.imported_at,
  };
}

export async function listAnalyses(days: number, limit = 250) {
  const d1 = await ensureDatabase();
  const cutoff = new Date(Date.now() - days * 86_400_000).toISOString();
  const response = await d1
    .prepare(
      `
        SELECT
          id, source_key, job_name, build_number, build_url, build_result,
          build_timestamp, duration_ms, branch, commit_sha, model,
          analysis_status, summary, failed_stage, failed_component, category,
          root_cause, secondary_errors_json, evidence_json, checks_json,
          remediation_steps_json, prevention_json, missing_information_json,
          confidence, imported_at
        FROM failure_analyses
        WHERE build_timestamp >= ?
        ORDER BY build_timestamp DESC, build_number DESC
        LIMIT ?
      `,
    )
    .bind(cutoff, Math.min(Math.max(limit, 1), 500))
    .all<AnalysisRow>();

  return response.results.map(toAnalysis);
}

export async function upsertAnalysis(input: IngestedAnalysis) {
  const d1 = await ensureDatabase();
  const value = input.analysis;

  await d1
    .prepare(
      `
        INSERT INTO failure_analyses (
          source_key, job_name, build_number, build_url, build_result,
          build_timestamp, duration_ms, branch, commit_sha, model,
          analysis_status, summary, failed_stage, failed_component, category,
          root_cause, secondary_errors_json, evidence_json, checks_json,
          remediation_steps_json, prevention_json, missing_information_json,
          confidence, raw_json, imported_at, updated_at
        )
        VALUES (
          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
          ?, ?, ?, CURRENT_TIMESTAMP
        )
        ON CONFLICT(source_key) DO UPDATE SET
          job_name = excluded.job_name,
          build_number = excluded.build_number,
          build_url = excluded.build_url,
          build_result = excluded.build_result,
          build_timestamp = excluded.build_timestamp,
          duration_ms = excluded.duration_ms,
          branch = excluded.branch,
          commit_sha = excluded.commit_sha,
          model = excluded.model,
          analysis_status = excluded.analysis_status,
          summary = excluded.summary,
          failed_stage = excluded.failed_stage,
          failed_component = excluded.failed_component,
          category = excluded.category,
          root_cause = excluded.root_cause,
          secondary_errors_json = excluded.secondary_errors_json,
          evidence_json = excluded.evidence_json,
          checks_json = excluded.checks_json,
          remediation_steps_json = excluded.remediation_steps_json,
          prevention_json = excluded.prevention_json,
          missing_information_json = excluded.missing_information_json,
          confidence = excluded.confidence,
          raw_json = excluded.raw_json,
          updated_at = CURRENT_TIMESTAMP
      `,
    )
    .bind(
      value.sourceKey,
      value.jobName,
      value.buildNumber,
      value.buildUrl,
      value.buildResult,
      value.timestamp,
      value.durationMs,
      value.branch,
      value.commitSha,
      value.model,
      value.analysisStatus,
      value.summary,
      value.failedStage,
      value.failedComponent,
      value.category,
      value.rootCause,
      JSON.stringify(value.secondaryErrors),
      JSON.stringify(value.evidence),
      JSON.stringify(value.checks),
      JSON.stringify(value.remediationSteps),
      JSON.stringify(value.prevention),
      JSON.stringify(value.missingInformation),
      value.confidence,
      input.rawJson,
      value.importedAt,
    )
    .run();

  const row = await d1
    .prepare(
      `
        SELECT
          id, source_key, job_name, build_number, build_url, build_result,
          build_timestamp, duration_ms, branch, commit_sha, model,
          analysis_status, summary, failed_stage, failed_component, category,
          root_cause, secondary_errors_json, evidence_json, checks_json,
          remediation_steps_json, prevention_json, missing_information_json,
          confidence, imported_at
        FROM failure_analyses
        WHERE source_key = ?
      `,
    )
    .bind(value.sourceKey)
    .first<AnalysisRow>();

  if (!row) throw new Error("The stored analysis could not be reloaded.");
  return toAnalysis(row);
}

