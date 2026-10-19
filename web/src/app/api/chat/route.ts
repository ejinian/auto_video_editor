import { runTurn, isRunning } from "@/lib/agent";
import { hasChatAuth } from "@/lib/chatAuth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** POST {message, sessionId?, context?} → NDJSON stream of ChatEvent. */
export async function POST(req: Request) {
  if (!hasChatAuth()) {
    return Response.json({ error: "No ANTHROPIC_API_KEY in web/.env.local and no Claude Code login on this Mac: put a key there and restart the app, or run `claude` in a terminal and /login once." }, { status: 503 });
  }
  const body = (await req.json().catch(() => null)) as { message?: string; sessionId?: string | null; context?: string | null } | null;
  const message = body?.message?.trim();
  if (!message) return Response.json({ error: "empty message" }, { status: 400 });
  if (body?.sessionId && isRunning(body.sessionId)) {
    return Response.json({ error: "that chat is still working — stop it first" }, { status: 409 });
  }
  const enc = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        for await (const ev of runTurn({ prompt: message, sessionId: body?.sessionId ?? null, context: body?.context ?? null, signal: req.signal })) {
          controller.enqueue(enc.encode(JSON.stringify(ev) + "\n"));
        }
      } catch (e) {
        controller.enqueue(enc.encode(JSON.stringify({ t: "error", message: String(e) }) + "\n"));
      } finally {
        controller.close();
      }
    },
  });
  return new Response(stream, {
    headers: { "Content-Type": "application/x-ndjson; charset=utf-8", "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no" },
  });
}
