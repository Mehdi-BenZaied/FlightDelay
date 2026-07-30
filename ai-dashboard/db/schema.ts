import { sql } from "drizzle-orm";
import {
  index,
  integer,
  real,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

export const failureAnalyses = sqliteTable(
  "failure_analyses",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    sourceKey: text("source_key").notNull(),
    jobName: text("job_name").notNull(),
    buildNumber: integer("build_number").notNull(),
    buildUrl: text("build_url").notNull().default(""),
    buildResult: text("build_result").notNull().default("FAILURE"),
    buildTimestamp: text("build_timestamp").notNull(),
    durationMs: integer("duration_ms").notNull().default(0),
    branch: text("branch").notNull().default("unknown"),
    commitSha: text("commit_sha").notNull().default("unknown"),
    model: text("model").notNull().default("unknown"),
    analysisStatus: text("analysis_status").notNull(),
    summary: text("summary").notNull(),
    failedStage: text("failed_stage").notNull(),
    failedComponent: text("failed_component").notNull(),
    category: text("category").notNull(),
    rootCause: text("root_cause").notNull(),
    secondaryErrorsJson: text("secondary_errors_json").notNull().default("[]"),
    evidenceJson: text("evidence_json").notNull().default("[]"),
    checksJson: text("checks_json").notNull().default("[]"),
    remediationStepsJson: text("remediation_steps_json").notNull().default("[]"),
    preventionJson: text("prevention_json").notNull().default("[]"),
    missingInformationJson: text("missing_information_json")
      .notNull()
      .default("[]"),
    confidence: real("confidence").notNull(),
    rawJson: text("raw_json").notNull(),
    importedAt: text("imported_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    uniqueIndex("failure_analyses_source_key_unique").on(table.sourceKey),
    index("failure_analyses_build_timestamp_idx").on(table.buildTimestamp),
    index("failure_analyses_category_idx").on(table.category),
  ],
);

