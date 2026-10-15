import path from "node:path";

/** The beatcut folder: `BEATCUT_ROOT`, else the parent of `web/`. Every path the app
 *  reads or writes hangs off it, exactly like beatcut.py's own ROOT. */
export const ROOT = process.env.BEATCUT_ROOT
  ? path.resolve(process.env.BEATCUT_ROOT)
  : path.resolve(process.cwd(), "..");

export const CLIPS = path.join(ROOT, "clips");
export const SOUND = path.join(ROOT, "sound");
export const OUT = path.join(ROOT, "out");
export const FINAL = path.join(ROOT, "final");
export const PROJECTS = path.join(ROOT, "projects");
export const BEATCUT_PY = path.join(ROOT, "beatcut.py");

export const VIDEO_EXT = new Set([".mp4", ".mov", ".m4v"]);
export const PRESETS = ["tight", "loose", "chill"] as const;
export type Preset = (typeof PRESETS)[number];

/** A path under ROOT, as beatcut.py prints it (`clips/day3/x.MOV`). */
export function rel(p: string): string {
  const r = path.relative(ROOT, p);
  return r.startsWith("..") ? p : r;
}

/** Resolve a user-supplied relative path and refuse anything that escapes `base`. */
export function safeJoin(base: string, ...parts: string[]): string | null {
  const p = path.resolve(base, ...parts);
  return p === base || p.startsWith(base + path.sep) ? p : null;
}
