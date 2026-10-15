/**
 * The chat: the Claude Agent SDK running the same agent as Claude Code inside the
 * beatcut folder, so it gets CLAUDE.md, the beatcut / day / ig-* skills and Bash.
 * Each turn is one `query()`; the conversation continues through `resume`.
 */
import { query, type Options, type SDKMessage, type Query } from "@anthropic-ai/claude-agent-sdk";
import { ROOT } from "./paths";
import { upsertThread } from "./chats";

export type ChatEvent =
  | { t: "init"; sessionId: string; model: string; skills: string[] }
  | { t: "text"; delta: string }
  | { t: "tool_use"; id: string; name: string; input: unknown }
  | { t: "tool_result"; id: string; text: string; isError: boolean }
  | { t: "status"; text: string }
  | { t: "done"; sessionId: string; costUsd: number; turns: number; durationMs: number; isError: boolean; errors?: string[]; result?: string }
  | { t: "error"; message: string };

export const DEFAULT_MODEL = process.env.BEATCUT_MODEL || "claude-opus-5-5";

/** Queries in flight, by session id, so a later request can interrupt them. */
const g = globalThis as unknown as { __beatcutQueries?: Map<string, { q: Query; ac: AbortController }> };
const active = g.__beatcutQueries ?? (g.__beatcutQueries = new Map());

export function interrupt(sessionId: string): boolean {
  const a = active.get(sessionId);
  if (!a) return false;
  a.ac.abort();
  a.q.interrupt().catch(() => undefined);
  return true;
}

export function isRunning(sessionId: string): boolean {
  return active.has(sessionId);
}

function appendPrompt(context: string | null): string {
  const ctx = context?.startsWith("project:")
    ? `The user has the video "${context.slice(8)}" open in the app (project ${context.slice(8)}: use \`-p ${context.slice(8)}\` for every beatcut command about it). "Clip 7" means the source clip numbered 7 in that project's clip list.`
    : context?.startsWith("folder:")
      ? `The user has the shoot folder "clips/${context.slice(7)}" open in the app. A new video from it is named "${context.slice(7)}_<N>" (next free N) and uses \`plan --clips-dir clips/${context.slice(7)}\`.`
      : "The user is on the app's home page.";
  return [
    "## You are running inside the beatcut web app",
    `The app is a Next.js UI over this folder (${ROOT}); the user talks to you in a side panel next to the pages. Everything you do here runs for real: run \`uv run beatcut.py …\` from the folder root for every edit (never hand-edit projects/*.json), exactly as CLAUDE.md and the beatcut skill say. Follow the beatcut skill's procedure (frames → plan → board → render → verify) and the /day skill for a whole shoot day. The ig-* skills write captions and plans.`,
    ctx,
    "The app re-reads the folder after every command you run, so the page next to the chat updates by itself: do not describe the UI, just do the work and say what changed, with the full path of any finished mp4 (~/Desktop/beatcut/final/<name>.mp4). To check a result, Read the storyboard jpg (out/<folder>/_<name>_board.jpg) and frame sheets like the skill says; the user sees the same images in the app.",
    "Keep answers short: what you did, what you noticed, what you suggest. Markdown is rendered. Never post anything anywhere; nothing leaves this Mac without the user doing it.",
  ].join("\n\n");
}

export interface RunOptions {
  prompt: string;
  sessionId?: string | null;
  context?: string | null;
  signal?: AbortSignal;
}

/** Run one chat turn, yielding UI events. The session id is known from the first event. */
export async function* runTurn(opts: RunOptions): AsyncGenerator<ChatEvent> {
  const ac = new AbortController();
  opts.signal?.addEventListener("abort", () => ac.abort());
  const options: Options = {
    cwd: ROOT,
    model: DEFAULT_MODEL,
    systemPrompt: { type: "preset", preset: "claude_code", append: appendPrompt(opts.context ?? null) },
    // all setting sources (user + project + local): CLAUDE.md, .claude/skills and the ig-* skills in ~/.claude
    permissionMode: "bypassPermissions",
    allowDangerouslySkipPermissions: true,
    includePartialMessages: true,
    abortController: ac,
    env: { ...process.env, CLAUDE_AGENT_SDK_CLIENT_APP: "beatcut-web/0.1.0" } as Record<string, string>,
    ...(opts.sessionId ? { resume: opts.sessionId } : {}),
  };
  let sessionId = opts.sessionId ?? null;
  let q: Query;
  try {
    q = query({ prompt: opts.prompt, options });
  } catch (e) {
    yield { t: "error", message: String(e) };
    return;
  }
  let registered = false;
  const toolNames = new Map<string, string>();
  try {
    for await (const m of q as AsyncIterable<SDKMessage>) {
      if (!sessionId && "session_id" in m && m.session_id) sessionId = m.session_id;
      if (sessionId && !registered) {
        active.set(sessionId, { q, ac });
        registered = true;
      }
      // Subagent traffic (parent_tool_use_id set) stays inside the Agent tool's result.
      if ("parent_tool_use_id" in m && m.parent_tool_use_id) continue;
      switch (m.type) {
        case "system":
          if (m.subtype === "init") {
            yield { t: "init", sessionId: m.session_id, model: m.model, skills: m.skills ?? [] };
            upsertThread({ id: m.session_id, context: opts.context ?? null, title: opts.sessionId ? undefined : opts.prompt.slice(0, 60) });
          }
          break;
        case "stream_event": {
          const ev = m.event;
          if (ev.type === "content_block_delta" && ev.delta.type === "text_delta") yield { t: "text", delta: ev.delta.text };
          break;
        }
        case "assistant":
          for (const b of m.message.content) {
            if (b.type === "tool_use") {
              toolNames.set(b.id, b.name);
              yield { t: "tool_use", id: b.id, name: b.name, input: b.input };
            }
          }
          break;
        case "user": {
          const content = m.message.content;
          if (Array.isArray(content)) {
            for (const b of content) {
              if (b.type === "tool_result") {
                const text = typeof b.content === "string"
                  ? b.content
                  : (b.content ?? []).map((c) => (c.type === "text" ? c.text : `[${c.type}]`)).join("\n");
                yield { t: "tool_result", id: b.tool_use_id, text: text.slice(0, 4000), isError: !!b.is_error };
              }
            }
          }
          break;
        }
        case "tool_use_summary":
          yield { t: "status", text: m.summary };
          break;
        case "result": {
          const sid = m.session_id;
          const ok = m.subtype === "success";
          upsertThread({ id: sid, turns: m.num_turns, costUsd: m.total_cost_usd });
          yield {
            t: "done", sessionId: sid, costUsd: m.total_cost_usd, turns: m.num_turns, durationMs: m.duration_ms,
            isError: !ok || ("is_error" in m && m.is_error),
            errors: ok ? undefined : m.errors,
            result: ok ? m.result : undefined,
          };
          break;
        }
        default:
          break;
      }
    }
  } catch (e) {
    if (ac.signal.aborted) yield { t: "status", text: "stopped." };
    else yield { t: "error", message: e instanceof Error ? e.message : String(e) };
  } finally {
    if (sessionId) active.delete(sessionId);
  }
}
