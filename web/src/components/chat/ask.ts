/**
 * The one way a page asks Claude something: it dispatches a `beatcut:chat` window event
 * that the ChatPanel (mounted in the layout) listens for. The panel opens, optionally
 * starts a new thread, puts the prompt in its box and, with `send`, sends it at once.
 * A sent ask resolves when that turn is done (or stopped / failed) with the final text,
 * through a `beatcut:chat:done` event the panel dispatches back. A prefill-only ask
 * resolves right away with null: nothing is sent until the user presses Enter.
 */

export interface Ask {
  /** The question, as the user would have typed it. */
  prompt: string;
  /** Send it now (true) or only put it in the box (false, the default). */
  send?: boolean;
  /** Start a new thread first (otherwise the turn joins the panel's current thread). */
  newThread?: boolean;
  /** Where the ask came from, shown on the turn in the panel ("Fix it · day3_1"). */
  from?: string;
  /** Page context for the agent (`project:<name>` / `folder:<name>`); defaults to the
   *  one the panel derives from the pathname. The /new flow has no pathname context. */
  context?: string | null;
}

export interface AskResult {
  /** The final text of the assistant's turn ("" when it was stopped or failed). */
  text: string;
  isError: boolean;
  /** Why it failed, when it did (also "stopped" after the Stop button). */
  error?: string;
  sessionId: string | null;
}

export interface AskDetail extends Ask { id: string }
export interface AskDoneDetail extends AskResult { id: string }

export const ASK_EVENT = "beatcut:chat";
export const ASK_DONE_EVENT = "beatcut:chat:done";

const pending = new Map<string, (r: AskResult) => void>();
let listening = false;

function listen() {
  if (listening || typeof window === "undefined") return;
  listening = true;
  window.addEventListener(ASK_DONE_EVENT, (e: Event) => {
    const d = (e as CustomEvent<AskDoneDetail>).detail;
    const resolve = pending.get(d.id);
    if (!resolve) return;
    pending.delete(d.id);
    resolve({ text: d.text, isError: d.isError, error: d.error, sessionId: d.sessionId });
  });
}

/** Open the panel with `prompt`; with `send: true` the promise resolves when the turn is done. */
export function askClaude(ask: Ask): Promise<AskResult | null> {
  listen();
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const p = ask.send
    ? new Promise<AskResult>((resolve) => { pending.set(id, resolve); })
    : Promise.resolve(null);
  window.dispatchEvent(new CustomEvent<AskDetail>(ASK_EVENT, { detail: { ...ask, id } }));
  return p;
}

/** The last non-empty line of a turn, e.g. the `SOUND: sound/x.mp3` answer line. */
export function lastLine(text: string): string {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  return lines[lines.length - 1] ?? "";
}
