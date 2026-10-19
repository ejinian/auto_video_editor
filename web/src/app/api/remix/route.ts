import Busboy from "busboy";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { Readable, Writable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { clipsFolderExists, isVideo, nextProjectName, validFolderName } from "@/lib/beatcut";
import { beatcut, startJob } from "@/lib/jobs";
import { CLIPS, rel } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** remix1, remix2… — the first with no clips folder and no project (the CLI's rule). */
function nextRemixFolder(prefix = "remix"): string {
  for (let n = 1; ; n++) {
    const f = `${prefix}${n}`;
    if (!clipsFolderExists(f) && nextProjectName(f) === `${f}_1`) return f;
  }
}

/** JSON {link, name?, cookies?}: a posted TikTok / Instagram / YouTube video. The CLI
 *  downloads it into clips/<name>/.source/ and goes on exactly like an uploaded file. */
async function fromLink(req: Request) {
  const b = (await req.json().catch(() => ({}))) as { link?: string; name?: string; cookies?: string; mode?: string };
  const link = b.link?.trim() ?? "";
  if (!/^https?:\/\/\S+$/.test(link)) return Response.json({ error: "paste a TikTok, Instagram or YouTube link" }, { status: 400 });
  const folder = b.name?.trim() || nextRemixFolder(b.mode === "recut" ? "remix" : "reel");
  if (!validFolderName(folder)) return Response.json({ error: "bad name: letters, digits, space, _ - . only" }, { status: 400 });
  if (clipsFolderExists(folder)) return Response.json({ error: `clips/${folder}/ already exists — give it another name` }, { status: 409 });
  return start(b.mode, link, folder, b.cookies, link.replace(/^https?:\/\/(www\.)?/, "").slice(0, 50));
}

/** One job for a posted video. "reformat" (the default): three framings of the same
 *  cut, copy written by Claude on the page that opens (`?ask=reformat`). "recut": four
 *  re-cuts of its shots (`remix --video`), the right call for raw footage, not for a
 *  finished reel. */
function start(mode: string | undefined, video: string, folder: string, cookies: string | undefined, label: string) {
  const recut = mode === "recut";
  const argv = recut ? ["remix", "--video", video, "--name", folder, "--render"] : ["reformat", "--video", video, "--name", folder];
  if (cookies && /^(chrome|safari|firefox)$/.test(cookies)) argv.push("--cookies", cookies);
  const source = nextProjectName(folder);
  const job = startJob(recut ? `Remix ${label} ×4` : `Reformat ${label}`, [beatcut(...argv)], recut ? `/video/${source}` : `/video/${source}?ask=reformat`);
  return Response.json({ job: job.id, folder, source });
}

/** A folder name from a filename: "IMG_1234 final.mp4" → "img_1234_final". */
function folderFromFile(name: string): string {
  const stem = path.parse(name).name.replace(/[^A-Za-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "").toLowerCase();
  return stem || "remix";
}

/**
 * Remix a finished video: multipart {file, name?}. The file is streamed to
 * clips/<name>/.source/<file> (a dot-folder, so it is not a clip), then one job runs
 * `remix --video … --name <name> --render`: the video is split into its shots
 * (clips/<name>/shot_NN.mp4), its audio joins the pool, a project <name>_1 replays it
 * as the source, and the four remixes are cut and rendered. Then the source's page.
 */
export async function POST(req: Request) {
  const ct = req.headers.get("content-type") ?? "";
  if (ct.startsWith("application/json")) return fromLink(req);
  if (!ct.startsWith("multipart/form-data") || !req.body) return Response.json({ error: "multipart/form-data or JSON {link} expected" }, { status: 400 });
  const bb = Busboy({ headers: { "content-type": ct }, preservePath: true, limits: { files: 1 } });
  let wanted = "";
  let mode = "";
  let saved: { tmp: string; name: string } | null = null;
  let reason: string | null = null;
  const writes: Promise<void>[] = [];
  bb.on("field", (k, v) => { if (k === "name") wanted = v.trim(); if (k === "mode") mode = v.trim(); });
  bb.on("file", (_field, file, info) => {
    const fname = path.basename(info.filename ?? "").trim();
    if (!fname || fname !== info.filename || fname.startsWith(".") || !isVideo(fname)) {
      reason = "not a video file (.mp4, .mov, .m4v)";
      file.resume();
      return;
    }
    const tmp = path.join(CLIPS, `.upload.${process.pid}.${Date.now()}.part`);
    writes.push((async () => {
      await fsp.mkdir(CLIPS, { recursive: true });
      await pipeline(file, fs.createWriteStream(tmp));
      saved = { tmp, name: fname };
    })());
  });
  try {
    await pipeline(Readable.fromWeb(req.body as unknown as import("node:stream/web").ReadableStream), bb as unknown as Writable);
    await Promise.all(writes);
  } catch (e) {
    await Promise.allSettled(writes);
    if (saved) await fsp.unlink((saved as { tmp: string }).tmp).catch(() => undefined);
    return Response.json({ error: `upload failed: ${e instanceof Error ? e.message : String(e)}` }, { status: 400 });
  }
  if (!saved) return Response.json({ error: reason ?? "no file" }, { status: 400 });
  const { tmp, name: fname } = saved as { tmp: string; name: string };
  const folder = wanted || (mode === "recut" ? folderFromFile(fname) : nextRemixFolder("reel"));
  if (!validFolderName(folder) || folder.includes("..")) { await fsp.unlink(tmp).catch(() => undefined); return Response.json({ error: "bad name: letters, digits, space, _ - . only" }, { status: 400 }); }
  if (clipsFolderExists(folder)) { await fsp.unlink(tmp).catch(() => undefined); return Response.json({ error: `clips/${folder}/ already exists — give it another name` }, { status: 409 }); }
  const dest = path.join(CLIPS, folder, ".source", fname);
  await fsp.mkdir(path.dirname(dest), { recursive: true });
  await fsp.rename(tmp, dest);
  return start(mode, rel(dest), folder, undefined, fname);
}
