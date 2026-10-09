# Setting up beatcut on a new Mac

For Christian (or anyone). Hand this file to your own Claude Code session and say
"set this up" — every step is a command it can run or a click you have to make yourself.
Nothing here needs Ernest's machine. Budget: 20 minutes, mostly downloads.

## 1. Tools

```bash
brew install ffmpeg uv node          # video engine · Python runner · Node for capcut-cli
uv tool install yt-dlp               # Instagram / YouTube sounds (do NOT brew install yt-dlp — it compiles LLVM for an hour)
npm install -g capcut-cli            # writes CapCut's project files
```

`uv` puts yt-dlp in `~/.local/bin`; the tool looks there itself, so PATH doesn't matter.

## 2. The repo

```bash
git clone https://github.com/ejinian/auto_video_editor.git ~/Desktop/beatcut
cd ~/Desktop/beatcut
uv run beatcut.py setup
```

`setup` installs the tool's Python deps on first run (librosa, pillow, playwright,
pyobjc), downloads a headless Chromium (~95 MB, used only to resolve TikTok sound-page
links), and checks ffmpeg / yt-dlp / the caption font. It must end with `ready`.

Keep the folder at `~/Desktop/beatcut` — the docs and the skill assume that path.

## 3. CapCut (only if you want the CapCut export)

1. Install CapCut: `brew install --cask capcut` (or the Mac App Store). Version 9.x is what
   this was built on; 10.x is reported to reject tool-written projects — if CapCut updates
   itself, run `capcut doctor` before trusting an export.
2. Open CapCut, sign in, click **Create project**, then quit CapCut. That empty project is
   the **seed**: CapCut only opens projects that carry its own version stamp, and the
   export copies the stamp from the newest project CapCut itself created. **Never delete
   the seed project.** (On Ernest's Mac it's called `1007`.)

That's enough for `export`: it writes the project and CapCut shows it as the first tile.

## 4. Optional: let `export --open` land inside the project

Without this, `--open` launches CapCut and you click the first tile. With it, the tool
clicks for you. macOS has to trust the process that does the clicking:

- **Claude Code inside the Claude desktop app:** System Settings → Privacy & Security →
  **Accessibility** → `+` → press Cmd+Shift+G and paste the runtime's path, which is
  `~/Library/Application Support/Claude/claude-code/<version>/<hash>/claude.app`
  (find the exact one with `ls ~/Library/Application\ Support/Claude/claude-code/*/`).
  Turn it on. It shows up in the list as lowercase `claude`. Add the same app under
  **Screen Recording** if you want Claude to be able to *see* the CapCut window
  (`tools/winshot.py CapCut out.png`), which is how it verifies the open.
- **Running from Terminal / iTerm:** grant Accessibility (and Screen Recording) to the
  terminal app instead.

Claude Code may need its session restarted after the grant.

## 4b. The Instagram skills (what `/day` and the captions run on)

Thirteen `/ig-*` skills from [Jakeschincariol/instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill)
(MIT, no API keys, nothing posts). Install them globally so they work in every session:

```bash
git clone --depth 1 https://github.com/Jakeschincariol/instagram-agent-skill.git /tmp/igskills
cp -r /tmp/igskills/skills/ig-* ~/.claude/skills/
mkdir -p ~/.claude/instagram
cp ~/Desktop/beatcut/research/voice.youngvibas.md ~/.claude/instagram/voice.md   # our shared voice file
cp ~/Desktop/beatcut/research/swipe-2026-10-09.md ~/.claude/instagram/swipe.md   # the current research
```

What each does is in that repo's README; the ones we use daily are `/ig-viral` (research →
swipe file), `/ig-reel` (hook options scored off 26 formulas, `hookscore.py`),
`/ig-caption` (caption + the 125-character lint, `caption.py`) and `/ig-human` (strips the
AI tells and scores it). `/day` calls them. The swipe file goes stale after ~30 days;
`/ig-viral` rebuilds it (on TikTok, where view counts are public — see the research
notes in `research/`).

## 5. Smoke test

```bash
cd ~/Desktop/beatcut
mkdir -p clips/day0 && cp /path/to/two/phone/clips/*.MOV clips/day0/
uv run beatcut.py -p day0_1 sound "https://www.tiktok.com/t/ZP9DHQwpko3bC-jPksf/"
uv run beatcut.py -p day0_1 plan --clips-dir clips/day0 --preset loose --length 12
uv run beatcut.py -p day0_1 render          # -> out/day0/day0_1.mp4
uv run beatcut.py -p day0_1 export --open   # -> CapCut (needs step 3)
```

Always quote links: zsh chokes on `?` and `=` in an unquoted URL.

## 6. How we use it day to day

Clips for day N go in `clips/dayN/` with names you'll refer to (`before_barber.MOV`,
`trolley2.mov`). Video V of that day is project `dayN_V`, everything it produces lands in
`out/dayN/`: `dayN_V.mp4` is the deliverable, `versions/` keeps earlier renders,
`_dayN_V_board.jpg` is one frame per cut.

Open this folder in Claude Code and talk to it: "day3 video 1: the trolley clips, then the
bushes, on this sound: <link>, not too strict on the beat, 12 seconds". The skill in
`.claude/skills/beatcut/SKILL.md` and the reference in `CLAUDE.md` load automatically;
they hold the workflow, every command, and the lessons log. Then "swap clips 3 and 8",
"hold the chair shot longer", "export it to CapCut" — and it re-renders.

**A re-run of `export` deletes the same-named CapCut project first**, your edits included.
That's on purpose: the template always starts from the automation, you edit after, and
re-running is exactly when you want the old one gone.

## 7. If something fails

| symptom | cause / fix |
|---|---|
| `zsh: no matches found` | quote the link |
| `that's a SOUND page link…` / TikTok didn't hand over the sound | the headless browser isn't installed: `uv run beatcut.py setup` |
| Instagram `/reels/audio/…` link refused | audio pages are login-walled everywhere; use a reel link, or a TikTok link |
| `CapCut is running` / export quits CapCut | expected — capcut-cli won't write while the editor is open |
| CapCut: "project is from an unusual path" | no seed project — step 3.2 |
| `--open` says "click the first tile" | Accessibility not granted (step 4), or CapCut's home layout changed |
| every clip "file inaccessible" in CapCut | run `capcut register "<draft dir>" --materials --apply`; export does this itself |
| audio seems missing in a preview | VS Code / Electron previews can't decode AAC; open the mp4 in QuickTime |
