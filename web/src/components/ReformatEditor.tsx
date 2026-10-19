"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { askClaude } from "@/components/chat/ask";
import { useJob } from "@/components/useJob";
import { mb, mediaUrl } from "@/lib/format";
import type { ProjectDetail } from "@/lib/types";

const KIND_LABEL: Record<string, string> = { hook: "Hook line", narrated: "Narrated", reply: "Comment reply" };
const KIND_HINT: Record<string, string> = {
  hook: "the same video with a new line on screen — the cheapest second run a reel can get",
  narrated: "two or three lines said over the footage in the TikTok voice, each shown as it is said; the original audio is ducked under it",
  reply: "the video as the answer to a comment, with the comment bubble on top — paste a real comment from your post",
};

/** The copy of a reformat: the one thing that makes it a different post. Save & render
 *  runs `reformat … --render` through the job runner; the panel can write the copy for
 *  all three reformats of the video at once (also fired by `?ask=reformat` right after
 *  the reformats are made). */
export function ReformatEditor({ d }: { d: ProjectDetail }) {
  const { run, busy, error } = useJob();
  const pr = d.project;
  const kind = pr.reformat ?? "hook";
  const [hook, setHook] = useState(pr.hook ?? "");
  const [lines, setLines] = useState((pr.lines ?? []).join("\n"));
  const [voice, setVoice] = useState(pr.voice ?? "Samantha");
  const [comment, setComment] = useState(pr.comment?.text ?? "");
  const [user, setUser] = useState(pr.comment?.user ?? "");
  const [asking, setAsking] = useState<"idle" | "running" | "done" | "error">("idle");
  const params = useSearchParams();
  const fired = useRef(false);

  const siblings = d.reformats.length ? d.reformats : [];
  const src = pr.source ?? "";
  const stem = src.split("/").pop()?.replace(/\.[^.]+$/, "") ?? "";
  const folder = d.folder ?? "";
  const prompt =
    `${siblings.map((p) => `${p.name} (${p.reformat})`).join(", ")} are reformats of the posted video ${src} (${d.realLength.toFixed(0)} s): the same cut, three framings. ` +
    `Read its frame sheet out/${folder}/_frames_${stem}.jpg (and listen to nothing — judge from the frames and the sound's title). Then write, in the Young Vibas voice: ` +
    `a hook line for the hook reformat (\`reformat -p <name> --hook "…"\`); 2-3 narration lines for the narrated one in the TikTok voice-over style, the first a reaction to what is on screen (\`reformat -p <name> --lines "first|second|third"\`); ` +
    `and for the reply one the comment it answers — the user's own comment if one is already set on it, otherwise the question a viewer would ask, with no username (\`reformat -p <name> --comment "…"\`). ` +
    `Run /ig-human on the lines first. Add --render to each reformat command so it renders, then write each one's post caption with /ig-caption into its caption file. End with \`REFORMATS: ${siblings.map((p) => p.name).join(" ")}\`.`;

  const writeWithClaude = async () => {
    if (asking === "running") return;
    setAsking("running");
    const r = await askClaude({ prompt, send: true, newThread: true, from: `Reformats · ${folder}`, context: `project:${d.name}` });
    if (!r) return;
    setAsking(r.isError ? "error" : "done");
  };

  // right after `reformat --video …` the job lands here with ?ask=reformat: Claude writes the copy
  useEffect(() => {
    if (params.get("ask") === "reformat" && !fired.current && !pr.hook && !(pr.lines ?? []).length && !pr.comment) {
      fired.current = true;
      window.history.replaceState(null, "", window.location.pathname);
      void writeWithClaude();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire once on arrival
  }, []);

  const save = () => {
    const args: Record<string, string> = { render: "1", voice };
    if (kind === "hook") args.hook = hook.trim();
    if (kind === "narrated") args.lines = lines.split("\n").map((l) => l.trim()).filter(Boolean).join("|");
    if (kind === "reply") { args.comment = comment.trim(); args.user = user.replace(/^@/, "").trim(); }
    run(`/api/projects/${encodeURIComponent(d.name)}/run`, { cmd: "reformat", args });
  };

  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: "minmax(240px, 300px) 1fr" }}>
      <div>
        {d.mp4 ? (
          <video controls playsInline src={mediaUrl(d.mp4)} className="w-full rounded-xl bg-black" style={{ maxHeight: "62vh" }} />
        ) : (
          <div className="card text-muted aspect-[9/16] max-h-[50vh] flex items-center justify-center text-center text-sm">not rendered yet — write the copy on the right and press Save &amp; render</div>
        )}
        {d.mp4 && (
          <div className="text-xs text-muted mt-2 space-y-0.5">
            <div><code>~/Desktop/beatcut/{d.inFinal ? `final/${d.name}.mp4` : d.mp4}</code> · {mb(d.mp4Size)}</div>
            <div><a href={mediaUrl(d.inFinal ? `final/${d.name}.mp4` : d.mp4, true)}>download</a></div>
          </div>
        )}
      </div>
      <div className="card space-y-3 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <b className="text-base">{KIND_LABEL[kind] ?? kind} reformat</b>
          <span className="text-muted text-sm">of <code>{src.split("/").pop()}</code> · the cut is kept; only the framing changes</span>
        </div>
        <div className="text-muted text-sm">{KIND_HINT[kind]}</div>
        {kind === "hook" && (
          <div>
            <label className="label">Hook line on screen</label>
            <input className="input" value={hook} onChange={(e) => setHook(e.target.value)} placeholder="pov: your PR is due and it's leg day" />
          </div>
        )}
        {kind === "narrated" && (
          <div className="grid gap-3" style={{ gridTemplateColumns: "1fr auto" }}>
            <div>
              <label className="label">Narration, one line per row (2–3)</label>
              <textarea className="textarea min-h-[96px]" value={lines} onChange={(e) => setLines(e.target.value)} placeholder={"wait, he's shipping code between sets\nand the prompt is still running\nthis is insane"} />
            </div>
            <div>
              <label className="label">Voice</label>
              <input className="input !w-36" value={voice} onChange={(e) => setVoice(e.target.value)} title="a macOS voice (say -v '?')" />
            </div>
          </div>
        )}
        {kind === "reply" && (
          <div className="grid gap-3" style={{ gridTemplateColumns: "1fr auto" }}>
            <div>
              <label className="label">The comment this video answers</label>
              <input className="input" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="how do you code at the gym??" />
            </div>
            <div>
              <label className="label">Who wrote it <span className="text-muted">(only if real)</span></label>
              <input className="input !w-40" value={user} onChange={(e) => setUser(e.target.value)} placeholder="@handle" />
            </div>
          </div>
        )}
        <div className="flex items-center gap-2 flex-wrap">
          <button className="btn" disabled={busy} onClick={save}>Save &amp; render</button>
          <button className="btn sec" disabled={asking === "running"} onClick={writeWithClaude} title="a new chat: Claude reads the frames, writes the hook, the narration and the comment for all three reformats, renders them and writes their captions">
            {asking === "running" ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {asking === "running" ? "Claude is writing…" : "Write all three with Claude"}
          </button>
          {asking === "done" && <span className="text-acc text-sm">written — reload if the page has not caught up</span>}
          {asking === "error" && <span className="text-bad text-sm">Claude did not finish — see the panel</span>}
          {error && <span className="text-bad text-sm">{error}</span>}
        </div>
      </div>
    </div>
  );
}
