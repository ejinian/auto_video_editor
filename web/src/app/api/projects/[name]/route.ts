import { deleteProject, loadProject, projectDetail } from "@/lib/beatcut";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const d = await projectDetail(name);
  return d ? Response.json(d) : Response.json({ error: "no such project" }, { status: 404 });
}

/** Delete the project and everything it produced (the mp4 in final/ included). */
export async function DELETE(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!loadProject(name)) return Response.json({ error: "no such project" }, { status: 404 });
  return Response.json({ removed: deleteProject(name) });
}
