import { interrupt } from "@/lib/agent";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const { sessionId } = (await req.json().catch(() => ({}))) as { sessionId?: string };
  if (!sessionId) return Response.json({ error: "sessionId required" }, { status: 400 });
  return Response.json({ stopped: interrupt(sessionId) });
}
