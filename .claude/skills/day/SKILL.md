---
name: day
description: The whole Young Vibas loop in one command. "/day plan" picks tomorrow's video idea from the research and writes the shot list; "/day N" cuts the day's clips into two finished videos with a trending sound, the hook on screen and a checked caption; "/day post N" hands over the files ready to upload. Use whenever Christian or Ernest says "day N", "plan tomorrow", "what should we shoot", "cut today's clips", or "ready to post".
---

# /day — plan → cut → post

Three forms. Always start with `python3 tools/day.py` (read-only): it prints the next day
number, whether the research is stale, which ideas were already used, and what each day
has. Decide from that, not from memory. Read `.claude/skills/beatcut/SKILL.md` before
cutting; it is the editing procedure and lessons log.

## `/day plan` — tomorrow's idea and shot list (before filming)

1. If `swipe_stale: yes` or the swipe file is missing, run `/ig-viral vibe coding` first
   and come back. Otherwise read `~/.claude/instagram/swipe.md`, the "Hand-read formulas"
   section and the links.
2. Pick ONE formula not yet in `projects/ideas.md` (rotate; never two days in a row on
   the same formula). Write the hook line in Young Vibas' shape: lowercase, ≤10 words,
   names a specific tool or number, no call to action. The bit is two guys, gym/life ×
   coding, no talking, hard cuts.
3. Run `/ig-reel` with that line and formula so the shot list comes from the same place
   captions do. Keep its output to: the on-screen line, 5–8 shots (what, where, who,
   ~10–20 s each, which one is the opener and which one is the drop moment), and one
   sentence on why this formula.
4. Save it as `projects/dayN.plan.md` (N = `next_day_to_plan`) with the line, the formula
   name, the shot list and two reference links from the swipe file. Append
   `dayN  <formula>  <line>` to `projects/ideas.md`.
5. Reply with the shot list only. Tell them the folder to drop clips in:
   `~/Desktop/beatcut/clips/dayN/`.

## `/day N` — cut the day (after filming)

Inputs: the clips in `clips/dayN/`; the hook from `projects/dayN.plan.md` if it exists
(else take the best-fitting formula from the swipe file and write one, and say so); an
optional sound link in the message.

1. `frames` every clip, Read the sheets. Know what happens when before planning. Carve a
   long take whose punchline sits in its tail into its own pieces (`ffmpeg -ss -t -c
   copy`), as day 3 did with the bench takes.
2. Sound. If no link was given: research this week's trending sounds (Metricool,
   SocialPilot, CreatorDB weekly lists; TikTok Creative Center is login-walled), pick one
   whose described use matches the bit, prefer a clear drop, one line of reasoning.
   `-p dayN_1 sound "<link>"` (the `-p` goes BEFORE the subcommand). Never run `sound`
   on a path inside `sound/`; copy `projects/<other>.sound.json` to reuse a sound.
3. Variation 1, `dayN_1`: `plan --clips … --first <opener> --story <order> --length 30`
   (tight), `caption "<hook>"`. Put the strongest joke moment on the drop with
   `set <dropslot> <clip> --at <sec>`. `board`, Read it, fix in-points; no two adjacent
   slots from the same take with the same framing.
4. Variation 2, `dayN_2`: different opener, different order or `--random --seed`,
   `--preset loose` if the sound is flat, a different sound if a second good one is
   known. It must not look like the same edit with a new song.
5. `render` both. Verify: scene-detect the output and check every planned cut within one
   frame; `ffprobe` shows an AAC track. Fix and re-render anything the board or the
   detector caught.
6. Caption: `/ig-caption` for `dayN_1` with the hook as line 1 (the video carries no
   spoken hook, so the caption is the content), then `/ig-human` until PASS, save to
   `out/dayN/dayN_1.caption.txt`; copy for `dayN_2` with a different ask.
7. SendUserFile each mp4 with its storyboard as it finishes. One line each: what is in
   it, length, where the drop lands, the full path `~/Desktop/beatcut/out/dayN/dayN_V.mp4`.
   Paste the caption in the final message. Append the day's lessons to the beatcut log.

## `/day post N` — hand-off

1. `python3 tools/day.py`; confirm `dayN_1` is rendered and has a caption, else say what
   is missing and do it.
2. SendUserFile `out/dayN/dayN_1.mp4` and paste the caption as a code block. Then the
   same for `dayN_2` with "post this one a day or two later".
3. Three-line checklist: upload the mp4 as a Reel, paste the caption, add the sound
   name in the post if Instagram asks (the audio is baked in). Nothing is posted by
   Claude.

## Re-prompts

"swap clips 3 and 8", "get rid of clip 7", "hold that longer", "make it 20 seconds",
"different sound": run the matching beatcut edit on the right `-p` project, `board`,
`render`, re-send. Table in `CLAUDE.md`.
