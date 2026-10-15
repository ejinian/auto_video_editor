import { sounds } from "@/lib/beatcut";
import { beatcut, startJob } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(await sounds());
}

/** Download + analyze a sound into the pool (no project attached). */
export async function POST(req: Request) {
  const { link, cookies } = (await req.json().catch(() => ({}))) as { link?: string; cookies?: string };
  const l = link?.trim();
  if (!l) return Response.json({ error: "link required" }, { status: 400 });
  if (l.startsWith("sound/") || l.includes("/sound/")) {
    return Response.json({ error: "that file is already in the pool — pick it from the list instead (re-importing truncates it)" }, { status: 400 });
  }
  const argv = ["sound", l, ...(cookies ? ["--cookies", cookies] : [])];
  const job = startJob(`Sound: ${l}`, [beatcut(...argv)], "/sounds");
  return Response.json({ job: job.id });
}
