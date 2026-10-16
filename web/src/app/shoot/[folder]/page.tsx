import Link from "next/link";
import { Plus } from "lucide-react";
import { notFound } from "next/navigation";
import fs from "node:fs";
import path from "node:path";
import { ClipGrid } from "@/components/ClipGrid";
import { FramesButton } from "@/components/FramesButton";
import { Markdown } from "@/components/Markdown";
import { StatusTag, Tag } from "@/components/Tag";
import { folderClips, projects, readPlan } from "@/lib/beatcut";
import { mediaUrl, mmss } from "@/lib/format";
import { OUT } from "@/lib/paths";

export const dynamic = "force-dynamic";

export default async function Shoot({ params }: { params: Promise<{ folder: string }> }) {
  const { folder: raw } = await params;
  const folder = decodeURIComponent(raw);
  if (folder.includes("/") || folder.includes("..")) notFound();
  const clips = await folderClips(folder);
  const plan = readPlan(folder);
  if (!clips.length && !plan) notFound();
  const ps = await projects();
  const mine = ps.filter((p) => p.folder === folder);
  const sheets = clips
    .map((c) => ({ clip: c, rel: `out/${folder}/_frames_${c.stem}.jpg` }))
    .filter((s) => fs.existsSync(path.join(OUT, folder, `_frames_${s.clip.stem}.jpg`)));

  return (
    <div>
      <h1>
        {folder}
        <Tag>{clips.length} clips · {mmss(clips.reduce((a, c) => a + c.duration, 0))}</Tag>
        {clips.some((c) => c.hdr) && <Tag kind="warn" title="HDR clips get an Apple-tone-mapped SDR proxy at render time, automatically">HDR</Tag>}
      </h1>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <p className="lede flex-1 min-w-[280px]">
          Clips live in <code>clips/{folder}/</code>. Their numbers are what the edit buttons and Claude use (&ldquo;clip 3&rdquo;); adding or renaming files renumbers them.
          {" "}<Link href={`/new?folder=${encodeURIComponent(folder)}`}>Add clips</Link> ·{" "}
          <FramesButton folder={folder} label={sheets.length ? "Redo frame sheets" : "Make frame sheets"} />
        </p>
        {clips.length > 0 && (
          <Link href={`/new?folder=${encodeURIComponent(folder)}`} className="btn lg no-underline hover:no-underline" title="pick a sound, then length, pace, opener and order — or ask the Claude panel"><Plus size={18} /> New video from these clips</Link>
        )}
      </div>

      {clips.length > 0 ? <ClipGrid clips={clips} /> : <div className="card">No clips in <code>clips/{folder}/</code> yet. <Link href="/new">New video</Link> with this folder name drops them in.</div>}

      {plan && (
        <>
          <h2>Shot list</h2>
          <div className="card"><Markdown text={plan} /></div>
        </>
      )}

      {sheets.length > 0 && (
        <>
          <h2>Frame sheets (what happens when, per clip)</h2>
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
            {sheets.map((s) => (
              <a key={s.rel} href={mediaUrl(s.rel)} target="_blank" rel="noreferrer" className="card !p-2 block no-underline">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={mediaUrl(s.rel)} alt={s.clip.name} className="w-full rounded" loading="lazy" />
                <div className="text-xs text-muted mt-1">{s.clip.n} · {s.clip.name}</div>
              </a>
            ))}
          </div>
        </>
      )}

      <h2>Videos from this shoot</h2>
      {mine.length ? (
        <div className="card !p-0 overflow-hidden">
          <table className="t">
            <thead><tr><th>video</th><th>sound</th><th>cut</th><th>hook</th><th></th></tr></thead>
            <tbody>
              {mine.map((p) => (
                <tr key={p.name}>
                  <td><Link href={`/video/${encodeURIComponent(p.name)}`}>{p.name}</Link></td>
                  <td className="text-muted">{p.sound}</td>
                  <td>{p.length.toFixed(0)} s · {p.slots} shots</td>
                  <td className="text-muted">{p.caption ?? ""}</td>
                  <td><StatusTag rendered={p.rendered} stale={p.stale} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div className="text-muted text-sm">none yet</div>}
    </div>
  );
}
