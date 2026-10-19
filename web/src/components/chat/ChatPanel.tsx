"use client";

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Loader2, MessageSquare, Plus, Send, Square, Trash2, X } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { ASK_DONE_EVENT, ASK_EVENT, type AskDetail, type AskDoneDetail } from "@/components/chat/ask";
import type { ChatEvent } from "@/lib/agent";
import type { ChatThread } from "@/lib/chats";
import type { HistoryTurn } from "@/lib/history";

type Part =
  | { kind: "text"; text: string }
  | { kind: "tool"; id: string; name: string; input: unknown; result?: string; isError?: boolean; done: boolean }
  | { kind: "status"; text: string };

interface Turn {
  role: "user" | "assistant";
  parts: Part[];
  /** Which button on which page sent this turn ("Fix it · day3_1"); typed turns have none. */
  from?: string;
  meta?: { costUsd: number; turns: number; durationMs: number; isError: boolean; errors?: string[] };
}

/** Options for one send: an explicit thread (null = new) and, for an ask from a page
 *  button, where it came from and the id to answer through `beatcut:chat:done`. */
interface SendOpts { sid?: string | null; from?: string; askId?: string; context?: string | null }

const OPEN_KEY = "beatcut.chat.open";
const THREAD_KEY = "beatcut.chat.thread";

function contextFor(pathname: string): { ctx: string | null; label: string } {
  const v = pathname.match(/^\/video\/([^/]+)/);
  if (v) return { ctx: `project:${decodeURIComponent(v[1])}`, label: decodeURIComponent(v[1]) };
  const s = pathname.match(/^\/shoot\/([^/]+)/);
  if (s) return { ctx: `folder:${decodeURIComponent(s[1])}`, label: `clips/${decodeURIComponent(s[1])}` };
  return { ctx: null, label: "beatcut" };
}

function suggestions(ctx: string | null): string[] {
  if (ctx?.startsWith("project:")) {
    return [
      "Look at the storyboard and tell me what you'd change",
      "Make it 20 seconds",
      "Hold the drop shot longer",
      "Write the caption for this post",
      "Make a second variation with a different sound",
    ];
  }
  if (ctx?.startsWith("folder:")) {
    return [
      "Look at the footage and suggest a story order and an opener",
      "Cut two variations of this day with a trending sound",
      "Make frame sheets for every clip",
    ];
  }
  return ["/day plan", "What's the state of things? What should we do next?", "Find this week's trending sounds for a vibe-coding bit"];
}

export function ChatPanel() {
  const pathname = usePathname();
  const router = useRouter();
  const { ctx, label } = useMemo(() => contextFor(pathname), [pathname]);
  const [open, setOpen] = useState(false);
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showThreads, setShowThreads] = useState(false);
  const [model, setModel] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const historyFor = useRef<string | null>(null);

  /** Replace the turns with everything said so far in thread `id` (read back from the
   *  SDK's transcript). A later pick cancels the display of an earlier fetch. */
  const loadHistory = useCallback((id: string) => {
    historyFor.current = id;
    setTurns([{ role: "assistant", parts: [{ kind: "status", text: "loading earlier messages…" }] }]);
    fetch(`/api/chat/threads/${id}/messages`)
      .then(async (r) => {
        const j = (await r.json()) as HistoryTurn[] | { error?: string };
        if (!r.ok || !Array.isArray(j)) throw new Error((j as { error?: string }).error ?? `history failed (${r.status})`);
        return j;
      })
      .then((history) => {
        if (historyFor.current !== id) return;
        setTurns(history.length ? history : [{ role: "assistant", parts: [{ kind: "status", text: "nothing said in this chat yet." }] }]);
      })
      .catch((e: unknown) => {
        if (historyFor.current !== id) return;
        setTurns([{ role: "assistant", parts: [{ kind: "status", text: `couldn't load earlier messages: ${e instanceof Error ? e.message : String(e)}` }] }]);
      });
  }, []);

  // remembered open state and thread: read after mount so the server and client
  // render the same closed panel first (no hydration mismatch). They are written back
  // where they change (openPanel / switchThread), not in an effect: an effect would store
  // the initial closed state first and, under React's strict-mode double run, read
  // that back and lose what was remembered.
  useEffect(() => {
    try {
      const wasOpen = localStorage.getItem(OPEN_KEY) === "1";
      const t = localStorage.getItem(THREAD_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage is only readable on the client
      setOpen(wasOpen);
      if (t) { setSessionId(t); loadHistory(t); }
    } catch { /* private window */ }
  }, [loadHistory]);
  useEffect(() => { document.documentElement.classList.toggle("chat-open", open); }, [open]);

  // a button on the page asks Claude something (askClaude() in chat/ask.ts): the panel
  // opens, optionally on a new thread, and either puts the question in the box (nothing
  // is sent until the user presses Enter) or sends it at once and answers the ask with a
  // `beatcut:chat:done` event when the turn is over
  const wantFocus = useRef(false);
  const sendRef = useRef<(text?: string, opts?: SendOpts) => Promise<void>>(async () => undefined);
  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent<Partial<AskDetail>>).detail;
      if (typeof d?.prompt !== "string" || typeof d.id !== "string") return;
      setOpen(true);
      try { localStorage.setItem(OPEN_KEY, "1"); } catch { /* none */ }
      if (d.newThread) {
        historyFor.current = null;
        setSessionId(null);
        try { localStorage.removeItem(THREAD_KEY); } catch { /* none */ }
        setTurns([]);
        setError(null);
        setShowThreads(false);
      }
      if (d.send) {
        void sendRef.current(d.prompt, { sid: d.newThread ? null : undefined, from: d.from, askId: d.id, context: d.context });
      } else {
        setInput(d.prompt);
        wantFocus.current = true;
        setTimeout(() => taRef.current?.focus(), 0);
      }
    };
    window.addEventListener(ASK_EVENT, h);
    return () => window.removeEventListener(ASK_EVENT, h);
  }, []);
  useEffect(() => {
    if (open && wantFocus.current) { wantFocus.current = false; taRef.current?.focus(); }
  }, [open]);
  const openPanel = (v: boolean) => {
    setOpen(v);
    try { localStorage.setItem(OPEN_KEY, v ? "1" : "0"); } catch { /* none */ }
  };
  const switchThread = (id: string | null) => {
    setSessionId(id);
    try { if (id) localStorage.setItem(THREAD_KEY, id); else localStorage.removeItem(THREAD_KEY); } catch { /* none */ }
  };

  const loadThreads = useCallback(() => {
    fetch("/api/chat/threads").then((r) => r.json()).then((j: ChatThread[]) => setThreads(j)).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!open) return;
    let live = true;
    fetch("/api/chat/threads").then((r) => r.json()).then((j: ChatThread[]) => { if (live) setThreads(j); }).catch(() => undefined);
    return () => { live = false; };
  }, [open]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, running]);

  const newThread = () => {
    historyFor.current = null;
    switchThread(null);
    setTurns([]);
    setError(null);
    setShowThreads(false);
    taRef.current?.focus();
  };

  const pickThread = (t: ChatThread) => {
    if (running) return;
    switchThread(t.id);
    setError(null);
    loadHistory(t.id);
    setShowThreads(false);
  };

  const removeThread = async (id: string) => {
    await fetch(`/api/chat/threads/${id}`, { method: "DELETE" });
    if (id === sessionId) newThread();
    loadThreads();
  };

  const send = async (text?: string, opts?: SendOpts) => {
    const message = (text ?? input).trim();
    const answer = (r: Omit<AskDoneDetail, "id">) => {
      if (opts?.askId) window.dispatchEvent(new CustomEvent<AskDoneDetail>(ASK_DONE_EVENT, { detail: { id: opts.askId, ...r } }));
    };
    if (!message) return;
    if (running) { answer({ text: "", isError: true, error: "Claude is still working on the last ask — stop it first", sessionId }); return; }
    setInput("");
    setError(null);
    setRunning(true);
    setTurns((t) => [...t, { role: "user", parts: [{ kind: "text", text: message }], from: opts?.from }, { role: "assistant", parts: [] }]);
    const ac = new AbortController();
    abortRef.current = ac;
    let sid = opts?.sid !== undefined ? opts.sid : sessionId;
    let finalText = "";
    let doneEv: Extract<ChatEvent, { t: "done" }> | null = null;
    let failure: string | null = null;
    const patch = (fn: (parts: Part[]) => Part[], meta?: Turn["meta"]) =>
      setTurns((t) => {
        const last = t[t.length - 1];
        if (!last || last.role !== "assistant") return t;
        return [...t.slice(0, -1), { ...last, parts: fn(last.parts), meta: meta ?? last.meta }];
      });
    try {
      const r = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, sessionId: sid, context: opts?.context !== undefined ? opts.context : ctx }), signal: ac.signal,
      });
      if (!r.ok || !r.body) {
        const j = (await r.json().catch(() => ({}))) as { error?: string };
        throw new Error(j.error ?? `chat failed (${r.status})`);
      }
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      let touched = false;
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl: number;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl); buf = buf.slice(nl + 1);
          if (!line.trim()) continue;
          const ev = JSON.parse(line) as ChatEvent;
          switch (ev.t) {
            case "init":
              if (!sid) { sid = ev.sessionId; switchThread(ev.sessionId); }
              setModel(ev.model);
              break;
            case "text":
              finalText += ev.delta;
              patch((p) => {
                const last = p[p.length - 1];
                if (last?.kind === "text") return [...p.slice(0, -1), { kind: "text", text: last.text + ev.delta }];
                return [...p, { kind: "text", text: ev.delta }];
              });
              break;
            case "tool_use":
              patch((p) => [...p, { kind: "tool", id: ev.id, name: ev.name, input: ev.input, done: false }]);
              break;
            case "tool_result":
              touched = true;
              patch((p) => p.map((x) => (x.kind === "tool" && x.id === ev.id ? { ...x, result: ev.text, isError: ev.isError, done: true } : x)));
              router.refresh();
              break;
            case "status":
              patch((p) => [...p, { kind: "status", text: ev.text }]);
              break;
            case "done":
              doneEv = ev;
              patch((p) => p, { costUsd: ev.costUsd, turns: ev.turns, durationMs: ev.durationMs, isError: ev.isError, errors: ev.errors });
              if (ev.isError && ev.errors?.length) { failure = ev.errors.join("\n"); setError(failure); }
              break;
            case "error":
              failure = ev.message;
              setError(ev.message);
              break;
          }
        }
      }
      if (touched) router.refresh();
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") failure = "stopped";
      else { failure = e instanceof Error ? e.message : String(e); setError(failure); }
    } finally {
      setRunning(false);
      abortRef.current = null;
      loadThreads();
      const done: Extract<ChatEvent, { t: "done" }> | null = doneEv;
      const ok = !!done && !done.isError && !failure;
      answer({ text: ok ? (done.result ?? finalText) : finalText, isError: !ok, error: ok ? undefined : (failure ?? "the turn ended without a result"), sessionId: sid });
    }
  };
  useEffect(() => { sendRef.current = send; });

  const stop = async () => {
    if (sessionId) await fetch("/api/chat/interrupt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sessionId }) });
    abortRef.current?.abort();
  };

  const current = threads.find((t) => t.id === sessionId);

  if (!open) {
    return (
      <button className="btn fixed bottom-5 right-5 z-40 shadow-lg" onClick={() => openPanel(true)} title="Talk to Claude about this page">
        <MessageSquare size={16} /> Claude
      </button>
    );
  }

  return (
    <aside className="fixed top-0 right-0 bottom-0 z-40 w-[440px] max-w-full flex flex-col bg-card border-l border-line shadow-2xl">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-line">
        <div className="relative min-w-0 flex-1">
          <button className="flex items-center gap-1.5 max-w-full text-left" onClick={() => setShowThreads((s) => !s)} title="Switch chat">
            <span className="font-semibold truncate">{current?.title ?? (sessionId ? "Chat" : "New chat")}</span>
            <ChevronDown size={14} className="text-muted shrink-0" />
          </button>
          <div className="text-[11.5px] text-muted truncate">on {label}{model ? ` · ${model}` : ""}{current ? ` · $${current.costUsd.toFixed(2)}` : ""}</div>
          {showThreads && (
            <div className="absolute left-0 top-full mt-1 w-[380px] max-h-[50vh] overflow-auto bg-bg-2 border border-line rounded-lg shadow-xl z-10">
              <button className="w-full text-left px-3 py-2 hover:bg-card-2 flex items-center gap-2 border-b border-line" onClick={newThread}><Plus size={14} /> New chat</button>
              {threads.length === 0 && <div className="px-3 py-2 text-muted text-sm">no chats yet</div>}
              {threads.map((t) => (
                <div key={t.id} className={`flex items-center gap-2 px-3 py-1.5 hover:bg-card-2 ${t.id === sessionId ? "bg-card-2" : ""}`}>
                  <button className="flex-1 min-w-0 text-left" onClick={() => pickThread(t)}>
                    <div className="truncate text-sm">{t.title}</div>
                    <div className="text-[11px] text-muted truncate">{t.context?.replace(/^(project|folder):/, "") ?? "home"} · {t.turns} turns · ${t.costUsd.toFixed(2)}</div>
                  </button>
                  <button className="text-muted hover:text-bad" onClick={() => removeThread(t.id)} title="Forget this chat"><Trash2 size={14} /></button>
                </div>
              ))}
            </div>
          )}
        </div>
        <button className="btn sec sm" onClick={newThread} title="New chat"><Plus size={14} /></button>
        <button className="btn sec sm" onClick={() => openPanel(false)} title="Hide"><X size={14} /></button>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-auto px-3 py-3 space-y-3">
        {turns.length === 0 && (
          <div className="text-sm text-muted space-y-2">
            <p>Claude runs the beatcut tool for real from here: it reads the clips, cuts, renders, writes captions and plans the next shoot. Everything it changes shows up on the page next to this panel.</p>
            <div className="flex flex-col gap-1.5 pt-1">
              {suggestions(ctx).map((s) => (
                <button key={s} className="text-left text-fg bg-bg-2 border border-line rounded-lg px-3 py-2 hover:border-acc" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, i) => <TurnView key={i} turn={turn} running={running && i === turns.length - 1} />)}
        {error && <div className="text-bad text-sm whitespace-pre-wrap border border-bad/40 rounded-lg px-3 py-2">{error}</div>}
      </div>

      <footer className="border-t border-line p-2">
        <div className="flex items-end gap-2">
          <textarea
            ref={taRef}
            className="textarea !min-h-[42px] max-h-40"
            rows={1}
            placeholder={ctx?.startsWith("project:") ? `Tell Claude what to change in ${label}…` : "Ask Claude…"}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          />
          {running
            ? <button className="btn warn" onClick={stop} title="Stop"><Square size={14} /></button>
            : <button className="btn" onClick={() => send()} disabled={!input.trim()} title="Send (Enter)"><Send size={14} /></button>}
        </div>
      </footer>
    </aside>
  );
}

function TurnView({ turn, running }: { turn: Turn; running: boolean }) {
  if (turn.role === "user") {
    const text = turn.parts.map((p) => (p.kind === "text" ? p.text : "")).join("");
    return (
      <div className="ml-8">
        {turn.from && <div className="text-[11px] text-muted text-right mb-0.5 truncate" title="sent by a button on the page">from {turn.from}</div>}
        <div className="bg-acc/15 border border-acc/30 rounded-xl px-3 py-2 text-sm whitespace-pre-wrap">{text}</div>
      </div>
    );
  }
  return (
    <div className="text-sm space-y-2">
      {turn.parts.map((p, i) => {
        if (p.kind === "text") return <Markdown key={i} text={p.text} />;
        if (p.kind === "status") return <div key={i} className="text-muted text-[12.5px] italic">{p.text}</div>;
        return <ToolView key={p.id} part={p} />;
      })}
      {running && <div className="flex items-center gap-2 text-muted text-[12.5px]"><Loader2 size={13} className="animate-spin" /> working…</div>}
      {turn.meta && !running && (
        <div className="text-[11px] text-muted">
          {turn.meta.isError ? "stopped with an error · " : ""}{turn.meta.turns} steps · {(turn.meta.durationMs / 1000).toFixed(0)} s · ${turn.meta.costUsd.toFixed(3)}
        </div>
      )}
    </div>
  );
}

function summarizeInput(name: string, input: unknown): string {
  const i = (input ?? {}) as Record<string, unknown>;
  switch (name) {
    case "Bash": return String(i.command ?? "").replace(/^uv run beatcut\.py /, "beatcut ");
    case "Read": return String(i.file_path ?? "");
    case "Write": case "Edit": case "MultiEdit": return String(i.file_path ?? "");
    case "Glob": case "Grep": return String(i.pattern ?? "");
    case "Skill": return `/${String(i.skill ?? "")} ${String(i.args ?? "")}`.trim();
    case "WebSearch": return String(i.query ?? "");
    case "WebFetch": return String(i.url ?? "");
    case "Agent": case "Task": return String(i.description ?? "");
    default: {
      const s = JSON.stringify(input);
      return s.length > 120 ? s.slice(0, 117) + "…" : s;
    }
  }
}

function ToolView({ part }: { part: Extract<Part, { kind: "tool" }> }) {
  const [openIt, setOpenIt] = useState(false);
  const summary = summarizeInput(part.name, part.input);
  return (
    <div className={`border rounded-lg text-[12.5px] ${part.isError ? "border-bad/50" : "border-line"} bg-bg-2`}>
      <button className="w-full text-left px-2.5 py-1.5 flex items-center gap-2" onClick={() => setOpenIt((o) => !o)}>
        {part.done ? <span className={`w-1.5 h-1.5 rounded-full ${part.isError ? "bg-bad" : "bg-acc"}`} /> : <Loader2 size={12} className="animate-spin text-muted" />}
        <span className="font-semibold text-muted">{part.name}</span>
        <span className="truncate font-mono text-fg/90">{summary}</span>
      </button>
      {openIt && (
        <div className="border-t border-line px-2.5 py-2 space-y-1.5">
          <pre className="whitespace-pre-wrap break-words font-mono text-[12px] text-muted max-h-40 overflow-auto">{JSON.stringify(part.input, null, 1)}</pre>
          {part.result !== undefined && <pre className="whitespace-pre-wrap break-words font-mono text-[12px] max-h-60 overflow-auto">{part.result}</pre>}
        </div>
      )}
    </div>
  );
}
