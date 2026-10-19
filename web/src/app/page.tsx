import Link from "next/link";
import { AlertTriangle, Plus, Shuffle } from "lucide-react";
import path from "node:path";
import { exists, folders, health, pendingPlans, projectOut, projects, readIdeas } from "@/lib/beatcut";
import { mediaUrl, mmss } from "@/lib/format";
import { runningJobFor } from "@/lib/jobs";
import { rel } from "@/lib/paths";
import { LiveJobs } from "@/components/LiveJobs";
import { Poster } from "@/components/Poster";
import { StatusChip } from "@/components/StatusChip";

export const dynamic = "force-dynamic";

/** The feed: every video, newest first, with the one thing that matters about it (its status). */
export default async function Home() {
  const [fs, ps, h] = await Promise.all([folders(), projects(), health()]);
  const plans = pendingPlans(fs.map((f) => f.name));
  const ideas = readIdeas().trim().split("\n").filter(Boolean);

  return (
    <div>
      <LiveJobs />
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
          <h1>Videos</h1>
          <p className="lede">Newest first. A card is a video: open it to fix the edit, or press <b>Post it</b> on it when the chip says ready. Nothing is ever posted by the app.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/remix" className="btn sec lg no-underline hover:no-underline" title="drop a reel that did numbers, get four new posts from its shots"><Shuffle size={18} /> Remix</Link>
          <Link href="/new" className="btn lg no-underline hover:no-underline"><Plus size={18} /> New video</Link>
        </div>
      </div>

      {ps.length === 0 && (
        <div className="card">No video yet. Press <Link href="/new">New video</Link>: drop the phone clips in, pick a sound, cut.</div>
      )}

      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
        {ps.map((p) => {
          const board = path.join(projectOut(p.name), `_${p.name}_board.jpg`);
          const sources = [`/api/slot-thumb/${encodeURIComponent(p.name)}/1`];
          if (exists(board)) sources.push(mediaUrl(rel(board)));
          return (
            <Link key={p.name} href={`/video/${encodeURIComponent(p.name)}`} className="card vcard hover:border-acc">
              <Poster sources={sources} alt={p.name} />
              <div className="body">
                <div className="name">{p.name}{p.remixOf && <span className="tag ml-1.5 font-normal" title={`a ${p.remix} remix of ${p.remixOf}`}>remix of {p.remixOf}</span>}{p.reformat && <span className="tag ml-1.5 font-normal" title="a reformat of a posted video: the same cut, a new framing">{p.reformat} reformat</span>}</div>
                <div className="meta" title={p.sound}>
                  {p.folder ? <>shoot {p.folder} · </> : null}{p.length.toFixed(0)} s · {p.slots} shots
                </div>
                <div className="meta" title={p.sound}>♪ {p.sound}</div>
                {p.caption ? <div className="hook">&ldquo;{p.caption}&rdquo;</div> : <div className="meta">no hook on screen</div>}
                <div className="foot">
                  <StatusChip name={p.name} rendered={p.rendered} stale={p.stale} posted={p.posted} job={runningJobFor(p.name)} bar />
                </div>
              </div>
            </Link>
          );
        })}
      </div>

      <h2>Shoots</h2>
      <div className="strip">
        {fs.length === 0 && <span>no clips yet — <Link href="/new">New video</Link> drops them into <code>clips/&lt;folder&gt;/</code></span>}
        {fs.map((f, i) => (
          <span key={f.name} className="inline-flex items-baseline gap-[10px]">
            {i > 0 && <span className="dot">·</span>}
            <span>
              <Link href={`/shoot/${encodeURIComponent(f.name)}`} title={`${f.clipCount} clips · ${mmss(f.footage)}${f.plan ? " · has a shot list" : ""}`}>{f.name}</Link>
              <small className="text-muted ml-[6px]">{f.clipCount} clips</small>
            </span>
          </span>
        ))}
        {plans.length > 0 && (
          <span className="text-muted inline-flex items-baseline gap-[10px]">
            {fs.length > 0 && <span className="dot">·</span>}
            <span>planned, not shot yet: {plans.map((p, i) => <span key={p.folder}>{i > 0 && ", "}<Link href={`/shoot/${encodeURIComponent(p.folder)}`}>{p.folder}</Link></span>)}
            {" "}(<Link href="/new">New video</Link> with that folder name)</span>
          </span>
        )}
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
