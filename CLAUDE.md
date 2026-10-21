# beatcut — cut phone clips to a TikTok sound, one mp4 out

**Fresh machine? `SETUP.md` is the runbook** (tools, CapCut seed project, macOS permission
grants, smoke test, troubleshooting). This file is the command reference and the record of
every gotcha; `.claude/skills/beatcut/SKILL.md` is the daily workflow + lessons log.

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

## Ernest's defaults since 2026-10-09 (read before planning anything for him)

- **HDR clips get an SDR proxy, automatically.** iPhone clips from day 2 on are HEVC
  10-bit HLG BT.2020. Rendering them straight to SDR flattened the picture ("I hate the
  lighting changes"). This ffmpeg has no `zscale`/`libplacebo`, so `sdr_proxy()` tone-maps
  each HDR clip ONCE with macOS's own `avconvert --preset Preset3840x2160` (AVFoundation,
  the same mapping QuickTime/Photos use = the phone look) into `clips/<folder>/.sdr/<stem>.mov`
  (H.264 4K, rotation baked in), and `scan_clips`/`frames` point every stage at the proxy
  (`clip["src"]` keeps the original). ~2× realtime; build proxies BEFORE launching parallel
  agents (two processes writing the same proxy would corrupt it). No other color work,
  ever, unless he asks.
- **Free cuts are the default; beats are opt-in.** `plan` now cuts at seeded random shot
  lengths per preset (`FREE_RANGES`: tight 0.6-1.4 s, loose 1.4-3.2 s, chill 3-6 s) and
  the sound just plays underneath. `--sync` restores the beat grid (drops, bursts, holds).
  He says "sync it to the audio" when he wants that.
- **`final/` is the deliverable folder.** `render` copies the finished mp4 to
  `final/<name>.mp4` (flat). `out/` stays the workspace (boards, frame sheets, versions);
  he does not want to navigate it. "Keep only X" = delete the rest from `final/` and `out/`.

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
never a wrap-around), `--random` (every slot: a random clip weighted by footage left, never
the same clip twice in a row, at a random in-point that overlaps no earlier pick — "random
angles in random order"; seeded by `--seed`; this is what day2_5 used over the take's first
and last 22 s, which were carved out as their own clips with `ffmpeg -ss/-t -c copy` because
"only use these parts of the clip" is easiest as two clips), `--preset tight|loose|chill`
(density presets; `density loose` on an existing project). With `--story`, `hero` is ignored (the drop takes whatever story moment
falls there — pick the story/seed so a strong moment lands on it, check `board`). A sound
shorter than `--length` plays to its END (meme sounds keep the punchline in the tail).
`frames <clip…>` writes a timestamped frame sheet per clip (`out/_frames_<clip>.jpg`) — the
way to SEE a long take before deciding the story.

## Remix — four new posts from a video that worked (2026-10-19)

`-p dayN_V remix [--render] [--only hook,sound] [--sounds a.mp3 b.mp3]` cuts FOUR new projects
from the source's clips, each different enough to be a new post, named with the next free
`dayN_K` numbers and tagged `remix_of: dayN_V` + `remix: <kind>` in their project.json
(`plan` keeps both tags when a remix is re-planned; `show` prints "hook remix of dayN_V"):
- **hook** — 8 s, tight, random angles, opens on the strongest shot (the drop's clip, else
  the hero, else the source's opener, else the most-used clip).
- **sound** — the source's story (or random) on ANOTHER sound from the pool, loose pace.
- **reorder** — 15 s, random angles with a new seed, a different opener (the source's slot 2).
- **long** — 30 s, chill, a story of the clips the source used LEAST, first; on a second
  other sound when the pool has one.
Other sounds = `--sounds` in order, else `sound/*.mp3` minus the source's, the ones with a
clear drop first, then newest. The start in each sound is the suggested start unless the
video would not fit before the sound ends (a drop near the end gave a 6 s video) — then as
late as the length allows. Each remix keeps the source's on-screen hook; the hook, caption
and opener are what "Remix with Claude" then changes. Seeds derive from the source's
(+11, +1, +23, +5) so a second `remix` of the same video gives the same four. The last line
is `REMIXES: name1 name2 name3 name4`.

**Any finished video, not only a project (2026-10-19):** `remix --video <mp4|LINK> [--name F]
[--cookies chrome]` first imports it — a TikTok / Instagram / YouTube LINK is downloaded into
`clips/F/.source/` first (`fetch_video`: TikTok through tikwm's `hdplay`/`play`, the post
without the watermark; the rest through yt-dlp as mp4; F defaults to `remixN` for a link),
then `shots` (ffmpeg scene detection, `select='gt(scene,0.3)'`, no shot shorter than
1.5 s so each can hold a slot, re-encoded H.264 without audio into `clips/F/shot_NN.mp4`),
`sound <mp4>` (its audio joins the pool as `sound/<slug>.mp3`), then a project `F_1` replays
the shots in story order on that sound (`imported_from` in its json; preset from the median
shot length, stepped down by `cap_preset` to a pace the shots can hold) — and remixes THAT.
Too little footage for a recipe's order (a two-shot talking head) falls back to the plain
assignment, which reuses footage, and only then skips the recipe. Prints `SOURCE: F_1` before `REMIXES:`. `shots <video>
[--into F] [--min-shot S]` is the import alone. In the app, **/remix** (sidebar + home
header): drop one video → `POST /api/remix` (multipart; stored at `clips/F/.source/<file>`,
a dot-folder so it is not a clip; refuses an existing folder) or paste the post's link
(JSON `{link, name?, cookies?}` to the same route) → one job `remix --video … --render` → the
source's page with the four cards; the page also lists every rendered
video with its own Remix ×4. **Remix ×4** on a video page runs
`remix --render` as one job (`POST /api/projects/<name>/remix`, `{only, render}`) and comes
back to the source, whose page shows the family (`RemixStrip`: "hook cut of X" on a remix,
the four cards with their status on the source); feed cards carry a "remix of X" tag.
**Remix with Claude** is an ask: run `remix`, read each board, improve openers/sounds,
`caption` a different hook line on each, write each post caption, render all four.

## Reformat — a posted reel, same cut, three framings (2026-10-19)

A posted reel is already its best cut; re-dealing its shots only makes a worse one (seen
on the first link remixes). `reformat --video <mp4|LINK> [--name F] [--cookies chrome]
[--only hook,reply] [--hook "…"] [--lines "a|b|c"] [--voice Samantha] [--comment "…"
[--user handle]] [--render]` keeps the cut and makes THREE projects `F_1..3` of
`kind: "reformat"` (no cuts/slots; `source` = the mp4 under `clips/F/.source/`, F defaults
to `reelN` for a link): **hook** (a new hook line on screen), **narrated** (2-3 lines said
in the TikTok text-to-speech style — by **ElevenLabs** (`voice: "eleven"` = the voice in
`web/.env.local`'s `ELEVENLABS_VOICE_ID`, with `ELEVENLABS_API_KEY`; `eleven:<id>` for
another; model `eleven_multilingual_v2`, `ELEVENLABS_MODEL` overrides; the CLI reads
`web/.env.local` itself, `web_env()`) when a key is set (Christian's, 2026-10-19), else by
the Mac's `say -v Samantha` — each line shown as it is said, the original audio ducked to
0.3 under it) and **reply** (the comment the
video answers in a white TikTok reply bubble; "Reply to @user" only when `--user` names
a real commenter, else "replying to a comment"). The audio joins the pool, a frame sheet
goes to `out/F/_frames_<stem>.jpg` and is copied as each project's board. Overlays are
placed in the quietest band of the frame (`quiet_y`: least horizontal edge detail across
four sampled frames) so they do not sit on the source's own text. `render` on such a
project is `render_reformat` (scale/pad to 1080x1920, PNG overlays, amix); `show`,
`board` and `remix` know the kind. On one of them, `reformat -p F_2 --lines … --render`
sets its copy and renders. Prints `FRAMES:` and `REFORMATS: F_1 F_2 F_3`.
**reaction** (2026-10-19, silent): a character reacts in the corner — `avatar <name> [--image
<public url | file> | --prompt "…"] [--reactions nod,shocked,laugh,point,think]` generates one
5 s clip per reaction ONCE (without a picture it first DRAWS the character with Higgsfield's
Soul text-to-image, `higgsfield-ai/soul/standard`, 1:1 720p, `GENERIC_AVATAR` prompt by
default → `clips/_avatar/<name>/character.png` + `.json` with the hosted url the video
model is then fed) with **Higgsfield** image-to-video (Kling 3.0 std, sound off; `HIGGSFIELD_KEY_ID`
/ `HIGGSFIELD_KEY_SECRET` in `web/.env.local`, pay as you go ≈ $0.4 a clip; a local file is
sent as a data url, a public url as is; async: `status_url` polled every 5 s, `video.url`
downloaded) into `clips/_avatar/<name>/<reaction>.mp4`; `avatar --list` shows them. A
reaction reformat (`reactions: [{t, kind}]`, `--reactions "0:nod,2.5:shocked"`, empty =
spread evenly; `--avatar`, default the first character) overlays the clip for each window as a
rounded square (38 % of the width, bottom-left above TikTok's caption zone, `pip_mask` +
`alphamerge`, looped to the window) — the original audio untouched. It is made with the
other three whenever a character exists; the Claude ask also picks the moments.
**Green screen, and cheap rounds (2026-10-19, after the first avatar "looked horrible and cost
too much"):** `avatar <name> --image-only --prompt "… in front of a solid bright chroma key
green screen …"` draws the character alone (a cent; `character.json` notes `green: true`
when the prompt says green screen / chroma). A green character is composed TikTok-green-
screen style: `chromakey=0x00ff00:0.28:0.12,despill`; `avatar_pos` **corner** (default, Christian: "the
natural reaction" — 46 % of the width, bottom-left, above the caption zone) or **center**
(82 %, bottom-centre, shoulders off the edge); `reformat --pos corner|center` — and a character with NO clips yet is used as a still that
breathes in place (crop wobble) for the whole video, so the look is judged before any video
is bought. Clips then come from the cheapest model by default (`kling-2.5` turbo standard
≈ $0.21 per 5 s; `--model kling-3` ≈ $0.56) with calm, product-presenting reactions
(`agree`, `present`, `listen`, `thumbs`, `nod`…; every prompt tells the model to keep the
green background; default set agree,present,listen). Christian's pick of the girl
character decides which of `girl1..3` becomes the house avatar.
**Real comments (2026-10-19, Christian: "the comment reply thing" is the keeper; the avatar is
off by default now — `--avatar` only):** `comments <link>` lists a post's top comments
(TikTok keylessly through tikwm's `api/comment/list`, most liked first; others through
yt-dlp's `--write-comments`, best effort). `reformat --video <link>` fetches them into
`clips/F/.source/comments.json` and onto the reply project (`comments: [{user, text, likes}]`,
top 20); `--pick N` answers the N-th (`comment` gets `user`, `likes`, `pick`, so the bubble
says "Reply to @user's comment" for real). `reformat -p F_3 --another --pick M [--render]`
is the chain: one more reply to the same video answering another comment, as a new project
(same source, comments and board). The reply editor lists the comments to click; "Another
reply with this comment"; the Claude ask picks the comment with the best hook potential
(`--pick`) and only writes one when the list is empty.
**Styles (2026-10-19, "not just cut it up"):** two more reformat kinds change the FEEL of the
same cut, with ffmpeg and the pool only (`render_style`): **goofy** — punch-zooms (`scale`
with `eval=frame` + `crop`, +22 % for 0.55 s) and a shake on the moments, a boom / 'bruh' /
'nah' / whoosh on the reveal, crunchy audio (`bass=g=7,acrusher`), an all-caps big caption,
optionally a meme sound from the pool under it; **cinematic** — slow motion (2.5×, 1.2 s)
on the key moments via trim/setpts/concat (the length grows), a riser leading into each,
letterbox bars, warm grade + vignette + grain, fades, a pool sound INSTEAD of the original
audio (the project's `style_sound`, else the first pool sound that is not the source's),
a small caption at 80 %. `moments: [{t, fx}]` (`--moments "1.2:zoom,3:boom"`; fx per style
in `STYLE_FX`; empty = `default_moments`), `--sound <pool mp3>` (`''` = none), `--hook`.
The SFX shelf `sound/_sfx/` is synthesized on first use (`sfx()`: boom = 52 Hz sine +
brown noise, whoosh, riser = 2.5 s sweep, scratch; bruh/nah = the narration voice saying
it). They are made only with `--only …,goofy,cinematic`; the Remix page's style
checkboxes (both on by default) add them to the three framings; the Claude ask picks the
moments and the sound from the frames.
**hype (2026-10-19, Christian's feedback on the first styles: "the fifth is by far the best…
but the noise took out the audio… make the song in the background, add popping text, other
effects, pictures, be creative"):** `render_hype` parlays them — slow motion (2.2×, 1 s)
retimes the video AND the original audio (`atempo=0.5,atempo=0.909`), every other moment
is mapped through that retiming (`remap`); the ORIGINAL audio stays (bass +4) and the pool
song is DUCKED under it with `sidechaincompress` keyed by the original (`--sound`, else the
first pool sound ≠ source); goofy's zooms (+20 %, 0.5 s) and booms with a shake; lighter
bars (6 %) and grade; a riser into each slow moment; pop-in text (`t:pop:NO WAY`,
`pop_png`: big tilted caps, scale-in 0.14 s with a tiny overshoot), emoji (`t:emoji:😭`,
`emoji_png`: Apple Color Emoji renders only at 160 px, scaled), snapshots (`t:snap`,
`polaroid_png`: the source frame at t as a tilted polaroid with a shadow, pops in centred,
a whoosh); narration `lines` if any (shown at 66 %); the hook caption in the quiet band of
the middle third (not the top: the source's own text lives there). Moments carry an
optional third field for pop/emoji text. Hype is the Remix page's default style.
In the app the Remix page's default is **Reformat** (Re-cut ×4 is the other option,
for raw footage); the job lands on `/video/F_1?ask=reformat`, which fires a Claude ask
(`ReformatEditor`): read the frame sheet, write the hook, the narration and the comment
for all three, lint with /ig-human, render each, write the captions. The page edits the
copy by hand too (Save & render = `run` cmd `reformat`), and the three framings show as a
strip on each of them; feed cards carry a "hook reformat" tag.

## CapCut export — the edit as an editable project (2026-10-07)

`-p dayN_V export [--open]` writes the SAME edit `render` would bake (identical frame math)
as a CapCut desktop project in CapCut's draft store
(`~/Movies/CapCut/User Data/Projects/com.lveditor.draft/<dayN_V>/`): one video track with
every slot as a segment (clip + `sourceStart` in-point, so each cut can be dragged longer
or shorter in CapCut), the sound on an audio track offset to `audio_start`, 1080x1920 @30.
Media is COPIED into the draft's `assets/` (self-contained; ~200 MB–1 GB per project with
4K sources). **A re-run of `export` DELETES the same-named project first, CapCut edits
included** — Ernest's rule: the template always starts from the automation, he only
touches it afterwards, and re-running is exactly the moment he wants the old one gone.
Only `dayN_V` names are ever removed; CapCut's seed project is never touched. Then `open -a CapCut`: the project
is at the top of CapCut's list; there is no URL scheme to open a specific draft on macOS.

**Mechanism:** CapCut has no API; its drafts are plain JSON on disk. We do NOT hand-write
the format (it drifts per version): the export writes a **capcut-cli compile spec**
(`out/dayN/dayN_V.capcut.json`) and shells out to `capcut compile … --template auto`, then
the CapCut-9.x-on-macOS recipe from capcut-cli's version matrix: `sync-timelines --nested
--apply` (the app reads `Timelines/<id>/draft_info.json`, not only the root file),
`register --materials --apply` (else every clip shows "file inaccessible" on 9.1+), and
`lint --fix`. capcut-cli (`npm install -g capcut-cli`, found under nvm) is the only
dependency; `capcut doctor` checks the environment. Segment starts in the spec are the
running sum of the µs-ROUNDED durations: capcut-cli rounds each value separately, so
float starts left 1 µs gaps on the main track, which CapCut closes on open by shifting
every later clip left (lint `main-track-gap`). capcut-cli refuses to write a managed draft
while CapCut is running — `export` on an open project needs CapCut quit first
(`osascript -e 'quit app "CapCut"'`), then `--open` brings it back.

⚠️ **One-time per machine:** CapCut 9.x refuses drafts built from capcut-cli's bundled
6.5-era template — seen live 2026-10-07: "Couldn't use project — Current project is from
an unusual path" — so `--template auto` seeds new drafts from the NEWEST APP-AUTHORED
project in the store. Before the first export, open CapCut, create one empty project
(any name), and close it. On this Mac that seed is the empty project **`1007`** in the
store — never delete it (if it goes, create another). If the store is empty the export
stops with that message.

**Every export carries the caption layer, styled (2026-10-21, Ernest).** After `lint --fix`
the export runs `capcut add-text` for the whole length and then restyles the text material in
every draft JSON copy (`add_capcut_caption` / `_style_capcut_text`): `fonts/TikTokSans-700.ttf`
copied into the draft's `assets/fonts/` and set as `font_path` AND `content.styles[].font.path`,
white, a thin black stroke (`styles[].strokes` width 0.06 + the legacy `border_*` fields = the
IG "Classic" look; 0.15 reads as TikTok's), size 9, centred at `clip.transform.y` 0.55, full
length. The text is the project's `caption` if set, else "caption goes here" for him to retype
(`CAPCUT_CAPTION` in beatcut.py). Why JSON: CapCut's font picker can't reach a local TTF and
capcut-cli's `add-text`/`text-style` can't set fonts. A 9.x draft keeps up to FIVE live copies
(root `draft_content.json`, `draft_info.json`, `template-2.tmp`, `Timelines/<id>/draft_info.json`
+ its `template-2.tmp`) — the app reads the nested one once it exists, capcut-cli writes the root
ones; patch all or they disagree. Order matters: `lint --fix` clamps any caption to 7 s, so the
caption is added after it. Scratch exports (`--drafts <dir>` outside the store) no longer quit
CapCut. To add the layer to a draft he has ALREADY edited in the app, do NOT re-export (that
deletes his edits): quit CapCut, back up the folder, apply the same restyle to all copies.

**`--open` lands INSIDE the project (2026-10-07).** CapCut has no deep link for a draft
(its `capcut://` scheme only targets features; four draft-shaped URLs were ignored), so
`open_in_capcut()` launches the app, waits for the home window, closes any front dialog
via its AX close button, then sends a REAL mouse click (Quartz `CGEvent`, pyobjc) at the
first project tile — `CAPCUT_FIRST_TILE = (306, 782)` points from the window's top-left,
valid for any normal window size because the sidebar and the sections above the grid are
fixed-size; the newest project is always the first tile. Success = CapCut starts writing
its own files into the draft folder (`Timelines/`, `draft_settings`, `Resources`…) —
the window's AX title stays "CapCut" in both views, so it is no signal. Accessibility
`click at` is IGNORED by CapCut's home canvas; only the Quartz click works. Requirements,
granted by Ernest for the Claude Code runtime (`~/Library/Application Support/Claude/
claude-code/<ver>/<hash>/claude.app`, listed as lowercase `claude`): **Accessibility**
(window geometry + clicks) and **Screen Recording** (only for capturing the window to
debug; `screencapture -l <CGWindowID>` captures CapCut even when the Claude window covers
it — see the winshot recipe in the skill). Without the grants, `--open` just launches
CapCut and prints "click the first tile". The user's shell runs `uv run beatcut.py` as
their own process, so no sandbox flag is needed there; from Claude's Bash tool the call
needs the sandbox disabled. Installed here: CapCut 9.5.0 (Homebrew cask), capcut-cli 0.28.0. The
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
| "cut faster there" (beat-synced edits) | `split 9` (cuts slot 9 on its middle BEAT — only meaningful with `--sync`) |
| "cut shot 9 two seconds in" / "add a cut at 12.4" | `cut 9 +2` / `cut 9 12.4` (free cuts: a new cut at that time of the VIDEO, as `show` prints it; `+N` = N s into the slot; the same clip runs on across the cut, then `set`/`in` the new slot) |
| "start clip 4 later / use the part where …" | `in <slot> <seconds>` or `set <slot> 4 --at <seconds>` |
| "move the laptop shot to the start" | `move <slot> 1` |
| "make it 20 seconds" | `length 20` (rebuilds the whole edit) |
| "start the song at the drop" | `start <seconds>` (rebuilds) |
| "fewer cuts" / "more cuts" | `density calm=8 hype=4` / `density hype=1` (rebuilds) |
| "different clips in the same cuts" | `shuffle` |
| "remix this" / "four more posts from this" | `remix --render` (see Remix) |
| "this reel did numbers, repost it" (a posted video) | `reformat --video <link> --render` then the copy (see Reformat) |
| "put text on it: …" | `caption "…"` (`caption none` clears) |
| always after an edit | `render` — then tell them `out/final.mp4` is updated |

Every edit command re-prints the plan; `render` prints the path, length and version copy.
Edits that only touch slots keep every other slot exactly where it was. `length`, `start`
and `density` rebuild the grid AND the clip order (say so when you run them).

A clip shorter than a slot can't go there — the command refuses with the two lengths.
Options then: `merge`/`split`/`cut` to change the slot, or pick a longer clip. `cut` refuses a
time outside the slot or a half shorter than one frame (1/30 s).

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

## The app: `web/` (Next.js, 2026-10-15; replaced the Flask `ui.py`)

`cd web && npm run dev` → http://localhost:3000 (or `preview_start beatcut-web` from Claude;
see `.claude/launch.json`). A Next.js 16 app (App Router, TypeScript, Tailwind) that is a
UI over THIS folder: every button runs `uv run beatcut.py …` as a **job** (one beatcut
process at a time, log streamed over SSE to `/jobs/<id>`, then it opens the result), and
every page reads the same `projects/*.json`, `out/<folder>/`, `sound/`, `clips/` files the
CLI writes, so the CLI, the chat and the buttons never disagree. Nothing in `web/` edits
an edit by hand; the only direct writes are the sound pointer (`projects/<name>.sound.json`,
same reason as before: `sound sound/x.mp3` TRUNCATES the file), the post caption
(`out/<folder>/<name>.caption.txt`), the thumbnail cache (`out/<folder>/.thumbs/`) and
the chat index (`out/.app/chats.json`).

Pages: `/` **the feed (2026-10-19)**: the **New video** button on top, then one card per
video, newest first — poster frame (`/api/slot-thumb/<name>/1`, else the storyboard, else
a placeholder), name, shoot, sound, length, the on-screen hook and ONE status chip; under
the feed a one-line **Shoots** strip (each folder a link to `/shoot/<folder>`, plus the
planned-not-shot plans) and the setup warnings as before · `/new` (the guided flow, below)
· `/shoot/<folder>` (clips, shot list, frame sheets, videos from it, and "New video from
these clips" on top, which is `/new?folder=<folder>` = the flow at its sound step) ·
`/video/<name>` (toolbar, player + **timeline**, storyboard and "All commands" collapsed,
post caption, versions, and a **Post it →** link in the title) · `/video/<name>/post`
(the post step, below) · `/videos` · `/sounds` (the pool, add by link) · `/jobs` ·
`/howto` (HOWTO.md). API routes live under `web/src/app/api/`; `GET /api/state` dumps
folders/projects/sounds/health as JSON. The nav's first entry is "Home".

**The status chip (`StatusChip`, on the feed cards and the `/videos` and `/shoot/<folder>`
rows) is one of, in this order:** `cutting…` / `rendering…` with the elapsed seconds while a
job for that project runs (the feed card also draws an indeterminate bar and the step
names `plan → board → render` with the current one lit) · `posted <date>` · `needs render`
(never rendered, or edited since) · `ready to post`. Live state comes from `LiveJobs`: one
client store polling `GET /api/jobs` every 2 s while any job runs (10 s idle), mounted once
per page; when a job finishes it calls `router.refresh()` so the chip settles on what is on
disk. `jobs.ts` derives `project` (from `-p <name>`) and `steps` (the subcommand of each
command) when a job starts, and `/api/jobs` adds `step` = the number of `$ ` lines in the
log so far minus one (`web/src/lib/jobmeta.ts` holds those pure helpers).

**Posted = `out/.app/posted.json`** (`{ "<name>": { postedAt, platform?, url? } }`,
`web/src/lib/posted.ts`; `PUT`/`DELETE /api/projects/<name>/posted`; `deleteProject`
drops the entry too). It is the user's own note that they uploaded the video — **the app
never posts anything**, it has no account. `/video/<name>/post` is the hand-off: the
finished mp4 (`final/<name>.mp4`, a Download button via `/api/media/...?download`), the
on-screen hook, the post caption (`CaptionEditor`) with a **Copy caption** button (copies
the SAVED caption), a three-item checklist (upload as Reel/TikTok, paste the caption, add
the sound by name), and **Mark as posted** (TikTok / Instagram / both, optional link) which
writes the note and returns to the feed; a posted video shows **Unmark** instead.

**Starting a video = `/new`, three steps (2026-10-15; the old "Cut it" form at the bottom
of the shoot page is gone):**
1. **Clips.** A folder name (default the next free `dayN`, counting clip folders, plans and
   projects; editable) and a drop zone. Files go to `clips/<name>/` through
   `POST /api/folders/<name>/clips` (multipart, busboy, each file streamed to a `.part`
   file then renamed — never held in memory; original filenames kept; refused: anything
   not .mov/.mp4/.m4v, names with `/` or `..`, a name already in the folder, a folder
   name outside `[A-Za-z0-9_][A-Za-z0-9 _.-]*`). One request per file, so the numbered
   thumbnails appear as each one lands. Or click an existing folder instead.
   `GET /api/folders/<name>/clips` returns the numbered clips + the next project name.
2. **Sound.** The pool as cards (title, author, length, bpm, first drop, `<audio>`, which
   videos used it); click one. A paste-a-link box runs `sound <link>` as a job
   (`POST /api/sounds`), polls `/api/jobs/<id>` and selects the newly added file when it
   is done. **Let Claude pick** sends an ask (see "Claude in each step" below): Claude
   looks at the clips' frame sheets and the pool (or downloads a trending sound) and
   ends with `SOUND: sound/<file>.mp3`; the step re-reads the pool and selects that file
   (if the line is missing, the list just refreshes).
3. **Cut.** Length and preset as segmented controls, the opener by clicking a thumbnail,
   Story vs Random as two cards, the rest (video name, story order, seed, hook, `--sync`,
   render now) under "More options". "Cut it" posts to the same `POST /api/cut` as before
   → `/jobs/<id>` → the video page. No second way to run the CLI was added.

**The timeline (2026-10-15) is how an edit is made in the app.** Under the player, one
tile per slot (width ∝ length, min 44 px), showing the slot number, clip number, length,
`DROP` and `★ hero`; a playhead follows the `<video>` and the current tile lights up;
clicking a tile seeks to it; ← → move the selection, space plays/pauses. Dragging a tile
to the EDGE of another runs `move`, dropping it ON another runs `swap`. The side card
for the selected shot runs `set` (clip grid), `in` (a scrubber that previews the frame
and commits on release), `merge <slot+1>` ("Hold longer"), `cut <slot> <playhead>`
("Cut here", when the playhead is inside the shot), `split` ("Cut in half"), `drop`
and `hero`. Nothing asks for confirmation — the next action undoes the last and every
render is versioned. Every action is the same `POST /api/projects/<name>/run` job the
forms use (the job log shows the exact command), so the CLI stays the only writer. The
tile frames come from `GET /api/slot-thumb/<name>/<slot>` (clip at in-point + half the
slot, i.e. the `board` frame; HDR clips read their `.sdr/` proxy when it exists), cached
in `out/<folder>/.slots/` under a name holding clip, in-point and length, so an edit
invalidates it; the scrubber preview is `GET /api/clip-frame/<folder>/<stem>?t=`, cached
in `out/<folder>/.frames/`. The number-keyed forms and the slot table live on under
"All commands" at the bottom of the page. Components: `VideoEditor` (player + card +
keyboard), `Timeline` (tiles, playhead, drag), `SlotCard`, `EditPanel` (`EditToolbar`
+ `AllCommands`).

**Claude in the app:** the side panel (bottom-right button on every page) is the **Claude
Agent SDK** (`@anthropic-ai/claude-agent-sdk`) running the same agent as Claude Code with
`cwd` = this folder, the `claude_code` system-prompt preset plus a short note about the
page the user has open (`project:<name>` / `folder:<name>`), all setting sources (so
CLAUDE.md, `.claude/skills/*` and the ig-* skills in `~/.claude` load) and
`bypassPermissions` — it runs beatcut for real, nothing is simulated. Needs
`ANTHROPIC_API_KEY` in `web/.env.local` (pay per token; `BEATCUT_MODEL` overrides the
model, default `claude-opus-5-5`). Turns stream as NDJSON from `POST /api/chat`
(`web/src/lib/agent.ts`); the conversation continues through the SDK session id
(`resume`), so a thread survives a restart; the page next to the panel re-reads the
folder after every tool call. Chats are listed in the panel's header; "Stop" interrupts.
When you (Claude Code) and the app both touch a project, the app wins nothing: it is the
same files. The SDK signs in with `ANTHROPIC_API_KEY` when `web/.env.local` has one, else
with the Claude Code login on this Mac (`lib/chatAuth.ts`; the key that was in the main
checkout's `.env.local` on 2026-10-19 is a `sk-ant-usr-…` token the API rejects, so the
login is what actually runs the chat).

**Claude in each step (2026-10-19):** pages ask Claude through one helper,
`askClaude()` in `web/src/components/chat/ask.ts` — a `beatcut:chat` window event the
panel listens for: it opens, optionally starts a NEW thread, prefills the prompt and,
with `send: true`, sends it at once; the user turn shows where it came from ("from Fix
it · day3_1"). A sent ask returns a promise that resolves when the turn is done (the
panel answers with a `beatcut:chat:done` event carrying the final text, `isError`,
the session id); while one runs, another sent ask is refused ("stop it first"). The
asks, each a new thread with the page's context:
- **Fix it** box under the player (`VideoEditor.tsx`): one line ("swap 3 and 8"), Enter
  sends it; "Claude is editing…" under the box until the turn is done, then its last
  line; three example chips fill the box. The timeline/storyboard follow by themselves
  (the panel calls `router.refresh()` after every tool result).
- **Write with Claude** in the caption card (`CaptionEditor.tsx`): "/ig-caption, lint
  with /ig-human until PASS, save to the caption file"; at done the editor re-fetches
  `GET /api/projects/<name>/caption` into the box.
- **Let Claude pick** in the /new sound step (`new/SoundStep.tsx`, above).
- **Ask Claude about this shot** in the slot card (`SlotCard.tsx`): "Look at slot n
  (clip c at Xs) on the storyboard… suggest one change".
- **Remix with Claude** in the toolbar (`EditPanel.tsx`): run `remix`, tune the four, hooks,
  captions, render (see Remix above).
The agent's appended system prompt (`lib/agent.ts`) says these arrive from buttons and
may be terse, that a Fix-it line is an edit to the open project (run it, board,
render), that a shot question must be checked on the storyboard first, and that the
sound pick must end with the `SOUND:` line.

**`/day` is the loop (2026-10-08):** `/day plan` (idea + shot list from the swipe file,
rotating formulas via `projects/ideas.md`, saved as `projects/dayN.plan.md`), `/day N`
(cut two variations, hook on screen, caption), `/day post N` (hand-off). `tools/day.py`
prints the facts the skill decides from. Skill text: `.claude/skills/day/SKILL.md`.

## Captions skill — real captions from the niche (2026-10-21)

`.claude/skills/captions/` (symlinked to `~/.claude/skills/captions`): `captions.jsonl` is
~3.8k TikTok/YouTube posts (captions as posted, views, likes, per-creator `multiple`), of
which ~1k are short niche meme captions about code / AI / Claude; `scripts/find.py` retrieves
by keyword / top-by-multiple / random sample; `patterns.md` is the distilled read (POV,
imagine, first-person fear-as-a-bit, "every dev" win; questions and "you" advice lose).
Every caption request reads it first. Harvest: hashtag feeds via the keyless tikwm
`challenge/posts` endpoint (search/user endpoints are 403) + creator profiles via `yt-dlp
--flat-playlist`; the browser pane and headless Chromium both get empty bodies from TikTok's
own API, don't use them for this. `scripts/build.py` rebuilds from `raw/`.
