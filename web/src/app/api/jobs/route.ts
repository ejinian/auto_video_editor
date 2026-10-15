import { listJobs } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(listJobs().map((j) => ({ ...j, log: j.log.slice(-400) })));
}
