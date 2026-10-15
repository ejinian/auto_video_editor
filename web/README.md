# beatcut web

The UI for the beatcut folder one level up: shoots, the cut form, jobs, the video page
with every edit button, the sounds pool, and Claude in a side panel (Claude Agent SDK,
running the same agent as Claude Code inside the beatcut folder).

```bash
npm install
cp .env.example .env.local   # ANTHROPIC_API_KEY=… (the Claude panel needs it; buttons don't)
npm run dev                  # http://localhost:3000
```

- `src/lib/paths.ts` — where the beatcut folder is (`BEATCUT_ROOT`, default `..`).
- `src/lib/beatcut.ts` — reads clips / projects / sounds / renders; no edit logic lives here.
- `src/lib/jobs.ts` — runs `uv run beatcut.py …` one job at a time, streams the log.
- `src/lib/agent.ts` — the chat: `query()` from the Agent SDK, NDJSON events to the panel.
- `src/app/api/*` — route handlers the pages and the panel call.

Everything the app changes goes through the CLI, so the CLI, Claude Code and the app
never disagree about an edit.
