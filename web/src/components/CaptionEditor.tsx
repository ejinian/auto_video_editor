"use client";

import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { askClaude } from "@/components/chat/ask";

export function CaptionEditor({ name, initial, file }: { name: string; initial: string; file: string }) {
  const [text, setText] = useState(initial);
  const [saved, setSaved] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [writing, setWriting] = useState<"idle" | "running" | "done" | "error">("idle");
  const [writeError, setWriteError] = useState<string | null>(null);
  const save = async () => {
    setSaved("saving");
    const r = await fetch(`/api/projects/${encodeURIComponent(name)}/caption`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    setSaved(r.ok ? "saved" : "error");
    setTimeout(() => setSaved("idle"), 1500);
  };
  // Claude writes it (caption skill, linted with /ig-human) into the caption file as a
  // new chat thread; when the turn is done the file is read back into the box
  const write = async () => {
    if (writing === "running") return;
    setWriting("running");
    setWriteError(null);
    const r = await askClaude({
      prompt: `Write the caption for ${name} with /ig-caption, lint it with /ig-human until PASS, and save it to the caption file`,
      send: true, newThread: true, from: `Caption · ${name}`, context: `project:${name}`,
    });
    if (!r) return;
    try {
      const j = (await (await fetch(`/api/projects/${encodeURIComponent(name)}/caption`)).json()) as { text?: string };
      if (typeof j.text === "string" && j.text.trim()) setText(j.text);
    } catch { /* keep what is in the box */ }
    if (r.isError) { setWriting("error"); setWriteError(r.error ?? "it did not finish"); } else setWriting("done");
  };
  return (
    <div className="card">
      <div className="text-muted text-sm mb-1">The text for the post. Press <b className="text-fg">Write with Claude</b> (the caption skill, linted until it passes as human) or write it here. Saved as <code>{file}</code>.</div>
      <textarea className="textarea min-h-[120px]" value={text} onChange={(e) => setText(e.target.value)} placeholder="first line is what survives the “… more” cut" />
      <div className="flex items-center gap-3 mt-2 flex-wrap">
        <button className="btn sm" onClick={write} disabled={writing === "running"} title="a new chat: /ig-caption, then /ig-human until PASS, saved to the caption file">
          {writing === "running" ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {writing === "running" ? "Claude is writing…" : "Write with Claude"}
        </button>
        <button className="btn sec sm" onClick={save} disabled={saved === "saving"}>Save caption</button>
        <button className="btn sec sm" onClick={() => navigator.clipboard.writeText(text)} disabled={!text}>Copy</button>
        {saved === "saved" && <span className="text-acc text-sm">saved</span>}
        {saved === "error" && <span className="text-bad text-sm">could not save</span>}
        {writing === "done" && <span className="text-acc text-sm">written by Claude — read it in the box</span>}
        {writing === "error" && <span className="text-bad text-sm">{writeError}</span>}
      </div>
    </div>
  );
}
