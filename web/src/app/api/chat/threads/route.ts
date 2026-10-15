import { listThreads } from "@/lib/chats";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(listThreads());
}
