import fs from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { ROOT, safeJoin } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ALLOWED = ["out", "final", "sound", "clips", "projects"];
const TYPES: Record<string, string> = {
  ".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/x-m4v",
  ".mp3": "audio/mpeg", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
  ".json": "application/json", ".txt": "text/plain; charset=utf-8", ".md": "text/markdown; charset=utf-8",
};

/** Serve a file under out/, final/, sound/, clips/ or projects/ with HTTP Range support (video seeking). */
export async function GET(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path: parts } = await params;
  if (!parts?.length || !ALLOWED.includes(parts[0])) return new Response("not found", { status: 404 });
  const full = safeJoin(ROOT, ...parts.map(decodeURIComponent));
  if (!full) return new Response("not found", { status: 404 });
  let st: fs.Stats;
  try {
    st = fs.statSync(full);
    if (!st.isFile()) throw new Error("not a file");
  } catch {
    return new Response("not found", { status: 404 });
  }
  const type = TYPES[path.extname(full).toLowerCase()] ?? "application/octet-stream";
  const headers: Record<string, string> = {
    "Content-Type": type,
    "Accept-Ranges": "bytes",
    "Last-Modified": st.mtime.toUTCString(),
    "Cache-Control": "private, no-cache",
  };
  if (new URL(req.url).searchParams.has("download")) headers["Content-Disposition"] = `attachment; filename="${path.basename(full)}"`;
  const range = req.headers.get("range");
  if (range) {
    const m = range.match(/bytes=(\d*)-(\d*)/);
    if (m) {
      let start = m[1] ? Number(m[1]) : 0;
      let end = m[2] ? Number(m[2]) : st.size - 1;
      if (!m[1] && m[2]) { start = Math.max(0, st.size - Number(m[2])); end = st.size - 1; }
      if (start >= st.size || end >= st.size || start > end) {
        return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${st.size}` } });
      }
      headers["Content-Range"] = `bytes ${start}-${end}/${st.size}`;
      headers["Content-Length"] = String(end - start + 1);
      const nodeStream = fs.createReadStream(full, { start, end });
      return new Response(Readable.toWeb(nodeStream) as ReadableStream, { status: 206, headers });
    }
  }
  headers["Content-Length"] = String(st.size);
  return new Response(Readable.toWeb(fs.createReadStream(full)) as ReadableStream, { status: 200, headers });
}
