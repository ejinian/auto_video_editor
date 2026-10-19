import Link from "next/link";
import { notFound } from "next/navigation";
import { CaptionEditor } from "@/components/CaptionEditor";
import { ClipGrid } from "@/components/ClipGrid";
import { AllCommands, EditToolbar } from "@/components/EditPanel";
import { StatusTag, Tag } from "@/components/Tag";
import { VideoEditor } from "@/components/VideoEditor";
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
        <Link href={`/video/${encodeURIComponent(name)}/post`} className="btn sm no-underline hover:no-underline ml-auto" title="download the mp4, copy the caption, mark it posted">Post it →</Link>
      </h1>
      <p className="lede">
        {d.sound ? <>{d.sound.title}{d.sound.author ? ` — ${d.sound.author}` : ""}{d.sound.tempo ? ` · ${d.sound.tempo.toFixed(0)} bpm` : ""}</> : pr.sound}
        {" · "}{d.realLength.toFixed(1)} s · {d.slots.length} shots · {rhythm}{extras ? ` · ${extras}` : ""}
        {" · "}hook: {pr.caption ? <i>{pr.caption}</i> : "none"}
        {d.folder && <> · shoot <Link href={`/shoot/${encodeURIComponent(d.folder)}`}>{d.folder}</Link></>}
      </p>

      <EditToolbar d={d} sounds={snds} />

      {missing.length > 0 && (
        <div className="card border-bad/60 mt-4 text-sm">
          <b>Clips moved or renamed:</b> {missing.map((c) => c.path).join(", ")}. Nothing can render or rebuild until they are back at those paths (or the video is re-planned from its shoot folder).
        </div>
      )}

      <h2>Edit</h2>
      <VideoEditor d={d} />

      <div className="mt-4 space-y-3">
        <details className="card !p-0 overflow-hidden">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold select-none">Storyboard <span className="text-muted font-normal">— one frame per shot, labelled slot · clip · length (what Claude reads)</span></summary>
          <div className="px-4 pb-4">
            {d.board ? (
              <a href={mediaUrl(d.board)} target="_blank" rel="noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`${mediaUrl(d.board)}?v=${d.boardMtime}`} alt="storyboard" className="w-full rounded-xl" />
              </a>
            ) : <div className="text-muted text-sm">no storyboard yet — press Storyboard</div>}
          </div>
        </details>
        <AllCommands d={d} />
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
