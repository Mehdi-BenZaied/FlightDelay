"use client";

import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Database,
  ExternalLink,
  FileJson,
  Filter,
  Gauge,
  Home,
  Menu,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { DashboardResponse, FailureAnalysis } from "../lib/analysis";
import { formatCategory, statusLabel } from "../lib/analysis";
import { demoAnalyses } from "../lib/demo-data";

type View = "overview" | "failures" | "trends" | "settings";
type Range = "7d" | "30d" | "90d";
type Sort = { key: "build" | "confidence"; direction: "asc" | "desc" };
type StorageState = "checking" | "ready" | "unavailable";

const navItems = [
  { id: "overview" as const, label: "Overview", icon: Home },
  { id: "failures" as const, label: "Failures", icon: AlertTriangle },
  { id: "trends" as const, label: "Trends", icon: BarChart3 },
  { id: "settings" as const, label: "Settings", icon: Settings },
];

const rangeLabels: Record<Range, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "90d": "Last 90 days",
};

function dayKey(date: Date) {
  return date.toISOString().slice(0, 10);
}

function daysForRange(range: Range) {
  return range === "7d" ? 7 : range === "30d" ? 30 : 90;
}

function withinRange(item: FailureAnalysis, range: Range) {
  const latest = Date.now();
  const threshold = latest - daysForRange(range) * 24 * 60 * 60 * 1000;
  return new Date(item.timestamp).getTime() >= threshold;
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(new Date(value));
}

function formatDuration(durationMs: number) {
  const minutes = Math.floor(durationMs / 60_000);
  const seconds = Math.round((durationMs % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function statusTone(status: FailureAnalysis["analysisStatus"]) {
  if (status === "probable") return "probable";
  if (status === "diagnosed") return "diagnosed";
  return "evidence";
}

function StatusPill({ status }: { status: FailureAnalysis["analysisStatus"] }) {
  return (
    <span className={`status-pill status-${statusTone(status)}`}>
      {status === "diagnosed" ? (
        <CheckCircle2 aria-hidden="true" />
      ) : status === "probable" ? (
        <CircleAlert aria-hidden="true" />
      ) : (
        <FileJson aria-hidden="true" />
      )}
      {statusLabel(status)}
    </span>
  );
}

function KpiCard({
  icon: Icon,
  value,
  label,
  hint,
}: {
  icon: typeof AlertTriangle;
  value: string;
  label: string;
  hint: string;
}) {
  return (
    <article className="kpi-card">
      <div className="kpi-icon">
        <Icon aria-hidden="true" />
      </div>
      <div className="kpi-copy">
        <strong>{value}</strong>
        <span>{label}</span>
      </div>
      <p>{hint}</p>
    </article>
  );
}

type TrendPoint = {
  key: string;
  label: string;
  count: number;
};

function buildTrend(analyses: FailureAnalysis[], range: Range): TrendPoint[] {
  const totalDays = daysForRange(range);
  const visibleDays = range === "7d" ? 7 : range === "30d" ? 10 : 12;
  const bucketSize = Math.ceil(totalDays / visibleDays);
  const end = new Date();
  const points: TrendPoint[] = [];

  for (let bucket = visibleDays - 1; bucket >= 0; bucket -= 1) {
    const bucketEnd = new Date(end);
    bucketEnd.setUTCDate(end.getUTCDate() - bucket * bucketSize);
    const bucketStart = new Date(bucketEnd);
    bucketStart.setUTCDate(bucketEnd.getUTCDate() - bucketSize + 1);
    const count = analyses.filter((item) => {
      const date = new Date(item.timestamp);
      return date >= bucketStart && date < new Date(bucketEnd.getTime() + 86_400_000);
    }).length;

    points.push({
      key: dayKey(bucketEnd),
      label: new Intl.DateTimeFormat("en", {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      }).format(bucketEnd),
      count,
    });
  }

  return points;
}

function makeSmoothPath(points: Array<{ x: number; y: number }>) {
  if (points.length < 2) return "";
  return points.reduce((path, point, index) => {
    if (index === 0) return `M ${point.x} ${point.y}`;
    const previous = points[index - 1];
    const midX = (previous.x + point.x) / 2;
    return `${path} C ${midX} ${previous.y}, ${midX} ${point.y}, ${point.x} ${point.y}`;
  }, "");
}

function FailureTrendChart({
  analyses,
  range,
  selectedDate,
  onSelectDate,
  large = false,
}: {
  analyses: FailureAnalysis[];
  range: Range;
  selectedDate: string | null;
  onSelectDate: (key: string | null) => void;
  large?: boolean;
}) {
  const trend = useMemo(() => buildTrend(analyses, range), [analyses, range]);
  const width = 720;
  const height = large ? 290 : 230;
  const plot = { left: 34, right: 18, top: 18, bottom: 42 };
  const max = Math.max(4, ...trend.map((point) => point.count));
  const chartWidth = width - plot.left - plot.right;
  const chartHeight = height - plot.top - plot.bottom;
  const points = trend.map((point, index) => ({
    ...point,
    x: plot.left + (index / Math.max(1, trend.length - 1)) * chartWidth,
    y: plot.top + chartHeight - (point.count / max) * chartHeight,
  }));
  const linePath = makeSmoothPath(points);
  const areaPath = points.length
    ? `${linePath} L ${points.at(-1)?.x} ${plot.top + chartHeight} L ${points[0].x} ${plot.top + chartHeight} Z`
    : "";

  return (
    <div className={`trend-wrap ${large ? "trend-large" : ""}`}>
      <svg
        className="trend-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Failure counts for the ${rangeLabels[range].toLowerCase()}`}
      >
        <defs>
          <linearGradient id={`trend-area-${range}-${large}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4f46e5" stopOpacity="0.16" />
            <stop offset="100%" stopColor="#4f46e5" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3, 4].map((line) => {
          const y = plot.top + (line / 4) * chartHeight;
          const value = Math.round(max - (line / 4) * max);
          return (
            <g key={line}>
              <line
                className="chart-gridline"
                x1={plot.left}
                x2={width - plot.right}
                y1={y}
                y2={y}
              />
              <text className="chart-axis-y" x={plot.left - 10} y={y + 4}>
                {value}
              </text>
            </g>
          );
        })}
        <path
          className="chart-area"
          d={areaPath}
          fill={`url(#trend-area-${range}-${large})`}
        />
        <path className="chart-line" d={linePath} />
        {points.map((point, index) => {
          const isSelected = selectedDate === point.key;
          const showLabel =
            range === "7d" || index === 0 || index === points.length - 1 || index % 2 === 0;
          return (
            <g key={point.key}>
              {showLabel ? (
                <text
                  className="chart-axis-x"
                  x={point.x}
                  y={height - 14}
                  textAnchor="middle"
                >
                  {point.label}
                </text>
              ) : null}
              <circle
                className={`chart-point ${isSelected ? "is-selected" : ""}`}
                cx={point.x}
                cy={point.y}
                r={isSelected ? 7 : 5}
                role="button"
                aria-label={`${point.label}: ${point.count} failures. ${
                  isSelected ? "Clear day filter" : "Filter table to this day"
                }`}
                tabIndex={0}
                onClick={() => onSelectDate(isSelected ? null : point.key)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectDate(isSelected ? null : point.key);
                  }
                }}
              />
            </g>
          );
        })}
      </svg>
      <div className="chart-caption">
        <span>
          <span className="legend-dot" />
          Failed pipelines
        </span>
        {selectedDate ? (
          <button type="button" onClick={() => onSelectDate(null)}>
            <X aria-hidden="true" />
            Clear {selectedDate}
          </button>
        ) : (
          <span>Select a point to filter</span>
        )}
      </div>
    </div>
  );
}

function DiagnosisCard({
  analysis,
  onOpenDetail,
}: {
  analysis: FailureAnalysis;
  onOpenDetail: () => void;
}) {
  return (
    <article className="card diagnosis-card">
      <div className="card-heading">
        <div>
          <p className="eyebrow">Latest diagnosis</p>
          <h2>Build #{analysis.buildNumber}</h2>
        </div>
        <div className="incident-icon" aria-label="Failure detected">
          <XCircle aria-hidden="true" />
        </div>
      </div>
      <dl className="diagnosis-grid">
        <dt>Stage</dt>
        <dd>{analysis.failedStage}</dd>
        <dt>Component</dt>
        <dd>{analysis.failedComponent}</dd>
        <dt>Category</dt>
        <dd>{formatCategory(analysis.category)}</dd>
        <dt>Summary</dt>
        <dd>{analysis.summary}</dd>
      </dl>
      <div className="diagnosis-footer">
        <StatusPill status={analysis.analysisStatus} />
        <span className="confidence-pill">
          <Gauge aria-hidden="true" />
          {Math.round(analysis.confidence * 100)}% confidence
        </span>
      </div>
      <button className="text-button" type="button" onClick={onOpenDetail}>
        View diagnosis
        <ExternalLink aria-hidden="true" />
      </button>
    </article>
  );
}

function FailuresTable({
  analyses,
  selectedId,
  onSelect,
  sort,
  onSort,
  compact = false,
}: {
  analyses: FailureAnalysis[];
  selectedId: string;
  onSelect: (analysis: FailureAnalysis) => void;
  sort: Sort;
  onSort: (key: Sort["key"]) => void;
  compact?: boolean;
}) {
  const sorted = useMemo(() => {
    return [...analyses].sort((left, right) => {
      const difference =
        sort.key === "build"
          ? left.buildNumber - right.buildNumber
          : left.confidence - right.confidence;
      return sort.direction === "asc" ? difference : -difference;
    });
  }, [analyses, sort]);
  const rows = compact ? sorted.slice(0, 5) : sorted;

  return (
    <div className="table-scroll">
      <table className="failures-table">
        <thead>
          <tr>
            <th aria-sort={sort.key === "build" ? `${sort.direction}ending` : "none"}>
              <button type="button" onClick={() => onSort("build")}>
                Build
                {sort.key === "build" ? (
                  sort.direction === "asc" ? (
                    <ArrowUp aria-hidden="true" />
                  ) : (
                    <ArrowDown aria-hidden="true" />
                  )
                ) : null}
              </button>
            </th>
            <th>Stage</th>
            <th>Component</th>
            <th>Category</th>
            <th
              aria-sort={
                sort.key === "confidence" ? `${sort.direction}ending` : "none"
              }
            >
              <button type="button" onClick={() => onSort("confidence")}>
                Confidence
                {sort.key === "confidence" ? (
                  sort.direction === "asc" ? (
                    <ArrowUp aria-hidden="true" />
                  ) : (
                    <ArrowDown aria-hidden="true" />
                  )
                ) : null}
              </button>
            </th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((analysis) => (
            <tr
              key={analysis.id}
              className={selectedId === analysis.id ? "is-active" : ""}
              onClick={() => onSelect(analysis)}
            >
              <td>
                <button
                  className="build-link"
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(analysis);
                  }}
                >
                  #{analysis.buildNumber}
                </button>
              </td>
              <td>{analysis.failedStage}</td>
              <td>
                <span className="component-name">{analysis.failedComponent}</span>
              </td>
              <td>{formatCategory(analysis.category)}</td>
              <td className="numeric">{Math.round(analysis.confidence * 100)}%</td>
              <td>
                <StatusPill status={analysis.analysisStatus} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length ? (
        <div className="empty-state">
          <ShieldCheck aria-hidden="true" />
          <strong>No failures in this scope</strong>
          <span>Try another date range or clear the active filter.</span>
        </div>
      ) : null}
    </div>
  );
}

function DetailDrawer({
  analysis,
  onClose,
}: {
  analysis: FailureAnalysis | null;
  onClose: () => void;
}) {
  if (!analysis) return null;
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        className="detail-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="drawer-header">
          <div>
            <span>AI diagnosis</span>
            <h2 id="detail-title">Build #{analysis.buildNumber}</h2>
          </div>
          <button type="button" aria-label="Close diagnosis" onClick={onClose}>
            <X aria-hidden="true" />
          </button>
        </div>
        <div className="drawer-meta">
          <StatusPill status={analysis.analysisStatus} />
          <span>{Math.round(analysis.confidence * 100)}% confidence</span>
          <span>{formatDateTime(analysis.timestamp)}</span>
        </div>
        <section>
          <p className="eyebrow">Summary</p>
          <h3>{analysis.summary}</h3>
          <p>{analysis.rootCause}</p>
        </section>
        <section>
          <p className="eyebrow">Evidence</p>
          {analysis.evidence.map((item, index) => (
            <article className="evidence-card" key={`${item.logFile}-${index}`}>
              <strong>{item.logFile}</strong>
              <code>{item.excerpt}</code>
              <p>{item.interpretation}</p>
            </article>
          ))}
        </section>
        <section>
          <p className="eyebrow">Recommended checks</p>
          <ol className="checks-list">
            {analysis.checks.map((check, index) => (
              <li key={`${check.command}-${index}`}>
                <span>{index + 1}</span>
                <div>
                  <strong>{check.purpose}</strong>
                  <code>{check.command}</code>
                  <p>{check.expectedResult}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
        <section className="build-context">
          <p className="eyebrow">Build context</p>
          <dl>
            <dt>Job</dt>
            <dd>{analysis.jobName}</dd>
            <dt>Branch</dt>
            <dd>{analysis.branch}</dd>
            <dt>Commit</dt>
            <dd>{analysis.commitSha}</dd>
            <dt>Duration</dt>
            <dd>{formatDuration(analysis.durationMs)}</dd>
            <dt>Model</dt>
            <dd>{analysis.model}</dd>
          </dl>
        </section>
      </aside>
    </div>
  );
}

export default function FailureDashboard() {
  const [view, setView] = useState<View>("overview");
  const [range, setRange] = useState<Range>("7d");
  const [analyses, setAnalyses] = useState<FailureAnalysis[]>(demoAnalyses);
  const [usingDemo, setUsingDemo] = useState(true);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selected, setSelected] = useState<FailureAnalysis>(demoAnalyses[0]);
  const [drawer, setDrawer] = useState<FailureAnalysis | null>(null);
  const [sort, setSort] = useState<Sort>({ key: "build", direction: "desc" });
  const [mobileNav, setMobileNav] = useState(false);
  const [search, setSearch] = useState("");
  const [storageState, setStorageState] = useState<StorageState>("checking");
  const [manualJob, setManualJob] = useState("FlightDelay/main");
  const [manualBuild, setManualBuild] = useState("25");
  const [importState, setImportState] = useState<
    "idle" | "importing" | "success" | "error"
  >("idle");
  const [importMessage, setImportMessage] = useState(
    "JSON must match the existing analyzer output.",
  );

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/analyses?range=${range}`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Dashboard API unavailable");
        return (await response.json()) as DashboardResponse;
      })
      .then((payload) => {
        if (cancelled) return;
        if (payload.analyses.length) {
          setAnalyses(payload.analyses);
          setSelected(payload.analyses[0]);
          setUsingDemo(false);
        } else {
          setAnalyses(demoAnalyses.filter((item) => withinRange(item, range)));
          setUsingDemo(true);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setAnalyses(demoAnalyses.filter((item) => withinRange(item, range)));
        setUsingDemo(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [range]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDrawer(null);
        setMobileNav(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    fetch("/api/health", { cache: "no-store" })
      .then((response) => {
        setStorageState(response.ok ? "ready" : "unavailable");
      })
      .catch(() => setStorageState("unavailable"));
  }, []);

  const scoped = useMemo(
    () => analyses.filter((item) => withinRange(item, range)),
    [analyses, range],
  );
  const tableRows = useMemo(() => {
    const byDay = selectedDate
      ? scoped.filter((item) => dayKey(new Date(item.timestamp)) === selectedDate)
      : scoped;
    const term = search.trim().toLowerCase();
    if (!term) return byDay;
    return byDay.filter((item) =>
      [
        item.buildNumber,
        item.failedStage,
        item.failedComponent,
        item.category,
        item.summary,
      ]
        .join(" ")
        .toLowerCase()
        .includes(term),
    );
  }, [scoped, search, selectedDate]);

  const diagnosed = scoped.filter(
    (item) => item.analysisStatus !== "insufficient_evidence",
  ).length;
  const averageConfidence = scoped.length
    ? scoped.reduce((sum, item) => sum + item.confidence, 0) / scoped.length
    : 0;
  const categories = useMemo(() => {
    const totals = new Map<string, number>();
    scoped.forEach((item) =>
      totals.set(item.category, (totals.get(item.category) ?? 0) + 1),
    );
    return [...totals.entries()].sort((left, right) => right[1] - left[1]);
  }, [scoped]);

  function handleSort(key: Sort["key"]) {
    setSort((current) => ({
      key,
      direction:
        current.key === key && current.direction === "desc" ? "asc" : "desc",
    }));
  }

  function selectAnalysis(analysis: FailureAnalysis) {
    setSelected(analysis);
    if (window.innerWidth < 1180 || view === "failures") setDrawer(analysis);
  }

  async function importReport(file: File) {
    const buildNumber = Number(manualBuild);
    if (!manualJob.trim() || !Number.isInteger(buildNumber) || buildNumber < 0) {
      setImportState("error");
      setImportMessage("Enter a valid Jenkins job and build number first.");
      return;
    }

    setImportState("importing");
    setImportMessage("Validating and storing the analyzer result…");
    try {
      const analysisPayload = JSON.parse(await file.text()) as unknown;
      const response = await fetch("/api/analyses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jenkins: {
            source_key: `${manualJob.trim()}#${buildNumber}`,
            job_name: manualJob.trim(),
            build_number: buildNumber,
            build_url: "",
            result: "FAILURE",
            timestamp: new Date().toISOString(),
            duration_ms: 0,
            branch: "manual-import",
            commit_sha: "unknown",
            model: "unknown",
          },
          analysis: analysisPayload,
        }),
      });
      const payload = (await response.json()) as {
        analysis?: FailureAnalysis;
        error?: string;
      };
      if (!response.ok || !payload.analysis) {
        throw new Error(payload.error || "The report could not be imported.");
      }
      setAnalyses((current) => [
        payload.analysis as FailureAnalysis,
        ...current.filter(
          (item) => item.sourceKey !== payload.analysis?.sourceKey,
        ),
      ]);
      setSelected(payload.analysis);
      setUsingDemo(false);
      setStorageState("ready");
      setImportState("success");
      setImportMessage(
        `Build #${payload.analysis.buildNumber} was stored successfully.`,
      );
    } catch (error) {
      setImportState("error");
      setImportMessage(
        error instanceof Error ? error.message : "The JSON report is invalid.",
      );
    }
  }

  const title =
    view === "overview"
      ? "Failure Intelligence"
      : view === "failures"
        ? "Failure History"
        : view === "trends"
          ? "Failure Trends"
          : "Dashboard Settings";

  return (
    <div className="dashboard-shell">
      <aside className={`sidebar ${mobileNav ? "is-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">
            <Sparkles aria-hidden="true" />
          </div>
          <div>
            <strong>FlightDelay AI</strong>
            <span>Pipeline intelligence</span>
          </div>
        </div>
        <nav aria-label="Dashboard">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={view === item.id ? "is-active" : ""}
                type="button"
                onClick={() => {
                  setView(item.id);
                  setMobileNav(false);
                }}
              >
                <Icon aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="collector-state">
          <span
            className={`state-dot ${
              storageState !== "ready" || usingDemo ? "is-waiting" : ""
            }`}
          />
          <div>
            <strong>
              {storageState === "ready"
                ? usingDemo
                  ? "Collector ready"
                  : "Collector synced"
                : storageState === "checking"
                  ? "Connecting storage"
                  : "Storage unavailable"}
            </strong>
            <span>
              {usingDemo ? "Waiting for first failure" : "Live results connected"}
            </span>
          </div>
        </div>
      </aside>

      {mobileNav ? (
        <button
          className="mobile-overlay"
          type="button"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      ) : null}

      <main className={`dashboard-main ${loading ? "is-loading" : ""}`}>
        <header className="dashboard-header">
          <div className="header-title">
            <button
              className="mobile-menu"
              type="button"
              aria-label="Open navigation"
              onClick={() => setMobileNav(true)}
            >
              <Menu aria-hidden="true" />
            </button>
            <div>
              <p className="eyebrow">Jenkins · FlightDelay</p>
              <h1>{title}</h1>
            </div>
          </div>
          <div className="header-actions">
            {usingDemo ? (
              <span className="demo-badge">
                <Sparkles aria-hidden="true" />
                Demo data
              </span>
            ) : (
              <span className="live-badge">
                <span />
                Live data
              </span>
            )}
            <label className="range-control">
              <CalendarDays aria-hidden="true" />
              <span className="sr-only">Date range</span>
              <select
                value={range}
                onChange={(event) => {
                  setLoading(true);
                  setRange(event.target.value as Range);
                  setSelectedDate(null);
                }}
              >
                <option value="7d">Last 7 days</option>
                <option value="30d">Last 30 days</option>
                <option value="90d">Last 90 days</option>
              </select>
              <ChevronDown aria-hidden="true" />
            </label>
          </div>
        </header>

        {view === "overview" ? (
          <div className="view-stack">
            <section className="kpi-grid" aria-label="Key metrics">
              <KpiCard
                icon={AlertTriangle}
                value={String(scoped.length)}
                label="Failures"
                hint={`${rangeLabels[range].toLowerCase()}`}
              />
              <KpiCard
                icon={CheckCircle2}
                value={`${scoped.length ? Math.round((diagnosed / scoped.length) * 100) : 0}%`}
                label="Diagnosed"
                hint={`${diagnosed} actionable results`}
              />
              <KpiCard
                icon={Gauge}
                value={`${Math.round(averageConfidence * 100)}%`}
                label="Avg confidence"
                hint="Across AI diagnoses"
              />
              <KpiCard
                icon={Clock3}
                value="2m"
                label="Since last scan"
                hint="Collector is up to date"
              />
            </section>

            <section className="analysis-grid">
              <article className="card trend-card">
                <div className="card-heading">
                  <div>
                    <p className="eyebrow">Operational pattern</p>
                    <h2>{range === "7d" ? "7-day" : rangeLabels[range]} failure trend</h2>
                  </div>
                  <Activity aria-hidden="true" />
                </div>
                <FailureTrendChart
                  analyses={scoped}
                  range={range}
                  selectedDate={selectedDate}
                  onSelectDate={setSelectedDate}
                />
              </article>
              <DiagnosisCard
                analysis={selected}
                onOpenDetail={() => setDrawer(selected)}
              />
            </section>

            <section className="card recent-card">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Action queue</p>
                  <h2>Recent failures</h2>
                </div>
                <button className="secondary-button" type="button" onClick={() => setView("failures")}>
                  View all
                  <ExternalLink aria-hidden="true" />
                </button>
              </div>
              <FailuresTable
                analyses={tableRows}
                selectedId={selected.id}
                onSelect={selectAnalysis}
                sort={sort}
                onSort={handleSort}
                compact
              />
            </section>
          </div>
        ) : null}

        {view === "failures" ? (
          <div className="view-stack">
            <section className="toolbar-card">
              <label className="search-control">
                <Search aria-hidden="true" />
                <span className="sr-only">Search failures</span>
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search build, stage, component, or summary"
                />
              </label>
              <div className="toolbar-meta">
                <Filter aria-hidden="true" />
                <span>
                  {tableRows.length} of {scoped.length} failures
                </span>
                {selectedDate ? (
                  <button type="button" onClick={() => setSelectedDate(null)}>
                    Clear day filter
                  </button>
                ) : null}
              </div>
            </section>
            <section className="card full-table-card">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Stored analyses</p>
                  <h2>Pipeline failure history</h2>
                </div>
                <span className="retention-note">SQLite-backed history</span>
              </div>
              <FailuresTable
                analyses={tableRows}
                selectedId={selected.id}
                onSelect={selectAnalysis}
                sort={sort}
                onSort={handleSort}
              />
            </section>
          </div>
        ) : null}

        {view === "trends" ? (
          <div className="trends-layout">
            <section className="card trends-main-card">
              <div className="card-heading">
                <div>
                  <p className="eyebrow">Failure volume</p>
                  <h2>{rangeLabels[range]} overview</h2>
                </div>
                <BarChart3 aria-hidden="true" />
              </div>
              <FailureTrendChart
                analyses={scoped}
                range={range}
                selectedDate={selectedDate}
                onSelectDate={setSelectedDate}
                large
              />
            </section>
            <section className="card category-card">
              <div className="card-heading">
                <div>
                  <p className="eyebrow">Root-cause signal</p>
                  <h2>Top categories</h2>
                </div>
                <Gauge aria-hidden="true" />
              </div>
              <div className="category-list">
                {categories.slice(0, 7).map(([category, total]) => (
                  <div key={category}>
                    <div>
                      <span>{formatCategory(category)}</span>
                      <strong>{total}</strong>
                    </div>
                    <span className="category-bar">
                      <span
                        style={{
                          width: `${Math.max(10, (total / Math.max(1, scoped.length)) * 100)}%`,
                        }}
                      />
                    </span>
                  </div>
                ))}
              </div>
            </section>
          </div>
        ) : null}

        {view === "settings" ? (
          <div className="settings-grid">
            <section className="card setup-card">
              <div className="settings-icon">
                <Database aria-hidden="true" />
              </div>
              <div>
                <p className="eyebrow">Persistence</p>
                <h2>Analysis storage</h2>
                <p>
                  Every imported report is normalized and stored once using the
                  Jenkins job and build number as its unique source key.
                </p>
              </div>
              <span
                className={`settings-state ${
                  storageState !== "ready" ? "neutral" : ""
                }`}
              >
                {storageState === "ready" ? (
                  <CheckCircle2 aria-hidden="true" />
                ) : (
                  <Clock3 aria-hidden="true" />
                )}
                {storageState === "ready" ? "Ready" : "Connecting"}
              </span>
            </section>
            <section className="card setup-card">
              <div className="settings-icon">
                <RefreshCw aria-hidden="true" />
              </div>
              <div>
                <p className="eyebrow">Automation</p>
                <h2>Jenkins collector</h2>
                <p>
                  The separate collector polls failed builds and downloads the
                  archived <code>ai-failure-analysis.json</code> artifact.
                </p>
              </div>
              <span className="settings-state neutral">
                <Clock3 aria-hidden="true" />
                Every 60s
              </span>
            </section>
            <section className="card import-card">
              <div className="settings-icon">
                <Upload aria-hidden="true" />
              </div>
              <div>
                <p className="eyebrow">Manual fallback</p>
                <h2>Import a JSON report</h2>
                <p>
                  Drop an analyzer result here when you want to verify the
                  dashboard without waiting for the next failed build.
                </p>
                <div className="import-fields">
                  <label>
                    <span>Jenkins job</span>
                    <input
                      value={manualJob}
                      onChange={(event) => setManualJob(event.target.value)}
                      placeholder="FlightDelay/main"
                    />
                  </label>
                  <label>
                    <span>Build number</span>
                    <input
                      type="number"
                      min="0"
                      value={manualBuild}
                      onChange={(event) => setManualBuild(event.target.value)}
                    />
                  </label>
                </div>
              </div>
              <label
                className={`primary-button file-button ${
                  importState === "importing" ? "is-disabled" : ""
                }`}
              >
                {importState === "importing" ? (
                  <RefreshCw className="is-spinning" aria-hidden="true" />
                ) : (
                  <Upload aria-hidden="true" />
                )}
                {importState === "importing" ? "Importing…" : "Select report"}
                <input
                  type="file"
                  accept="application/json,.json"
                  disabled={importState === "importing"}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void importReport(file);
                    event.target.value = "";
                  }}
                />
              </label>
              <span className={`import-message is-${importState}`}>
                {importMessage}
              </span>
            </section>
          </div>
        ) : null}
      </main>

      <DetailDrawer analysis={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}
