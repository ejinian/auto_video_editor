import fs from "node:fs";
import path from "node:path";
import { folderClips, linkSound, nextProjectName, safeName } from "@/lib/beatcut";
import { beatcut, startJob } from "@/lib/jobs";
import { CLIPS, PRESETS, PROJECTS } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface CutBody {
  folder: string;
  name?: string;
  length?: number;
  preset?: string;
  link?: string;
  existing?: string;
  first?: number | null;
  mode?: "story" | "random" | "auto";
  story?: string;
  seed?: number | null;
  caption?: string;
  sync?: boolean;
  render?: boolean;
}

/** The "Cut it" form: sound (link or pool) → plan → caption → board → render, as one job. */
export async function POST(req: Request) {
  const b = (await req.json().catch(() => null)) as CutBody | null;
  if (!b?.folder || b.folder.includes("/") || b.folder.includes("..") || !fs.existsSync(path.join(CLIPS, b.folder))) {
    return Response.json({ error: "unknown clip folder" }, { status: 400 });
  }
  const clips = await folderClips(b.folder);
  if (!clips.length) return Response.json({ error: "that folder has no clips" }, { status: 400 });
  const name = safeName(b.name?.trim() || "") || nextProjectName(b.folder);
  const cmds: string[][] = [];
  const link = b.link?.trim();
  if (link) {
    cmds.push(beatcut("-p", name, "sound", link));
  } else if (b.existing) {
    try { linkSound(name, b.existing); } catch (e) { return Response.json({ error: String(e) }, { status: 400 }); }
  } else if (!fs.existsSync(path.join(PROJECTS, `${name}.sound.json`))) {
    return Response.json({ error: "pick a sound: paste a link or choose one from the pool" }, { status: 400 });
  }
  const preset = PRESETS.includes((b.preset ?? "") as never) ? b.preset! : "tight";
  const plan = ["-p", name, "plan", "--clips-dir", `clips/${b.folder}`, "--length", String(Math.min(120, Math.max(3, Number(b.length) || 30))), "--preset", preset];
  if (b.sync) plan.push("--sync");
  if (b.first) plan.push("--first", String(b.first));
  if (b.mode === "random") {
    plan.push("--random");
  } else if (b.mode === "story" || !b.mode) {
    let story = (b.story ?? "").replace(/[^\d,]/g, "").replace(/,+/g, ",").replace(/^,|,$/g, "");
    if (!story) story = clips.map((c) => c.n).filter((n) => n !== b.first).join(",");
    if (story) plan.push("--story", story);
  }
  if (b.seed !== undefined && b.seed !== null && b.seed !== ("" as never)) plan.push("--seed", String(Number(b.seed)));
  cmds.push(beatcut(...plan));
  const cap = b.caption?.trim();
  if (cap) cmds.push(beatcut("-p", name, "caption", cap));
  cmds.push(beatcut("-p", name, "board"));
  if (b.render !== false) cmds.push(beatcut("-p", name, "render"));
  const job = startJob(`Cutting ${name}`, cmds, `/video/${name}`);
  return Response.json({ job: job.id, name });
}
