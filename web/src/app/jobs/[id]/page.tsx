import { notFound } from "next/navigation";
import { JobView } from "@/components/JobView";
import { getJob } from "@/lib/jobs";

export const dynamic = "force-dynamic";

export default async function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const job = getJob(id);
  if (!job) notFound();
  return <JobView initial={{ ...job }} />;
}
