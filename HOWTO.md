# How to run a day, start to finish

Two ways to drive this. **The chat** (Claude Code in this folder): say what you want and
Claude runs the tool, the research and the caption skills. **The buttons** (`uv run ui.py`,
then open http://127.0.0.1:8765): every pipeline step as a form, no commands to remember.
Both read and write the same files, so you can mix them.

## Once, on a new machine

1. Follow `SETUP.md` (tools, CapCut seed project, permissions). Christian's Mac is done.
2. Fill in `~/.claude/instagram/voice.md`. Every Instagram skill reads it; empty means a
   generic voice. Ten minutes, or paste three of your own captions in the chat and say
   "write my voice.md from these".
3. In the chat, run `/ig-profile` once on the Young Vibas profile.

## Monthly

- `/ig-viral` in the chat refreshes the swipe file at `~/.claude/instagram/swipe.md`:
  which premises are over-indexing in the vibe-coding niche right now. Formulas last a
  season. The 2026-10-07 read is in there already.

## Each week

1. `/ig-plan` turns the swipe formulas into a shoot list: the bits for the week and when
   they post.
2. After the week's posts: paste the insights into `/ig-audit`. It tells you which sound,
   hook and variation won, and that feeds next week's list.

## Each shoot day: three commands

1. **`/day plan`** (the night before). Claude picks tomorrow's idea from the research,
   rotating formulas, and gives you the on-screen line and a shot list of 5–8 shots.
   Saved as `projects/dayN.plan.md`.
2. **Film it.** Phone, portrait, 10–20 s per shot, no talking. AirDrop the clips into
   `~/Desktop/beatcut/clips/dayN/`.
3. **`/day N`** (after filming). Claude looks at the footage, picks a trending sound that
   fits, cuts two variations, burns the line on screen, writes and checks the caption,
   sends you both mp4s. Say what to change in plain English ("swap 3 and 8", "lose clip
   7", "make it 20 seconds") and it re-cuts.
4. **`/day post N`**. Both files and the caption, ready to upload. Post the second
   variation a day or two later. Paste comments into `/ig-reply` when they come in.

## What goes where

| thing | path |
| --- | --- |
| clips for a day | `clips/dayN/` |
| the finished video | `out/dayN/dayN_V.mp4` |
| every earlier render | `out/dayN/versions/` |
| the storyboard | `out/dayN/_dayN_V_board.jpg` |
| the caption for the post | `out/dayN/dayN_V.caption.txt` |
| the edit itself (what the buttons change) | `projects/dayN_V.json` |
| downloaded sounds | `sound/` |
| the swipe file the Instagram skills read | `~/.claude/instagram/swipe.md` |
| your voice, read by every Instagram skill | `~/.claude/instagram/voice.md` |

## Rules we settled on

- Hard cuts only. No transitions, no speed ramps, no zoom. That is the format.
- The opener must read in half a second. The drop gets the biggest visual.
- The premise is the product. Name a specific tool or number, no call to action in the
  hook, premise in ten words or fewer. That is what the outliers in the niche do.
- Two variations per folder of clips, posted on different days, then audit which won.
