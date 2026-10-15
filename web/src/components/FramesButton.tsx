"use client";

import { useJob } from "@/components/useJob";

export function FramesButton({ folder, label = "Make frame sheets" }: { folder: string; label?: string }) {
  const { run, busy, error } = useJob();
  return (
    <span className="inline-flex items-center gap-2">
      <button className="btn sec sm" disabled={busy} onClick={() => run(`/api/folders/${encodeURIComponent(folder)}/frames`)}>{label}</button>
      {error && <span className="text-bad text-sm">{error}</span>}
    </span>
  );
}
