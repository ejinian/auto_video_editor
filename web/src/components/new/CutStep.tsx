"use client";

import { useState } from "react";
import { Seg } from "@/components/new/Seg";
import { useJob } from "@/components/useJob";
import { thumbUrl } from "@/lib/format";
import type { ClipInfo, SoundInfo } from "@/lib/types";

const LENGTHS = [10, 15, 20, 30, 45, 60];

export function CutStep({ folder, clips, sound, nextName, onBack }: {
  folder: string;
  clips: ClipInfo[];
  sound: SoundInfo;
  nextName: string;
  onBack: () => void;
}) {
  const { run, busy, error } = useJob();
  const [name, setName] = useState(nextName);
  const [length, setLength] = useState(30);
  const [custom, setCustom] = useState("");
  const [preset, setPreset] = useState<"tight" | "loose" | "chill">("tight");
  const [first, setFirst] = useState<number | null>(null);
  const [mode, setMode] = useState<"story" | "random">("story");
  const [story, setStory] = useState("");
  const [seed, setSeed] = useState("");
  const [caption, setCaption] = useState("");
  const [sync, setSync] = useState(false);
  const [render, setRender] = useState(true);
  const len = custom.trim() ? Math.min(120, Math.max(3, Number(custom) || 30)) : length;
  const maxClip = Math.max(0, ...clips.map((c) => c.duration));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    await run("/api/cut", {
      folder, name, length: len, preset, existing: sound.path, first, mode, story,
      seed: seed.trim() === "" ? null : Number(seed), caption, sync, render,
    });
  };

  return (
    <form onSubmit={submit}>
      <div className="card">
        <div className="grid gap-5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
          <div>
            <label className="label !mt-0">Length <span className="text-muted">· ends on the nearest downbeat, so 20 may come out 19.7</span></label>
            <Seg ariaLabel="length" options={LENGTHS.map((n) => ({ value: n, label: `${n} s` }))} value={custom.trim() ? null : length} onChange={(v) => { setLength(v); setCustom(""); }} />
            <div className="flex items-center gap-2 mt-2 text-xs text-muted">other: <input className="input !w-20 !py-1" type="number" min={3} max={120} placeholder="s" value={custom} onChange={(e) => setCustom(e.target.value)} />
              {sound.duration && len > sound.duration ? <span className="text-warn">the sound is only {sound.duration.toFixed(0)} s; it plays to its end</span> : null}
            </div>
          </div>
          <div>
            <label className="label !mt-0">How often to cut</label>
            <Seg ariaLabel="preset" value={preset} onChange={setPreset} options={[
              { value: "tight", label: "tight", sub: "a shot every 0.6–1.4 s" },
              { value: "loose", label: "loose", sub: "1.4–3.2 s" },
              { value: "chill", label: "chill", sub: "3–6 s" },
            ]} />
          </div>
        </div>

        <label className="label mt-5">Opens with <span className="text-muted">· click a clip; it plays from its start. None = the tool chooses</span></label>
        <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(96px, 1fr))" }}>
          {clips.map((c) => (
            <div key={c.path} className={`clip ${first === c.n ? "sel" : ""}`}>
              <button type="button" onClick={() => setFirst(first === c.n ? null : c.n)} title={`${c.name} · ${c.duration.toFixed(1)} s`} aria-pressed={first === c.n}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={thumbUrl(c.folder, c.stem)} alt={c.name} loading="lazy" />
                <span className="n">{c.n}</span>
                <small>{c.duration.toFixed(0)}s{first === c.n ? " · opener" : ""}</small>
              </button>
            </div>
          ))}
        </div>

        <label className="label mt-5">Order</label>
        <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }} role="radiogroup" aria-label="order">
          <button type="button" className={`pick ${mode === "story" ? "on" : ""}`} role="radio" aria-checked={mode === "story"} onClick={() => setMode("story")}>
            <div className="font-semibold">Story</div>
            <div className="text-muted text-xs mt-0.5">The footage plays out in clip order: a long take runs across the video, every clip appears at least once.</div>
          </button>
          <button type="button" className={`pick ${mode === "random" ? "on" : ""}`} role="radio" aria-checked={mode === "random"} onClick={() => setMode("random")}>
            <div className="font-semibold">Random</div>
            <div className="text-muted text-xs mt-0.5">Random angles in random order, never the same clip twice in a row; another seed gives another shuffle.</div>
          </button>
        </div>

        <details className="more mt-5">
          <summary>More options</summary>
          <div className="grid gap-3 mt-1" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
            <div><label className="label">Video name</label><input className="input font-mono" value={name} onChange={(e) => setName(e.target.value)} /></div>
            {mode === "story" && <div><label className="label">Story order, clip numbers (blank = all, in order)</label><input className="input" placeholder="e.g. 3,1,5,2" value={story} onChange={(e) => setStory(e.target.value)} /></div>}
            <div><label className="label">Seed (another number = another variation)</label><input className="input" type="number" placeholder="blank = none" value={seed} onChange={(e) => setSeed(e.target.value)} /></div>
          </div>
          <label className="label">On-screen hook (burned in, lowercase, top-centre; blank = none)</label>
          <input className="input" placeholder="claude code takes 10 minutes a prompt so we started lifting between prompts" value={caption} onChange={(e) => setCaption(e.target.value)} />
          <div className="flex flex-wrap items-center gap-4 mt-3 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" checked={sync} onChange={(e) => setSync(e.target.checked)} /> sync cuts to the beats (default: free cuts, the sound plays underneath)</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={render} onChange={(e) => setRender(e.target.checked)} /> render right away</label>
          </div>
        </details>
      </div>

      <div className="stepbar flex-wrap">
        <button type="button" className="btn ghost" onClick={onBack} disabled={busy}>← Sound</button>
        <span className="status">
          <b className="text-fg">{name}</b> · {len} s · {preset} · {mode} · {sound.title} · {clips.length} clips{maxClip ? ` (longest ${maxClip.toFixed(0)} s)` : ""}. Plans, builds the storyboard{render ? " and renders: about 1–2 minutes, then the video page opens." : "."}
        </span>
        <button className="btn lg" disabled={busy}>Cut it</button>
      </div>
      {error && <div className="text-bad text-sm mt-2">{error}</div>}
    </form>
  );
}
