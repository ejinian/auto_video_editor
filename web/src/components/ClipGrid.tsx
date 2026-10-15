import { mediaUrl, thumbUrl } from "@/lib/format";
import type { ClipInfo } from "@/lib/types";

export function ClipTile({ clip, note, dim }: { clip: ClipInfo; note?: string; dim?: boolean }) {
  return (
    <a className={`clip block ${dim ? "opacity-40" : ""}`} href={mediaUrl(clip.path)} target="_blank" rel="noreferrer" title={`${clip.name} · ${clip.duration.toFixed(1)} s · ${clip.w}x${clip.h}${clip.hdr ? " · HDR (SDR proxy at render)" : ""}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={thumbUrl(clip.folder, clip.stem)} alt={clip.name} loading="lazy" />
      <span className="n">{clip.n}</span>
      {clip.hdr && <span className="absolute top-1.5 right-1.5 text-[10px] font-bold bg-black/70 text-warn px-1.5 py-0.5 rounded">HDR</span>}
      {clip.w > clip.h && <span className="absolute bottom-8 right-1.5 text-[10px] font-bold bg-black/70 text-warn px-1.5 py-0.5 rounded">landscape</span>}
      <small>{clip.name} · {clip.duration.toFixed(0)}s{note ? ` · ${note}` : ""}</small>
    </a>
  );
}

export function ClipGrid({ clips, notes, dim }: { clips: ClipInfo[]; notes?: Record<number, string>; dim?: Set<number> }) {
  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" }}>
      {clips.map((c) => <ClipTile key={c.path} clip={c} note={notes?.[c.n]} dim={dim?.has(c.n)} />)}
    </div>
  );
}
