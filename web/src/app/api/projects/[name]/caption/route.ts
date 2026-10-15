import { loadProject, readPostCaption, writePostCaption } from "@/lib/beatcut";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** The post caption (out/<folder>/<name>.caption.txt), not the on-screen hook. */
export async function GET(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!loadProject(name)) return Response.json({ error: "no such project" }, { status: 404 });
  return Response.json({ text: readPostCaption(name) });
}

export async function PUT(req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!loadProject(name)) return Response.json({ error: "no such project" }, { status: 404 });
  const { text } = (await req.json().catch(() => ({}))) as { text?: string };
  writePostCaption(name, text ?? "");
  return Response.json({ ok: true });
}
