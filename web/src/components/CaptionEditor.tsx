"use client";

import { useState } from "react";

export function CaptionEditor({ name, initial, file }: { name: string; initial: string; file: string }) {
  const [text, setText] = useState(initial);
  const [saved, setSaved] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const save = async () => {
    setSaved("saving");
    const r = await fetch(`/api/projects/${encodeURIComponent(name)}/caption`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    setSaved(r.ok ? "saved" : "error");
    setTimeout(() => setSaved("idle"), 1500);
  };
  return (
    <div className="card">
      <div className="text-muted text-sm mb-1">The text for the post. Ask Claude &ldquo;write the caption&rdquo; (it uses the caption skill and lints it) or write it here. Saved as <code>{file}</code>.</div>
      <textarea className="textarea min-h-[120px]" value={text} onChange={(e) => setText(e.target.value)} placeholder="first line is what survives the “… more” cut" />
      <div className="flex items-center gap-3 mt-2">
        <button className="btn sec sm" onClick={save} disabled={saved === "saving"}>Save caption</button>
        <button className="btn sec sm" onClick={() => navigator.clipboard.writeText(text)} disabled={!text}>Copy</button>
        {saved === "saved" && <span className="text-acc text-sm">saved</span>}
        {saved === "error" && <span className="text-bad text-sm">could not save</span>}
      </div>
    </div>
  );
}
