"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { askClaude } from "@/components/chat/ask";
import { clipFrameUrl, thumbUrl } from "@/lib/format";
import type { ProjectDetail, SlotRow } from "@/lib/types";

const FRAME = 1 / 30;
const HEAD_PAD = 0.3, TAIL_PAD = 0.15;   // beatcut.py's own margins when it places a clip

type Run = (cmd: string, args: Record<string, string>) => void;

/** The side card for the selected shot: what it is, where it starts in its clip, and
 *  every edit that applies to it. Each button is one CLI command. */
export function SlotCard({ d, slot, time, busy, onRun, onSeek }: {
  d: ProjectDetail; slot: SlotRow; time: number; busy: boolean; onRun: Run; onSeek: (t: number) => void;
}) {
  const clip = d.clips[slot.clip - 1];
  const maxIn = clip ? Math.max(0, clip.duration - slot.dur - TAIL_PAD) : 0;
  const [inAt, setInAt] = useState(slot.in);
  const [frame, setFrame] = useState<string | null>(null);
  const dirty = useRef(false);
  const want = useRef<string | null>(null);

  // the frame at the scrub position, debounced; stale responses are ignored
  useEffect(() => {
    if (!clip) return;
    const url = clipFrameUrl(clip.folder, clip.stem, inAt + slot.dur / 2);
    want.current = url;
    const t = setTimeout(() => {
      const img = new Image();
      img.onload = () => { if (want.current === url) setFrame(url); };
      img.src = url;
    }, 90);
    return () => clearTimeout(t);
  }, [clip, inAt, slot.dur]);

  const commitIn = () => {
    if (!dirty.current) return;
    dirty.current = false;
    if (Math.abs(inAt - slot.in) >= 0.01) onRun("in", { slot: String(slot.n), sec: inAt.toFixed(2) });
  };

  const inside = d.mp4 != null && time > slot.t0 + FRAME && time < slot.t1 - FRAME;
  const hasDrop = (d.project._drops ?? []).length > 0;
  const last = slot.n === d.slots.length;

  return (
    <div className="card space-y-3 min-w-0">
      <div className="flex items-baseline gap-2 flex-wrap">
        <b className="text-base">Shot {slot.n}</b>
        <span className="text-muted text-sm">clip <b className="text-fg">{slot.clip}</b> · {slot.file} · {slot.dur.toFixed(2)} s · {slot.t0.toFixed(2)}–{slot.t1.toFixed(2)} s</span>
        {slot.drop && <span className="tag ok">DROP</span>}
        {slot.hero && <span className="tag warn">hero</span>}
        {slot.uses > 1 && <span className="tag">clip used ×{slot.uses}</span>}
        <span className="flex-1" />
        {d.mp4 && <button className="btn sec sm" onClick={() => onSeek(slot.t0)} title="seek the player to this shot">▶ {slot.t0.toFixed(1)} s</button>}
      </div>

      {clip && (
        <div className="flex gap-3 items-start">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={frame ?? clipFrameUrl(clip.folder, clip.stem, slot.in + slot.dur / 2)} alt="" className="rounded-lg bg-black shrink-0" style={{ height: 180, aspectRatio: `${clip.w || 9} / ${clip.h || 16}`, objectFit: "cover" }} draggable={false} />
          <div className="flex-1 min-w-0">
            <label className="label !mt-0">Starts <b className="text-fg">{inAt.toFixed(2)} s</b> into the clip <span className="text-muted">(0–{maxIn.toFixed(2)} s of {clip.duration.toFixed(1)} s)</span></label>
            <input
              type="range" className="w-full" min={0} max={maxIn} step={0.05} value={Math.min(inAt, maxIn)} disabled={busy || maxIn <= 0}
              onChange={(e) => { dirty.current = true; setInAt(Number(e.target.value)); }}
              onPointerUp={commitIn} onKeyUp={commitIn} onBlur={commitIn}
              aria-label="where in the clip this shot starts"
            />
            <div className="text-muted text-xs">Drag to pick the part of the clip; the frame is the middle of the shot. Lets go → <code>in {slot.n} {inAt.toFixed(2)}</code>.</div>

            <div className="flex flex-wrap gap-1.5 mt-3">
              <button className="btn sec sm" disabled={busy || last} title={last ? "the last shot has nothing after it" : `join shot ${slot.n + 1} into this one — merge ${slot.n + 1}`} onClick={() => onRun("merge", { slot: String(slot.n + 1) })}>Hold longer</button>
              <button className="btn sec sm" disabled={busy || !inside} title={inside ? `cut ${slot.n} ${time.toFixed(2)} — the clip runs on across the new cut` : "move the playhead inside this shot first"} onClick={() => onRun("cut", { slot: String(slot.n), sec: time.toFixed(3) })}>Cut here{inside ? ` (${time.toFixed(2)} s)` : ""}</button>
              <button className="btn sec sm" disabled={busy} title={`split ${slot.n} — cuts on the beat nearest the middle; the second half gets another clip`} onClick={() => onRun("split", { slot: String(slot.n) })}>Cut in half</button>
              <button className="btn sec sm" disabled={busy || !hasDrop || slot.hero} title={!hasDrop ? "this sound has no drop in range" : d.project.story?.length ? `hero ${slot.clip} — note: a story edit ignores the hero` : `hero ${slot.clip} — this clip lands on the drop`} onClick={() => onRun("hero", { clip: String(slot.clip) })}>Put on the drop</button>
              <button className="btn bad sm" disabled={busy} title={`drop ${slot.clip} — every shot of clip ${slot.clip} is refilled with another clip`} onClick={() => onRun("drop", { clip: String(slot.clip) })}>Remove clip {slot.clip} from the video</button>
            </div>
            <button
              type="button" className="btn sec sm mt-2" title="a new chat: Claude reads the storyboard and says whether this shot works"
              onClick={() => void askClaude({
                prompt: `Look at slot ${slot.n} (clip ${slot.clip} at ${slot.in.toFixed(2)}s) of ${d.name} on the storyboard and tell me if it works; suggest one change`,
                send: true, newThread: true, from: `Shot ${slot.n} · ${d.name}`, context: `project:${d.name}`,
              })}
            ><Sparkles size={13} /> Ask Claude about this shot</button>
          </div>
        </div>
      )}

      <div>
        <div className="label">Use another clip here <span className="text-muted">(→ <code>set {slot.n} &lt;clip&gt;</code>)</span></div>
        <div className="grid gap-1.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(56px, 1fr))" }}>
          {d.clips.map((c) => {
            const short = c.duration - HEAD_PAD - TAIL_PAD < slot.dur;
            const off = c.missing || c.excluded || short;
            const isCur = c.n === slot.clip;
            return (
              <button
                key={c.n} type="button" disabled={busy || off || isCur}
                className={`clip text-left ${off ? "opacity-30" : ""} ${isCur ? "ring-2 ring-acc rounded-lg" : ""}`}
                title={`${c.name} · ${c.duration.toFixed(1)} s${c.missing ? " · MISSING" : c.excluded ? " · dropped from the video" : short ? ` · too short for a ${slot.dur.toFixed(2)} s shot` : isCur ? " · this clip" : ""}`}
                onClick={() => onRun("set", { slot: String(slot.n), clip: String(c.n) })}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={thumbUrl(c.folder, c.stem)} alt={c.name} loading="lazy" draggable={false} />
                <span className="n">{c.n}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
