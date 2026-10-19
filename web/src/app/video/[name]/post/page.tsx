import Link from "next/link";
import { Download } from "lucide-react";
import { notFound } from "next/navigation";
import { CaptionEditor } from "@/components/CaptionEditor";
import { CopyCaption, PostPanel } from "@/components/PostPanel";
import { StatusChip } from "@/components/StatusChip";
import { projectDetail } from "@/lib/beatcut";
import { mb, mediaUrl } from "@/lib/format";
import { runningJobFor } from "@/lib/jobs";

export const dynamic = "force-dynamic";

/** The post step: the finished mp4 to download, the caption to copy, a checklist, and
 *  "Mark as posted". The app never posts; the user does, on their phone or in the browser. */
export default async function Post({ params }: { params: Promise<{ name: string }> }) {
  const { name: raw } = await params;
  const name = decodeURIComponent(raw);
  const d = await projectDetail(name);
  if (!d) notFound();
  const pr = d.project;
  const file = d.inFinal ? `final/${name}.mp4` : d.mp4;
  const sound = d.sound ? `${d.sound.title}${d.sound.author ? ` — ${d.sound.author}` : ""}` : "";

  return (
    <div>
      <h1>
        Post {name}
        <StatusChip name={name} rendered={d.rendered} stale={d.stale} posted={d.posted} job={runningJobFor(name)} />
      </h1>
      <p className="lede">
        Download the mp4, copy the caption, post it from your phone or the browser, then mark it here so the feed says so.
        {" "}<b>Nothing is posted by this app</b> — it has no account and never uploads.
        {" · "}<Link href={`/video/${encodeURIComponent(name)}`}>← back to the edit</Link>
      </p>

      {d.stale && d.rendered && (
        <div className="notice warn mb-4">
          <div>This video was edited after its last render. The file below is the <b>previous</b> cut; press Render on the <Link href={`/video/${encodeURIComponent(name)}`}>edit page</Link> first if that is not what you want to post.</div>
        </div>
      )}

      <div className="grid gap-5" style={{ gridTemplateColumns: "minmax(220px, 320px) 1fr" }}>
        <div>
          {file ? (
            <>
              <video src={mediaUrl(file)} controls playsInline className="w-full rounded-xl bg-black" style={{ aspectRatio: "9 / 16" }} />
              <div className="flex items-center gap-3 mt-3 flex-wrap">
                <a href={mediaUrl(file, true)} className="btn no-underline hover:no-underline" download><Download size={16} /> Download mp4</a>
                <span className="text-muted text-xs">{file} · {mb(d.mp4Size)}</span>
              </div>
            </>
          ) : (
            <div className="card">
              Not rendered yet — nothing to post. Press <b>Render</b> on the <Link href={`/video/${encodeURIComponent(name)}`}>edit page</Link>.
            </div>
          )}
        </div>

        <div className="min-w-0">
          <h2 className="!mt-0">On-screen hook</h2>
          <div className="card">{pr.caption ? <i>{pr.caption}</i> : <span className="text-muted">none (set one with &ldquo;Hook&rdquo; on the edit page)</span>}</div>

          <h2>Caption for the post</h2>
          <CaptionEditor name={name} initial={d.postCaption} file={d.captionFile} />
          <div className="mt-2"><CopyCaption name={name} /></div>

          <h2>Post it</h2>
          <PostPanel name={name} posted={d.posted} soundTitle={sound} />
        </div>
      </div>
    </div>
  );
}
