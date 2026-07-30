CREATE TABLE `failure_analyses` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`source_key` text NOT NULL,
	`job_name` text NOT NULL,
	`build_number` integer NOT NULL,
	`build_url` text DEFAULT '' NOT NULL,
	`build_result` text DEFAULT 'FAILURE' NOT NULL,
	`build_timestamp` text NOT NULL,
	`duration_ms` integer DEFAULT 0 NOT NULL,
	`branch` text DEFAULT 'unknown' NOT NULL,
	`commit_sha` text DEFAULT 'unknown' NOT NULL,
	`model` text DEFAULT 'unknown' NOT NULL,
	`analysis_status` text NOT NULL,
	`summary` text NOT NULL,
	`failed_stage` text NOT NULL,
	`failed_component` text NOT NULL,
	`category` text NOT NULL,
	`root_cause` text NOT NULL,
	`secondary_errors_json` text DEFAULT '[]' NOT NULL,
	`evidence_json` text DEFAULT '[]' NOT NULL,
	`checks_json` text DEFAULT '[]' NOT NULL,
	`remediation_steps_json` text DEFAULT '[]' NOT NULL,
	`prevention_json` text DEFAULT '[]' NOT NULL,
	`missing_information_json` text DEFAULT '[]' NOT NULL,
	`confidence` real NOT NULL,
	`raw_json` text NOT NULL,
	`imported_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `failure_analyses_source_key_unique` ON `failure_analyses` (`source_key`);--> statement-breakpoint
CREATE INDEX `failure_analyses_build_timestamp_idx` ON `failure_analyses` (`build_timestamp`);--> statement-breakpoint
CREATE INDEX `failure_analyses_category_idx` ON `failure_analyses` (`category`);