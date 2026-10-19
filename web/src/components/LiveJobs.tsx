"use client";

/**
 * Live job state for the status chips: one module-level store that polls /api/jobs
 * every 2 s while a job is running (every 10 s when nothing is, to notice a job started
 * from another page), shared by every chip on the page. `<LiveJobs>` is mounted once per
 * page that shows chips; it refreshes the page's server data when a job finishes, so the
 * chip settles on what is now on disk (rendered / stale).
 */
import { useRouter } from "next/navigation";
import { useEffect, useRef, useSyncExternalStore } from "react";
import type { JobSummary } from "@/lib/types";

const BUSY_MS = 2000, IDLE_MS = 10000;
const EMPTY: JobSummary[] = [];

let jobs: JobSummary[] = EMPTY;
let ready = false;
let timer: ReturnType<typeof setTimeout> | null = null;
let inflight = false;
const listeners = new Set<() => void>();

function notify() {
  for (const l of listeners) l();
}

async function poll() {
  if (inflight) return;
  inflight = true;
  try {
    const r = await fetch("/api/jobs", { cache: "no-store" });
    if (r.ok) {
      jobs = (await r.json()) as JobSummary[];
      ready = true;
      notify();
    }
  } catch {
    /* next tick */
  } finally {
    inflight = false;
    schedule();
  }
}

function schedule() {
  if (timer) clearTimeout(timer);
  timer = null;
  if (!listeners.size) return;
  timer = setTimeout(poll, jobs.some((j) => !j.done) ? BUSY_MS : IDLE_MS);
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  if (listeners.size === 1) void poll();
  return () => {
    listeners.delete(fn);
    if (!listeners.size && timer) { clearTimeout(timer); timer = null; }
  };
}

/** Every job the server knows, newest first; `[]` until the first poll answers. */
export function useLiveJobs(): JobSummary[] {
  return useSyncExternalStore(subscribe, () => jobs, () => EMPTY);
}

/** The running job for a project: the live one once polling has answered, else what the
 *  page was rendered with. Jobs run in the order they were started, so of several unfinished
 *  ones the OLDEST is the one actually running (the list comes newest first). */
export function useLiveJob(project: string, initial: JobSummary | null = null): JobSummary | null {
  const all = useLiveJobs();
  if (!ready) return initial;
  return all.filter((j) => !j.done && j.project === project).at(-1) ?? null;
}

/** Ask the server for new page data every time a job finishes. */
export function LiveJobs() {
  const all = useLiveJobs();
  const router = useRouter();
  const running = useRef<Set<string> | null>(null);
  useEffect(() => {
    const now = new Set(all.filter((j) => !j.done).map((j) => j.id));
    const before = running.current;
    running.current = now;
    if (before && [...before].some((id) => !now.has(id))) router.refresh();
  }, [all, router]);
  return null;
}
