"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Link2, Shuffle, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Seg } from "@/components/new/Seg";
import { useJob } from "@/components/useJob";
import type { ProjectSummary } from "@/lib/types";

const VIDEO_RE = /\.(mov|mp4|m4v)$/i;

/** The Remix page: drop one finished video (a reel that did numbers) and get four new
 *  posts from its shots; or press Remix on a video the app already made. */
export function RemixUpload({ videos }: { videos: ProjectSummary[] }) {
  const router = useRouter();
  const { run, busy, error: jobError } = useJob();
  const [name, setName] = useState("");
  const [over, setOver] = useState(false);
  const [pct, setPct] = useState<number | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const uploading = pct != null && pct < 100;
  const [link, setLink] = useState("");
  const [cookies, setCookies] = useState(false);
  const [linkBusy, setLinkBusy] = useState(false);
  // reformat (default): the same cut with three framings — right for a finished reel.
  // recut: four re-cuts of its shots — right for raw footage, worse for a finished reel.
  const [mode, setMode] = useState<"reformat" | "recut">("reformat");

  // a posted video by link: the CLI downloads it (tikwm for TikTok, yt-dlp otherwise) and
  // goes on like an uploaded file; the job page shows the download as it happens
  const fromLink = async () => {
    const l = link.trim();
    if (!/^https?:\/\/\S+$/.test(l)) { setError("paste a TikTok, Instagram or YouTube link"); return; }
    setError(null);
    setLinkBusy(true);
    try {
      const r = await fetch("/api/remix", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ link: l, name: name.trim(), cookies: cookies ? "chrome" : undefined, mode }) });
      const j = (await r.json().catch(() => ({}))) as { job?: string; error?: string };
      if (!r.ok || !j.job) { setError(j.error ?? `request failed (${r.status})`); return; }
      router.push(`/jobs/${j.job}`);
    } finally {
      setLinkBusy(false);
    }
  };

  const upload = (file: File) => {
    if (!VIDEO_RE.test(file.name)) { setError("drop a video: .mp4, .mov or .m4v"); return; }
    setError(null);
    setFileName(file.name);
    setPct(0);
    const fd = new FormData();
    fd.append("name", name.trim());
    fd.append("mode", mode);
    fd.append("file", file, file.name);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/remix");
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) setPct(Math.min(99, Math.round((e.loaded / e.total) * 100))); };
    xhr.onload = () => {
      let j: { job?: string; error?: string } = {};
      try { j = JSON.parse(xhr.responseText); } catch { /* not json */ }
      if (xhr.status >= 400 || !j.job) { setError(j.error ?? `upload failed (${xhr.status})`); setPct(null); return; }
      setPct(100);
      router.push(`/jobs/${j.job}`);
    };
    xhr.onerror = () => { setError("network error"); setPct(null); };
    xhr.send(fd);
  };

  return (
    <div>
      <div className="card">
        <div className="flex flex-wrap items-end gap-x-5 gap-y-2 mb-4">
          <div className="min-w-[220px]">
            <label className="label !mt-0" htmlFor="remix-name">Name <span className="text-muted font-normal">(optional)</span></label>
            <input id="remix-name" className="input font-mono" placeholder="from the file name" value={name} onChange={(e) => setName(e.target.value)} disabled={uploading} />
          </div>
          <div className="text-muted text-xs pb-2 flex-1 min-w-[240px]">Paste the post&apos;s link or drop the file.</div>
        </div>
        <div className="mb-4">
          <Seg<"reformat" | "recut"> ariaLabel="what to make" value={mode} onChange={setMode} options={[
            { value: "reformat", label: "Reformat", sub: "the same cut, new framings: a hook line, a narration in your voice, a comment reply, and your avatar reacting in the corner once you have one — Claude writes the copy" },
            { value: "recut", label: "Re-cut ×4", sub: "split into shots and cut again: hook cut, another sound, reorder, long version — for raw footage, not a finished reel" },
          ]} />
        </div>
        <div className="flex gap-2 items-center mb-3">
          <Link2 size={16} className="text-muted shrink-0" />
          <input
            className="input" placeholder="https://www.tiktok.com/@…/video/…  ·  instagram.com/reel/…  ·  youtube.com/…"
            aria-label="link to a posted video" value={link} disabled={linkBusy || uploading}
            onChange={(e) => setLink(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void fromLink(); } }}
          />
          <button type="button" className="btn" disabled={linkBusy || uploading || !link.trim()} onClick={() => void fromLink()}>{linkBusy ? "Starting…" : mode === "recut" ? "Re-cut the link" : "Reformat the link"}</button>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted mb-3"><input type="checkbox" checked={cookies} onChange={(e) => setCookies(e.target.checked)} /> use Chrome&apos;s login for Instagram (macOS asks for Keychain access)</label>
        <div className="text-muted text-xs mb-2">…or the file itself:</div>
        <div
          className={`drop ${over ? "over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) upload(f); }}
          onClick={() => { if (!uploading) fileRef.current?.click(); }}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileRef.current?.click(); }}
          data-testid="remix-dropzone"
        >
          <span className="ic"><Shuffle size={22} /></span>
          <div className="text-[15px] font-semibold text-fg">Drop the video that did numbers</div>
          <div className="text-[13px]">one .mp4, .mov or .m4v — the reel as you posted it, or any finished edit</div>
          <span className="btn sec sm mt-3 pointer-events-none"><Upload size={14} /> Choose a video</span>
          <input ref={fileRef} type="file" accept=".mov,.mp4,.m4v,video/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
        </div>
        {pct != null && (
          <div className="mt-3 text-xs flex items-center gap-2">
            <span className="font-mono truncate min-w-0 flex-1">{fileName}</span>
            {pct < 100
              ? <span className="text-muted w-32"><span className="inline-block h-1.5 rounded bg-acc align-middle" style={{ width: `${pct}%` }} /> uploading {pct}%</span>
              : <span className="text-acc">uploaded — cutting…</span>}
          </div>
        )}
        {error && <div className="text-bad text-sm mt-3">{error}</div>}
      </div>

      <h2>Or remix a video the app made</h2>
      {videos.length === 0 && <div className="text-muted text-sm">No rendered video yet.</div>}
      {jobError && <div className="text-bad text-sm mb-2">{jobError}</div>}
      <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
        {videos.map((p) => (
          <div key={p.name} className="card flex items-center gap-3 !py-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`/api/slot-thumb/${encodeURIComponent(p.name)}/1`} alt="" className="poster !w-12 rounded-lg" />
            <div className="min-w-0 flex-1">
              <div className="font-semibold truncate"><Link href={`/video/${encodeURIComponent(p.name)}`}>{p.name}</Link>{p.remixOf && <span className="tag ml-1.5 font-normal">remix of {p.remixOf}</span>}</div>
              <div className="text-muted text-xs truncate">{p.length.toFixed(0)} s · {p.slots} shots · ♪ {p.sound}</div>
            </div>
            <button type="button" className="btn sec sm" disabled={busy} onClick={() => run(`/api/projects/${encodeURIComponent(p.name)}/remix`, {})} title="four new videos from this one's clips, rendered"><Shuffle size={13} /> Remix ×4</button>
          </div>
        ))}
      </div>
    </div>
  );
}
