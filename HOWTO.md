# How to run a day, start to finish

Two ways to drive this, and they are the same thing. **The app** (`cd web && npm run dev`,
then open http://localhost:3000): every step as a button, the clips numbered, the
storyboard on the page, and Claude in a side panel on every page. **The chat** (Claude
Code in this folder, or that side panel): say what you want and Claude runs the tool, the
research and the caption skills. Both read and write the same files, so you can mix them.

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
2. **Film it.** Phone, portrait, 10–20 s per shot, no talking. AirDrop the clips to the
   Mac (they land in Downloads).
3. **`/day N`** (after filming). Claude looks at the footage, picks a trending sound that
   fits, cuts two variations, burns the line on screen, writes and checks the caption,
   sends you both mp4s. Say what to change in plain English ("swap 3 and 8", "lose clip
   7", "make it 20 seconds") and it re-cuts.
   **With the buttons instead:** press **New video** on the app's home page.
   - *Clips*: keep the folder name it suggests (`dayN`) and drag the clips from
     Downloads into the drop zone; they are copied to `clips/dayN/` and show up
     numbered as they land. Or click a folder that is already there.
   - *Sound*: click a card in the pool (play it there), or paste a TikTok / Instagram /
     YouTube link and it is downloaded and selected, or press **Let Claude pick**: Claude
     looks at the footage and the pool in the panel and selects one for you.
   - *Cut*: length, how often to cut, the opener (click a clip), Story or Random. Seed,
     the on-screen line, beat sync and "render now" sit under *More options*. **Cut it**
     plans, renders and opens the video page, where every edit is a button.
   A shoot page (`/shoot/dayN`) has **New video from these clips** on top, which skips
   straight to the sound step.
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
