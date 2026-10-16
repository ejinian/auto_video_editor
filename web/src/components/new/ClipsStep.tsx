"use client";

import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { thumbUrl } from "@/lib/format";
import type { ClipInfo, FolderInfo } from "@/lib/types";

interface UploadState { name: string; pct: number; error?: string }

export interface FolderClips { folder: string; clips: ClipInfo[]; nextName: string }

const VIDEO_RE = /\.(mov|mp4|m4v)$/i;

export function ClipsStep({ defaultName, folders, folder, clips, onFolder, onNext }: {
  defaultName: string;
  folders: FolderInfo[];
  folder: string | null;
  clips: ClipInfo[];
  onFolder: (f: FolderClips) => void;
  onNext: () => void;
}) {
  const [name, setName] = useState(folder ?? defaultName);
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const busy = uploads.some((u) => u.pct < 100 && !u.error);
  const target = name.trim();
  const nameOk = /^[A-Za-z0-9_][A-Za-z0-9 _.-]{0,79}$/.test(target) && !target.includes("..");

  const pickExisting = async (f: string) => {
    setName(f);
    setError(null);
    const r = await fetch(`/api/folders/${encodeURIComponent(f)}/clips`);
    const j = (await r.json()) as FolderClips | { error: string };
    if (!r.ok || "error" in j) { setError("error" in j ? j.error : `could not read ${f}`); return; }
    onFolder(j);
  };

  /** One request per file so the numbered thumbnails appear as each one lands. */
  const uploadOne = (file: File) =>
    new Promise<void>((resolve) => {
      const fd = new FormData();
      fd.append("file", file, file.name);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/folders/${encodeURIComponent(target)}/clips`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) setUploads((u) => u.map((x) => (x.name === file.name ? { ...x, pct: Math.min(99, Math.round((e.loaded / e.total) * 100)) } : x)));
      };
      xhr.onload = () => {
        let j: FolderClips & { rejected?: Array<{ name: string; reason: string }>; error?: string };
        try { j = JSON.parse(xhr.responseText); } catch { j = { folder: target, clips: [], nextName: "", error: `upload failed (${xhr.status})` }; }
        const rej = j.rejected?.find((x) => x.name === file.name);
        const err = xhr.status >= 400 ? (j.error ?? `upload failed (${xhr.status})`) : rej?.reason;
        setUploads((u) => u.map((x) => (x.name === file.name ? { ...x, pct: 100, error: err } : x)));
        if (xhr.status < 400 && Array.isArray(j.clips)) onFolder({ folder: j.folder, clips: j.clips, nextName: j.nextName });
        resolve();
      };
      xhr.onerror = () => { setUploads((u) => u.map((x) => (x.name === file.name ? { ...x, pct: 100, error: "network error" } : x))); resolve(); };
      xhr.send(fd);
    });

  const addFiles = async (list: FileList | File[]) => {
    if (!nameOk) { setError("give the folder a name first (letters, digits, space, _ - .)"); return; }
    setError(null);
    const files = [...list].filter((f) => !f.name.startsWith("."));
    const videos = files.filter((f) => VIDEO_RE.test(f.name));
    const skipped = files.filter((f) => !VIDEO_RE.test(f.name));
    setUploads((u) => [
      ...u.filter((x) => !videos.some((v) => v.name === x.name)),
      ...videos.map((f) => ({ name: f.name, pct: 0 })),
      ...skipped.map((f) => ({ name: f.name, pct: 100, error: "not a video" })),
    ]);
    for (const f of videos) await uploadOne(f);
  };

  return (
    <div>
      <div className="card">
        <div className="flex flex-wrap items-end gap-x-5 gap-y-2 mb-4">
          <div className="min-w-[220px]">
            <label className="label !mt-0" htmlFor="new-folder">Folder name</label>
            <input id="new-folder" className="input font-mono" value={name} onChange={(e) => setName(e.target.value)} disabled={busy} />
          </div>
          <div className="text-muted text-xs pb-2 flex-1 min-w-[200px]">The clips go to <code>clips/{target || "…"}/</code>; videos from it are named <code>{target || "…"}_1</code>, <code>_2</code>…</div>
          {folders.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 pb-1">
              <span className="text-muted text-xs mr-1">or an existing folder:</span>
              {folders.map((f) => (
                <button key={f.name} type="button" className={`tag !cursor-pointer hover:border-acc hover:text-fg ${f.name === folder ? "ok" : ""}`} onClick={() => pickExisting(f.name)} disabled={busy}>
                  {f.name} · {f.clipCount}
                </button>
              ))}
            </div>
          )}
        </div>
        <div
          className={`drop ${over ? "over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); addFiles(e.dataTransfer.files); }}
          onClick={() => fileRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileRef.current?.click(); }}
          data-testid="dropzone"
        >
          <span className="ic"><Upload size={22} /></span>
          <div className="text-[15px] font-semibold text-fg">Drop the phone clips here</div>
          <div className="text-[13px]">.mov, .mp4 or .m4v · AirDrop puts them in Downloads, drag them from there</div>
          <span className="btn sec sm mt-3 pointer-events-none">Choose files</span>
          <input ref={fileRef} type="file" accept=".mov,.mp4,.m4v,video/*" multiple className="hidden" onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
        </div>
        {uploads.length > 0 && (
          <div className="mt-3 space-y-1 text-xs">
            {uploads.map((u) => (
              <div key={u.name} className="flex items-center gap-2">
                <span className="font-mono truncate min-w-0 flex-1">{u.name}</span>
                {u.error ? <span className="text-bad">{u.error}</span>
                  : u.pct < 100 ? <span className="text-muted w-28"><span className="inline-block h-1.5 rounded bg-acc align-middle" style={{ width: `${u.pct}%` }} /> {u.pct}%</span>
                  : <span className="text-acc">saved</span>}
              </div>
            ))}
          </div>
        )}
        {error && <div className="text-bad text-sm mt-3">{error}</div>}
      </div>

      <h2>{folder ? `clips/${folder}/ · ${clips.length} clip${clips.length === 1 ? "" : "s"}` : "Clips"}</h2>
      {clips.length === 0 ? (
        <div className="text-muted text-sm">Nothing here yet. The number on each clip is what the edit buttons and Claude mean by &ldquo;clip 3&rdquo;; it follows the filename order.</div>
      ) : (
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
          {clips.map((c) => (
            <div key={c.path} className="clip">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={thumbUrl(c.folder, c.stem)} alt={c.name} loading="lazy" />
              <span className="n">{c.n}</span>
              {c.hdr && <span className="absolute top-1.5 right-1.5 text-[10px] font-bold bg-black/70 text-warn px-1.5 py-0.5 rounded">HDR</span>}
              <small>{c.name} · {c.duration.toFixed(0)}s</small>
            </div>
          ))}
        </div>
      )}

      <div className="stepbar">
        <span className="status">{busy ? "uploading…" : clips.length ? `${clips.length} clips ready` : "add at least one clip"}</span>
        <button type="button" className="btn lg" disabled={!folder || clips.length === 0 || busy} onClick={onNext}>Next: pick a sound →</button>
      </div>
    </div>
  );
}
