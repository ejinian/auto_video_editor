"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { askClaude } from "@/components/chat/ask";
import { useJob } from "@/components/useJob";
import { mb, mediaUrl } from "@/lib/format";
import type { ProjectDetail } from "@/lib/types";

const KIND_LABEL: Record<string, string> = { hook: "Hook line", narrated: "Narrated", reply: "Comment reply", reaction: "Reacting avatar", goofy: "Goofy", cinematic: "Cinematic" };
const STYLE_FX: Record<string, string[]> = { goofy: ["zoom", "boom", "bruh", "nah", "whoosh"], cinematic: ["slow", "riser"] };
const KIND_HINT: Record<string, string> = {
  hook: "the same video with a new line on screen — the cheapest second run a reel can get",
  narrated: "two or three lines said over the footage in the TikTok voice, each shown as it is said; the original audio is ducked under it",
  reply: "the video as the answer to a comment, with the comment bubble on top — pick one of the post's real comments below (the bubble then says who asked), or type one",
  reaction: "your character reacts in the corner, silent: short clips of it (nod, shocked, laugh, point, think) switched at the moments that earn a reaction; the original audio stays",
  goofy: "the meme treatment: punch-zooms and a shake at the moments, a boom or a 'bruh' on the reveal, crunchy bass-boosted audio, a big caption; a meme sound from the pool can play under it",
  cinematic: "a trailer: slow motion on the key moment (a riser leads into it), letterbox bars, warm grade and grain, fades; a dramatic sound from the pool replaces the original audio",
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
  const [voice, setVoice] = useState(pr.voice ?? "eleven");
  const [comment, setComment] = useState(pr.comment?.text ?? "");
  const [user, setUser] = useState(pr.comment?.user ?? "");
  const [pick, setPick] = useState<number | null>(pr.comment?.pick ?? null);
  const comments = pr.comments ?? [];
  const [avatar, setAvatar] = useState(pr.avatar ?? "");
  const [reactions, setReactions] = useState((pr.reactions ?? []).map((r) => `${r.t}:${r.kind}`).join(", "));
  const [moments, setMoments] = useState((pr.moments ?? []).map((m) => `${m.t}:${m.fx}`).join(", "));
  const [styleSound, setStyleSound] = useState(pr.style_sound ?? "");
  const [pool, setPool] = useState<Array<{ path: string; title: string }>>([]);
  const isStyle = kind === "goofy" || kind === "cinematic";
  useEffect(() => {
    if (!isStyle) return;
    fetch("/api/sounds").then((r) => r.json()).then((j: Array<{ path: string; title: string }>) => setPool(j.map((x) => ({ path: x.path, title: x.title })))).catch(() => undefined);
  }, [isStyle]);
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
    `and for the reply one the comment it answers — if its project json has a \`comments\` list (the post's real comments, most liked first), pick the one with the best hook potential, a question or a doubt the video answers, with \`reformat -p <name> --pick N\` (N is 1-based in that list); only if the list is empty write the question a viewer would ask, with no username (\`--comment "…"\`); ` +
    `if there is a reaction one, pick 3-5 moments and what the avatar does at each from its clips (nod, shocked, laugh, point, think — \`avatar --list\` shows which exist): \`reformat -p <name> --reactions "0:nod,2.4:shocked,6:laugh"\`; ` +
    `for a goofy one pick the moments from the frames — a zoom on the funny beat, a boom (and a zoom) on the reveal, a 'bruh' or 'nah' where a reaction fits — \`reformat -p <name> --moments "1.2:zoom,3.0:boom,3.0:zoom,6:bruh" --hook "…"\` (a short all-caps-worthy line), optionally \`--sound sound/<meme>.mp3\` from the pool; ` +
    `for a cinematic one pick the key moment to slow down and a dramatic sound from the pool (sound/*.mp3; the .source.json says what each is): \`reformat -p <name> --moments "4.2:slow" --sound sound/<x>.mp3 --hook "…"\` (a quiet, serious line); ` +
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
    if (kind === "reply") {
      if (pick != null && comments[pick - 1] && comments[pick - 1].text === comment.trim()) args.pick = String(pick);
      else { args.comment = comment.trim(); args.user = user.replace(/^@/, "").trim(); }
    }
    if (kind === "reaction") { args.reactions = reactions.split(/[,\n]/).map((x) => x.trim()).filter(Boolean).join(","); if (avatar.trim()) args.avatar = avatar.trim(); }
    if (isStyle) { args.moments = moments.split(/[,\n]/).map((x) => x.trim()).filter(Boolean).join(","); args.sound = styleSound; args.hook = hook.trim(); }
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
              <input className="input !w-36" value={voice} onChange={(e) => setVoice(e.target.value)} title="eleven = your ElevenLabs voice (web/.env.local); eleven:<voice id> for another; or a macOS voice name like Samantha" />
              <div className="text-muted text-[11px] mt-1 w-36">eleven = your ElevenLabs voice; or a Mac voice name</div>
            </div>
          </div>
        )}
        {kind === "reply" && comments.length > 0 && (
          <div>
            <label className="label">The post&apos;s comments <span className="text-muted">— click the one to answer (most liked first)</span></label>
            <div className="max-h-56 overflow-auto border border-line rounded-lg divide-y divide-line">
              {comments.map((c, i) => (
                <button key={i} type="button" className={`w-full text-left px-3 py-1.5 text-sm hover:bg-card-2 flex gap-2 ${pick === i + 1 ? "bg-acc/15" : ""}`}
                  onClick={() => { setPick(i + 1); setComment(c.text); setUser(c.user); }}>
                  <span className="text-muted w-14 shrink-0 text-right">{c.likes} ♥</span>
                  <span className="text-muted shrink-0">@{c.user}</span>
                  <span className="min-w-0 truncate">{c.text}</span>
                </button>
              ))}
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
        {isStyle && (
          <div className="space-y-3">
            <div>
              <label className="label">Moments <span className="text-muted">(seconds:effect, comma separated — {STYLE_FX[kind].join(", ")}; empty = a guess)</span></label>
              <input className="input" value={moments} onChange={(e) => setMoments(e.target.value)} placeholder={kind === "goofy" ? "1.2:zoom, 3:boom, 3:zoom, 6:bruh" : "4.2:slow"} />
            </div>
            <div className="grid gap-3" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div>
                <label className="label">Caption <span className="text-muted">(optional)</span></label>
                <input className="input" value={hook} onChange={(e) => setHook(e.target.value)} placeholder={kind === "goofy" ? "the gym has wifi so it's my office now" : "we never left"} />
              </div>
              <div>
                <label className="label">Sound from the pool <span className="text-muted">({kind === "goofy" ? "under the original audio" : "instead of it"})</span></label>
                <select className="select" value={styleSound} onChange={(e) => setStyleSound(e.target.value)}>
                  <option value="">{kind === "goofy" ? "none" : "first in the pool"}</option>
                  {pool.map((p) => <option key={p.path} value={p.path}>{p.title}</option>)}
                </select>
              </div>
            </div>
          </div>
        )}
        {kind === "reaction" && (
          <div className="grid gap-3" style={{ gridTemplateColumns: "1fr auto" }}>
            <div>
              <label className="label">When the avatar does what <span className="text-muted">(seconds:reaction, comma separated; empty = spread evenly)</span></label>
              <input className="input" value={reactions} onChange={(e) => setReactions(e.target.value)} placeholder="0:nod, 2.5:shocked, 6:laugh" />
            </div>
            <div>
              <label className="label">Avatar</label>
              <input className="input !w-36" value={avatar} onChange={(e) => setAvatar(e.target.value)} placeholder="first one" title="a character under clips/_avatar/ (avatar --list)" />
            </div>
          </div>
        )}
        <div className="flex items-center gap-2 flex-wrap">
          <button className="btn" disabled={busy} onClick={save}>Save &amp; render</button>
          {kind === "reply" && (
            <button className="btn sec" disabled={busy || !comment.trim()} title="one more reply to the same video, answering the comment chosen above, as a new post"
              onClick={() => { const args: Record<string, string> = { another: "1", render: "1" }; if (pick != null && comments[pick - 1]?.text === comment.trim()) args.pick = String(pick); else { args.comment = comment.trim(); args.user = user.replace(/^@/, "").trim(); } run(`/api/projects/${encodeURIComponent(d.name)}/run`, { cmd: "reformat", args }); }}>
              Another reply with this comment
            </button>
          )}
          <button className="btn sec" disabled={asking === "running"} onClick={writeWithClaude} title="a new chat: Claude reads the frames, writes the hook, the narration and the comment for all three reformats, renders them and writes their captions">
            {asking === "running" ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {asking === "running" ? "Claude is writing…" : "Write them all with Claude"}
          </button>
          {asking === "done" && <span className="text-acc text-sm">written — reload if the page has not caught up</span>}
          {asking === "error" && <span className="text-bad text-sm">Claude did not finish — see the panel</span>}
          {error && <span className="text-bad text-sm">{error}</span>}
        </div>
      </div>
    </div>
  );
}
