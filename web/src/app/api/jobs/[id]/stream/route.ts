import { getJob, onJob } from "@/lib/jobs";
import type { JobInfo } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Server-sent events: the whole job each time its log grows, then `done`. */
export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const job = getJob(id);
  if (!job) return Response.json({ error: "no such job" }, { status: 404 });
  const enc = new TextEncoder();
  let unsub: (() => void) | null = null;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const send = (j: JobInfo) => {
        controller.enqueue(enc.encode(`data: ${JSON.stringify(j)}\n\n`));
        if (j.done) {
          unsub?.();
          controller.close();
        }
      };
      send(job);
      if (!job.done) {
        unsub = onJob(id, send);
        req.signal.addEventListener("abort", () => { unsub?.(); try { controller.close(); } catch { /* closed */ } });
      }
    },
    cancel() { unsub?.(); },
  });
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", Connection: "keep-alive", "X-Accel-Buffering": "no" },
  });
}
