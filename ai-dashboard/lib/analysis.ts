export type AnalysisStatus =
  | "diagnosed"
  | "probable"
  | "insufficient_evidence";

export type EvidenceItem = {
  logFile: string;
  excerpt: string;
  interpretation: string;
};

export type DiagnosticCheck = {
  platform: string;
  command: string;
  purpose: string;
  expectedResult: string;
};

export type RemediationStep = {
  priority: "high" | "medium" | "low";
  action: string;
  command: string;
  risk: "safe" | "review_required" | "destructive";
};

export type FailureAnalysis = {
  id: string;
  sourceKey: string;
  jobName: string;
  buildNumber: number;
  buildUrl: string;
  buildResult: string;
  timestamp: string;
  durationMs: number;
  branch: string;
  commitSha: string;
  model: string;
  analysisStatus: AnalysisStatus;
  summary: string;
  failedStage: string;
  failedComponent: string;
  category: string;
  rootCause: string;
  secondaryErrors: string[];
  evidence: EvidenceItem[];
  checks: DiagnosticCheck[];
  remediationSteps: RemediationStep[];
  prevention: string[];
  missingInformation: string[];
  confidence: number;
  importedAt: string;
};

export type DashboardResponse = {
  analyses: FailureAnalysis[];
  source: "database" | "empty";
  syncedAt: string;
};

export function statusLabel(status: AnalysisStatus) {
  if (status === "diagnosed") return "Diagnosed";
  if (status === "probable") return "Probable";
  return "Needs evidence";
}

export function formatCategory(category: string) {
  return category
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

