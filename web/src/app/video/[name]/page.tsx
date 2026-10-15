import Link from "next/link";
import { notFound } from "next/navigation";
import { CaptionEditor } from "@/components/CaptionEditor";
import { ClipGrid } from "@/components/ClipGrid";
import { EditPanel } from "@/components/EditPanel";
import { StatusTag, Tag } from "@/components/Tag";
import { projectDetail, sounds } from "@/lib/beatcut";
import { ago, mb, mediaUrl } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Video({ params }: { params: Promise<{ name: string }> }) {
  const { name: raw } = await params;
  const name = decodeURIComponent(raw);
  const d = await projectDetail(name);
  if (!d) notFound();
  const snds = await sounds();
  const pr = d.project;
  const notes: Record<number, string> = {};
  for (const c of d.clips) notes[c.n] = c.missing ? "MISSING" : c.excluded ? "out" : c.uses ? `×${c.uses}` : "unused";
  const missing = d.clips.filter((c) => c.missing);
  const dim = new Set(d.clips.filter((c) => c.excluded || !c.uses).map((c) => c.n));
  const rhythm = pr.sync ? `synced to beats (${Object.entries(pr.density).map(([k, v]) => `${k}=${v}`).join(" ")})` : `free cuts, ${pr.preset ?? "tight"}`;
  const extras = [
    pr.first ? `opens on clip ${pr.first}` : null,
    pr.story?.length ? `story ${pr.story.join(">")}` : pr.random ? "random angles" : "auto",
    pr.seed != null ? `seed ${pr.seed}` : null,
  ].filter(Boolean).join(" · ");

  return (
    <div>
      <h1>
        {name}
        <StatusTag rendered={d.rendered} stale={d.stale} />
        {d.capcutDraft && <Tag title="a CapCut draft with this name exists">CapCut</Tag>}
      </h1>
      <p className="text-muted text-sm -mt-1 mb-3">
        {d.sound ? <>{d.sound.title}{d.sound.author ? ` — ${d.sound.author}` : ""}{d.sound.tempo ? ` · ${d.sound.tempo.toFixed(0)} bpm` : ""}</> : pr.sound}
        {" · "}{d.realLength.toFixed(1)} s · {d.slots.length} shots · {rhythm}{extras ? ` · ${extras}` : ""}
        {" · "}hook: {pr.caption ? <i>{pr.caption}</i> : "none"}
        {d.folder && <> · shoot <Link href={`/shoot/${encodeURIComponent(d.folder)}`}>{d.folder}</Link></>}
      </p>

      <div className="grid gap-5" style={{ gridTemplateColumns: "minmax(260px, 340px) 1fr" }}>
        <div>
          {d.mp4 ? (
            <video controls playsInline src={mediaUrl(d.mp4)} className="w-full rounded-xl bg-black" style={{ maxHeight: "70vh" }} />
          ) : (
            <div className="card text-muted aspect-[9/16] flex items-center justify-center">not rendered yet — press Render</div>
          )}
          {d.mp4 && (
            <div className="text-xs text-muted mt-2 space-y-0.5">
              <div><code>~/Desktop/beatcut/{d.inFinal ? `final/${name}.mp4` : d.mp4}</code> · {mb(d.mp4Size)}{!d.inFinal && " · draft, not in final/"}</div>
              <div><a href={mediaUrl(d.inFinal ? `final/${name}.mp4` : d.mp4, true)}>download</a></div>
            </div>
          )}
        </div>
        <div>
          {d.board ? (
            <a href={mediaUrl(d.board)} target="_blank" rel="noreferrer">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`${mediaUrl(d.board)}?v=${d.boardMtime}`} alt="storyboard" className="w-full rounded-xl" />
            </a>
          ) : <div className="card text-muted">no storyboard yet</div>}
          <div className="text-muted text-xs mt-1">Storyboard: one frame per shot, labelled slot · clip · length. The way to check a cut without playing it.</div>
        </div>
      </div>

      {missing.length > 0 && (
        <div className="card border-bad/60 mt-4 text-sm">
          <b>Clips moved or renamed:</b> {missing.map((c) => c.path).join(", ")}. Nothing can render or rebuild until they are back at those paths (or the video is re-planned from its shoot folder).
        </div>
      )}

      <h2>Edit</h2>
      <EditPanel d={d} sounds={snds} />

      <h2>Shots</h2>
      <div className="card !p-0 overflow-hidden">
        <table className="t">
          <thead><tr><th>slot</th><th>time (s)</th><th>dur</th><th>clip</th><th>in at</th><th></th></tr></thead>
          <tbody>
            {d.slots.map((r) => (
              <tr key={r.n} className={r.drop ? "drop" : ""}>
                <td>{r.n}</td>
                <td>{r.t0.toFixed(2)}–{r.t1.toFixed(2)}</td>
                <td>{r.dur.toFixed(2)}</td>
                <td><b>{r.clip}</b> <span className="text-muted">{r.file}</span></td>
                <td>{r.in.toFixed(1)}</td>
                <td className="text-muted text-xs">{[r.drop ? "DROP" : "", r.hero ? "hero" : "", r.uses > 1 ? `clip used ×${r.uses}` : ""].filter(Boolean).join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Caption for the post</h2>
      <CaptionEditor name={name} initial={d.postCaption} file={d.captionFile} />

      <h2>Clips in this video</h2>
      <ClipGrid clips={d.clips} notes={notes} dim={dim} />

      {(d.versions.length > 0 || d.frameSheets.length > 0) && (
        <div className="grid gap-5 mt-6" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
          {d.versions.length > 0 && (
            <div>
              <h2 className="!mt-0">Earlier renders</h2>
              <div className="card !p-0 overflow-hidden">
                <table className="t">
                  <tbody>
                    {d.versions.map((v) => (
                      <tr key={v.name}><td><a href={mediaUrl(v.path)} target="_blank" rel="noreferrer">{v.name}</a></td><td className="text-muted">{mb(v.size)}</td><td className="text-muted">{ago(v.mtime)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {d.frameSheets.length > 0 && (
            <div>
              <h2 className="!mt-0">Frame sheets</h2>
              <div className="card text-sm">
                {d.frameSheets.map((f) => <div key={f.path}><a href={mediaUrl(f.path)} target="_blank" rel="noreferrer">{f.clip}</a></div>)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
