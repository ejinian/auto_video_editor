"use client";

/**
 * The one status chip a video gets, in this order: a running job for it
 * ("cutting…" / "rendering…", live, with the elapsed seconds and the step), "posted
 * <date>", "needs render" (never rendered, or edited since), "ready to post".
 */
import { useEffect, useState } from "react";
import { jobVerb } from "@/lib/jobmeta";
import { shortDate } from "@/lib/format";
import type { JobSummary, PostedInfo } from "@/lib/types";
import { useLiveJob } from "./LiveJobs";
import { Tag } from "./Tag";

export interface StatusProps {
  name: string;
  rendered: boolean;
  stale: boolean;
  posted: PostedInfo | null;
  /** The running job for this video at render time, so the chip is right before the first poll. */
  job?: JobSummary | null;
  /** Also draw the progress bar with the step name under the chip (the feed cards). */
  bar?: boolean;
}

/** Seconds since `since`, ticking once a second; null until the first tick in the browser
 *  (the server and the browser would disagree on Date.now(), so it is not rendered on the server). */
function useElapsed(since: number | null): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (since == null) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [since]);
  return since == null || now == null ? null : Math.max(0, Math.round((now - since) / 1000));
}

export function StatusChip({ name, rendered, stale, posted, job: initial = null, bar = false }: StatusProps) {
  const job = useLiveJob(name, initial);
  const elapsed = useElapsed(job ? job.startedAt : null);
  if (job) {
    const verb = jobVerb(job.steps, job.step);
    const step = job.steps[job.step] ?? "…";
    return (
      <span className="inline-flex flex-col gap-1 min-w-0" title={`${job.title}: step ${job.step + 1} of ${job.steps.length} (${step})`}>
        <Tag kind="warn"><span className="pulse">{verb}</span>{elapsed != null && <> {elapsed} s</>}</Tag>
        {bar && (
          <span className="prog" aria-hidden>
            <span className="prog-bar"><span /></span>
            <span className="prog-steps">
              {job.steps.map((s, i) => (
                <span key={i} className={i === job.step ? "on" : i < job.step ? "done" : ""}>{s}</span>
              ))}
            </span>
          </span>
        )}
      </span>
    );
  }
  if (posted) return <Tag kind="ok" title={posted.url ?? (posted.platform ? `on ${posted.platform}` : undefined)}>posted {shortDate(posted.postedAt)}</Tag>;
  if (!rendered || stale) return <Tag kind="warn" title={rendered ? "edited since the last render" : "not rendered yet"}>needs render</Tag>;
  return <Tag kind="ok">ready to post</Tag>;
}
