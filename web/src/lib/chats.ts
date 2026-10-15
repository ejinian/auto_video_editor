/**
 * The chat threads the app knows about. The conversation itself lives where the Agent
 * SDK keeps it (~/.claude/projects/…, resumed by session id); this file only remembers
 * which sessions exist, their titles and the page they were opened from.
 */
import fs from "node:fs";
import path from "node:path";
import { OUT } from "./paths";

export interface ChatThread {
  id: string;             // the SDK session id
  title: string;
  context: string | null; // "project:day3_1" | "folder:day3" | null
  createdAt: number;
  updatedAt: number;
  turns: number;
  costUsd: number;
}

const FILE = path.join(OUT, ".app", "chats.json");

export function listThreads(): ChatThread[] {
  try {
    const t = JSON.parse(fs.readFileSync(FILE, "utf8")) as ChatThread[];
    return t.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

export function saveThreads(threads: ChatThread[]): void {
  fs.mkdirSync(path.dirname(FILE), { recursive: true });
  fs.writeFileSync(FILE, JSON.stringify(threads, null, 1));
}

export function upsertThread(t: Partial<ChatThread> & { id: string }): ChatThread {
  const all = listThreads();
  const i = all.findIndex((x) => x.id === t.id);
  const now = Date.now();
  const merged: ChatThread = {
    id: t.id,
    title: t.title ?? all[i]?.title ?? "New chat",
    context: t.context ?? all[i]?.context ?? null,
    createdAt: all[i]?.createdAt ?? now,
    updatedAt: now,
    turns: t.turns ?? all[i]?.turns ?? 0,
    costUsd: t.costUsd ?? all[i]?.costUsd ?? 0,
  };
  if (i >= 0) all[i] = merged; else all.push(merged);
  saveThreads(all.slice(0, 200));
  return merged;
}

export function deleteThread(id: string): void {
  saveThreads(listThreads().filter((t) => t.id !== id));
}
