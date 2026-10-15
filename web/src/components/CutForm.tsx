"use client";

import { useState } from "react";
import { useJob } from "@/components/useJob";
import type { ClipInfo, SoundInfo } from "@/lib/types";

export function CutForm({ folder, clips, sounds, nextName }: { folder: string; clips: ClipInfo[]; sounds: SoundInfo[]; nextName: string }) {
  const { run, busy, error } = useJob();
  const [f, setF] = useState({
    name: nextName, length: 30, preset: "tight", link: "", existing: "", first: "", story: "", mode: "story", seed: "", caption: "", sync: false, render: true,
  });
  const set = (k: keyof typeof f, v: string | number | boolean) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    await run("/api/cut", {
      folder, name: f.name, length: Number(f.length), preset: f.preset, link: f.link, existing: f.existing,
      first: f.first ? Number(f.first) : null, mode: f.mode, story: f.story, seed: f.seed === "" ? null : Number(f.seed),
      caption: f.caption, sync: f.sync, render: f.render,
    });
  };
  return (
    <form className="card" onSubmit={submit}>
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <div><label className="label">Video name</label><input className="input" value={f.name} onChange={(e) => set("name", e.target.value)} /></div>
        <div><label className="label">Length (s, ends on the nearest downbeat)</label><input className="input" type="number" min={3} max={120} value={f.length} onChange={(e) => set("length", e.target.value)} /></div>
        <div>
          <label className="label">How often to cut</label>
          <select className="select" value={f.preset} onChange={(e) => set("preset", e.target.value)}>
            <option value="tight">tight · a shot every 0.6–1.4 s</option>
            <option value="loose">loose · 1.4–3.2 s</option>
            <option value="chill">chill · 3–6 s</option>
          </select>
        </div>
      </div>
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
        <div><label className="label">Sound link (TikTok video / sound page, Instagram reel, YouTube)</label><input className="input" placeholder="https://www.tiktok.com/…" value={f.link} onChange={(e) => set("link", e.target.value)} /></div>
        <div>
          <label className="label">…or one from the pool</label>
          <select className="select" value={f.existing} onChange={(e) => set("existing", e.target.value)}>
            <option value="">— pick —</option>
            {sounds.map((s) => <option key={s.path} value={s.path}>{s.title}{s.author ? ` — ${s.author}` : ""}{s.duration ? ` (${s.duration.toFixed(0)} s)` : ""}</option>)}
          </select>
        </div>
      </div>
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <div>
          <label className="label">Opens with clip (from its start)</label>
          <select className="select" value={f.first} onChange={(e) => set("first", e.target.value)}>
            <option value="">let the tool choose</option>
            {clips.map((c) => <option key={c.n} value={c.n}>{c.n} · {c.name}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Mode</label>
          <select className="select" value={f.mode} onChange={(e) => set("mode", e.target.value)}>
            <option value="story">story: footage plays out in order</option>
            <option value="random">random angles in random order</option>
            <option value="auto">auto: longest clip gets the longest shot</option>
          </select>
        </div>
        {f.mode === "story" && <div><label className="label">Story order, clip numbers (blank = all, in order)</label><input className="input" placeholder="e.g. 3,1,5,2" value={f.story} onChange={(e) => set("story", e.target.value)} /></div>}
        <div><label className="label">Seed (change it for another variation)</label><input className="input" type="number" placeholder="blank = none" value={f.seed} onChange={(e) => set("seed", e.target.value)} /></div>
      </div>
      <label className="label">On-screen hook (burned in, lowercase, top-centre; blank = none)</label>
      <input className="input" placeholder="claude code takes 10 minutes a prompt so we started lifting between prompts" value={f.caption} onChange={(e) => set("caption", e.target.value)} />
      <div className="flex flex-wrap items-center gap-4 mt-3 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" checked={f.sync} onChange={(e) => set("sync", e.target.checked)} /> sync cuts to the beats (default: free cuts, the sound plays underneath)</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={f.render} onChange={(e) => set("render", e.target.checked)} /> render right away</label>
      </div>
      <div className="flex items-center gap-3 mt-4">
        <button className="btn" disabled={busy}>Cut it</button>
        <span className="text-muted text-sm">downloads the sound if needed, plans, builds the storyboard{f.render ? " and renders. About 1–2 minutes." : "."}</span>
      </div>
      {error && <div className="text-bad text-sm mt-2">{error}</div>}
    </form>
  );
}
