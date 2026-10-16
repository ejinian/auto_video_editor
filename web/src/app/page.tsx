import Link from "next/link";
import { AlertTriangle, Plus } from "lucide-react";
import { folderClips, folders, health, pendingPlans, projects, readIdeas } from "@/lib/beatcut";
import { mmss, thumbUrl } from "@/lib/format";
import { StatusTag, Tag } from "@/components/Tag";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [fs, ps, h] = await Promise.all([folders(), projects(), health()]);
  const plans = pendingPlans(fs.map((f) => f.name));
  const ideas = readIdeas().trim().split("\n").filter(Boolean);
  const strips = await Promise.all(fs.map(async (f) => (await folderClips(f.name)).slice(0, 6)));

  return (
    <div>
      {(!h.apiKey || !h.ffmpeg || !h.uv) && (
        <div className="notice warn mb-5">
          <AlertTriangle size={16} />
          <div>
            {!h.uv && <span><code>uv</code> is not on the PATH (the CLI runs with it). </span>}
            {!h.ffmpeg && <span><code>ffmpeg</code> is not on the PATH. </span>}
            {!h.apiKey && <span>The Claude panel needs <code>ANTHROPIC_API_KEY</code> in <code>web/.env.local</code> (restart <code>npm run dev</code>); the buttons work without it. </span>}
            See <Link href="/howto">how to</Link>.
          </div>
        </div>
      )}

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex-1 min-w-[280px]">
          <h1>Shoots</h1>
          <p className="lede">A shoot is a folder of phone clips in <code>clips/</code>. Open one to see its clips and the videos cut from it; the number on each clip is what the edit buttons and Claude mean by &ldquo;clip 3&rdquo;.</p>
        </div>
        <Link href="/new" className="btn lg no-underline hover:no-underline"><Plus size={18} /> New video</Link>
      </div>

      {plans.length > 0 && (
        <div className="notice mb-3">
          <div>
            <b>Planned, not shot yet:</b>{" "}
            {plans.map((p) => <span key={p.folder} className="mr-3"><Link href={`/shoot/${encodeURIComponent(p.folder)}`}>{p.folder}</Link> <span className="text-muted">(shot list in {p.path})</span></span>)}
            <span className="text-muted">— <Link href="/new">New video</Link> with the folder named <code>{plans[0].folder}</code> and it shows up here.</span>
          </div>
        </div>
      )}

      {fs.length === 0 && (
        <div className="card">No clips yet. Press <Link href="/new">New video</Link> and drop the phone clips in. Or ask Claude to <i>/day plan</i> tomorrow&apos;s shoot.</div>
      )}

      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
        {fs.map((f, i) => (
          <Link key={f.name} href={`/shoot/${encodeURIComponent(f.name)}`} className="card no-underline hover:border-acc hover:no-underline text-fg block">
            <div className="flex items-center gap-2 mb-2">
              <b className="text-[15px]">{f.name}</b>
              <Tag>{f.clipCount} clips · {mmss(f.footage)}</Tag>
              {f.plan && <Tag kind="ok">plan</Tag>}
            </div>
            <div className="flex gap-1 overflow-hidden rounded-lg">
              {strips[i].map((c) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img key={c.path} src={thumbUrl(c.folder, c.stem)} alt="" className="h-[96px] w-[54px] object-cover rounded-md bg-black" loading="lazy" />
              ))}
            </div>
            <div className="text-muted text-sm mt-2">
              {f.projects.length ? <>videos: {f.projects.join(", ")}</> : "no video yet"}
            </div>
          </Link>
        ))}
      </div>

      <h2>Latest videos</h2>
      <div className="card !p-0 overflow-hidden">
        <table className="t">
          <thead><tr><th>video</th><th>sound</th><th>cut</th><th>on-screen hook</th><th></th></tr></thead>
          <tbody>
            {ps.slice(0, 8).map((p) => (
              <tr key={p.name}>
                <td><Link href={`/video/${encodeURIComponent(p.name)}`}>{p.name}</Link></td>
                <td className="text-muted">{p.sound}</td>
                <td>{p.length.toFixed(0)} s · {p.slots} shots</td>
                <td className="text-muted">{p.caption ?? ""}</td>
                <td><StatusTag rendered={p.rendered} stale={p.stale} /></td>
              </tr>
            ))}
            {ps.length === 0 && <tr><td colSpan={5} className="text-muted">none yet</td></tr>}
          </tbody>
        </table>
        {ps.length > 8 && <div className="px-3 py-2 text-sm"><Link href="/videos">all {ps.length} videos →</Link></div>}
      </div>

      {ideas.length > 0 && (
        <>
          <h2>Ideas used so far</h2>
          <div className="card text-sm">
            {ideas.map((l, i) => <div key={i} className="font-mono text-[13px] text-muted">{l}</div>)}
            <div className="mt-2">Ask Claude <i>/day plan</i> for the next one; it rotates formulas from the swipe file.</div>
          </div>
        </>
      )}
    </div>
  );
}
