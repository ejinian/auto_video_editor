import { getJob } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const j = getJob(id);
  return j ? Response.json(j) : Response.json({ error: "no such job" }, { status: 404 });
}
