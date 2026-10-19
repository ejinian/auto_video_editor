import Busboy from "busboy";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { Readable, Writable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { folderClips, isVideo, nextProjectName, validFolderName } from "@/lib/beatcut";
import { CLIPS } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** The clips of a folder, numbered, plus the name the next video from it would get. */
export async function GET(_req: Request, { params }: { params: Promise<{ folder: string }> }) {
  const { folder } = await params;
  if (!validFolderName(folder)) return Response.json({ error: "bad folder name" }, { status: 400 });
  return Response.json({ folder, clips: await folderClips(folder), nextName: nextProjectName(folder) });
}

interface Saved { name: string; size: number }
interface Rejected { name: string; reason: string }

/**
 * Upload clips into clips/<folder>/ (created if missing). Multipart; every file part is
 * streamed straight to disk through a `.part` file and renamed when complete, so a 4K
 * clip never sits in memory. Original filenames are kept. Anything that is not a
 * .mov/.mp4/.m4v, or whose name has a "/" or "..", is refused; so is a name already in
 * the folder (adding clips renumbers the folder, overwriting would silently change an
 * edit that already used the old file).
 */
export async function POST(req: Request, { params }: { params: Promise<{ folder: string }> }) {
  const { folder } = await params;
  if (!validFolderName(folder)) return Response.json({ error: "bad folder name: letters, digits, space, _ - . only" }, { status: 400 });
  const ct = req.headers.get("content-type") ?? "";
  if (!ct.startsWith("multipart/form-data") || !req.body) return Response.json({ error: "multipart/form-data expected" }, { status: 400 });
  const dir = path.join(CLIPS, folder);
  await fsp.mkdir(dir, { recursive: true });

  const saved: Saved[] = [];
  const rejected: Rejected[] = [];
  const writes: Promise<void>[] = [];
  // preservePath: see the raw name, so "../x.mp4" is refused rather than quietly saved as x.mp4
  const bb = Busboy({ headers: { "content-type": ct }, preservePath: true });

  bb.on("file", (_field, file, info) => {
    const name = path.basename(info.filename ?? "").trim();
    const reason =
      !name ? "no filename"
      : name !== info.filename || name.includes("/") || name.includes("..") || name.startsWith(".") ? "bad filename"
      : !isVideo(name) ? "not a video (.mov, .mp4, .m4v)"
      : fs.existsSync(path.join(dir, name)) ? "already in the folder"
      : null;
    if (reason) {
      rejected.push({ name: info.filename ?? "?", reason });
      file.resume(); // drain and drop
      return;
    }
    const dest = path.join(dir, name);
    const tmp = `${dest}.${process.pid}.part`;
    let size = 0;
    file.on("data", (d: Buffer) => { size += d.length; });
    const w = (async () => {
      try {
        await pipeline(file, fs.createWriteStream(tmp));
        await fsp.rename(tmp, dest);
        saved.push({ name, size });
      } catch (e) {
        try { await fsp.unlink(tmp); } catch { /* none */ }
        rejected.push({ name, reason: e instanceof Error ? e.message : String(e) });
      }
    })();
    writes.push(w);
  });

  try {
    await pipeline(Readable.fromWeb(req.body as unknown as import("node:stream/web").ReadableStream), bb as unknown as Writable);
    await Promise.all(writes);
  } catch (e) {
    await Promise.allSettled(writes);
    return Response.json({ error: `upload failed: ${e instanceof Error ? e.message : String(e)}`, saved, rejected }, { status: 400 });
  }
  const clips = await folderClips(folder);
  return Response.json({ folder, saved, rejected, clips, nextName: nextProjectName(folder) });
}
