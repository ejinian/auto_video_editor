---
name: beatcut
description: Edit Ernest + Christian's daily "Young Vibas" TikTok/Reels videos with the beatcut tool at ~/Desktop/beatcut — clips in clips/dayN + a sound link (TikTok video/sound page, Instagram reel) → one beat-cut 1080x1920 mp4 with the music baked in; story-ordered edits, A/B variations, re-prompt edits (swap/drop/merge/caption), verification, delivery, and the running lessons log. Use whenever they mention editing a video, a day's clips, a sound/audio link, variations, or Young Vibas.
---

# beatcut — how we make the daily videos

The tool is `~/Desktop/beatcut/beatcut.py` (`uv run beatcut.py …`, run from that folder). Its
`CLAUDE.md` is the full command reference and the record of every gotcha — **read it first**.
This skill is the *workflow*: what Ernest asks for, how to turn it into commands, how to
verify, and what we've learned. Append to the lessons log at the bottom every day.

## Ernest's rules for working with him (2026-10-09; Christian may run it differently)

- **Claude is the consultant.** Suggest the right thing, including mid-automation, and
  VERIFY: frames at the right moments, the storyboard, the scene check, the swipe file.
  He decides. Nothing posts.
- **Two kinds of video.** *Day-specific* = clips of one day's theme only ("claude, connect
  to the barber shop" = only walking-to / at-the-barber clips), named `dayN_V`.
  *Generalized* = mixes clips across days ("life after claude code"), named `general_V`
  (→ `out/general/`). Don't mix days unless it's a generalized video.
- **Sounds are a pool** (`sound/`). Pick from it, or find new ones through the skills.
- **No beat sync unless he says "sync it to the audio".** `plan` cuts at free shot
  lengths by default (`--sync` is the opt-in). Same logic as lighting: nothing he didn't
  ask for.
- **No lighting / color changes, ever.** His day-2+ clips are HDR; the tool tone-maps them
  to SDR proxies with Apple's own mapping so they look like the phone. Never add filters.
- **`final/` is the only folder he opens.** `render` copies the finished mp4 there. `out/`
  is the workspace he doesn't want to navigate. "Keep only X" = delete the rest from both.
- **Never `export --open` unless he explicitly asks.** Ideally he never edits. He will say
  when he wants a surgical change; only then open CapCut.
- **Re-rolls:** he may clear `out/` and ask for a batch (e.g. 3 × day 1, 3 × day 2, 1 ×
  day 3, 2 generalized). Produce them all, verify each, send each as it's done.
- Christian's own day-3 edit configs live in `projects/christian/` (his clips, not here);
  Ernest's day 3 is the tennis clip.

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
   `set/in/swap/merge/split/cut` before rendering if something's off.
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
  with the black outline, top-centre. Lowercase. **Any caption / hook / post-text request
  goes through the `captions` skill first** (`~/.claude/skills/captions`: ~1k real niche
  captions with views + multiples, `scripts/find.py`, `patterns.md`) — retrieve, then write.
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
- **2026-10-07, day 3 (Christian's machine; gym "coding on the laptop everywhere" bit, 10
  clips).** First session in a git WORKTREE: `clips/ sound/ out/` are gitignored, so they
  don't exist in the worktree — symlink them to `~/Desktop/beatcut/{clips,sound,out}` and
  every path in this file stays true. Christian delegates the sound ("just pick the best
  one and cut it"): read the footage FIRST, then match a sound to the bit, not the other
  way round. Picked DUNG DING BREGA (3VILCORE & PHEYX; #4 on TikTok that week, "chaotic,
  hyped, ironic, meme compilations") via the music-page link — headless Chromium worked
  first try on a fresh machine. `-p` goes BEFORE the subcommand (`-p day3_1 sound …`).
  Two 21 s bench takes had the laptop only in their last 4-5 s, and story quotas spread
  slots evenly inside a clip, so the punchline would never be picked → carved each take
  into a 7-8 s "reps" piece and a 4-6 s "laptop" piece (`ffmpeg -ss -t -c copy`) and
  listed all 12 pieces in `--clips`. Story mode put plain benching on the drop → `set
  <dropslot> <clip> --at <sec>` is the hero control when `--story` is on. The scene-detect
  check flagged a cut the detector couldn't see: a jump cut inside the same take (clip
  used x2 in adjacent slots, same framing) — that's a real visual weakness, not a false
  alarm; replace one of the two slots with another clip. 17/17 cuts verified after.
- **2026-10-07, day 3 variation (day3_2, "geekin" by Nemzzz).** Christian: "use that British
  rap one I just heard you playing" — he had heard nothing from beatcut; a background
  research agent had TikTok pages open in the built-in browser pane, which AUTOPLAYS with
  sound even while hidden. When he names a sound "you were playing", `tabs_context` +
  `get_page_text` on the TikTok tabs finds it (video link → tikwm, worked first try).
  A 22 s "original sound" post audio with flat energy after a soft 4 s drop → `--preset
  loose` gave 9 shots of 2-4 s, a real contrast to the 18-cut tight version on the same
  clips; different opener (`--first`), reversed story, hang moved onto the drop with
  `set`. Story quotas again dealt the same clip to two adjacent slots and dropped two
  plain-reps pieces back-to-back at the end — the board catches both every time.
- **2026-10-08, the buttons + /day.** Christian asked for "a UI to use these features
  easily" → `ui.py` (Flask, one file, every button = a `beatcut.py` subprocess; job page
  polls a log; `.claude/launch.json` has `beatcut-ui`), `HOWTO.md` (the shoot-day
  procedure, served at /howto), and `.claude/skills/day/SKILL.md` (`/day N` = frames →
  sound → two variations → hook burned in → caption + lint → deliver). Testing the
  "Make variation" button found a real CLI hazard: `sound <local mp3 inside sound/>`
  rewrites the mp3 onto itself and truncates it to ~1.4 s; the only tell was a 1-slot
  plan. Fixed in the UI by writing the `.sound.json` pointer instead; the CLI still has
  the hazard, so never point `sound` at `sound/`. Renders are ~10 s here on
  videotoolbox, not a minute.
- **2026-10-08, Lisa v1 (SlideLabs promo, not a beat-cut montage).** Brief: "her face, then
  a transition into SlideLabs, text over it". Clips: a 2.8 s shocked-face selfie and a 51 s
  earlier post (4 s face, then a phone filming the laptop running SlideLabs). Built outside
  beatcut (it has no speed or transitions): face on the bar before DUNG DING BREGA's drop, a
  zoom+blur transition ON the drop, demo in bar-long pieces at 2x / 8.4x / 2.5x, two Pillow
  captions. Scripts: `out/lisa_v1/lisa_v1_build.py` (mp4) and `lisa_v1_capcut.py` (spec).
  CapCut export of such an edit: capcut-cli `compile` takes `speed`, text tracks and a
  `transition` op (`pull-in` ≈ our zoom), BUT (1) compile leaves the speed MATERIAL at 1x
  — run `capcut speed <draft> <seg> <x>` per segment afterwards, lint flags it as
  `speed-material-mismatch`; (2) `lint --fix` clamps any caption >7 s to 7 s, so for hook
  text that stays up, lint WITHOUT `--fix`. After a Claude app restart the runtime path
  changes and the Accessibility / Screen Recording grants stop applying (`--open` can't
  click, `winshot` fails) — re-grant the new `claude` entry. CapCut here reports 8.7.0.
- **2026-10-09, the re-roll (9 videos in parallel: 3 × day 1, 3 × day 2, 1 × day 3, 2
  generalized).** Ernest cleared `out/` and asked for a batch; one Workflow agent per video
  (frames → plan → board → fix → render → verify → structured result) cut all nine in
  ~14 minutes, every one 100% on the scene check. Lessons: (1) `tile()` used ONE shared
  scratch dir that every process rmtree'd — concurrent `frames`/`board` runs deleted each
  other's frames and one sheet came back with another clip's frames; now a per-process
  `tempfile.mkdtemp` (an agent fixed it mid-run). (2) The random/story plans are a
  starting point, never the edit: every agent re-set 3-9 slots from the frame sheets —
  passers-by (barber_start 13.5-14.5 s and 20 s; IMG_2745 at 3.7-4.9 s; IMG_2748 at
  4.8-5.9 s; IMG_2746 at 1-4.7 s), laptop-only close-ups (barber_start 0-4 s), the
  trolley2 street pan (5-7 s), apple_store_sit's tabletop pan (from 7.5 s), far-away
  openers that don't read in half a second. (3) `in` left a stale `reused` flag → fixed.
  (4) For a one-take clip (tennis), `--random` gives the shape but the hits must be placed
  by hand from a dense sheet (`--n 26`); same-framing jump cuts inside the take are the
  thing to hunt. (5) A generalized video needs the recap/burst slots filled with UNUSED
  moments of already-seen clips, not repeats — merge the flashes, re-deal the bursts.
  Boards reviewed by the lead for general_1/2, day3_1, day1_1, day2_1: all clean.
- **2026-10-09, the redo after Ernest's verdict.** Kept day1_1, day1_3, day3_1; redid
  day1_2, day2_1-3, general_1-2. Three rules came out of it and are now in the tool:
  (1) **no lighting changes** — the complaint was HDR (HLG) clips rendered to SDR without
  tone mapping; ffmpeg here has no zscale/libplacebo, so `sdr_proxy()` runs macOS
  `avconvert` once per HDR clip (Apple's mapping = the phone look; L 112 vs 136 on the
  same frame, real blacks and greens back) and everything reads the proxy; (2) **no beat
  sync unless asked** — free cuts are the default, `--sync` is opt-in; (3) **`final/`** is
  the deliverable folder, `out/` the workspace. day3_1 was re-rendered through its proxy
  with the identical cut. Agent lessons: a seeded free/story plan is a shape, not an edit
  (every agent re-set most in-points from the sheets); `frames --n 26` on a 1.5 s clip
  sampled past the last frame (clamped now); `split` only cuts on the old beat grid in
  free mode, so one agent hand-wrote the cut list into the project JSON — a `cut <slot>
  <sec>` command would be the honest fix (added 2026-10-15: `cut 9 +2` / `cut 9 12.4`). Pre-build HDR proxies BEFORE a parallel batch.
- **2026-10-15, the app (`web/`).** Christian asked for "a full-fledged app using Next.js,
  full UI, fully integrated with Claude" → `web/` replaced `ui.py` (deleted). Same shape
  as before: every button is a `beatcut.py` job; plus the Claude Agent SDK in a side panel
  with `cwd` = this folder, so it loads this skill, `/day` and the ig-* skills and runs
  for real. Lessons: with cacheComponents on, Next 16 wants every page static or in
  Suspense — off, with `force-dynamic` everywhere, since every page is a folder read; the
  SDK ships its own CLI binary (`@anthropic-ai/claude-agent-sdk-darwin-arm64`), no
  `claude` on PATH needed; `env` passed to `query()` REPLACES the subprocess env (spread
  `process.env`); subagent frames carry `parent_tool_use_id` — skip them in the UI. A
  worktree's `projects/` is the committed set, so `day3_1` there pointed at Ernest's
  tennis clips, not Christian's gym day: the video page now flags "clips moved or renamed"
  instead of a broken storyboard button.
- **2026-10-14, day 4 (LA Kings game, 3 clips: solo POV 6.7 s SDR, two third-party 4K60
  HDR takes of 4.5 s and 13 s).** Ernest dropped the clips into `out/day4/<pov folders>/`
  rather than `clips/day4/` — moved them to `clips/day4/{solo.mp4, third_party_1.mov,
  third_party_2.mov}` and said so. Brief: "a few outputs, I pick one, THEN CapCut" → four
  variations (`day4_1..4`), each a different sound from the pool, different opener and
  preset (loose story / tight random / chill 4-shot / tight 808s), no CapCut. The solo
  POV's tilt-up from the code to the rink (1.5-2.5 s) is the hook; the story plan skipped
  it (slot 1 ended mid-tilt, slot 2 started after it) → `in 1 0.7` so the 1.8 s opener
  carries hands → tilt → rink. Random plans ended on the weakest frame (hands, or the
  static from-behind shot) → `in 9 …` to end on the reveal / the close-up. `--preset
  chill --story 3,1,2` over 12 s produced TWO slots, both the longest clip, two clips
  unused — chill + few clips = plan by hand (`split`, then `set <slot> <clip> --at`).
  `frames <explicit HDR path>` did not build the proxy on first run here (the `.sdr/`
  folder was missing until `sdr_proxy()` was called directly) — check `cmd_frames`'
  probe path; `plan`/`render` go through `scan_clips` and are fine. All four 100% on the
  scene check, AAC present, delivered in one SendUserFile. `final/` was cleared first on
  request (the old nine still exist under `out/*/` and `out/*/versions/`).
- **2026-10-14, day 4 re-roll.** Ernest rejected the first four for MIXING the solo POV
  clip with the third-party takes ("I don't like that"), and a lone POV clip isn't worth
  cutting at all — rule 11 in memory: one point of view per video. Re-rolled three from
  the two third-party takes only (`day4_1..3`, different opener each: from-behind, the
  side close-up, the wide push-in). With two clips, alternate behind / wide / close so no
  two adjacent slots share a framing. `--preset chill` again dealt both slots to the long
  take → `split` + `set`. day4_4 deleted. All three 100% on the scene check.
- **2026-10-20, "life after claude code" prep (generalized video, one clip from every
  shoot).** Ernest's sound: ROÜGE "Cosmic Mission" (Detriti Records, YouTube chapter
  29:20-34:18 of `SnscU4OG8YE`; whole track in `sound/cosmic-mission-rouge.mp3`, 136 bpm,
  big drop at 88.4 s). He wants ONLY seconds 15-30 → `sound/cosmic_mission_cut.mp3`
  (15.0 s, re-encoded cut). His rhythm rule for it: a new clip on every heavy bass-drum
  hit, "a little under 2 s" = one bar. Low-pass onset analysis puts the kicks at 1.00,
  2.81, 4.61, 6.42, 8.22, 10.04, 11.83, 13.63 s (1.80 s apart, a half-beat ghost kick
  0.45 s after most of them — ignore those). So the cut list is kick-synced: 8 shots, the
  opener 1.0 s then ~1.8 s each; make them with `cut <slot> <sec>` at those times (or
  `plan --sync` if a preset gives one cut per bar). Clips not yet downloaded.
- **2026-10-20, "life after claude code" samples (general_3/4/5).** Five shoots now
  (day 5 = a bar/restaurant night, SDR: IMG_2539 dark patio, IMG_2547 from behind at the
  bar, IMG_2549 1.8 s close typing with a beer, IMG_2550 bar + TV). Ernest's grid for
  Cosmic Mission: a 1.0 s opener, then a new clip on every kick (every 1.80 s) → 9 slots
  over the 15 s cut. Built with the CLI only: `plan --preset chill --length 15 --start 0`,
  `merge 2` until one slot, `cut 1 <kick>` for each kick time descending, then `set k k
  --at <in>` with the 9 clips passed in slot order — a 40-line driver script
  (`kickbuild.py`) did all three. A per-day six-frame contact sheet (one image per day,
  every clip a row) is the fastest way to choose one clip per shoot; `frames` per clip
  is for in-points. Lessons: IMG_2788 (tennis) is a far-away figure in every frame — the
  close look Ernest had was his 315% CapCut zoom — use `tennis_ckip` 1.0 (swing at 1.6)
  or 7.3 (swing at 7.8) instead; IMG_2739 only reads from 12 s (closer to the cart).
  Each sample: a different opener (bar close-up / tennis swing / bushes), no two slots
  from the same day adjacent, every day present. All three 8/8 on the scene check with
  cuts exactly on the kick list.
- **2026-10-21, Ernest-only re-roll (general_6/7/8).** New standing rules (memory rule
  12): only Ernest in his videos (Christian = the white cap — that rules out the bananas,
  pumpkin box, cart and most of day 1; only IMG_2743 and IMG_2746 from 6 s are his), tennis
  only where the ball is actually hit, and at least one clip of the haircut being cut.
  The hits had to be FOUND on a 26-frame sheet of the raw take: `tennis_ckip` 4.4-6.2 s
  (ball at 4.9-5.4) and 8.9-10.7 s (overhead, ball at 9.4-9.8); the earlier "swing"
  in-points (1.0, 7.3) were him standing still — never trust a hit moment read off a
  rendered video's sheet, the times are the render's, not the clip's. `set` refuses a
  clip shorter than the slot by even a frame (IMG_2549 1.83 s vs a 1.81 s slot) — the
  1.0 s opener is the place for sub-2 s clips. `in` can fix a back-to-camera frame
  (IMG_2743 2.0 → 5.0). All three 8/8 on the scene check.
- **2026-10-21, general_final (Ernest's pick: general_7 + 3 changes).** "Extend the music
  ~10 s with more well-cut beats" = the SAME kick grid continued: the kicks keep landing
  every 1.80 s through the whole intro (measured to 26.3 s), so the audio was re-cut from
  the full track to end exactly ON a kick (`sound/cosmic_mission_cut_24s.mp3`, song
  15→39.47 s) → 14 slots, 13 cuts, the video ends on a downbeat. "Add a few clips from 6
  and 8" = appended after 7's nine (bushes, Kings close-up, oil shelf, trolley1, overhead
  hit as the closer); "barber at a different angle like in 6" = `barber_end` 13.9 → 1.0.
  A project named without `<folder>_V` renders to `out/<name>.mp4` and its board to
  `out/_<name>_board.jpg` (not `out/general/`); `final/` is unaffected. 13/13 on the
  scene check.
- **2026-10-21, general_final → CapCut.** `export --open` wrote the draft but fell back to
  "click the first tile": CapCut came up with a SMALLER home window at (132,88) 1464x976
  (not full-size at (0,33)), and the tile click evidently fired before the grid was
  there. Accessibility was still trusted. The tile offset (306,782) from the window's
  top-left is STILL right for the new home layout (verified on a capture), so a manual
  Quartz click at window-origin + (307,783) opened it on the first try (`Timelines/`
  appeared within 6 s). If this repeats, lengthen the home-window wait in
  `open_in_capcut()` before raising the retry count. He asked for CapCut explicitly, so
  the click was in scope.
