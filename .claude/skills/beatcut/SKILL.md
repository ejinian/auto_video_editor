---
name: beatcut
description: Edit Ernest + Christian's daily "Young Vibas" TikTok/Reels videos with the beatcut tool at ~/Desktop/beatcut — clips in clips/dayN + a sound link (TikTok video/sound page, Instagram reel) → one beat-cut 1080x1920 mp4 with the music baked in; story-ordered edits, A/B variations, re-prompt edits (swap/drop/merge/caption), verification, delivery, and the running lessons log. Use whenever they mention editing a video, a day's clips, a sound/audio link, variations, or Young Vibas.
---

# beatcut — how we make the daily videos

The tool is `~/Desktop/beatcut/beatcut.py` (`uv run beatcut.py …`, run from that folder). Its
`CLAUDE.md` is the full command reference and the record of every gotcha — **read it first**.
This skill is the *workflow*: what Ernest asks for, how to turn it into commands, how to
verify, and what we've learned. Append to the lessons log at the bottom every day.

## The ask, decoded

- **"day N"** → clips live in `clips/dayN/`. Ernest NAMES the clips (`before_barber.MOV`,
  `barber_long.MOV`, `trolley_think1.mov`…) so he can reference them. Use those names back.
- **"Video 1 / Video 2 … with Audio: <link>"** → one project per video, named
  **`dayN_V`** (`-p day2_1`, `-p day2_2`…). Everything for it lands in `out/dayN/`:
  `dayN_V.mp4` is the deliverable, `versions/` the earlier renders, `_dayN_V_board.jpg`
  the storyboard. Ernest asked for this to be obvious in Finder — always name the full
  path `~/Desktop/beatcut/out/dayN/dayN_V.mp4` and say which brief item it is.
- **"variation 1 / variation 2"** → same clips, a different combination AND a different
  sound. Same `--story` order with a different `--seed`, or a different story order, or a
  different preset. They must not look like the same edit with a new song.
- **"always start with X"** → `--first <clip#>` (slot 1 is cut to fit that clip's length).
- **"multiple sub clips of the long take"** → `--story <long clip#>`: the take is used
  CHRONOLOGICALLY across the video (haircut progresses, trolley ride moves). Different
  angles come for free because the camera moves during a long take.
- **"doesn't have to be that strict / not every beat"** → `--preset loose` (a cut every
  2-4 s, the drop still gets its own shot). `tight` is the day-1 rapid-fire default;
  `chill` for 4-8 s shots.
- **"X + Y + Z"** (several locations) → `--story` in the order he lists them unless the
  footage says otherwise; longer clips get more slots automatically.
- **"only use the first/last N seconds of the take, random order, any angles"** → carve
  those windows out as their own clips (`ffmpeg -ss … -t … -c copy`, lossless, seconds),
  then `--random --seed N` (plus `--first` for the opener). day2_5 is the reference.
- Length: default 30 s; `--length N` ends on the nearest downbeat.

## The procedure (every time)

1. `clips/dayN/`: probe every clip (`ffprobe` or `clips`), note durations and that they're
   portrait. 4K60 phone clips are normal; hardware decode makes a 20 s render ~12 s.
2. **LOOK at the footage before planning**: `frames clips/dayN/<clip>` → Read
   `out/_frames_<clip>.jpg`. For a long take, know what happens when (outside → walking in →
   chair → cape → cutting). Choose `--first`, `--story`, and which moment should land on
   the drop from what you SEE, not from filenames.
3. Sound, per link type (details in CLAUDE.md): TikTok video link → tikwm; TikTok sound
   page → headless Chromium; Instagram REEL link → yt-dlp (no login needed so far);
   **Instagram AUDIO page (`instagram.com/reels/audio/<id>`) is login-walled everywhere**
   — ask Ernest for the reel link that uses the sound, or have him log into Instagram in
   the built-in browser pane and read the page there. Always quote links in zsh.
   `sound -p <name> "<link>"` keys the sound to the project.
4. `-p <name> plan --clips <paths in order> --first … --story … --preset loose --length …`
   (or `--clips-dir clips/dayN`). Read the slot table: opener right? drop on a strong
   moment? no flash-frame slots (<0.6 s) unless intended?
5. `-p <name> board` → Read `out/_<name>_board.jpg`. One frame per slot. Fix with
   `set/in/swap/merge/split` before rendering if something's off.
6. `-p <name> render`. Then verify mechanically: scene-detect the output and confirm every
   planned cut has a scene change within one frame (snippet in CLAUDE.md); ffprobe shows
   an AAC track. Audio can't be judged in Electron previews (VS Code, the Claude app) —
   `open out/<name>.mp4` (QuickTime) or SendUserFile and say to check on the phone.
7. Deliver each finished mp4 with SendUserFile as it's done, not all at the end. One line
   each: what's in it, length, where the drop lands.
7b. When Ernest wants to polish by hand: `-p <name> export --open` writes the same edit as
   a CapCut project (via capcut-cli; details in CLAUDE.md) and opens CapCut INSIDE it by
   real-mouse-clicking the first tile. Run it from Bash with the sandbox disabled, or
   let Ernest run it himself. Verify with a window capture: `winshot.py CapCut out.png`
   (pyobjc `CGWindowListCopyWindowInfo` for CapCut's window id → `screencapture -l`),
   which works even when the Claude app covers CapCut. The seed project `1007` must stay.
   Tell him the draft name; the mp4 render stays the deliverable if he doesn't touch it.
8. On re-prompt ("swap clips 3 and 8", "get rid of clip 7", "hold that longer"), run the
   matching edit command on the right `-p` project, then `render`. Table in CLAUDE.md.

## Taste rules we've settled on

- The opener is the most scroll-stopping frame, and it must read in half a second.
- The drop takes the biggest visual beat (the cape going on, the laptop opening in the
  bushes), held for a bar or two.
- Hard cuts only. No transitions, no speed ramps, no zooms. That's the format.
- Captions are burned in only when Ernest gives the line (`caption "…"`), in TikTok Sans
  with the black outline, top-centre. Lowercase.
- Baked-in commercial audio may be muted by content ID; Ernest accepts that.

## Lessons log (append, newest last)

- **2026-10-05, day 1 (grocery store, 11 clips, TikTok sound).** First pipeline. 24 cuts in
  29 s was fine for a rapid-fire first video but Ernest's day-2 brief says "not that
  strict" → `loose` exists now. Verified 23/23 cuts on beats. Electron previews have no
  AAC → "no audio" false alarm.
- **2026-10-06, day 2 (barber long take; trolley / Apple store / Grove bushes).** Four
  videos from one brief → multi-project (`-p dayN_V`), explicit `--clips`, `--first`,
  `--story`, `--preset`, `--seed`, `frames`, `out/dayN/` layout. A regular cut landing 1
  beat before a forced drop cut made a 0.6 s flash shot → fixed. Instagram AUDIO-page
  links are login-walled everywhere; Ernest swapped them for four TikTok links. The
  sounds were 9-18 s "original sound" memes with FLAT energy (no drops): the video then
  plays the sound to its END (punchline is in the tail) and the story decides everything.
  Story mode went through three designs in one evening: proportional position mapping
  (long clips swallow every slot; sub-shots overlap when a clip runs short), a sequential
  walk with uniform gaps (seeded jitter accumulated until it wrapped and re-showed the
  opening), and finally per-clip SLOT QUOTAS (every story clip gets ≥1 slot when there
  are enough, the rest by footage) + even spread within each clip + jitter bounded to a
  pick's own gap. Keep that one. The opener (`--first`) takes the START of its clip and
  the story continues after it. Still manual: the storyboard caught a 3.8 s slot on empty
  shop floor and a slot running into the trolley clip's street pan — `frames` + `board`
  before `render`, every time, and fix with `in <slot> <sec>`. A pinned 1.5 s opener
  caps slot 1 to one beat; the first-slot rule must CAP, never stretch (a 10 s opener
  once became the whole video). Sound→video pairing: longer sounds to the long take,
  short punchy ones to the three-location montage; `tight` on a 9 s sound so all three
  locations fit.
- **2026-10-07, day 2 follow-up.** Ernest's verdict on the barber videos: the long take's
  MIDDLE (talking to the barber, the cape going on, ~22-90 s) is dead; the first and last
  ~20 s carry it, and he wants random angles in random order. Chronological story mode
  was the wrong instinct there → `--random` mode + carved windows (day2_5). Also: CapCut
  export shipped (`export --open`, via capcut-cli); first real draft went into an EMPTY
  store, so it carries the bundled 6.5 template markers that CapCut 9.x may refuse —
  the one-time "create an empty project in CapCut" seed is still pending Ernest.
  Computer use is not available in this app session, so "does it open in CapCut" can
  only be confirmed by Ernest or by CapCut writing `Timelines/` into the draft folder.
- **2026-10-07, later.** `export --open` now lands inside the project. What it took:
  CapCut 9.5 refused the generic-template draft ("unusual path") until an app-made seed
  project existed (`1007`, created by clicking Create project for him); CapCut's home
  canvas ignores AX `click at` but takes a Quartz mouse event; the editor's AX window
  title is always "CapCut", so the open signal is CapCut writing its own files into the
  draft folder; Screen Recording lets `screencapture -l <windowid>` see CapCut even
  under the Claude window (`tools/winshot.py`). Ernest granted Accessibility + Screen
  Recording to the lowercase `claude` runtime. Verified: editor open on day2_5, 15 clips
  + the mp3 on the timeline, 18:02, 9:16, 30 fps. His rule for this kind of thing:
  iterate, but not endlessly — "if it's stubborn it's no big deal".
