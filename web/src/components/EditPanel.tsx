"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useJob } from "@/components/useJob";
import type { ProjectDetail, SoundInfo } from "@/lib/types";

type Args = Record<string, string>;

function Cmd({ label, hint, fields, cmd, onRun, busy, submit = "Go", inline = false }: {
  label: string; hint?: string; fields: Array<{ k: string; ph: string; required?: boolean; type?: string; options?: string[]; initial?: string }>;
  cmd: string; onRun: (cmd: string, args: Args) => void; busy: boolean; submit?: string; inline?: boolean;
}) {
  const [v, setV] = useState<Args>(() => Object.fromEntries(fields.filter((f) => f.initial != null).map((f) => [f.k, f.initial!])));
  return (
    <form
      className={inline ? "flex gap-1.5 items-center" : "min-w-0"}
      onSubmit={(e) => { e.preventDefault(); onRun(cmd, v); }}
    >
      <label className={inline ? "text-muted text-sm whitespace-nowrap" : "label"} title={hint}>{label}</label>
      <div className="flex gap-1.5 items-end flex-wrap">
        {fields.map((f) =>
          f.options ? (
            <select key={f.k} className="select !w-auto flex-1 min-w-[90px]" value={v[f.k] ?? f.options[0]} onChange={(e) => setV({ ...v, [f.k]: e.target.value })}>
              {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <input key={f.k} className={`input !w-auto flex-1 ${inline ? "min-w-[60px] max-w-[90px] !py-1.5" : "min-w-[70px]"}`} type={f.type ?? "text"} placeholder={f.ph} required={f.required} value={v[f.k] ?? ""} onChange={(e) => setV({ ...v, [f.k]: e.target.value })} />
          ),
        )}
        <button className="btn sec sm" disabled={busy}>{submit}</button>
      </div>
    </form>
  );
}

/** The toolbar: render / storyboard / CapCut / frame sheets / variation / delete on one
 *  row, the whole-video settings (hook, length, density) on a second. */
export function EditToolbar({ d, sounds }: { d: ProjectDetail; sounds: SoundInfo[] }) {
  const { run, busy, error } = useJob();
  const router = useRouter();
  const name = d.name;
  const onRun = (cmd: string, args: Args) => run(`/api/projects/${encodeURIComponent(name)}/run`, { cmd, args });
  const [varOpen, setVarOpen] = useState(false);
  const [varLink, setVarLink] = useState("");
  const [varExisting, setVarExisting] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [exportHint, setExportHint] = useState(false);

  const del = async () => {
    const r = await fetch(`/api/projects/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (r.ok) router.push(d.folder ? `/shoot/${encodeURIComponent(d.folder)}` : "/videos");
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2 items-center">
        <button className={`btn ${d.stale || !d.rendered ? "warn" : "sec"}`} disabled={busy} onClick={() => onRun("render", {})}>Render{d.stale ? " (edited)" : ""}</button>
        <button className="btn sec" disabled={busy} onClick={() => onRun("board", {})} title="rebuild the storyboard from the current plan">Storyboard</button>
        <button className="btn sec" disabled={busy} onClick={() => { setExportHint(true); onRun("export-open", {}); }} title="writes the edit as a CapCut project (every cut still editable) and opens CapCut inside it. Quit CapCut first if it's open.">Open in CapCut</button>
        <button className="btn sec" disabled={busy} onClick={() => onRun("frames", {})} title="timestamped frame sheets for every clip in this video">Frame sheets</button>
        <button className={`btn sec ${varOpen ? "!border-acc" : ""}`} onClick={() => setVarOpen(!varOpen)} title="the same clips and settings with the next seed, as a new video">Make variation</button>
        <span className="flex-1" />
        {!confirmDelete
          ? <button className="btn bad sm" onClick={() => setConfirmDelete(true)}>Delete video</button>
          : <span className="flex items-center gap-2 text-sm"><span className="text-bad">Delete {name}, its renders and final/{name}.mp4?</span><button className="btn bad sm" onClick={del}>Yes, delete</button><button className="btn sec sm" onClick={() => setConfirmDelete(false)}>No</button></span>}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-2 items-center">
        <CaptionCmd current={d.project.caption ?? ""} busy={busy} onRun={onRun} />
        <Cmd inline label="Length" hint="seconds; rebuilds the whole edit" cmd="length" busy={busy} onRun={onRun} fields={[{ k: "value", ph: "s", required: true, type: "number", initial: String(Math.round(d.project.length)) }]} submit="Change" />
        <Cmd inline label="Density" hint="rebuilds the whole edit" cmd="density" busy={busy} onRun={onRun} fields={[{ k: "value", ph: "", options: ["tight", "loose", "chill"], initial: d.project.preset ?? "tight" }]} submit="Change" />
      </div>
      {exportHint && <div className="text-muted text-sm">If CapCut was open the export stops; quit CapCut and press again. The project lands at the top of CapCut&apos;s list and re-exporting replaces it.</div>}
      {error && <div className="text-bad text-sm">{error}</div>}

      {varOpen && (
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
      )}
    </div>
  );
}

/** Every command as a form keyed by slot and clip numbers, plus the slot table — the
 *  timeline covers the same ground visually; this is for power use and copy-paste. */
export function AllCommands({ d }: { d: ProjectDetail }) {
  const { run, busy, error } = useJob();
  const name = d.name;
  const onRun = (cmd: string, args: Args) => run(`/api/projects/${encodeURIComponent(name)}/run`, { cmd, args });
  return (
    <details className="card !p-0 overflow-hidden">
      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold select-none">All commands <span className="text-muted font-normal">— every edit by slot and clip number, and the shot table</span></summary>
      <div className="px-4 pb-4 space-y-4">
        <div className="text-muted text-sm">Slots are positions in the video (1–{d.slots.length}); clips are the numbered source files. Each button changes the plan and rebuilds the storyboard.</div>
        {error && <div className="text-bad text-sm">{error}</div>}
        <div className="grid gap-x-4 gap-y-1" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
          <Cmd label="Swap two slots" hint="swap 5 12 — or c3 c8 for the slots holding clips 3 and 8" cmd="swap" busy={busy} onRun={onRun} fields={[{ k: "a", ph: "slot", required: true }, { k: "b", ph: "slot", required: true }]} submit="Swap" />
          <Cmd label="Move a slot to a position" cmd="move" busy={busy} onRun={onRun} fields={[{ k: "a", ph: "slot", required: true }, { k: "b", ph: "to", required: true }]} submit="Move" />
          <Cmd label="Put a clip in a slot" cmd="set" busy={busy} onRun={onRun} fields={[{ k: "slot", ph: "slot", required: true }, { k: "clip", ph: "clip", required: true }, { k: "at", ph: "start s (opt)" }]} submit="Set" />
          <Cmd label="Start a slot later in its clip" cmd="in" busy={busy} onRun={onRun} fields={[{ k: "slot", ph: "slot", required: true }, { k: "sec", ph: "seconds", required: true }]} submit="Set in" />
          <Cmd label="Hold a shot longer (join a slot into the previous)" cmd="merge" busy={busy} onRun={onRun} fields={[{ k: "slot", ph: "slot", required: true }]} submit="Merge" />
          <Cmd label="Cut faster there (split a slot)" hint="split 9 — cuts slot 9 on its middle beat; for free cuts use Cut at a time" cmd="split" busy={busy} onRun={onRun} fields={[{ k: "slot", ph: "slot", required: true }]} submit="Split" />
          <Cmd label="Cut a shot at a time (s into the video, or +s into the shot)" hint="cut 9 +2 — a new cut two seconds into slot 9; cut 9 12.4 — at 12.4 s of the video. The clip runs on across the cut; change the new slot with Put a clip / Start later" cmd="cut" busy={busy} onRun={onRun} fields={[{ k: "slot", ph: "slot", required: true }, { k: "sec", ph: "12.4 or +2", required: true }]} submit="Cut" />
          <Cmd label="Get rid of a clip (its slots refill)" cmd="drop" busy={busy} onRun={onRun} fields={[{ k: "clip", ph: "clip", required: true }]} submit="Drop" />
          <Cmd label="Put a clip back" cmd="restore" busy={busy} onRun={onRun} fields={[{ k: "clip", ph: "clip", required: true }]} submit="Restore" />
          <Cmd label="Clip on the drop (ignored in story mode)" cmd="hero" busy={busy} onRun={onRun} fields={[{ k: "clip", ph: "clip", required: true }]} submit="Hero" />
          <Cmd label="Same cuts, different clips in them" cmd="shuffle" busy={busy} onRun={onRun} fields={[{ k: "seed", ph: "seed (opt)" }]} submit="Shuffle" />
          <Cmd label="Start the sound at (s, rebuilds)" cmd="start" busy={busy} onRun={onRun} fields={[{ k: "value", ph: d.project.audio_start.toFixed(1), required: true, type: "number" }]} submit="Change" />
          <Cmd label="Cut density (rebuilds)" hint="a preset, or calm=8 hype=4 for beat-synced edits" cmd="density" busy={busy} onRun={onRun} fields={[{ k: "value", ph: "tight · loose · chill · calm=8 hype=4", required: true }]} submit="Change" />
        </div>
        <div className="card !p-0 overflow-hidden !bg-bg-2">
          <table className="t">
            <thead><tr><th>slot</th><th>time (s)</th><th>dur</th><th>clip</th><th>in at</th><th></th></tr></thead>
            <tbody>
              {d.slots.map((r) => (
                <tr key={r.n} className={r.drop ? "drop" : ""}>
                  <td>{r.n}</td>
                  <td>{r.t0.toFixed(2)}–{r.t1.toFixed(2)}</td>
                  <td>{r.dur.toFixed(2)}</td>
                  <td><b>{r.clip}</b> <span className="text-muted">{r.file}</span></td>
                  <td>{r.in.toFixed(1)}</td>
                  <td className="text-muted text-xs">{[r.drop ? "DROP" : "", r.hero ? "hero" : "", r.uses > 1 ? `clip used ×${r.uses}` : ""].filter(Boolean).join(" · ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </details>
  );
}

function CaptionCmd({ current, busy, onRun }: { current: string; busy: boolean; onRun: (cmd: string, args: Args) => void }) {
  const [text, setText] = useState(current);
  return (
    <form className="flex gap-1.5 items-center flex-1 min-w-[260px]" onSubmit={(e) => { e.preventDefault(); onRun("caption", { text }); }}>
      <label className="text-muted text-sm whitespace-nowrap" title="burned in at render; blank = remove">Hook</label>
      <input className="input !py-1.5" value={text} onChange={(e) => setText(e.target.value)} placeholder="on-screen text: lowercase, ≤10 words, names a tool or a number" />
      <button className="btn sec sm" disabled={busy}>Set hook</button>
    </form>
  );
}
