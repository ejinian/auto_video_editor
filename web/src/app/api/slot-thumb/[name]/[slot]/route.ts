import fs from "node:fs";
import { slotThumb } from "@/lib/beatcut";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** The frame the timeline shows for one slot: clip at in-point + half the slot, like `board`. */
export async function GET(_req: Request, { params }: { params: Promise<{ name: string; slot: string }> }) {
  const { name, slot } = await params;
  const n = Number(slot);
  if (!/^[A-Za-z0-9_.-]+$/.test(name) || !Number.isInteger(n) || n < 1) return new Response("bad path", { status: 400 });
  const t = await slotThumb(name, n);
  if (!t) return new Response("no frame", { status: 404 });
  return new Response(fs.readFileSync(t), {
    headers: { "Content-Type": "image/jpeg", "Cache-Control": "private, max-age=3600" },
  });
}
