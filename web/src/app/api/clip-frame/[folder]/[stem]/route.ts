import fs from "node:fs";
import { clipFrame } from "@/lib/beatcut";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** One frame of a clip at `?t=` seconds (0.1 s steps), for the in-point scrubber. */
export async function GET(req: Request, { params }: { params: Promise<{ folder: string; stem: string }> }) {
  const { folder, stem } = await params;
  if (folder.includes("..") || stem.includes("..") || folder.includes("/") || stem.includes("/")) return new Response("bad path", { status: 400 });
  const t = Number(new URL(req.url).searchParams.get("t") ?? "0");
  if (!Number.isFinite(t) || t < 0) return new Response("bad time", { status: 400 });
  const f = await clipFrame(folder, stem, t);
  if (!f) return new Response("no frame", { status: 404 });
  return new Response(fs.readFileSync(f), {
    headers: { "Content-Type": "image/jpeg", "Cache-Control": "private, max-age=86400" },
  });
}
