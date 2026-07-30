import { listAnalyses, upsertAnalysis } from "../../../db/analysis-repository";
import { getRuntimeEnv } from "../../../db/runtime";
import { normalizeIngestPayload } from "../../../lib/ingest";

export const dynamic = "force-dynamic";

const rangeDays: Record<string, number> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
};

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unexpected dashboard error";
}

function isDatabaseUnavailable(error: unknown) {
  return (
    error instanceof Error &&
    (error.message.includes("database binding is unavailable") ||
      error.message.includes("D1_ERROR"))
  );
}

async function isAuthorized(request: Request) {
  const expected = (await getRuntimeEnv()).DASHBOARD_INGEST_TOKEN?.trim();
  const authorization = request.headers.get("authorization") ?? "";
  const supplied = authorization.toLowerCase().startsWith("bearer ")
    ? authorization.slice(7).trim()
    : request.headers.get("x-analysis-token")?.trim() ?? "";
  const authenticatedUser = request.headers.get("oai-authenticated-user-email");
  const hostname = new URL(request.url).hostname;
  const localPreview = hostname === "terminal.local" || hostname === "localhost";

  if (expected && supplied && expected === supplied) return true;
  if (authenticatedUser) return true;
  return localPreview;
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const days = rangeDays[url.searchParams.get("range") ?? "7d"] ?? 7;

  try {
    const analyses = await listAnalyses(days);
    return Response.json({
      analyses,
      source: analyses.length ? "database" : "empty",
      syncedAt: new Date().toISOString(),
    });
  } catch (error) {
    if (isDatabaseUnavailable(error)) {
      return Response.json({
        analyses: [],
        source: "empty",
        syncedAt: new Date().toISOString(),
      });
    }
    return Response.json({ error: errorMessage(error) }, { status: 500 });
  }
}

export async function POST(request: Request) {
  if (!(await isAuthorized(request))) {
    return Response.json({ error: "Unauthorized ingestion request" }, { status: 401 });
  }

  try {
    const normalized = normalizeIngestPayload(await request.json());
    const analysis = await upsertAnalysis(normalized);
    return Response.json({ analysis }, { status: 201 });
  } catch (error) {
    const message = errorMessage(error);
    const badRequest =
      message.includes("required") ||
      message.includes("must be") ||
      message.includes("is invalid");
    return Response.json(
      { error: message },
      { status: badRequest ? 400 : 500 },
    );
  }
}
