import fs from "node:fs";
import path from "node:path";
import { Markdown } from "@/components/Markdown";
import { ROOT } from "@/lib/paths";

export const dynamic = "force-dynamic";

export default function HowTo() {
  const p = path.join(ROOT, "HOWTO.md");
  const md = fs.existsSync(p) ? fs.readFileSync(p, "utf8") : "HOWTO.md is missing.";
  return (
    <div className="max-w-[820px]">
      <div className="card howto"><Markdown text={md} /></div>
      <div className="card mt-4 text-sm">
        <b>This app</b> is <code>web/</code> in the beatcut folder: <code>npm run dev</code> there, open <code>http://localhost:3000</code>. It needs <code>ANTHROPIC_API_KEY</code> in <code>web/.env.local</code> for the Claude panel. Every button runs the same <code>uv run beatcut.py</code> commands as the chat, so the CLI, the chat and the buttons never disagree.
      </div>
    </div>
  );
}
