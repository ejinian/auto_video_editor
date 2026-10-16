"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { SlotCard } from "@/components/SlotCard";
import { Timeline } from "@/components/Timeline";
import { useJob } from "@/components/useJob";
import { mb, mediaUrl } from "@/lib/format";
import type { ProjectDetail } from "@/lib/types";

const selListeners = new Set<() => void>();
function subscribeSel(fn: () => void) { selListeners.add(fn); return () => { selListeners.delete(fn); }; }
function readSel(key: string): number | null {
  try { const v = Number(sessionStorage.getItem(key)); return v >= 1 ? v : null; } catch { return null; }
}
function writeSel(key: string, n: number | null) {
  try { if (n == null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, String(n)); } catch { /* no storage */ }
  selListeners.forEach((f) => f());
}

/** The player, the timeline under it and the side card for the selected shot. Every
 *  edit here is one beatcut command through /api/projects/<name>/run (then `board`),
 *  watched on the job page, which comes back here when it is done. */
export function VideoEditor({ d }: { d: ProjectDetail }) {
  const { run, busy, error } = useJob();
  const name = d.name;
  const video = useRef<HTMLVideoElement>(null);
  const [time, setTime] = useState(0);
  // the selection lives in sessionStorage so it survives the job-page round-trip after an edit
  const key = `beatcut.sel.${name}`;
  const stored = useSyncExternalStore(subscribeSel, () => readSel(key), () => null);
  const selected = stored != null && stored <= d.slots.length ? stored : null;
  const select = useCallback((n: number | null) => writeSel(key, n), [key]);

  const seek = useCallback((t: number) => {
    const v = video.current;
    if (!v) return;
    v.currentTime = t;
    setTime(t);
  }, []);

  // a smooth playhead: poll the player while it plays, follow its own events otherwise
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    let raf = 0;
    const tick = () => { setTime(v.currentTime); if (!v.paused && !v.ended) raf = requestAnimationFrame(tick); };
    const onPlay = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(tick); };
    const onTime = () => { if (v.paused) setTime(v.currentTime); };
    v.addEventListener("play", onPlay);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("seeked", onTime);
    return () => { cancelAnimationFrame(raf); v.removeEventListener("play", onPlay); v.removeEventListener("timeupdate", onTime); v.removeEventListener("seeked", onTime); };
  }, [d.mp4]);

  const onRun = useCallback((cmd: string, args: Record<string, string>) => {
    run(`/api/projects/${encodeURIComponent(name)}/run`, { cmd, args });
  }, [run, name]);

  const pick = useCallback((n: number) => {
    select(n);
    const s = d.slots[n - 1];
    if (s && video.current) seek(s.t0);
  }, [d.slots, seek, select]);

  // ← → pick the previous/next shot (and seek to it), space plays/pauses, esc clears
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.closest("input, textarea, select, button, a, [contenteditable=true]") || t.isContentEditable)) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        const n = selected ?? (d.slots.findIndex((s) => time >= s.t0 && time < s.t1) + 1 || 1);
        pick(Math.min(d.slots.length, Math.max(1, n + (e.key === "ArrowRight" ? 1 : -1))));
      } else if (e.key === " ") {
        const v = video.current;
        if (!v) return;
        e.preventDefault();
        if (v.paused) void v.play(); else v.pause();
      } else if (e.key === "Escape") select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, d.slots, time, pick, select]);

  const slot = selected != null ? d.slots[selected - 1] : null;

  return (
    <div className="space-y-3">
      {error && <div className="text-bad text-sm">{error}</div>}
      <div className="grid gap-4" style={{ gridTemplateColumns: "minmax(240px, 300px) 1fr" }}>
        <div>
          {d.mp4 ? (
            <video ref={video} controls playsInline src={mediaUrl(d.mp4)} className="w-full rounded-xl bg-black" style={{ maxHeight: "62vh" }} />
          ) : (
            <div className="card text-muted aspect-[9/16] max-h-[50vh] flex items-center justify-center text-center text-sm">not rendered yet — the timeline below is the plan; press Render</div>
          )}
          {d.mp4 && (
            <div className="text-xs text-muted mt-2 space-y-0.5">
              <div><code>~/Desktop/beatcut/{d.inFinal ? `final/${name}.mp4` : d.mp4}</code> · {mb(d.mp4Size)}{!d.inFinal && " · draft, not in final/"}</div>
              <div><a href={mediaUrl(d.inFinal ? `final/${name}.mp4` : d.mp4, true)}>download</a></div>
            </div>
          )}
        </div>
        {slot ? (
          <SlotCard key={`${slot.n}-${slot.clip}-${slot.in}`} d={d} slot={slot} time={time} busy={busy} onRun={onRun} onSeek={seek} />
        ) : (
          <div className="card text-muted text-sm space-y-2">
            <div><b className="text-fg">Click a shot</b> on the timeline to edit it: another clip in it, where it starts, hold it longer, cut it, take its clip out of the video, put it on the drop.</div>
            <div><b className="text-fg">Drag a shot</b> onto another to swap them, or to the edge of one to move it there.</div>
            <div><b className="text-fg">Keys:</b> ← → pick the previous / next shot, space plays and pauses.</div>
            <div>Every button is one beatcut command (the job log shows it) and rebuilds the storyboard; press <b className="text-fg">Render</b> when it looks right. Nothing asks for confirmation: the next action undoes the last, and every render is kept under <code>versions/</code>.</div>
          </div>
        )}
      </div>
      <Timeline name={name} slots={d.slots} selected={selected} time={time} hasVideo={!!d.mp4} busy={busy} onSelect={pick}
        onMove={(a, b) => onRun("move", { a: String(a), b: String(b) })}
        onSwap={(a, b) => onRun("swap", { a: String(a), b: String(b) })} />
    </div>
  );
}
