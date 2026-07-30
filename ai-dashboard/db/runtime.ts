export type DashboardEnv = {
  DB?: D1Database;
  DASHBOARD_INGEST_TOKEN?: string;
};

export async function getRuntimeEnv() {
  const { env } = await import("cloudflare:workers");
  return env as unknown as DashboardEnv;
}

export async function ensureDatabase() {
  const d1 = (await getRuntimeEnv()).DB;
  if (!d1) {
    throw new Error("The dashboard database binding is unavailable.");
  }

  await d1.batch([
    d1.prepare(`
      CREATE TABLE IF NOT EXISTS failure_analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_key TEXT NOT NULL,
        job_name TEXT NOT NULL,
        build_number INTEGER NOT NULL,
        build_url TEXT NOT NULL DEFAULT '',
        build_result TEXT NOT NULL DEFAULT 'FAILURE',
        build_timestamp TEXT NOT NULL,
        duration_ms INTEGER NOT NULL DEFAULT 0,
        branch TEXT NOT NULL DEFAULT 'unknown',
        commit_sha TEXT NOT NULL DEFAULT 'unknown',
        model TEXT NOT NULL DEFAULT 'unknown',
        analysis_status TEXT NOT NULL,
        summary TEXT NOT NULL,
        failed_stage TEXT NOT NULL,
        failed_component TEXT NOT NULL,
        category TEXT NOT NULL,
        root_cause TEXT NOT NULL,
        secondary_errors_json TEXT NOT NULL DEFAULT '[]',
        evidence_json TEXT NOT NULL DEFAULT '[]',
        checks_json TEXT NOT NULL DEFAULT '[]',
        remediation_steps_json TEXT NOT NULL DEFAULT '[]',
        prevention_json TEXT NOT NULL DEFAULT '[]',
        missing_information_json TEXT NOT NULL DEFAULT '[]',
        confidence REAL NOT NULL,
        raw_json TEXT NOT NULL,
        imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      )
    `),
    d1.prepare(`
      CREATE UNIQUE INDEX IF NOT EXISTS failure_analyses_source_key_unique
      ON failure_analyses (source_key)
    `),
    d1.prepare(`
      CREATE INDEX IF NOT EXISTS failure_analyses_build_timestamp_idx
      ON failure_analyses (build_timestamp)
    `),
    d1.prepare(`
      CREATE INDEX IF NOT EXISTS failure_analyses_category_idx
      ON failure_analyses (category)
    `),
  ]);

  return d1;
}
