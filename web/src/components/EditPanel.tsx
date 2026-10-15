"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useJob } from "@/components/useJob";
import type { ProjectDetail, SoundInfo } from "@/lib/types";

type Args = Record<string, string>;

function Cmd({ label, hint, fields, cmd, onRun, busy, submit = "Go" }: {
  label: string; hint?: string; fields: Array<{ k: string; ph: string; required?: boolean; type?: string; options?: string[] }>;
  cmd: string; onRun: (cmd: string, args: Args) => void; busy: boolean; submit?: string;
}) {
  const [v, setV] = useState<Args>({});
  return (
    <form
      className="min-w-0"
      onSubmit={(e) => { e.preventDefault(); onRun(cmd, v); }}
    >
      <label className="label" title={hint}>{label}</label>
      <div className="flex gap-1.5 items-end flex-wrap">
        {fields.map((f) =>
          f.options ? (
            <select key={f.k} className="select !w-auto flex-1 min-w-[90px]" value={v[f.k] ?? f.options[0]} onChange={(e) => setV({ ...v, [f.k]: e.target.value })}>
              {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <input key={f.k} className="input !w-auto flex-1 min-w-[70px]" type={f.type ?? "text"} placeholder={f.ph} required={f.required} value={v[f.k] ?? ""} onChange={(e) => setV({ ...v, [f.k]: e.target.value })} />
          ),
        )}
        <button className="btn sec sm" disabled={busy}>{submit}</button>
      </div>
    </form>
  );
}

export function EditPanel({ d, sounds }: { d: ProjectDetail; sounds: SoundInfo[] }) {
  const { run, busy, error } = useJob();
  const router = useRouter();
  const name = d.name;
  const onRun = (cmd: string, args: Args) => run(`/api/projects/${encodeURIComponent(name)}/run`, { cmd, args });
  const [varLink, setVarLink] = useState("");
  const [varExisting, setVarExisting] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [exportHint, setExportHint] = useState(false);

  const del = async () => {
    const r = await fetch(`/api/projects/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (r.ok) router.push(d.folder ? `/shoot/${encodeURIComponent(d.folder)}` : "/videos");
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        <button className={`btn ${d.stale || !d.rendered ? "warn" : "sec"}`} disabled={busy} onClick={() => onRun("render", {})}>Render{d.stale ? " (edited)" : ""}</button>
        <button className="btn sec" disabled={busy} onClick={() => onRun("board", {})} title="rebuild the storyboard from the current plan">Storyboard</button>
        <button className="btn sec" disabled={busy} onClick={() => { setExportHint(true); onRun("export-open", {}); }} title="writes the edit as a CapCut project (every cut still editable) and opens CapCut inside it. Quit CapCut first if it's open.">Open in CapCut</button>
        <button className="btn sec" disabled={busy} onClick={() => onRun("frames", {})} title="timestamped frame sheets for every clip in this video">Frame sheets</button>
        <span className="flex-1" />
        {!confirmDelete
          ? <button className="btn bad sm" onClick={() => setConfirmDelete(true)}>Delete video</button>
          : <span className="flex items-center gap-2 text-sm"><span className="text-bad">Delete {name}, its renders and final/{name}.mp4?</span><button className="btn bad sm" onClick={del}>Yes, delete</button><button className="btn sec sm" onClick={() => setConfirmDelete(false)}>No</button></span>}
      </div>
      {exportHint && <div className="text-muted text-sm">If CapCut was open the export stops; quit CapCut and press again. The project lands at the top of CapCut&apos;s list and re-exporting replaces it.</div>}
      {error && <div className="text-bad text-sm">{error}</div>}

      <div className="card">
        <div className="text-muted text-sm mb-1">Each button changes the plan and rebuilds the storyboard. Press <b>Render</b> when it looks right; every render is kept under <code>versions/</code>. Slots are positions in the video (1–{d.slots.length}); clips are the numbered source files.</div>
        <div className="grid gap-x-4 gap-y-1" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
          <Cmd label="Swap two slots" hint="swap 5 12 — or c3 c8 for the slots holding clips 3 and 8" cmd="swap" busy={busy} onRun={onRun} fields={[{ k: "a", ph: "slot", required: true }, { k: "b", ph: "slot", required: true }]} submit="Swap" />
          <Cmd label="Move a slot to a position" cmd="move" busy={busy} onRun={onRun} fields={[{ k: "a", ph: "slot", required: true }, { k: "b", ph: "to", required: true }]} submit="Move" />
          <Cmd label="Put a clip in a slot" cmd="set" busy={busy} onRun={onRun} fields={[{ k: "slot", ph: "slot", required: true }, { k: "clip", ph: "clip", required: true }, { k: "at", ph: "start s (opt)" }]} submit="Set" />
          <Cmd label="Start a slot later in its clip" cmd="in" busy={busy} onRun={onRun} fields={[{ k: "slot", ph: "slot", required: true }, { k: "sec", ph: "seconds", required: true }]} submit="Set in" />
          <Cmd label="Hold a shot longer (join a slot into the previous)" cmd="merge" busy={busy} onRun={onRun} fields={[{ k: "slot", ph: "slot", required: true }]} submit="Merge" />
          <Cmd label="Cut faster there (split a slot)" cmd="split" busy={busy} onRun={onRun} fields={[{ k: "slot", ph: "slot", required: true }]} submit="Split" />
          <Cmd label="Get rid of a clip (its slots refill)" cmd="drop" busy={busy} onRun={onRun} fields={[{ k: "clip", ph: "clip", required: true }]} submit="Drop" />
          <Cmd label="Put a clip back" cmd="restore" busy={busy} onRun={onRun} fields={[{ k: "clip", ph: "clip", required: true }]} submit="Restore" />
          <Cmd label="Clip on the drop (ignored in story mode)" cmd="hero" busy={busy} onRun={onRun} fields={[{ k: "clip", ph: "clip", required: true }]} submit="Hero" />
          <Cmd label="Same cuts, different clips in them" cmd="shuffle" busy={busy} onRun={onRun} fields={[{ k: "seed", ph: "seed (opt)" }]} submit="Shuffle" />
        </div>
        <div className="grid gap-x-4 gap-y-1 mt-2 pt-2 border-t border-line" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
          <CaptionCmd current={d.project.caption ?? ""} busy={busy} onRun={onRun} />
          <Cmd label="Length in seconds (rebuilds the whole edit)" cmd="length" busy={busy} onRun={onRun} fields={[{ k: "value", ph: String(Math.round(d.project.length)), required: true, type: "number" }]} submit="Change" />
          <Cmd label="Start the sound at (s, rebuilds)" cmd="start" busy={busy} onRun={onRun} fields={[{ k: "value", ph: d.project.audio_start.toFixed(1), required: true, type: "number" }]} submit="Change" />
          <Cmd label="Cut density (rebuilds)" cmd="density" busy={busy} onRun={onRun} fields={[{ k: "value", ph: "", options: ["tight", "loose", "chill"] }]} submit="Change" />
        </div>
      </div>

      <form className="card" onSubmit={(e) => { e.preventDefault(); run(`/api/projects/${encodeURIComponent(name)}/variation`, { link: varLink, existing: varExisting }); }}>
        <div className="font-semibold">Make a variation</div>
        <div className="text-muted text-sm">Same clips and settings, the next seed, a new name ({d.folder ?? "misc"}_N). Give it another sound so it doesn&apos;t look like the same edit with a new song.</div>
        <div className="grid gap-3 mt-2 items-end" style={{ gridTemplateColumns: "1fr 1fr auto" }}>
          <div><label className="label">Sound link (opt)</label><input className="input" placeholder="https://…" value={varLink} onChange={(e) => setVarLink(e.target.value)} /></div>
          <div>
            <label className="label">…or from the pool (default: same sound)</label>
            <select className="select" value={varExisting} onChange={(e) => setVarExisting(e.target.value)}>
              <option value="">same sound</option>
              {sounds.map((s) => <option key={s.path} value={s.path}>{s.title}{s.author ? ` — ${s.author}` : ""}</option>)}
            </select>
          </div>
          <button className="btn" disabled={busy}>Make variation</button>
        </div>
      </form>
    </div>
  );
}

function CaptionCmd({ current, busy, onRun }: { current: string; busy: boolean; onRun: (cmd: string, args: Args) => void }) {
  const [text, setText] = useState(current);
  return (
    <form className="min-w-0" onSubmit={(e) => { e.preventDefault(); onRun("caption", { text }); }} style={{ gridColumn: "1 / -1" }}>
      <label className="label">On-screen hook (burned in at render; blank = remove)</label>
      <div className="flex gap-1.5">
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="lowercase, ≤10 words, names a tool or a number" />
        <button className="btn sec sm" disabled={busy}>Set hook</button>
      </div>
    </form>
  );
}
