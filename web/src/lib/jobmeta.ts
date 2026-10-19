/**
 * What a job is about, read from its command list. Pure functions with no node
 * imports, so the feed's client components can use them on a job fetched from
 * /api/jobs as well as jobs.ts on the server.
 */

/** `["uv","run",".../beatcut.py","-p","day3_1","render"]` → `["-p","day3_1","render"]`. */
function args(cmd: string[]): string[] {
  return cmd[0] === "uv" ? cmd.slice(3) : cmd;
}

/** The project a command works on (`-p <name>`), or null for a bare `sound <link>`. */
export function cmdProject(cmd: string[]): string | null {
  const a = args(cmd);
  return a[0] === "-p" && a[1] ? a[1] : null;
}

/** The beatcut subcommand of one command: `sound`, `plan`, `caption`, `board`, `render`, … */
export function cmdStep(cmd: string[]): string {
  const a = args(cmd);
  return (a[0] === "-p" ? a[2] : a[0]) ?? "?";
}

/** The first project any of the job's commands names. */
export function jobProject(cmds: string[][]): string | null {
  for (const c of cmds) {
    const p = cmdProject(c);
    if (p) return p;
  }
  return null;
}

/** The step names in order (`sound → plan → board → render`). */
export function jobSteps(cmds: string[][]): string[] {
  return cmds.map(cmdStep);
}

/** Which command is running: the log gets a `$ …` line as each one starts. */
export function jobStepIndex(log: string): number {
  const n = (log.match(/^\$ /gm) ?? []).length;
  return Math.max(0, n - 1);
}

/** The chip's word for a running job: rendering when the current step is `render`, else cutting. */
export function jobVerb(steps: string[], step: number): "cutting…" | "rendering…" {
  return steps[step] === "render" ? "rendering…" : "cutting…";
}
