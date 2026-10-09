# beatcut / Young Vibas: everything we've built so far

*Oct 5 to Oct 9, 2026. Christian + Claude, for Ernest.*

## The short version

We built **beatcut**, a tool that turns a folder of phone clips plus a sound link into a
finished 1080x1920 TikTok/Reels mp4 with the music baked in and every cut on the beat.
After that you change it by asking in plain English ("swap clips 3 and 8", "get rid of
clip 7", "hold that shot longer") and it re-renders in about 10 seconds. When you want
to polish by hand, it opens the same edit as a **CapCut project** with every cut still
adjustable.

It all lives in `~/Desktop/beatcut`. The finished video for each day is always at
`~/Desktop/beatcut/out/dayN/dayN_V.mp4`.

---

## What got made, day by day

### Day 1 (Oct 5): grocery store, 11 clips
- The first version of the pipeline: download the sound, find the beats, cut, render.
- Sound: *Call It What You Like (Slowed)*, Robbie Doherty.
- Checked automatically: every planned cut lines up with a real scene change within one
  frame.
- Output: `out/day1/day1_1.mp4`

### Day 2 (Oct 6–7): barber long take + trolley / Apple store / Grove bushes
Your brief asked for 4 videos from one batch of clips, so the tool now handles
**several projects per day** (`day2_1` … `day2_5`).

| video | clips | sound |
|---|---|---|
| day2_1 | before barber → barber long take | original sound, Space Snicker AE |
| day2_2 | before barber → barber long take | *The WORST 808s known to man* |
| day2_3 | trolley → Apple store → bushes | original sound, Shahbazov |
| day2_4 | trolley → Apple store → bushes (different mix) | original sound, Spirefx |
| day2_5 | barber, **first and last ~20 s only, random angles** | original sound, Shahbazov |

New controls that came out of your brief:
- **"Always start with X"**: pin an opener clip.
- **"Multiple sub-clips of the long take"**: story mode. A long take plays out in order
  across the video, so the haircut actually progresses.
- **"Doesn't have to be that strict"**: a `loose` preset (a cut every 2–4 s instead of
  every beat), plus `tight` and `chill`.
- **Variations**: same clips, different combination and different sound, so they don't
  look like one edit with a new song.
- **Your feedback on the barber videos** (the middle of the take is dead, random angles
  are better): we added **random mode** and only used the good windows. That's day2_5.
- Instagram *audio-page* links need a login everywhere, so we switched to TikTok links.
  Instagram **reel** links work fine.

### CapCut export (Oct 7)
- `export --open` writes the edit as a real CapCut project: every clip is a separate
  segment you can drag longer or shorter, and the sound sits on its own track. CapCut
  then opens **straight into the project**.
- Getting there took some work. CapCut has no API, it refused projects that didn't
  come from a project the app made itself, and it ignores normal automation clicks. What
  we did:
  - Use the empty **`1007`** project in CapCut as the template. **Please don't delete
    it.**
  - Click the first tile with a real mouse event.
  - Watch for CapCut writing its own files to confirm the project opened.
- Re-running the export **replaces** the CapCut project with the same name (your rule:
  the template always starts from the automation).
- This needs Accessibility + Screen Recording permission for Claude. After a Claude app
  update those permissions have to be granted again.

### Christian's machine set up (Oct 7)
- `SETUP.md` is the runbook for a new machine: the tools, the CapCut seed project,
  the macOS permissions, a quick test run, and troubleshooting.

### Day 3 (Oct 7): gym, "coding on the laptop everywhere" bit, 10 clips
| video | what | sound | length |
|---|---|---|---|
| day3_1 | rapid-fire, 18 cuts | *DUNG DING BREGA*, 3VILCORE & Pheyx (#4 trending that week) | 30 s |
| day3_2 | loose, 9 longer shots, different opener, reversed order | *geekin*, Nemzzz | 22 s |
| day3_3 | day3_1's cut with on-screen text "every dev nowadays" | DUNG DING BREGA | 30 s |

- I let Claude pick the sound. It looked at the footage first, then matched a trending
  sound to the bit.
- Two bench takes only had the laptop in their last few seconds, so we split each one
  into a "reps" clip and a "laptop" clip so the punchline actually shows up.
- The storyboard check caught a jump cut (the same take in two slots back to back). We
  fixed it before posting.
- Post caption saved in `out/day3/day3_1.caption.txt`.

### Lisa v1 (Oct 8): SlideLabs promo
- Different format: her shocked face on the bar before the drop, a **zoom-blur
  transition on the drop**, then the SlideLabs demo sped up (2x / 8x / 2.5x) with two
  text lines:
  - "wait... this app makes your whole carousel for you??"
  - "it's called slidelabs"
- beatcut itself doesn't do speed changes or transitions, so this one was built with a
  separate script. There's also a CapCut version.
- Output: `out/lisa_v1/lisa_v1.mp4` (13.3 s)

### The buttons + `/day` (Oct 8)
- **A simple web UI** (`uv run ui.py` → http://127.0.0.1:8765). You get clip thumbnails
  per day and a "Cut it" form (sound, length, preset, opener, story order, hook text).
  The video page has the player, the storyboard, every edit as a button, Render, Open
  in CapCut, Make variation, and the caption. It runs the same commands as the chat, so
  the two never disagree.
- **`HOWTO.md`**: the step-by-step for a shoot day.
- **`/day` in Claude**, the whole loop in one command:
  - `/day plan` picks tomorrow's idea from our research on what's going viral and writes
    a shot list.
  - `/day N` cuts that day's clips into two finished variations, with the hook on screen
    and a checked caption.
  - `/day post N` hands over the files ready to upload.
- Found and worked around a bug along the way: re-importing a sound that's already
  downloaded could cut it to 1.4 s.

### Research + Instagram skills
- A **swipe file** of 160 reels from comparable accounts, ranked by how far each one
  beat its account's usual views (`out/swipe.md`). The closest comps for us are
  @iansbrash and @ayxanium.
- A set of Instagram skills in Claude: viral research, reel scripts/hooks, captions,
  carousels, stories, comments/replies/DMs, profile score, weekly plan, analytics audit,
  and a "make it not sound like AI" pass.

---

## Next up: Day 4 (planned for today, Oct 9)
**Idea:** "AI is about to replace me", played completely deadpan. It's the same shape
as @iansbrash's two biggest posts (1.3M and 322k views).
**On-screen line:** *6 months before opus does our job so we're at the gym*

Shot list (portrait, 10–20 s each, no talking, dead serious faces the whole time):
1. **Opener:** both of us walk into the gym in work clothes, laptops under our arms,
   toward the camera
2. Bench press, laptop open on the floor, glancing at it between reps
3. **Drop:** one of us mid pull-up, the other holding the laptop up to his face with a
   terminal running. Hold it.
4. Treadmill side by side, laptops on the consoles, both typing
5. Dumbbell curls at the mirror, laptop screen showing in the reflection
6. Sauna/locker room, towel on, laptop on knees
7. Protein shake at the counter, typing one-handed
8. **Closer:** both on the floor against the wall, laptops closed, staring at the
   ceiling (the "it's over" face, 10 s)

Drop the clips in `~/Desktop/beatcut/clips/day4/`, then run `/day 4`.

---

## How to use it day to day
1. Put the day's clips in `clips/dayN/`. Name them something you can refer to.
2. Tell Claude: "day N, video 1 with audio: <TikTok or Instagram reel link>". Or just
   `/day N` and let it pick the sound.
3. Get `out/dayN/dayN_1.mp4` back, then ask for changes in plain English.
4. Want to tweak by hand? Ask for it in CapCut.

Things to know:
- Hard cuts only, no transitions or zooms. That's the format we chose on purpose.
- TikTok/IG may mute the baked-in music because of copyright. We've accepted that.
- Audio doesn't play in the Claude app preview, so check the video on your phone or in
  QuickTime.
