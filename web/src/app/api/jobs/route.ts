import { jobSummaries } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(jobSummaries());
}
