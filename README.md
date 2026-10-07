# beatcut

Drop phone clips in `clips/dayN/`, give it a sound link, get one mp4 cut to the beat with
the sound baked in. Then edit by command and re-render.

**What this is for.** Ernest + Christian's daily "Young Vibas" videos: coding a SaaS in
absurd places, one post a day, quantity over quality. The whole point is to never open
CapCut: film, drop the clips in a folder, say which sound, get the video. Edits are
sentences to Claude ("swap clips 3 and 8", "hold the cape shot longer"), which run the
commands below. Day 1 (grocery store, 11 clips, one TikTok sound) and day 2 (the barber
long take + trolley / Apple store / Grove bushes, four videos on four TikTok sounds) were
cut entirely this way. `CLAUDE.md` is the full command reference and every gotcha we hit;
`.claude/skills/beatcut/SKILL.md` is the workflow Claude follows plus a lessons log.

**Setup on a new Mac (Christian):**

```bash
brew install ffmpeg uv
uv tool install yt-dlp            # only for Instagram / YouTube sounds — never brew install yt-dlp
git clone https://github.com/ejinian/auto_video_editor.git beatcut && cd beatcut
uv run beatcut.py setup           # checks ffmpeg, installs the headless browser for TikTok sound pages
```

Clips, sounds and renders are not in the repo (gitignored); only the tool, the docs, the
caption font and the day's `projects/*.json` edit files are.

**Where things are:** day N's clips → `clips/dayN/`. Video V of day N is project `dayN_V`
and everything about it is in `out/dayN/`: `dayN_V.mp4` is the video, `versions/` keeps
earlier renders, `_dayN_V_board.jpg` is one frame per cut, `_frames_<clip>.jpg` are the
clips' timestamped frame sheets.

```bash
uv run beatcut.py setup                                           # once per machine
uv run beatcut.py -p day2_1 sound "https://www.tiktok.com/t/…"    # TikTok video / sound page, Instagram reel, YouTube
uv run beatcut.py -p day2_1 plan --clips-dir clips/day2 --length 15 --preset loose
uv run beatcut.py -p day2_1 render                                # -> out/day2/day2_1.mp4
```

Always put the link in quotes (zsh chokes on `?` and `=` otherwise). An Instagram reel gives
you the reel's audio as it plays, only as long as the reel; add `--cookies chrome` if IG
asks for a login.

Edit, then render again:

```bash
uv run beatcut.py show          # the edit: slot → clip
uv run beatcut.py sheet         # out/_clips.jpg — which clip is which number
uv run beatcut.py swap c3 c8    # swap the slots holding clips 3 and 8
uv run beatcut.py drop 7        # take clip 7 out of the video
uv run beatcut.py hero 2        # clip 2 lands on the drop
uv run beatcut.py merge 10      # slot 10 joins slot 9 (longer hold)
uv run beatcut.py split 9       # slot 9 cut in two
uv run beatcut.py caption "we coded a saas at the strip club"
uv run beatcut.py length 20     # rebuilds the edit at 20 s
uv run beatcut.py render
```

`uv run beatcut.py --help` lists everything. Needs `uv` and Homebrew `ffmpeg`.
