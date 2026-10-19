# beatcut web

The UI for the beatcut folder one level up, organised around the job: make a video
(`/new`), fix a video (`/video/<name>`, the timeline), post a video (`/video/<name>/post`).
The home page is the feed of videos with one status chip each (cutting… / rendering… live,
needs render, ready to post, posted); plus shoots, jobs, the sounds pool, and Claude in a
side panel (Claude Agent SDK, running the same agent as Claude Code inside the beatcut folder).

```bash
npm install
cp .env.example .env.local   # ANTHROPIC_API_KEY=… (optional: without it the panel uses the Claude Code login)
npm run dev                  # http://localhost:3000
```

- `src/lib/paths.ts` — where the beatcut folder is (`BEATCUT_ROOT`, default `..`).
- `src/lib/beatcut.ts` — reads clips / projects / sounds / renders; no edit logic lives here.
- `src/lib/jobs.ts` — runs `uv run beatcut.py …` one job at a time, streams the log;
  `src/lib/jobmeta.ts` reads a job's project and step names off its command list.
- `src/lib/posted.ts` — `out/.app/posted.json`, the user's note that a video went up
  (the app never posts anything itself).
- `src/components/StatusChip.tsx` + `LiveJobs.tsx` — the one chip per video, live while a
  job runs (polls `/api/jobs` every 2 s, refreshes the page when a job ends).
- `src/lib/agent.ts` — the chat: `query()` from the Agent SDK, NDJSON events to the panel;
  `src/lib/chatAuth.ts` — an API key in `.env.local` or the Claude Code login on this Mac.
- `src/components/chat/ask.ts` — `askClaude()`: how a page button opens the panel with a
  prompt and (optionally) sends it as a new thread, resolving with the turn's final text.
  Used by the Fix it box, Write with Claude, Let Claude pick and Ask Claude about this shot.
- `src/app/api/*` — route handlers the pages and the panel call.
- `src/components/VideoEditor.tsx`, `Timeline.tsx`, `SlotCard.tsx` — the video page's
  editor: tiles per slot under the player (drag = `move`/`swap`), a side card whose
  buttons are the edit commands, frames from `/api/slot-thumb` and `/api/clip-frame`.

Everything the app changes goes through the CLI, so the CLI, Claude Code and the app
never disagree about an edit.
