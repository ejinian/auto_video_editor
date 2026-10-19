import Busboy from "busboy";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { Readable, Writable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { exists, isVideo, nextProjectName, validFolderName } from "@/lib/beatcut";
import { beatcut, startJob } from "@/lib/jobs";
import { CLIPS, rel } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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
  if (!ct.startsWith("multipart/form-data") || !req.body) return Response.json({ error: "multipart/form-data expected" }, { status: 400 });
  const bb = Busboy({ headers: { "content-type": ct }, preservePath: true, limits: { files: 1 } });
  let wanted = "";
  let saved: { tmp: string; name: string } | null = null;
  let reason: string | null = null;
  const writes: Promise<void>[] = [];
  bb.on("field", (k, v) => { if (k === "name") wanted = v.trim(); });
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
  const folder = wanted || folderFromFile(fname);
  if (!validFolderName(folder) || folder.includes("..")) { await fsp.unlink(tmp).catch(() => undefined); return Response.json({ error: "bad name: letters, digits, space, _ - . only" }, { status: 400 }); }
  if (exists(path.join(CLIPS, folder))) { await fsp.unlink(tmp).catch(() => undefined); return Response.json({ error: `clips/${folder}/ already exists — give it another name` }, { status: 409 }); }
  const dest = path.join(CLIPS, folder, ".source", fname);
  await fsp.mkdir(path.dirname(dest), { recursive: true });
  await fsp.rename(tmp, dest);
  const source = nextProjectName(folder);
  const job = startJob(`Remix ${fname} ×4`, [beatcut("remix", "--video", rel(dest), "--name", folder, "--render")], `/video/${source}`);
  return Response.json({ job: job.id, folder, source });
}
