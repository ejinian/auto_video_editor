import Link from "next/link";
import { projects } from "@/lib/beatcut";
import { ago } from "@/lib/format";
import { StatusTag, Tag } from "@/components/Tag";

export const dynamic = "force-dynamic";

export default async function Videos() {
  const ps = await projects();
  return (
    <div>
      <h1>Videos</h1>
      <p className="lede">Every edit in <code>projects/</code>. The finished file is <code>final/&lt;name&gt;.mp4</code>; <code>out/</code> keeps the storyboard and earlier renders.</p>
      <div className="card !p-0 overflow-hidden">
        <table className="t">
          <thead><tr><th>video</th><th>shoot</th><th>sound</th><th>cut</th><th>on-screen hook</th><th>edited</th><th></th></tr></thead>
          <tbody>
            {ps.map((p) => (
              <tr key={p.name}>
                <td><Link href={`/video/${encodeURIComponent(p.name)}`}>{p.name}</Link>{p.inFinal && <Tag kind="ok" title="in final/">final</Tag>}</td>
                <td>{p.folder ? <Link href={`/shoot/${encodeURIComponent(p.folder)}`}>{p.folder}</Link> : <span className="text-muted">—</span>}</td>
                <td className="text-muted">{p.sound}</td>
                <td>{p.length.toFixed(0)} s · {p.slots} shots</td>
                <td className="text-muted max-w-[260px] truncate">{p.caption ?? ""}</td>
                <td className="text-muted">{ago(p.mtime)}</td>
                <td><StatusTag rendered={p.rendered} stale={p.stale} /></td>
              </tr>
            ))}
            {ps.length === 0 && <tr><td colSpan={7} className="text-muted">none yet — open a shoot and press Cut it</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
