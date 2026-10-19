import { loadProject } from "@/lib/beatcut";
import { markPosted, posted, unmarkPosted } from "@/lib/posted";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** The user's note that a video went up (out/.app/posted.json). The app posts nothing itself. */
export async function GET(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!loadProject(name)) return Response.json({ error: "no such project" }, { status: 404 });
  return Response.json({ posted: posted(name) });
}

export async function PUT(req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!loadProject(name)) return Response.json({ error: "no such project" }, { status: 404 });
  const b = (await req.json().catch(() => ({}))) as { platform?: string; url?: string };
  return Response.json({ posted: markPosted(name, b) });
}

export async function DELETE(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!loadProject(name)) return Response.json({ error: "no such project" }, { status: 404 });
  return Response.json({ removed: unmarkPosted(name) });
}
