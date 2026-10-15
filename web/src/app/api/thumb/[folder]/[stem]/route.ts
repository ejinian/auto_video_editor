import fs from "node:fs";
import { thumb } from "@/lib/beatcut";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, { params }: { params: Promise<{ folder: string; stem: string }> }) {
  const { folder, stem } = await params;
  if (folder.includes("..") || stem.includes("..") || folder.includes("/") || stem.includes("/")) return new Response("bad path", { status: 400 });
  const t = await thumb(folder, stem);
  if (!t) return new Response("no thumbnail", { status: 404 });
  return new Response(fs.readFileSync(t), {
    headers: { "Content-Type": "image/jpeg", "Cache-Control": "private, max-age=3600" },
  });
}
