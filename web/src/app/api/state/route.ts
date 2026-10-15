import { folders, health, projects, sounds } from "@/lib/beatcut";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Everything the home page shows, for scripts and for the chat panel's quick facts. */
export async function GET() {
  const [f, p, s, h] = await Promise.all([folders(), projects(), sounds(), health()]);
  return Response.json({ folders: f, projects: p, sounds: s, health: h });
}
