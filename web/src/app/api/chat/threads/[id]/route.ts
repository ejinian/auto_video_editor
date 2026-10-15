import { deleteThread, upsertThread } from "@/lib/chats";

export const dynamic = "force-dynamic";

export async function DELETE(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  deleteThread(id);
  return Response.json({ ok: true });
}

export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { title } = (await req.json().catch(() => ({}))) as { title?: string };
  if (!title?.trim()) return Response.json({ error: "title required" }, { status: 400 });
  return Response.json(upsertThread({ id, title: title.trim().slice(0, 80) }));
}
