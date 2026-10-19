"use client";

/**
 * The hand-off on /video/<name>/post: copy the caption, tick the checklist, then
 * "Mark as posted" writes out/.app/posted.json (through PUT /api/projects/<name>/posted)
 * and goes back to the feed. Nothing here uploads anything anywhere.
 */
import { Check, Copy } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { shortDate } from "@/lib/format";
import type { PostedInfo } from "@/lib/types";

const STEPS = [
  "Upload the mp4 as a Reel / TikTok (the Download button above)",
  "Paste the caption",
  "Add the sound by name if the app asks for one",
];

export function CopyCaption({ name }: { name: string }) {
  const [state, setState] = useState<"idle" | "copied" | "empty" | "error">("idle");
  const copy = async () => {
    try {
      const r = await fetch(`/api/projects/${encodeURIComponent(name)}/caption`, { cache: "no-store" });
      const { text } = (await r.json()) as { text?: string };
      if (!text) { setState("empty"); return; }
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("error");
    } finally {
      setTimeout(() => setState("idle"), 1800);
    }
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button className="btn sec sm" onClick={copy}><Copy size={14} /> Copy caption</button>
      {state === "copied" && <span className="text-acc text-sm">copied (the saved caption)</span>}
      {state === "empty" && <span className="text-warn text-sm">no caption saved yet — write one below and save it</span>}
      {state === "error" && <span className="text-bad text-sm">could not copy</span>}
    </span>
  );
}

export function PostPanel({ name, posted, soundTitle }: { name: string; posted: PostedInfo | null; soundTitle: string }) {
  const router = useRouter();
  const [done, setDone] = useState<boolean[]>(STEPS.map(() => false));
  const [platform, setPlatform] = useState<"tiktok" | "instagram" | "both">("both");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mark = async () => {
    setBusy(true);
    setError(null);
    const r = await fetch(`/api/projects/${encodeURIComponent(name)}/posted`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ platform, url }),
    });
    setBusy(false);
    if (!r.ok) { setError(`could not save (${r.status})`); return; }
    router.push("/");
    router.refresh();
  };
  const unmark = async () => {
    setBusy(true);
    const r = await fetch(`/api/projects/${encodeURIComponent(name)}/posted`, { method: "DELETE" });
    setBusy(false);
    if (!r.ok) { setError(`could not save (${r.status})`); return; }
    router.refresh();
  };

  return (
    <div className="card">
      <div className="check">
        {STEPS.map((s, i) => (
          <label key={i} className={done[i] ? "done" : ""}>
            <input type="checkbox" checked={done[i]} onChange={(e) => setDone(done.map((d, j) => (j === i ? e.target.checked : d)))} />
            <span>{s}{i === 2 && soundTitle ? <> — <i>{soundTitle}</i></> : null}</span>
          </label>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-line">
        {posted ? (
          <div className="flex items-center gap-3 flex-wrap">
            <span className="tag ok"><Check size={12} /> posted {shortDate(posted.postedAt)}{posted.platform ? ` on ${posted.platform}` : ""}</span>
            {posted.url && <a href={posted.url} target="_blank" rel="noreferrer" className="text-sm">{posted.url}</a>}
            <button className="btn sec sm" onClick={unmark} disabled={busy}>Unmark</button>
          </div>
        ) : (
          <div className="flex items-end gap-3 flex-wrap">
            <div>
              <span className="label !mt-0">Where</span>
              <div className="seg" role="radiogroup">
                {(["tiktok", "instagram", "both"] as const).map((p) => (
                  <button key={p} type="button" className={platform === p ? "on" : ""} onClick={() => setPlatform(p)} role="radio" aria-checked={platform === p}>
                    {p === "tiktok" ? "TikTok" : p === "instagram" ? "Instagram" : "Both"}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 min-w-[220px]">
              <span className="label !mt-0">Link to the post (optional)</span>
              <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.tiktok.com/@youngvibas/video/…" />
            </div>
            <button className="btn" onClick={mark} disabled={busy}><Check size={16} /> Mark as posted</button>
          </div>
        )}
        {error && <div className="text-bad text-sm mt-2">{error}</div>}
        <div className="text-muted text-xs mt-3">This only writes a note in <code>out/.app/posted.json</code> so the feed shows &ldquo;posted&rdquo;. The app never uploads or posts anything.</div>
      </div>
    </div>
  );
}
