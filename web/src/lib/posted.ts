/**
 * Which videos have been posted, and where: out/.app/posted.json as
 * `{ "<name>": { postedAt, platform?, url? } }`. The app never posts anything itself;
 * this is the user's own note that they did, written from the /video/<name>/post page.
 */
import fs from "node:fs";
import path from "node:path";
import { OUT } from "./paths";
import type { PostedInfo } from "./types";

export const POSTED_FILE = path.join(OUT, ".app", "posted.json");
export const PLATFORMS = ["tiktok", "instagram", "both"] as const;

export function readPosted(): Record<string, PostedInfo> {
  try {
    const j = JSON.parse(fs.readFileSync(POSTED_FILE, "utf8")) as Record<string, PostedInfo>;
    return j && typeof j === "object" ? j : {};
  } catch {
    return {};
  }
}

function writePosted(all: Record<string, PostedInfo>): void {
  fs.mkdirSync(path.dirname(POSTED_FILE), { recursive: true });
  const tmp = `${POSTED_FILE}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(all, null, 1) + "\n");
  fs.renameSync(tmp, POSTED_FILE);
}

export function posted(name: string): PostedInfo | null {
  return readPosted()[name] ?? null;
}

export function markPosted(name: string, info: { platform?: string; url?: string }): PostedInfo {
  const entry: PostedInfo = { postedAt: new Date().toISOString() };
  if (info.platform && (PLATFORMS as readonly string[]).includes(info.platform)) entry.platform = info.platform as PostedInfo["platform"];
  const url = info.url?.trim();
  if (url && /^https?:\/\//.test(url)) entry.url = url;
  const all = readPosted();
  all[name] = entry;
  writePosted(all);
  return entry;
}

export function unmarkPosted(name: string): boolean {
  const all = readPosted();
  if (!(name in all)) return false;
  delete all[name];
  writePosted(all);
  return true;
}
