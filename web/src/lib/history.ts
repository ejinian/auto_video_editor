/**
 * The earlier turns of a chat thread, read back from where the Agent SDK keeps the
 * conversation (`getSessionMessages` over the JSONL transcript under ~/.claude/projects)
 * and folded into the same turn/part shape the panel builds while streaming.
 */
import { getSessionMessages, type SessionMessage } from "@anthropic-ai/claude-agent-sdk";
import { ROOT } from "./paths";

export type HistoryPart =
  | { kind: "text"; text: string }
  | { kind: "tool"; id: string; name: string; input: unknown; result?: string; isError?: boolean; done: true };

export interface HistoryTurn {
  role: "user" | "assistant";
  parts: HistoryPart[];
}

const RESULT_MAX = 4000;

interface Block {
  type: string;
  text?: string;
  id?: string;
  name?: string;
  input?: unknown;
  tool_use_id?: string;
  content?: string | Block[];
  is_error?: boolean;
}

function blocks(message: unknown): Block[] | string | null {
  const m = message as { content?: unknown } | null;
  if (!m || m.content == null) return null;
  if (typeof m.content === "string") return m.content;
  return Array.isArray(m.content) ? (m.content as Block[]) : null;
}

/** Text the SDK/harness injected as a "user" message, never typed by the user. */
const INJECTED = ["<system-reminder>", "<command-name>", "<local-command-stdout>", "<local-command-caveat>", "<task-notification>"];
function isInjected(text: string): boolean {
  const t = text.trimStart();
  return INJECTED.some((tag) => t.startsWith(tag));
}

function resultText(content: string | Block[] | undefined): string {
  const text = typeof content === "string"
    ? content
    : (content ?? []).map((c) => (c.type === "text" ? c.text ?? "" : `[${c.type}]`)).join("\n");
  return text.slice(0, RESULT_MAX);
}

/** Fold raw session messages into user / assistant turns. Subagent frames and system
 *  frames are skipped; tool results are attached to the tool_use they answer. */
export function foldMessages(messages: SessionMessage[]): HistoryTurn[] {
  const turns: HistoryTurn[] = [];
  const tools = new Map<string, Extract<HistoryPart, { kind: "tool" }>>();
  let assistant: HistoryTurn | null = null;

  const pushAssistant = (part: HistoryPart) => {
    if (!assistant) {
      assistant = { role: "assistant", parts: [] };
      turns.push(assistant);
    }
    const last = assistant.parts[assistant.parts.length - 1];
    if (part.kind === "text" && last?.kind === "text") last.text += part.text;
    else assistant.parts.push(part);
  };

  for (const m of messages) {
    if (m.parent_tool_use_id) continue;
    if ((m as { isMeta?: boolean }).isMeta) continue;
    const content = blocks(m.message);
    if (content == null) continue;

    if (m.type === "assistant") {
      if (typeof content === "string") {
        if (content.trim()) pushAssistant({ kind: "text", text: content });
        continue;
      }
      for (const b of content) {
        if (b.type === "text" && b.text) pushAssistant({ kind: "text", text: b.text });
        else if (b.type === "tool_use" && b.id) {
          const part: Extract<HistoryPart, { kind: "tool" }> = { kind: "tool", id: b.id, name: b.name ?? "tool", input: b.input, done: true };
          tools.set(b.id, part);
          pushAssistant(part);
        }
      }
      continue;
    }

    if (m.type !== "user") continue;
    const texts: string[] = [];
    if (typeof content === "string") {
      if (!isInjected(content)) texts.push(content);
    } else {
      for (const b of content) {
        if (b.type === "text" && b.text && !isInjected(b.text)) texts.push(b.text);
        else if (b.type === "tool_result" && b.tool_use_id) {
          const t = tools.get(b.tool_use_id);
          if (t) {
            t.result = resultText(b.content);
            t.isError = !!b.is_error;
          }
        }
      }
    }
    const text = texts.join("\n").trim();
    if (text) {
      turns.push({ role: "user", parts: [{ kind: "text", text }] });
      assistant = null;
    }
  }
  return turns.filter((t) => t.parts.length > 0);
}

/** The thread's earlier turns, or [] when the SDK has no transcript for that id. */
export async function threadHistory(sessionId: string): Promise<HistoryTurn[]> {
  // web-app chats run with cwd = ROOT, so their transcripts sit in ROOT's project dir;
  // fall back to every project dir for a session started elsewhere.
  let messages = await getSessionMessages(sessionId, { dir: ROOT });
  if (messages.length === 0) messages = await getSessionMessages(sessionId);
  return foldMessages(messages);
}
