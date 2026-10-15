"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { JobInfo } from "@/lib/types";

export function JobView({ initial }: { initial: JobInfo }) {
  const [job, setJob] = useState(initial);
  const router = useRouter();
  const logRef = useRef<HTMLPreElement>(null);
  const [auto, setAuto] = useState(true);

  useEffect(() => {
    if (initial.done) return;
    const es = new EventSource(`/api/jobs/${initial.id}/stream`);
    es.onmessage = (e) => {
      const j = JSON.parse(e.data) as JobInfo;
      setJob(j);
      if (j.done) es.close();
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [initial.id, initial.done]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [job.log]);

  useEffect(() => {
    if (job.done && job.ok && job.then && auto) {
      const t = setTimeout(() => router.push(job.then!), 900);
      return () => clearTimeout(t);
    }
  }, [job.done, job.ok, job.then, auto, router]);

  const secs = job.endedAt ? (job.endedAt - job.startedAt) / 1000 : 0;
  return (
    <div>
      <h1>{job.title}</h1>
      <p className="text-muted text-sm -mt-1 mb-3">
        {job.done
          ? job.ok ? <span className="text-acc">done in {secs.toFixed(0)} s.</span> : <span className="text-bad">stopped on an error — read the last lines.</span>
          : <span className="pulse">running… a 30 s render takes about a minute. The log updates by itself.</span>}
      </p>
      <pre ref={logRef} className="log max-h-[60vh] overflow-auto">{job.log || " "}</pre>
      <div className="flex items-center gap-3 mt-3">
        {job.then && <Link className="btn" href={job.then}>Open the result →</Link>}
        {job.done && job.ok && job.then && auto && <span className="text-muted text-sm">opening it… <button className="underline" onClick={() => setAuto(false)}>stay here</button></span>}
        <Link className="btn sec" href="/jobs">All jobs</Link>
      </div>
    </div>
  );
}
