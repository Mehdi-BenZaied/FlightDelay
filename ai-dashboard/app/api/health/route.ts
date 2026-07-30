import { ensureDatabase } from "../../../db/runtime";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await ensureDatabase();
    return Response.json({
      status: "ok",
      storage: "connected",
      checkedAt: new Date().toISOString(),
    });
  } catch {
    return Response.json(
      {
        status: "degraded",
        storage: "unavailable",
        checkedAt: new Date().toISOString(),
      },
      { status: 503 },
    );
  }
}

