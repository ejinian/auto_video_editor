/**
 * Jobs: a queue of `uv run beatcut.py …` commands run one after another, with the log
 * streamed to whoever is watching. Kept in memory on globalThis so Next's dev reloads
 * don't lose running jobs. Mirrors ui.py's start_job.
 */
import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";
import { BEATCUT_PY, ROOT } from "./paths";
import type { JobInfo } from "./types";

interface Store { jobs: Map<string, JobInfo>; events: EventEmitter; queue: Promise<void> }

const g = globalThis as unknown as { __beatcutJobs?: Store };
const store: Store = g.__beatcutJobs ?? (g.__beatcutJobs = { jobs: new Map(), events: new EventEmitter(), queue: Promise.resolve() });
store.events.setMaxListeners(100);

/** argv for one beatcut command (`["-p", "day3_1", "render"]`). */
export type Argv = string[];

export function beatcut(...argv: string[]): string[] {
  return ["uv", "run", BEATCUT_PY, ...argv];
}

/** How the log prints a command: without the `uv run …/beatcut.py` prefix. */
export function pretty(cmd: string[]): string {
  const parts = cmd[0] === "uv" ? cmd.slice(3) : cmd;
  return parts.map((c) => (/[\s"']/.test(c) || c === "" ? JSON.stringify(c) : c)).join(" ");
}

export function listJobs(): JobInfo[] {
  return [...store.jobs.values()].sort((a, b) => b.startedAt - a.startedAt);
}

export function getJob(id: string): JobInfo | undefined {
  return store.jobs.get(id);
}

export function onJob(id: string, fn: (j: JobInfo) => void): () => void {
  const h = (j: JobInfo) => { if (j.id === id) fn(j); };
  store.events.on("job", h);
  return () => store.events.off("job", h);
}

function emit(j: JobInfo) {
  store.events.emit("job", j);
}

/**
 * Start a job. Commands run sequentially and the job stops on the first failure.
 * beatcut.py itself refuses to run two renders of the same project cleanly, so jobs
 * are serialized: one beatcut process at a time, in the order they were started.
 */
export function startJob(title: string, cmds: string[][], then: string | null = null): JobInfo {
  const job: JobInfo = {
    id: randomUUID().slice(0, 8),
    title, cmds, log: "", done: false, ok: true, then,
    startedAt: Date.now(), endedAt: null,
  };
  store.jobs.set(job.id, job);
  // keep the last 50 jobs
  if (store.jobs.size > 50) {
    const oldest = [...store.jobs.values()].filter((j) => j.done).sort((a, b) => a.startedAt - b.startedAt)[0];
    if (oldest) store.jobs.delete(oldest.id);
  }
  store.queue = store.queue.then(() => run(job)).catch(() => undefined);
  emit(job);
  return job;
}

function run(job: JobInfo): Promise<void> {
  return (async () => {
    for (const cmd of job.cmds) {
      job.log += `$ ${pretty(cmd)}\n`;
      emit(job);
      const code = await new Promise<number>((resolve) => {
        const p = spawn(cmd[0], cmd.slice(1), {
          cwd: ROOT,
          env: { ...process.env, PYTHONUNBUFFERED: "1", NO_COLOR: "1" },
        });
        const onData = (d: Buffer) => { job.log += d.toString(); emit(job); };
        p.stdout.on("data", onData);
        p.stderr.on("data", onData);
        p.on("error", (e) => { job.log += `\n✗ could not start ${cmd[0]}: ${e.message}\n`; resolve(127); });
        p.on("close", (c) => resolve(c ?? 1));
      });
      if (code !== 0) {
        job.ok = false;
        job.log += `\n✗ stopped: that step failed (exit ${code})\n`;
        break;
      }
    }
    job.done = true;
    job.endedAt = Date.now();
    emit(job);
  })();
}
