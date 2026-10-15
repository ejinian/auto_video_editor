import { folderClips } from "@/lib/beatcut";
import { beatcut, startJob } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Timestamped frame sheets for every clip of a folder (out/<folder>/_frames_<clip>.jpg). */
export async function POST(_req: Request, { params }: { params: Promise<{ folder: string }> }) {
  const { folder } = await params;
  if (folder.includes("/") || folder.includes("..")) return Response.json({ error: "bad folder" }, { status: 400 });
  const clips = await folderClips(folder);
  if (!clips.length) return Response.json({ error: "no clips" }, { status: 404 });
  const job = startJob(`Frame sheets for ${folder}`, [beatcut("frames", ...clips.map((c) => c.path))], `/shoot/${folder}`);
  return Response.json({ job: job.id });
}
