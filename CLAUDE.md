# beatcut — cut phone clips to a TikTok sound, one mp4 out

A single-file Python CLI (`beatcut.py`, run with `uv run beatcut.py …`; uv installs
librosa/numpy/soundfile/pillow on first run). ffmpeg 9 from Homebrew does the video
work. **This Homebrew ffmpeg has NO `drawtext` filter** — all text (captions, sheet
labels) is rendered with Pillow and overlaid as PNG. Don't add drawtext.

The user (Ernest, with Christian) is editing daily TikTok/Reels videos for the
"Young Vibas" account — quantity over quality. The ask: drop clips in, give a sound,
get a finished mp4 with the music baked in, then re-prompt Claude for edits
("swap clips 3 and 8", "get rid of clip 7") and re-render.

## Layout

| path | what |
|---|---|
| `clips/` | the input clips. **Numbered 1..N by filename order** (natural sort). Adding/renaming clips renumbers everything — re-`plan` after. |
| `sound/<slug>.mp3` + `.beats.json` + `current.json` | the downloaded sound, its beat analysis, and a pointer to the latest one |
| `project.json` | THE EDIT: `cuts` (absolute sound times) + `slots` (which clip, and its in-point, for each gap between cuts) + `excluded`, `hero`, `caption`, `density` |
| `out/final.mp4` | the latest render; every render is also copied to `out/final.vN.mp4` so earlier versions survive |
| `out/_clips.jpg` | contact sheet of the numbered clips (`sheet`) — Read it to see which clip is which |
| `out/_board.jpg` | storyboard, one frame per slot (`board`) — Read it to check the result without playing it |

## Projects (day 2+): several videos from one folder of clips

**Naming convention (Ernest, 2026-10-06 — "make it obvious"):** Ernest drops a day's clips
in `clips/dayN/`. Video V of that day is project **`dayN_V`** (`-p day2_1`), and
EVERYTHING it produces lands in **`out/dayN/`**: `dayN_V.mp4` (the deliverable),
`versions/dayN_V.vK.mp4` (every earlier render), `_dayN_V_board.jpg`, `_dayN_V_clips.jpg`,
and `_frames_<clip>.jpg` sheets. The project file is `projects/dayN_V.json`, its sound
pointer `projects/dayN_V.sound.json` (set by `sound -p dayN_V …` or `plan --sound …`).
`out_dir()` derives the folder from the `dayN_` prefix (or the clip's `clips/dayN/` path);
a project not named that way renders to `out/` directly. Day 1 was re-homed to this layout
(`clips/day1/`, `out/day1/day1_1.mp4`). Always tell Ernest the full path
`~/Desktop/beatcut/out/dayN/dayN_V.mp4` when a video is done.

The project's `clips` list is explicit (`plan --clips a b c` in that order, or
`--clips-dir clips/day2`, natural-sorted), so ids are stable per project and other
folders are never swept in.

`plan` options that shape the edit: `--first N` (clip N always opens, from its START; slot 1
is CAPPED at the latest beat the clip can fill, never stretched), `--story 2,1,3` (slots are
dealt to the story clips IN ORDER by per-clip quotas — every story clip gets at least one
slot when there are enough, the rest in proportion to footage — then spread evenly and
chronologically inside each clip, so a long take plays out across the video and a short
clip still appears; a clip that can't hold a slot is skipped for that slot but stays open
for a later shorter one; footage is re-shown only when the whole story runs out),
`--seed N` (jitters each pick within its own gap → a second variation of the same story,
never a wrap-around), `--preset tight|loose|chill` (density presets; `density loose` on an
existing project). With `--story`, `hero` is ignored (the drop takes whatever story moment
falls there — pick the story/seed so a strong moment lands on it, check `board`). A sound
shorter than `--length` plays to its END (meme sounds keep the punchline in the tail).
`frames <clip…>` writes a timestamped frame sheet per clip (`out/_frames_<clip>.jpg`) — the
way to SEE a long take before deciding the story.

## CapCut export — the edit as an editable project (2026-10-07)

`-p dayN_V export [--open]` writes the SAME edit `render` would bake (identical frame math)
as a CapCut desktop project in CapCut's draft store
(`~/Movies/CapCut/User Data/Projects/com.lveditor.draft/<dayN_V>/`): one video track with
every slot as a segment (clip + `sourceStart` in-point, so each cut can be dragged longer
or shorter in CapCut), the sound on an audio track offset to `audio_start`, 1080x1920 @30.
Media is COPIED into the draft's `assets/` (self-contained; ~200 MB–1 GB per project with
4K sources — delete old drafts in CapCut when done). Then `open -a CapCut`: the project
is at the top of CapCut's list; there is no URL scheme to open a specific draft on macOS.

**Mechanism:** CapCut has no API; its drafts are plain JSON on disk. We do NOT hand-write
the format (it drifts per version): the export writes a **capcut-cli compile spec**
(`out/dayN/dayN_V.capcut.json`) and shells out to `capcut compile … --template auto`, then
the CapCut-9.x-on-macOS recipe from capcut-cli's version matrix: `sync-timelines --nested
--apply` (the app reads `Timelines/<id>/draft_info.json`, not only the root file),
`register --materials --apply` (else every clip shows "file inaccessible" on 9.1+), and
`lint --fix`. capcut-cli (`npm install -g capcut-cli`, found under nvm) is the only
dependency; `capcut doctor` checks the environment.

⚠️ **One-time per machine:** CapCut 9.x refuses drafts built from capcut-cli's bundled
6.5-era template ("from an unusual path"), so `--template auto` seeds new drafts from the
NEWEST APP-AUTHORED project in the store. Before the first export, open CapCut, create
one empty project (any name), and close it. If the store is empty the export stops with
that message. Installed here: CapCut 9.5.0 (Homebrew cask), capcut-cli 0.28.0. The
version matrix calls 9.x "expected-compatible, unverified" and 10.x write-guarded — if a
CapCut update lands, run `capcut doctor` / `capcut version <draft>` before trusting an
export, and keep the 9.5.0 installer. Verified on a scratch store 2026-10-07: segments,
in-points and the audio offset round-trip; a real open in CapCut 9.5.0 is the pending check.

## The pipeline (= the "function")

```
uv run beatcut.py sound <tiktok-url>    # download + beats/drops report (sound/)
uv run beatcut.py plan                  # cut grid from the beats, a clip in every slot (project.json)
uv run beatcut.py render                # -> out/final.mp4 (≈1 min for 30 s at 1080x1920, videotoolbox)
```

**Sound links — all of these work with `sound <link>`** (QUOTE the link in zsh: a `?` or `=`
in an unquoted URL gives `zsh: no matches found` before the script even runs):
- **TikTok VIDEO link** (`tiktok.com/@user/video/…`, `/t/…`, `vm.tiktok.com/…`): resolved
  keylessly through tikwm (`tikwm.com/api/?url=`), which returns the post's `music` mp3 URL.
- **TikTok SOUND-PAGE link** (`tiktok.com/music/Name-<id>`, also what a `/t/…` short link from
  a sound's share sheet redirects to): TikTok only hands the page's data to a real browser —
  tikwm's music endpoints are Cloudflare-walled, yt-dlp's `tiktok:sound` extractor is dead
  ("No working app info"), and the unsigned `api/music/detail` returns an empty body (all
  verified 2026-10-05). So `resolve_music_page` runs **headless Chromium via Playwright**
  (pinned dep; `setup` or the first use downloads `chromium-headless-shell`, ~95 MB, once)
  for a few seconds and reads the page's own `api/music/detail` XHR → `musicInfo.music.playUrl`.
  If TikTok ever bot-walls it, the fallback is unchanged: any VIDEO link using the sound.
- **Instagram reel link**: yt-dlp (`uv tool install yt-dlp`, found at `~/.local/bin` too)
  downloads the reel's AUDIO track — i.e. the sound exactly as it plays in that reel, which is
  the music plus any voice over it, and only as long as the reel. Worked without login on
  2026-10-05; if IG demands a login, `sound <link> --cookies chrome` hands yt-dlp Chrome's
  session (opt-in because macOS prompts for Keychain access).
- **YouTube / any yt-dlp URL** and **local audio files** also go through `sound`.

**The three parameters of the "function":** the clips in `clips/`, the sound link, and the
**ideal length in seconds** — `plan --length 10` (or `length 10` on an existing edit). The video
ends on the downbeat closest to that number (±half a bar), so 10 may come out 9.7 or 10.3;
`show`'s first line prints the real length. Default 30.

**How the cut grid is built** (`build_cuts`): the video starts on a beat (`audio_start`, default =
2 bars before the first drop when the drop is >12 s in, else 0) and ends on the downbeat
nearest `audio_start + length` (falling back to the last beat inside it). Every bar is classified calm/hype by RMS vs. the track median.
Cuts fall every `calm` beats in quiet bars, every `hype` beats in loud bars, on EVERY beat
for the `burst` beats before a drop, and the drop itself starts a `hold`-beat shot (the
hero clip, default the longest). No slot may exceed the longest clip. Defaults
`calm=4 hype=2 burst=4 hold=4`.

**How clips are assigned** (`assign_all`): longest gap gets the longest clip, and so on;
each use takes a different stretch of the clip (centred first, then unused footage), no
clip twice in a row, and it cycles when there are more slots than clips (24 slots over 11
clips is normal — `show` prints "clip used x2"). Per-slot in-points skip the first 0.3 s
of a clip (phone shake) and the last 0.15 s.

**Rendering is frame-exact:** slot lengths are computed in frames from cumulative rounding so
cuts never drift off the beat; `-ss` input seeking + `trim=end_frame` per slot; concat;
the sound is `atrim`med to the same length with a 0.4 s fade-out; `h264_videotoolbox`
12 Mbps (falls back to libx264). 1080x1920, 30 fps, AAC 192k. Verified on the first
render: every planned cut coincided with a detected scene change within one frame.

## Editing on re-prompt — what the user says → what to run

Slots are positions in the video (1..N, see `show`); clips are the source files (1..N, see
`sheet`). **When the user says "clip 7" they almost always mean the SOURCE clip** (the
file numbered 7). The `cN` form targets "the slot holding clip N" and errors if that clip
sits in several slots — then read `show` and pick the slot number yourself.

| user says | run |
|---|---|
| "swap clips 3 and 8" | `swap c3 c8` (or `swap 5 12` by slot) |
| "get rid of clip 7" / "don't use clip 7" | `drop 7` (excludes it; its slots are refilled) |
| "put clip 7 back" | `restore 7` then `set <slot> 7` |
| "clip 2 should be on the drop" | `hero 2` |
| "hold that shot longer" / "slot 9 is too short" | `merge 10` (joins slot 10 into 9) |
| "cut faster there" | `split 9` |
| "start clip 4 later / use the part where …" | `in <slot> <seconds>` or `set <slot> 4 --at <seconds>` |
| "move the laptop shot to the start" | `move <slot> 1` |
| "make it 20 seconds" | `length 20` (rebuilds the whole edit) |
| "start the song at the drop" | `start <seconds>` (rebuilds) |
| "fewer cuts" / "more cuts" | `density calm=8 hype=4` / `density hype=1` (rebuilds) |
| "different clips in the same cuts" | `shuffle` |
| "put text on it: …" | `caption "…"` (`caption none` clears) |
| always after an edit | `render` — then tell them `out/final.mp4` is updated |

Every edit command re-prints the plan; `render` prints the path, length and version copy.
Edits that only touch slots keep every other slot exactly where it was. `length`, `start`
and `density` rebuild the grid AND the clip order (say so when you run them).

A clip shorter than a slot can't go there — the command refuses with the two lengths.
Options then: `merge`/`split` to change the slot, or pick a longer clip.

## Checking a result without watching it

`board` → Read `out/_board.jpg` (one frame per slot, labelled with slot and clip numbers).
`sheet` → Read `out/_clips.jpg`. To extract a specific frame: `ffmpeg -ss <t> -i out/final.mp4 -frames:v 1 x.jpg`.
To confirm cuts are on beats: scene-detect the render (`select='gt(scene,0.25)',showinfo`)
and compare `pts_time`s to `project.json` cuts minus `cuts[0]`.

## Known limits / later

- Beat tracking is librosa's; the "drop" is the biggest bar-to-bar energy jump (≥1.3×). Flat
  songs report no drop — cuts then follow calm/hype only. Downbeats are a phase guess.
- Landscape clips are centre-cropped to 9:16 (`clips` warns).
- No transitions, no speed ramps, no zoom — hard cuts only, on purpose (that's the format).
- Baked-in commercial audio can be muted by TikTok/IG content ID. The user accepts this.
- yt-dlp comes from `uv tool install yt-dlp` (`~/.local/bin`). **Never `brew install yt-dlp`
  here** — on 2026-10-05 it started compiling LLVM from source and had to be killed.
- `setup` checks ffmpeg / yt-dlp / the font and installs the headless browser — run it once
  on a new machine (Christian's).
