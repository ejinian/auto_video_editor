import Link from "next/link";
import path from "node:path";
import { Poster } from "@/components/Poster";
import { StatusChip } from "@/components/StatusChip";
import { exists, projectOut } from "@/lib/beatcut";
import { mediaUrl } from "@/lib/format";
import { runningJobFor } from "@/lib/jobs";
import { rel } from "@/lib/paths";
import type { ProjectDetail } from "@/lib/types";

export const REMIX_LABEL: Record<string, string> = {
  hook: "hook cut · 8 s",
  sound: "another sound",
  reorder: "reorder · 15 s",
  long: "long version · 30 s",
};

/** The remix family on a video page: where this video came from, and the remixes cut
 *  from it (one card each, same chip as the feed). Server component; nothing to click
 *  but the links. */
const REFORMAT_LABEL: Record<string, string> = { hook: "hook line", narrated: "narrated", reply: "comment reply", reaction: "reacting avatar", goofy: "goofy", cinematic: "cinematic" };

export function RemixStrip({ d }: { d: ProjectDetail }) {
  if (!d.remixOf && d.remixes.length === 0 && d.reformats.length < 2) return null;
  return (
    <div className="mt-4 space-y-3">
      {d.reformats.length > 1 && (
        <div>
          <h2 className="!mt-0">The framings <span className="text-muted font-normal text-sm">— same video, each a different post</span></h2>
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
            {d.reformats.map((p) => (
              <Link key={p.name} href={`/video/${encodeURIComponent(p.name)}`} className={`card vcard hover:border-acc ${p.name === d.name ? "!border-acc" : ""}`}>
                <Poster sources={[`/api/slot-thumb/${encodeURIComponent(p.name)}/1`, ...(exists(path.join(projectOut(p.name), `_${p.name}_board.jpg`)) ? [mediaUrl(rel(path.join(projectOut(p.name), `_${p.name}_board.jpg`)))] : [])]} alt={p.name} />
                <div className="body">
                  <div className="name">{p.name} <span className="tag ml-1">{REFORMAT_LABEL[p.reformat ?? ""] ?? p.reformat}</span></div>
                  {p.caption ? <div className="hook">&ldquo;{p.caption}&rdquo;</div> : <div className="meta">{p.name === d.name ? "this one" : "no copy yet"}</div>}
                  <div className="foot">
                    <StatusChip name={p.name} rendered={p.rendered} stale={p.stale} posted={p.posted} job={runningJobFor(p.name)} bar />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
      {d.remixOf && (
        <div className="notice text-sm">
          <span><b>{REMIX_LABEL[d.remix ?? ""] ?? d.remix ?? "remix"}</b> of <Link href={`/video/${encodeURIComponent(d.remixOf)}`}>{d.remixOf}</Link> — same clips, cut to be a different post.</span>
        </div>
      )}
      {d.remixes.length > 0 && (
        <div>
          <h2 className="!mt-0">Remixes of this video <span className="text-muted font-normal text-sm">— {d.remixes.length} new posts from the same clips</span></h2>
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
            {d.remixes.map((p) => {
              const board = path.join(projectOut(p.name), `_${p.name}_board.jpg`);
              const sources = [`/api/slot-thumb/${encodeURIComponent(p.name)}/1`];
              if (exists(board)) sources.push(mediaUrl(rel(board)));
              return (
                <Link key={p.name} href={`/video/${encodeURIComponent(p.name)}`} className="card vcard hover:border-acc">
                  <Poster sources={sources} alt={p.name} />
                  <div className="body">
                    <div className="name">{p.name} <span className="tag ml-1">{REMIX_LABEL[p.remix ?? ""] ?? p.remix}</span></div>
                    <div className="meta">{p.length.toFixed(0)} s · {p.slots} shots</div>
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
        </div>
      )}
    </div>
  );
}
