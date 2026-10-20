import { loadProject } from "@/lib/beatcut";
import { beatcut, startJob } from "@/lib/jobs";
import { PRESETS } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Body = { cmd: string; args?: Record<string, string | number | null | undefined> };

const num = (v: unknown) => String(v ?? "").trim();

/** One edit command on a project, then `board` (unless it was render/export). Mirrors ui.py. */
export async function POST(req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!loadProject(name)) return Response.json({ error: "no such project" }, { status: 404 });
  const b = (await req.json().catch(() => null)) as Body | null;
  if (!b?.cmd) return Response.json({ error: "cmd required" }, { status: 400 });
  const a = b.args ?? {};
  let argv: string[] | null = null;
  switch (b.cmd) {
    case "render": argv = ["render"]; break;
    case "render-draft": argv = ["render", "--draft"]; break;
    case "export": argv = ["export"]; break;
    case "export-open": argv = ["export", "--open"]; break;
    case "board": argv = ["board"]; break;
    case "frames": argv = ["frames"]; break;
    case "swap": if (num(a.a) && num(a.b)) argv = ["swap", num(a.a), num(a.b)]; break;
    case "move": if (num(a.a) && num(a.b)) argv = ["move", num(a.a), num(a.b)]; break;
    case "set": if (num(a.slot) && num(a.clip)) argv = ["set", num(a.slot), num(a.clip), ...(num(a.at) ? ["--at", num(a.at)] : [])]; break;
    case "in": if (num(a.slot) && num(a.sec)) argv = ["in", num(a.slot), num(a.sec)]; break;
    case "merge": case "split": if (num(a.slot)) argv = [b.cmd, num(a.slot)]; break;
    case "cut": if (num(a.slot) && num(a.sec)) argv = ["cut", num(a.slot), num(a.sec)]; break;
    case "drop": case "restore": case "hero": if (num(a.clip)) argv = [b.cmd, ...num(a.clip).split(/[\s,]+/).filter(Boolean)]; break;
    case "shuffle": argv = ["shuffle", ...(num(a.seed) ? ["--seed", num(a.seed)] : [])]; break;
    case "caption": argv = ["caption", num(a.text) || "none"]; break;
    case "reformat": {
      // a reformat's copy: hook line / narration lines / comment (+ user) / voice, then render
      argv = ["reformat"];
      if (a.hook !== undefined) argv.push("--hook", num(a.hook));
      if (a.lines !== undefined) argv.push("--lines", num(a.lines));
      if (a.comment !== undefined) argv.push("--comment", num(a.comment));
      if (num(a.user)) argv.push("--user", num(a.user));
      if (num(a.voice)) argv.push("--voice", num(a.voice));
      if (num(a.pick) && /^\d+$/.test(num(a.pick))) argv.push("--pick", num(a.pick));
      if (a.moments !== undefined) argv.push("--moments", num(a.moments));
      if (a.sound !== undefined) argv.push("--sound", num(a.sound));
      if (a.another) argv.push("--another");
      if (num(a.avatar)) argv.push("--avatar", num(a.avatar));
      if (a.reactions !== undefined) argv.push("--reactions", num(a.reactions));
      if (a.render) argv.push("--render");
      break;
    }
    case "length": if (num(a.value)) argv = ["length", num(a.value)]; break;
    case "start": if (num(a.value)) argv = ["start", num(a.value)]; break;
    case "density": {
      const v = num(a.value);
      if (PRESETS.includes(v as never) || /^(\w+=\d+\s*)+$/.test(v)) argv = ["density", ...v.split(/\s+/)];
      break;
    }
    default: return Response.json({ error: `unknown command ${b.cmd}` }, { status: 400 });
  }
  if (!argv) return Response.json({ error: "missing arguments" }, { status: 400 });
  const cmds = [beatcut("-p", name, ...argv)];
  if (!["render", "render-draft", "export", "export-open", "board", "frames", "reformat"].includes(b.cmd)) cmds.push(beatcut("-p", name, "board"));
  if (b.cmd === "export-open") cmds[0] = [...cmds[0]]; // CapCut must be quit first; beatcut.py handles it
  const job = startJob(`${name}: ${argv.join(" ")}`, cmds, `/video/${name}`);
  return Response.json({ job: job.id });
}
