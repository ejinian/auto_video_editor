"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { askClaude } from "@/components/chat/ask";
import { mediaUrl, mmss } from "@/lib/format";
import type { JobInfo, SoundInfo } from "@/lib/types";

/** "tiktok.com" for a link, the filename for a local import, nothing otherwise. */
function sourceLabel(src?: string): string {
  if (!src) return "";
  try { return new URL(src).hostname.replace(/^www\./, ""); } catch { return src.split("/").pop() ?? src; }
}

/** The `SOUND: sound/<file>.mp3` line Claude is asked to end with (the last one wins). */
export function pickedSound(text: string): string | null {
  const m = [...text.matchAll(/SOUND:\s*`?(sound\/[^\s`*]+\.mp3)`?/gi)];
  return m.length ? m[m.length - 1][1] : null;
}

export function SoundStep({ folder, clipCount, sounds, selected, onSounds, onSelect, onBack, onNext }: {
  folder: string;
  clipCount: number;
  sounds: SoundInfo[];
  selected: string | null;
  onSounds: (s: SoundInfo[]) => void;
  onSelect: (path: string) => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const [link, setLink] = useState("");
  const [cookies, setCookies] = useState(false);
  const [job, setJob] = useState<JobInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const known = useRef(new Set(sounds.map((s) => s.path)));

  // follow the download job; when it is done, re-read the pool and select the new sound
  useEffect(() => {
    if (!job || job.done) return;
    const t = setInterval(async () => {
      const r = await fetch(`/api/jobs/${job.id}`);
      if (!r.ok) return;
      const j = (await r.json()) as JobInfo;
      setJob(j);
      if (!j.done) return;
      clearInterval(t);
      if (!j.ok) { setError("the download failed — read the log below, or try a video link that uses the sound"); return; }
      const pool = (await (await fetch("/api/sounds")).json()) as SoundInfo[];
      onSounds(pool);
      const fresh = pool.filter((s) => !known.current.has(s.path)).sort((a, b) => b.mtime - a.mtime)[0] ?? pool.sort((a, b) => b.mtime - a.mtime)[0];
      for (const s of pool) known.current.add(s.path);
      if (fresh) onSelect(fresh.path);
      setLink("");
    }, 1500);
    return () => clearInterval(t);
  }, [job, onSounds, onSelect]);

  const download = async () => {
    const l = link.trim();
    if (!l) return;
    setError(null);
    const r = await fetch("/api/sounds", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ link: l, cookies: cookies ? "chrome" : undefined }) });
    const j = (await r.json().catch(() => ({}))) as { job?: string; error?: string };
    if (!r.ok || !j.job) { setError(j.error ?? `request failed (${r.status})`); return; }
    setJob({ id: j.job, title: l, cmds: [], log: "", done: false, ok: true, then: null, startedAt: Date.now(), endedAt: null });
  };

  // Claude picks: a new chat thread that reads the footage and the pool (or downloads a
  // trending sound); when the turn is done the pool is re-read and the file named on
  // the answer's last line is selected. If that line is missing, the list just refreshes.
  const [pick, setPick] = useState<{ kind: "idle" } | { kind: "running" } | { kind: "done"; chosen: string | null } | { kind: "error"; error: string }>({ kind: "idle" });
  const letClaudePick = async () => {
    if (pick.kind === "running") return;
    setPick({ kind: "running" });
    const r = await askClaude({
      prompt:
        `Look at the clips in clips/${folder} (frame sheets) and pick the best sound from the pool in sound/ for them, or find a trending one and download it with \`sound <link>\`. ` +
        "Answer with the chosen file's name on the last line as `SOUND: sound/<file>.mp3`.",
      send: true, newThread: true, from: `Let Claude pick · clips/${folder}`, context: `folder:${folder}`,
    });
    if (!r) return;
    let pool: SoundInfo[] = sounds;
    try {
      pool = (await (await fetch("/api/sounds")).json()) as SoundInfo[];
      onSounds(pool);
      for (const s of pool) known.current.add(s.path);
    } catch { /* keep the list we have */ }
    if (r.isError) { setPick({ kind: "error", error: r.error ?? "it did not finish" }); return; }
    const chosen = pickedSound(r.text);
    const hit = chosen ? pool.find((s) => s.path === chosen) ?? null : null;
    if (hit) onSelect(hit.path);
    setPick({ kind: "done", chosen: hit?.title ?? null });
  };

  const busy = !!job && !job.done;
  const tail = job?.log.trim().split("\n").slice(-6).join("\n");
  return (
    <div>
      <div className="grid gap-3 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
        <div className="card">
          <div className="font-semibold">Paste a link</div>
          <div className="text-muted text-xs mt-0.5 mb-2">TikTok video or sound page, Instagram reel (its audio, as long as the reel), YouTube. Downloaded and beat-analysed, then selected below.</div>
          <div className="flex gap-2">
            <input className="input" placeholder="https://www.tiktok.com/…" value={link} onChange={(e) => setLink(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); download(); } }} disabled={busy} />
            <button type="button" className="btn" onClick={download} disabled={busy || !link.trim()}>{busy ? "Downloading…" : "Download"}</button>
          </div>
          <label className="flex items-center gap-2 text-xs text-muted mt-2"><input type="checkbox" checked={cookies} onChange={(e) => setCookies(e.target.checked)} /> use Chrome&apos;s login for Instagram (macOS asks for Keychain access)</label>
          {job && <pre className="log mt-2 max-h-32 overflow-auto text-[11.5px]">{tail || "starting…"}</pre>}
          {error && <div className="text-bad text-sm mt-2">{error}</div>}
        </div>
        <div className="card">
          <div className="font-semibold">Not sure which?</div>
          <div className="text-muted text-xs mt-0.5 mb-2">Claude looks at the footage ({clipCount} clips) and the pool and picks one, or downloads a trending sound. It runs in the panel beside this page and selects the sound below when it is done; nothing is cut.</div>
          <button type="button" className="btn" onClick={letClaudePick} disabled={pick.kind === "running"}>
            {pick.kind === "running" ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {pick.kind === "running" ? "Claude is picking…" : "Let Claude pick"}
          </button>
          {pick.kind === "done" && <div className="text-acc text-xs mt-2">{pick.chosen ? <>picked <b>{pick.chosen}</b> — selected below</> : "done — the pool is refreshed; read the panel and click the one it named"}</div>}
          {pick.kind === "error" && <div className="text-bad text-xs mt-2">{pick.error}</div>}
        </div>
      </div>

      <h2>The pool · click one</h2>
      {sounds.length === 0 && <div className="text-muted text-sm">No sounds downloaded yet. Paste a link above.</div>}
      <div className="grid gap-3" role="radiogroup" aria-label="sound" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
        {sounds.map((s) => (
          <div key={s.path} className={`pick ${s.path === selected ? "on" : ""}`} role="radio" aria-checked={s.path === selected} tabIndex={0}
            onClick={() => onSelect(s.path)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(s.path); } }}>
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <div className="font-semibold truncate" title={s.title}>{s.title}</div>
                <div className="text-muted text-xs truncate">{s.author ?? sourceLabel(s.source)}</div>
              </div>
              {s.path === selected && <span className="tag ok">selected</span>}
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2 text-xs">
              {s.duration ? <span className="tag">{mmss(s.duration)}</span> : null}
              {s.tempo ? <span className="tag">{s.tempo.toFixed(0)} bpm</span> : null}
              <span className="tag">{s.drops.length ? `drop at ${s.drops[0].toFixed(1)} s` : "no clear drop"}</span>
            </div>
            <audio controls preload="none" src={mediaUrl(s.path)} className="w-full h-8 mt-2" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()} />
            <div className="text-xs text-muted mt-1.5 truncate">
              {s.usedBy.length
                ? <>used by {s.usedBy.map((n, i) => <span key={n}>{i ? ", " : ""}<Link href={`/video/${encodeURIComponent(n)}`} onClick={(e) => e.stopPropagation()}>{n}</Link></span>)}</>
                : "not used yet"}
            </div>
          </div>
        ))}
      </div>

      <div className="stepbar">
        <button type="button" className="btn ghost" onClick={onBack}>← Clips</button>
        <span className="status">{selected ? sounds.find((s) => s.path === selected)?.title : "pick a sound first"}</span>
        <button type="button" className="btn lg" disabled={!selected} onClick={onNext}>Next: how to cut it →</button>
      </div>
    </div>
  );
}
