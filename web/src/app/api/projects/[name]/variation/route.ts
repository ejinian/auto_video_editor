import { linkSound, loadProject, nextProjectName, projectFolder, projectSoundPointer } from "@/lib/beatcut";
import { beatcut, startJob } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Same clips and settings, the next seed (and optionally another sound) → a new project. */
export async function POST(req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const pr = loadProject(name);
  if (!pr) return Response.json({ error: "no such project" }, { status: 404 });
  const b = (await req.json().catch(() => ({}))) as { link?: string; existing?: string; preset?: string; mode?: string };
  const folder = projectFolder(name) ?? "misc";
  const next = nextProjectName(folder);
  const cmds: string[][] = [];
  const link = b.link?.trim();
  if (link) cmds.push(beatcut("-p", next, "sound", link));
  else {
    try { linkSound(next, b.existing || projectSoundPointer(name)?.sound || pr.sound); }
    catch (e) { return Response.json({ error: String(e) }, { status: 400 }); }
  }
  const plan = ["-p", next, "plan", "--clips", ...pr.clips, "--length", String(pr.length)];
  if (pr.first) plan.push("--first", String(pr.first));
  const mode = b.mode ?? (pr.random ? "random" : pr.story ? "story" : "auto");
  if (mode === "random") plan.push("--random");
  else if (mode === "story" && pr.story?.length) plan.push("--story", pr.story.join(","));
  plan.push("--seed", String((pr.seed ?? 0) + 1));
  if (pr.sync) plan.push("--sync");
  const preset = b.preset || pr.preset;
  if (preset) plan.push("--preset", preset);
  cmds.push(beatcut(...plan));
  if (pr.caption) cmds.push(beatcut("-p", next, "caption", pr.caption));
  cmds.push(beatcut("-p", next, "board"), beatcut("-p", next, "render"));
  const job = startJob(`Variation ${next} of ${name}`, cmds, `/video/${next}`);
  return Response.json({ job: job.id, name: next });
}
