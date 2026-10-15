import Link from "next/link";
import { listJobs, pretty } from "@/lib/jobs";
import { ago } from "@/lib/format";
import { Tag } from "@/components/Tag";

export const dynamic = "force-dynamic";

export default function Jobs() {
  const jobs = listJobs();
  return (
    <div>
      <h1>Jobs</h1>
      <p className="text-muted text-sm -mt-1 mb-3">Every button runs <code>uv run beatcut.py …</code> as a job, one at a time, and keeps the log here until the app restarts.</p>
      <div className="card !p-0 overflow-hidden">
        <table className="t">
          <thead><tr><th>job</th><th>commands</th><th>started</th><th></th></tr></thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td><Link href={`/jobs/${j.id}`}>{j.title}</Link></td>
                <td className="text-muted font-mono text-xs">{j.cmds.map(pretty).join(" && ")}</td>
                <td className="text-muted">{ago(j.startedAt)}</td>
                <td>{j.done ? (j.ok ? <Tag kind="ok">done</Tag> : <Tag kind="bad">failed</Tag>) : <Tag kind="warn">running</Tag>}</td>
              </tr>
            ))}
            {jobs.length === 0 && <tr><td colSpan={4} className="text-muted">nothing has run yet</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
