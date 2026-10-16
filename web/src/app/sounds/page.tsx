import Link from "next/link";
import { SoundForm } from "@/components/SoundForm";
import { sounds } from "@/lib/beatcut";
import { ago, mediaUrl } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Sounds() {
  const ss = await sounds();
  return (
    <div>
      <h1>Sounds</h1>
      <p className="lede">The pool in <code>sound/</code>. Pick from it when cutting, or ask Claude to find this week&apos;s trending sounds for a bit. Never re-import a file that is already here (it truncates it).</p>
      <SoundForm />
      <h2>In the pool</h2>
      <div className="space-y-2">
        {ss.map((s) => (
          <div key={s.path} className="card !py-3 flex flex-wrap items-center gap-3">
            <div className="min-w-[220px] flex-1">
              <div className="font-semibold">{s.title}{s.author ? <span className="text-muted font-normal"> — {s.author}</span> : null}</div>
              <div className="text-muted text-xs">
                {s.duration ? `${s.duration.toFixed(0)} s` : ""}{s.tempo ? ` · ${s.tempo.toFixed(0)} bpm` : ""}
                {s.drops.length ? ` · drop at ${s.drops.map((d) => d.toFixed(1)).join(", ")} s` : " · no clear drop"}
                {" · "}{ago(s.mtime)}
                {s.source && <> · <a href={s.source} target="_blank" rel="noreferrer">source</a></>}
              </div>
              {s.usedBy.length > 0 && <div className="text-xs text-muted mt-0.5">used by {s.usedBy.map((n, i) => <span key={n}>{i ? ", " : ""}<Link href={`/video/${encodeURIComponent(n)}`}>{n}</Link></span>)}</div>}
            </div>
            <audio controls preload="none" src={mediaUrl(s.path)} className="h-9 w-[300px]" />
          </div>
        ))}
        {ss.length === 0 && <div className="text-muted text-sm">no sounds yet</div>}
      </div>
    </div>
  );
}
