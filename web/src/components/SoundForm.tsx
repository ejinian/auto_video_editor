"use client";

import { useState } from "react";
import { useJob } from "@/components/useJob";

export function SoundForm() {
  const { run, busy, error } = useJob();
  const [link, setLink] = useState("");
  const [cookies, setCookies] = useState(false);
  return (
    <form className="card" onSubmit={(e) => { e.preventDefault(); run("/api/sounds", { link, cookies: cookies ? "chrome" : undefined }); }}>
      <div className="font-semibold">Add a sound to the pool</div>
      <div className="text-muted text-sm">TikTok video or sound-page link, Instagram reel (its audio as it plays, only as long as the reel), YouTube, or a local audio file path. The beats and drops are analysed right away.</div>
      <div className="flex gap-2 mt-2 items-end">
        <input className="input" placeholder="https://www.tiktok.com/…" value={link} onChange={(e) => setLink(e.target.value)} required />
        <button className="btn" disabled={busy}>Download</button>
      </div>
      <label className="flex items-center gap-2 text-sm mt-2"><input type="checkbox" checked={cookies} onChange={(e) => setCookies(e.target.checked)} /> use Chrome&apos;s login for Instagram (macOS asks for Keychain access)</label>
      {error && <div className="text-bad text-sm mt-2">{error}</div>}
    </form>
  );
}
