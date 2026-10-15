"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

/** POST to an API route that starts a job, then go watch it. */
export function useJob() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (url: string, body?: unknown, method = "POST") => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
      const j = (await r.json().catch(() => ({}))) as { job?: string; error?: string };
      if (!r.ok || !j.job) {
        setError(j.error ?? `request failed (${r.status})`);
        return null;
      }
      router.push(`/jobs/${j.job}`);
      return j.job;
    } catch (e) {
      setError(String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }, [router]);
  return { run, busy, error, setError };
}
