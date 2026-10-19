import { loadProject } from "@/lib/beatcut";
import { beatcut, startJob } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Four new videos from this one's clips (`remix`: hook cut, another sound, reorder,
 *  long version), rendered, as one job; then back to this video, whose page lists them. */
export async function POST(req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!loadProject(name)) return Response.json({ error: "no such project" }, { status: 404 });
  const b = (await req.json().catch(() => ({}))) as { only?: string; render?: boolean };
  const argv = ["-p", name, "remix"];
  if (b.render !== false) argv.push("--render");
  const only = b.only?.trim();
  if (only && /^[a-z,]+$/.test(only)) argv.push("--only", only);
  const job = startJob(`Remix ${name} ×${only ? only.split(",").length : 4}`, [beatcut(...argv)], `/video/${name}`);
  return Response.json({ job: job.id });
}
