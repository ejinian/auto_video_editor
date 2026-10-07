#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = ["librosa>=0.11", "numpy", "soundfile", "pillow", "playwright>=1.40", "pyobjc-framework-Quartz; sys_platform == 'darwin'"]
# ///
"""beatcut — cut phone clips to the beats of a TikTok sound and export ONE mp4.

    clips/         the input clips (numbered 1..N by filename order)
    sound/         the downloaded sound + its beat analysis
    project.json   the edit: cut times + which clip sits in each slot
    out/           renders (final.mp4 + numbered versions)

Typical run:
    uv run beatcut.py sound <tiktok-url>     download + analyze the sound
    uv run beatcut.py plan                   build the edit from clips/ + the beats
    uv run beatcut.py render                 -> out/final.mp4

Then edit and re-render:
    uv run beatcut.py swap 3 8 && uv run beatcut.py render
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIPS, SOUND, OUT = ROOT / "clips", ROOT / "sound", ROOT / "out"
PROJECTS = ROOT / "projects"
FONT = ROOT / "fonts" / "TikTokSans-800.ttf"
CUR = "default"  # the active project name (-p / --project); set in main()
DENSITY_PRESETS = {
    "tight": {"calm": 4, "hype": 2, "burst": 4, "hold": 4},   # a cut every 1-2 s, rapid-fire into the drop
    "loose": {"calm": 8, "hype": 4, "burst": 0, "hold": 8},   # a cut every 2-4 s, drop still gets its own shot
    "chill": {"calm": 16, "hype": 8, "burst": 0, "hold": 8},  # a cut every 4-8 s
}
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
FPS = 30
W, H = 1080, 1920
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
# calm: beats per cut in quiet bars; hype: beats per cut in loud bars;
# burst: the N beats before a drop cut on every beat; hold: beats the drop shot holds.
DEFAULT_DENSITY = {"calm": 4, "hype": 2, "burst": 4, "hold": 4}
HEAD_TRIM = 0.3   # skip the first 0.3s of a clip when there is room (phone shake)
TAIL_PAD = 0.15   # never use the last 0.15s of a clip (decoder margin)
BLOCKS = "▁▂▃▄▅▆▇█"


# ----------------------------------------------------------------- helpers

def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, text=True, capture_output=True)
    if check and p.returncode:
        die(f"{cmd[0]} failed:\n{p.stderr[-3000:]}")
    return p


def natural_key(s: str):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s)]


def http_get(url: str, binary: bool = False, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data, final = r.read(), r.geturl()
    except urllib.error.HTTPError as e:
        # TikTok often answers the canonical page with a bot wall; the
        # redirect still happened and the final URL is what we need.
        data, final = b"", e.geturl()
    return (data if binary else data.decode("utf-8", "replace")), final


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "sound"


def load_json(p: Path):
    return json.loads(p.read_text())


def save_json(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=1))


def project_path(name: str | None = None) -> Path:
    PROJECTS.mkdir(exist_ok=True)
    legacy = ROOT / "project.json"
    if legacy.exists():  # the single-project layout from day 1
        legacy.rename(PROJECTS / "default.json")
    return PROJECTS / f"{name or CUR}.json"


def load_project() -> dict:
    p = project_path()
    if not p.exists():
        die(f"no project '{CUR}' yet — run `plan` first (or `-p <name>` to pick another; have: "
            f"{', '.join(q.stem for q in PROJECTS.glob('*.json') if not q.name.endswith('.sound.json')) or 'none'})")
    return load_json(p)


def save_project(project: dict) -> None:
    save_json(project_path(), project)


def out_name(project: dict) -> str:
    return project.get("name") or ("final" if CUR == "default" else CUR)


def out_dir(project: dict | None = None, clip_path: str | None = None) -> Path:
    """Where a project's files go: out/dayN/ for a project named dayN_V (or a clip under
    clips/dayN/), else out/. The convention: clips/day2/ → -p day2_1 → out/day2/day2_1.mp4."""
    day = None
    if clip_path:
        m = re.search(r"/(day\d+)/", clip_path)
        day = m.group(1) if m else None
    if day is None and project is not None:
        m = re.match(r"(day\d+)_", out_name(project))
        day = m.group(1) if m else None
    d = OUT / day if day else OUT
    d.mkdir(parents=True, exist_ok=True)
    return d


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


# ------------------------------------------------------------------- sound

HEADLESS_HINT = "first run: downloading the headless browser (~95 MB, once)…"


def install_headless_browser() -> None:
    print(HEADLESS_HINT)
    run([sys.executable, "-m", "playwright", "install", "chromium-headless-shell"])


def resolve_music_page(url: str) -> dict:
    """A TikTok SOUND page (tiktok.com/music/Name-<id>) only hands its data to a real
    browser: the page's own `api/music/detail` XHR carries the sound's playUrl.
    (tikwm's music endpoints sit behind Cloudflare, yt-dlp's tiktok:sound extractor is
    dead, and the unsigned API answers with an empty body — all verified 2026-10-05.)
    So we run a headless Chromium for a few seconds and read that one response."""
    from playwright.sync_api import Error as PWError, sync_playwright

    def attempt() -> dict | None:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900}, locale="en-US")
            page = ctx.new_page()
            got: dict = {}

            def on_response(r):
                if "api/music/detail" in r.url and r.status == 200 and "j" not in got:
                    try:
                        got["j"] = r.json()
                    except Exception:  # noqa: BLE001
                        pass

            page.on("response", on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            for _ in range(60):
                if got:
                    break
                page.wait_for_timeout(500)
            browser.close()
        return got.get("j")

    try:
        j = attempt()
    except PWError as e:
        if "install" not in str(e).lower():
            die(f"headless browser failed: {str(e)[:300]}")
        install_headless_browser()
        j = attempt()
    m = ((j or {}).get("musicInfo") or {}).get("music") or {}
    if not m.get("playUrl"):
        die("TikTok didn't hand over the sound (bot check?). paste the link of any VIDEO "
            "that uses the sound instead — it resolves to the exact same track")
    return {
        "source": url,
        "post": None,
        "music_url": m["playUrl"],
        "title": m.get("title") or "sound",
        "author": m.get("authorName"),
        "music_id": m.get("id"),
        "original": m.get("original"),
        "duration": m.get("duration"),
    }


def resolve_tiktok(url: str) -> dict:
    """TikTok post URL (incl. /t/ and vm. short links) -> the sound's mp3 URL."""
    _, final = http_get(url)
    canonical = final.split("?")[0]
    if "/music/" in canonical:
        return resolve_music_page(canonical)
    last = None
    for candidate in dict.fromkeys([canonical, final, url]):
        try:
            body, _ = http_get(
                "https://www.tikwm.com/api/?url=" + urllib.parse.quote(candidate, safe="")
            )
            j = json.loads(body)
        except Exception as e:  # noqa: BLE001
            last = str(e)
            continue
        if j.get("code") == 0 and j.get("data"):
            d = j["data"]
            mi = d.get("music_info") or {}
            music = d.get("music") or mi.get("play")
            if not music:
                die("tikwm resolved the post but it carries no sound url")
            return {
                "source": url,
                "post": canonical,
                "post_author": (d.get("author") or {}).get("unique_id"),
                "music_url": music,
                "title": mi.get("title") or "sound",
                "author": mi.get("author"),
                "music_id": mi.get("id"),
                "original": mi.get("original"),
            }
        last = j.get("msg")
    die(f"could not resolve {url} via tikwm ({last})")


def ytdlp_bin() -> str | None:
    local = Path.home() / ".local" / "bin" / "yt-dlp"  # where `uv tool install yt-dlp` puts it
    return shutil.which("yt-dlp") or (str(local) if local.exists() else None)


def ytdlp_sound(src: str, cookies: str | None) -> tuple[Path, dict]:
    """Instagram reels, YouTube, anything else yt-dlp reads: the post's AUDIO track,
    which for a reel is the sound as it plays in the reel (music + any voice over it)."""
    yd = ytdlp_bin()
    if not yd:
        die("yt-dlp isn't installed — run: uv tool install yt-dlp")
    hint = ("\nInstagram often wants a logged-in browser: re-run with `--cookies chrome` "
            "(or safari / firefox)" if "instagram.com" in src and not cookies else "")
    base = [yd, "--no-warnings"] + (["--cookies-from-browser", cookies] if cookies else [])
    p = run(base + ["--skip-download", "--print", "%(id)s\t%(title)s\t%(uploader)s", src], check=False)
    if p.returncode:
        die(f"yt-dlp couldn't read that link:\n{p.stderr.strip()[-600:]}{hint}")
    vid, title, uploader = (p.stdout.strip().split("\t") + ["", ""])[:3]
    slug = (slugify(title)[:30] + "-" + slugify(vid)[-10:]).strip("-")
    target = SOUND / f"{slug}.mp3"
    p = run(base + ["-q", "-x", "--audio-format", "mp3", "--audio-quality", "2",
                    "-o", str(SOUND / f"{slug}.%(ext)s"), src], check=False)
    if p.returncode or not target.exists():
        die(f"yt-dlp couldn't download the audio:\n{p.stderr.strip()[-600:]}{hint}")
    platform = "instagram" if "instagram.com" in src else "yt-dlp"
    return target, {"source": src, "title": title or slug, "author": uploader or None, "platform": platform}


def fetch_sound(src: str, cookies: str | None = None) -> tuple[Path, dict]:
    SOUND.mkdir(exist_ok=True)
    p = Path(src).expanduser()
    if p.exists():
        slug, raw = slugify(p.stem), p
        meta = {"source": str(p), "title": p.stem}
    elif "tiktok.com" in src:
        meta = resolve_tiktok(src)
        slug = slugify(meta["title"]) + "-" + str(meta.get("music_id") or "")[-6:]
        raw = SOUND / f"{slug}.raw"
        data, _ = http_get(meta["music_url"], binary=True, timeout=180)
        if len(data) < 10_000:
            die("the sound download came back empty — the CDN link may have expired, re-run")
        raw.write_bytes(data)
    else:
        mp3, meta = ytdlp_sound(src, cookies)
        save_json(mp3.with_suffix(".source.json"), meta)
        return mp3, meta
    mp3 = SOUND / f"{slug}.mp3"
    if raw != mp3:
        run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-vn", "-c:a", "libmp3lame", "-q:a", "2", str(mp3)])
        if raw.suffix == ".raw":
            raw.unlink()
    save_json(SOUND / f"{slug}.source.json", meta)
    return mp3, meta


def analyze(mp3: Path) -> dict:
    import numpy as np
    import librosa
    import soundfile as sf

    wav = mp3.with_suffix(".wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", "22050", str(wav)])
    y, sr = sf.read(str(wav), dtype="float32")
    wav.unlink()
    hop = 512
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    tempo, bf = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=hop, trim=False)
    tempo = float(np.atleast_1d(tempo)[0])
    beats = [float(t) for t in librosa.frames_to_time(bf, sr=sr, hop_length=hop)]
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    duration = len(y) / sr

    bounds = bf.tolist() + [len(rms)]
    beat_e = [
        float(rms[bounds[i]:bounds[i + 1]].mean()) if bounds[i + 1] > bounds[i] else 0.0
        for i in range(len(bf))
    ]
    phase = 0
    if len(bf) >= 8:
        phase = int(max(range(4), key=lambda p: float(onset[bf[p::4]].sum())))
    bars = []
    for s in range(phase, len(beats), 4):
        if s + 1 >= len(beats):
            break
        end = beats[s + 4] if s + 4 < len(beats) else duration
        bars.append({"beat": s, "start": beats[s], "end": end, "energy": float(np.mean(beat_e[s:s + 4]))})
    emax = max((b["energy"] for b in bars), default=1.0) or 1.0
    for b in bars:
        b["level"] = round(b["energy"] / emax, 3)
    med = float(np.median([b["level"] for b in bars])) if bars else 0.0
    for b in bars:
        b["hype"] = b["level"] >= max(med, 0.35)

    cands = []
    for i in range(2, len(bars)):
        prev = float(np.mean([bars[j]["level"] for j in range(max(0, i - 4), i)]))
        ratio = bars[i]["level"] / max(prev, 0.05)
        if ratio >= 1.3 and bars[i]["level"] >= 0.5:
            cands.append((ratio, i))
    cands.sort(reverse=True)
    drops = []
    for ratio, i in cands:
        if all(abs(i - d["bar"]) >= 8 for d in drops):
            drops.append({"bar": i, "beat": bars[i]["beat"], "time": bars[i]["start"], "ratio": round(ratio, 2)})
        if len(drops) >= 3:
            break
    drops.sort(key=lambda d: d["time"])

    suggested_start = 0.0
    if drops and drops[0]["time"] > 12:
        suggested_start = beats[max(drops[0]["beat"] - 8, 0)]

    return {
        "file": str(mp3.relative_to(ROOT)),
        "duration": round(duration, 3),
        "tempo": round(tempo, 2),
        "beats": [round(t, 4) for t in beats],
        "downbeat_phase": phase,
        "bars": bars,
        "drops": drops,
        "suggested_start": round(suggested_start, 3),
    }


def print_sound_report(info: dict, meta: dict) -> None:
    bar_len = 60 / info["tempo"] * 4
    title = meta.get("title", "sound")
    by = f" — {meta['author']}" if meta.get("author") else ""
    print(f"sound: {title}{by}")
    print(f"  {info['duration']:.1f}s · {info['tempo']:.1f} bpm · {len(info['beats'])} beats · bar = {bar_len:.2f}s · file {info['file']}")
    if info["drops"]:
        print("  drops: " + "   ".join(f"{d['time']:.2f}s (bar {d['bar']}, x{d['ratio']})" for d in info["drops"]))
    else:
        print("  drops: none detected (flat energy) — cuts follow the calm/hype density only")
    strip = "".join(BLOCKS[min(7, int(b["level"] * 7.999))] for b in info["bars"])
    marks = "".join("!" if any(d["bar"] == i for d in info["drops"]) else " " for i in range(len(info["bars"])))
    print("  energy by bar: " + strip)
    print("                 " + marks)
    if info["suggested_start"] > 0:
        print(f"  suggested start: {info['suggested_start']:.2f}s (2 bars before the first drop) — `plan` uses it; `plan --start 0` to override")


def cmd_setup(_args) -> None:
    """One-time checks for a fresh machine (Christian's laptop)."""
    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        print(f"{tool}: {shutil.which(tool) or 'MISSING — brew install ffmpeg'}")
        ok &= bool(shutil.which(tool))
    print(f"yt-dlp: {ytdlp_bin() or 'missing — uv tool install yt-dlp   (only needed for Instagram / YouTube sounds)'}")
    print(f"caption font: {'ok' if FONT.exists() else 'MISSING ' + str(FONT)}")
    install_headless_browser()
    print("headless browser: ok (TikTok sound-page links)")
    print("ready" if ok else "fix the MISSING items above")


def cmd_sound(args) -> None:
    mp3, meta = fetch_sound(args.source, cookies=args.cookies)
    info = analyze(mp3)
    beats_path = mp3.with_suffix(".beats.json")
    save_json(beats_path, info)
    pointer = {"sound": str(mp3.relative_to(ROOT)), "beats": str(beats_path.relative_to(ROOT)), "meta": meta}
    save_json(SOUND / "current.json", pointer)
    if CUR != "default":  # remember which sound belongs to this project
        PROJECTS.mkdir(exist_ok=True)
        save_json(PROJECTS / f"{CUR}.sound.json", pointer)
    print_sound_report(info, meta)
    print(f"\nnext: uv run beatcut.py {'-p ' + CUR + ' ' if CUR != 'default' else ''}plan")


def current_sound() -> dict:
    for p in (PROJECTS / f"{CUR}.sound.json", SOUND / "current.json"):
        if p.exists():
            return load_json(p)
    die("no sound yet — run `sound <link>` first")


# ------------------------------------------------------------------- clips

def list_dir_clips(d: Path) -> list[Path]:
    if not d.is_dir():
        die(f"{d} is not a folder")
    return sorted(
        [p for p in d.iterdir() if p.suffix.lower() in VIDEO_EXT and not p.name.startswith(".")],
        key=lambda p: natural_key(p.name),
    )


def scan_clips(project: dict | None = None) -> list[dict]:
    """The project's clips (explicit `clips` list, in that order) or, with no project,
    the top-level files of clips/. Ids are 1..N in that order."""
    if project is None and project_path().exists():
        project = load_json(project_path())
    if project and project.get("clips"):
        files = [ROOT / c for c in project["clips"]]
        missing = [str(f) for f in files if not f.exists()]
        if missing:
            die("clips moved or renamed: " + ", ".join(missing))
    else:
        if not CLIPS.exists():
            die("clips/ folder is missing")
        files = list_dir_clips(CLIPS)
    if not files:
        die("no clips (mp4 / mov)")
    cache_path = CLIPS / ".probe.json"
    cache = load_json(cache_path) if cache_path.exists() else {}
    clips = []
    for i, p in enumerate(files, 1):
        st = p.stat()
        key = f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}:{st.st_size}:{int(st.st_mtime)}"
        if key not in cache:
            out = run([
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height:stream_side_data=rotation:format=duration",
                "-of", "json", str(p),
            ]).stdout
            j = json.loads(out)
            s = j["streams"][0]
            rot = 0
            for sd in s.get("side_data_list", []):
                if "rotation" in sd:
                    rot = int(float(sd["rotation"]))
            w, h = int(s["width"]), int(s["height"])
            if rot % 180:
                w, h = h, w
            cache[key] = {"duration": float(j["format"]["duration"]), "w": w, "h": h}
        c = dict(cache[key])
        c.update(id=i, name=p.name, path=str(p))
        clips.append(c)
    CLIPS.mkdir(exist_ok=True)
    save_json(cache_path, cache)
    return clips


def cmd_clips(_args) -> None:
    clips = scan_clips()
    total = sum(c["duration"] for c in clips)
    print(f"{len(clips)} clips · {total:.1f}s of footage")
    for c in clips:
        orient = "portrait" if c["h"] >= c["w"] else "LANDSCAPE (will be center-cropped)"
        print(f"  {c['id']:>2}  {c['name']:<18} {c['duration']:5.1f}s  {c['w']}x{c['h']} {orient}")


def font(size: int):
    from PIL import ImageFont
    return ImageFont.truetype(str(FONT), size)


def wrap_px(text: str, fnt, max_w: int) -> list[str]:
    """Greedy word wrap by rendered pixel width; explicit newlines are kept."""
    lines: list[str] = []
    for para in text.split("\n"):
        words, cur = para.split(), ""
        if not words:
            lines.append("")
            continue
        for wd in words:
            trial = f"{cur} {wd}".strip()
            if cur and fnt.getlength(trial) > max_w:
                lines.append(cur)
                cur = wd
            else:
                cur = trial
        lines.append(cur)
    return lines


def caption_png(text: str, w: int, h: int, path: Path) -> None:
    """A transparent w×h layer with the hook caption in TikTok Sans, white with the
    classic black outline, centred at 17% down — the same look the app bakes."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = int(h * 0.036)
    fnt = font(size)
    stroke = max(2, int(size * 0.13))
    gap = int(size * 0.28)
    y = int(h * 0.17)
    for line in wrap_px(text, fnt, int(w * 0.86)):
        if not line:
            y += size
            continue
        bb = d.textbbox((0, 0), line, font=fnt, stroke_width=stroke)
        d.text(((w - (bb[2] - bb[0])) / 2 - bb[0], y - bb[1]), line, font=fnt,
               fill="white", stroke_width=stroke, stroke_fill="black")
        y += (bb[3] - bb[1]) + gap
    img.save(path)


def tile(items: list[tuple[str, float]], labels: list[str], out_path: Path, cols: int = 4) -> None:
    """Grab one frame per item, label it, and lay them out in a grid (Pillow does the text)."""
    from PIL import Image, ImageDraw
    cw, ch, pad = 270, 480, 4
    tmp = OUT / ".frames"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    rows = max(1, math.ceil(len(items) / cols))
    sheet = Image.new("RGB", (cols * cw + (cols + 1) * pad, rows * ch + (rows + 1) * pad), "black")
    fnt = font(30)
    for i, ((path, t), label) in enumerate(zip(items, labels)):
        frame = tmp / f"{i:03d}.jpg"
        run([
            "ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
            "-vf", f"scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch}", "-q:v", "3", str(frame),
        ])
        im = Image.open(frame).convert("RGB")
        ImageDraw.Draw(im).text((10, 8), label, font=fnt, fill="white", stroke_width=4, stroke_fill="black")
        r, c = divmod(i, cols)
        sheet.paste(im, (pad + c * (cw + pad), pad + r * (ch + pad)))
    sheet.save(out_path, quality=88)
    shutil.rmtree(tmp)


def cmd_frames(args) -> None:
    """Evenly sampled frames of a clip, labelled with their timestamps — READ the sheet
    before planning so you know what the footage shows at each moment."""
    OUT.mkdir(exist_ok=True)
    if args.clips:
        paths = [Path(c).expanduser() if Path(c).expanduser().is_absolute() else ROOT / c for c in args.clips]
        clips = [{"path": str(p), "name": p.name} for p in paths]
        for c in clips:
            c["duration"] = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", c["path"]]).stdout)
    else:
        clips = scan_clips()
    for c in clips:
        n = args.n or max(6, min(30, round(c["duration"] / 4)))
        times = [c["duration"] * i / n + 0.05 for i in range(n)]
        out = out_dir(None, c["path"]) / f"_frames_{Path(c['name']).stem}.jpg"
        tile([(c["path"], t) for t in times], [f"{t:.1f}s" for t in times], out, cols=6)
        print(f"{Path(c['name']).name}: {n} frames over {c['duration']:.1f}s -> {rel(out)}")


def cmd_sheet(_args) -> None:
    clips = scan_clips()
    project = load_json(project_path()) if project_path().exists() else {}
    out = out_dir(project, clips[0]["path"]) / f"_{out_name(project)}_clips.jpg"
    tile([(c["path"], min(1.0, c["duration"] / 2)) for c in clips],
         [f"{c['id']}  {Path(c['name']).stem}  {c['duration']:.1f}s" for c in clips], out)
    print(f"contact sheet of the clips (numbered): {rel(out)}")


# -------------------------------------------------------------------- plan

def build_cuts(info: dict, start: float, length: float, density: dict, max_slot: float,
               first_max: float | None = None) -> list[float]:
    beats = info["beats"]
    at_or_before = [i for i, t in enumerate(beats) if t <= start + 1e-6]
    k0 = at_or_before[-1] if at_or_before else 0
    # `length` is the IDEAL length: end on the downbeat (bar start) closest to it, so
    # the video resolves on a bar; fall back to the last beat inside it.
    target = start + length
    half_bar = 2 * 60 / info["tempo"]
    # a sound shorter than the asked length plays to its END (meme sounds keep the
    # punchline in the tail) — otherwise end on the downbeat nearest the target
    to_end = target >= info["duration"] - half_bar
    bar_starts = [b["beat"] for b in info["bars"] if b["beat"] > k0 + 1 and beats[b["beat"]] <= info["duration"]]
    near = [] if to_end else [k for k in bar_starts if abs(beats[k] - target) <= half_bar]
    if near:
        k1 = min(near, key=lambda k: abs(beats[k] - target))
    else:
        end_t = min(target, info["duration"])
        k1 = [i for i, t in enumerate(beats) if t <= end_t + 1e-6][-1]
    if k1 <= k0 + 1:
        die("not enough beats in that range — lower `start` or raise `length`")
    hype = {}
    for b in info["bars"]:
        for k in range(b["beat"], b["beat"] + 4):
            hype[k] = b["hype"]
    drop_beats = {d["beat"] for d in info["drops"]}
    burst, hold = int(density["burst"]), int(density["hold"])
    cut_idx, last, hold_until = [k0], k0, -1
    for k in range(k0 + 1, k1 + 1):
        if k == k1:
            cut_idx.append(k)
            break
        too_long = beats[k] - beats[last] >= max_slot - 1e-6
        if k in drop_beats:
            cut_idx.append(k)
            last, hold_until = k, k + hold
            continue
        if k < hold_until:
            if too_long:
                cut_idx.append(k)
                last = k
            continue
        in_burst = any(0 < d - k <= burst for d in drop_beats)
        interval = 1 if in_burst else (int(density["hype"]) if hype.get(k, False) else int(density["calm"]))
        # no burst wanted and a drop is 1-2 beats away: let the drop make the cut, or
        # we'd get a flash-frame shot right before it
        drop_imminent = burst == 0 and any(0 < d - k <= 2 for d in drop_beats)
        if (k - last >= interval or too_long) and not drop_imminent:
            cut_idx.append(k)
            last = k
    if first_max is not None and len(cut_idx) > 1 and beats[cut_idx[1]] - beats[cut_idx[0]] > first_max:
        # the pinned opener is shorter than the grid's first slot: CAP slot 1 at the
        # latest beat the opener can fill (never stretch it), keep the rest of the grid
        kf = max([k for k in range(k0 + 1, k1) if beats[k] - beats[k0] <= first_max], default=k0 + 1)
        cut_idx = [k0, kf] + [k for k in cut_idx[1:] if k > kf]
    cuts = [beats[k] for k in cut_idx]
    if to_end:
        cuts[-1] = info["duration"]
        if len(cuts) > 2 and cuts[-1] - cuts[-2] < 0.8:  # no flash shot on the tail
            del cuts[-2]
        if len(cuts) > 2 and cuts[-1] - cuts[-2] > max_slot:  # ...but respect the clips
            cuts.insert(-1, beats[cut_idx[-1]])
    return cuts


def fit_in(clip: dict, used: list[tuple[float, float]], dur: float):
    """An in-point for `dur` seconds inside `clip` that avoids `used` ranges.
    Returns (in, overlapped) or None when the clip is simply too short."""
    D = clip["duration"] - TAIL_PAD
    if dur > D:
        return None
    lo = HEAD_TRIM if D - HEAD_TRIM >= dur else 0.0
    center = max(lo, min((D - dur) / 2, D - dur))

    def free(a: float) -> bool:
        return all(a + dur <= s or a >= e for s, e in used)

    if free(center):
        return center, False
    cursor = lo
    for s, e in sorted(used):
        if s - cursor >= dur:
            return cursor, False
        cursor = max(cursor, e)
    if D - cursor >= dur:
        return cursor, False
    return center, True


def slot_durs(project: dict) -> list[float]:
    c = project["cuts"]
    return [c[i + 1] - c[i] for i in range(len(c) - 1)]


def used_ranges(project: dict, skip: int | None = None) -> dict[int, list[tuple[float, float]]]:
    durs = slot_durs(project)
    used: dict[int, list] = {}
    for i, s in enumerate(project["slots"]):
        if i == skip or s is None:
            continue
        used.setdefault(s["clip"], []).append((s["in"], s["in"] + durs[i]))
    return used


def place(project: dict, i: int, clip: dict) -> bool:
    r = fit_in(clip, used_ranges(project, skip=i).get(clip["id"], []), slot_durs(project)[i])
    if r is None:
        return False
    a, overlapped = r
    project["slots"][i] = {"clip": clip["id"], "in": round(a, 3)}
    if overlapped:
        project["slots"][i]["reused"] = True
    return True


def pool_of(project: dict, clips: list[dict]) -> list[dict]:
    pool = [c for c in clips if c["id"] not in project.get("excluded", [])]
    if not pool:
        die("every clip is excluded")
    return pool


def free_footage(project: dict, clip: dict) -> float:
    return clip["duration"] - sum(e - s for s, e in used_ranges(project).get(clip["id"], []))


def best_replacement(project: dict, clips: list[dict], i: int, avoid: set[int]) -> dict | None:
    """The pool clip with the most unused footage that fits slot i, not in `avoid`."""
    n = len(project["slots"])
    neighbours = {project["slots"][j]["clip"] for j in (i - 1, i + 1) if 0 <= j < n and project["slots"][j]}
    dur = slot_durs(project)[i]
    cands = [c for c in pool_of(project, clips) if c["id"] not in avoid and c["duration"] - TAIL_PAD >= dur]
    if not cands:
        return None
    cands.sort(key=lambda c: (c["id"] in neighbours, -free_footage(project, c)))
    return cands[0]


def assign_story(project: dict, clips: list[dict], story: list[int], slots: list[int], seed: int | None) -> None:
    """Fill `slots` (timeline order) by walking the story clips IN ORDER, proportionally:
    the clips are laid end to end into one virtual timeline and each slot takes the
    footage at its own relative position — so a 112 s take plays out chronologically
    across the video, and a 6-clip story goes clip 1 → clip 6 with longer clips
    getting more slots. `seed` jitters each in-point so a second plan is a different
    combination of the same story."""
    byid = {c["id"]: c for c in clips}
    durs = slot_durs(project)
    # usable footage per story clip; a pinned opener's clip continues after the opener
    used0 = {}
    if project["slots"] and project["slots"][0]:
        s0 = project["slots"][0]
        used0[s0["clip"]] = s0["in"] + durs[0]
    segs = []
    for cid in story:
        c = byid[cid]
        lo = HEAD_TRIM if c["duration"] - TAIL_PAD - HEAD_TRIM > 1.0 else 0.0
        lo = max(lo, used0.get(cid, 0.0))
        hi = c["duration"] - TAIL_PAD
        if hi > lo:
            segs.append([c, lo, hi])
    if not segs:
        die("story clips are all too short")
    m, n = len(segs), len(slots)
    caps = [hi - lo for _, lo, hi in segs]
    # 1. slot QUOTAS per story clip: every clip gets one when there are enough slots,
    #    the rest go by footage (largest remainder) — so a 3 s clip still shows up next
    #    to a 110 s take, and the take gets more shots than the short ones.
    base = [1] * m if n >= m else [0] * m
    extra = n - sum(base)
    shares = [extra * cp / sum(caps) for cp in caps]
    counts = [b + int(s) for b, s in zip(base, shares)]
    for j in sorted(range(m), key=lambda j: -(shares[j] - int(shares[j])))[: extra - sum(int(s) for s in shares)]:
        counts[j] += 1
    # 2. walk the slots in order through the clips in story order; a clip that can't
    #    hold a slot is skipped for that slot but stays open for a later, shorter one
    blocks: list[list[int]] = [[] for _ in segs]
    si = 0

    def room(j: int) -> float:
        return caps[j] - sum(durs[x] for x in blocks[j])

    for i in slots:
        d = durs[i]
        j = next((j for j in range(si, m) if len(blocks[j]) < counts[j] and room(j) >= d), None)
        if j is None:
            j = next((j for j in range(si, m) if room(j) >= d), None)  # over quota, still no re-show
        if j is None:
            j = max(range(m), key=lambda j: caps[j])  # out of footage: re-show the biggest clip
            if caps[j] < d:
                die(f"slot {i + 1} ({d:.2f}s) is longer than every story clip")
        blocks[j].append(i)
        if j == si and len(blocks[j]) >= counts[j]:
            si = j + 1
    # 3. inside each clip, spread its slots evenly and chronologically; a seed jitters
    #    each pick within its own gap, so a second plan is a different combination
    rng = random.Random(seed) if seed is not None else None
    for j, (c, lo, hi) in enumerate(segs):
        if not blocks[j]:
            continue
        g = max(0.0, room(j)) / len(blocks[j])
        t = lo + g / 2
        for x in blocks[j]:
            d = durs[x]
            jit = rng.uniform(-g / 2, g / 2) if rng and g > 0 else 0.0
            start = max(lo, min(t + jit, hi - d))
            project["slots"][x] = {"clip": c["id"], "in": round(start, 3)}
            t += d + g


def assign_random(project: dict, clips: list[dict], slots: list[int], seed: int | None) -> None:
    """Every slot takes a random clip (weighted by footage left, never the same clip
    twice in a row when avoidable) at a random in-point that doesn't overlap an
    earlier pick — 'random angles in random order'. Seeded, so re-plans repeat."""
    rng = random.Random(seed if seed is not None else 0)
    pool = pool_of(project, clips)
    durs = slot_durs(project)
    for i in slots:
        d = durs[i]
        prev = project["slots"][i - 1]["clip"] if i > 0 and project["slots"][i - 1] else None
        cands = [c for c in pool if c["duration"] - TAIL_PAD >= d]
        if not cands:
            die(f"slot {i + 1} ({d:.2f}s) is longer than every clip")
        fresh = [c for c in cands if free_footage(project, c) >= d]
        if len(fresh) > 1 and prev is not None:
            fresh = [c for c in fresh if c["id"] != prev] or fresh
        picks = fresh or cands
        weights = [max(free_footage(project, c), 0.2) for c in picks]
        c = rng.choices(picks, weights=weights, k=1)[0]
        lo = HEAD_TRIM if c["duration"] > 1.0 else 0.0
        hi = c["duration"] - TAIL_PAD
        used = sorted(used_ranges(project, skip=i).get(c["id"], []))
        # free windows that can hold d, then a random start inside a random window
        windows, cursor = [], lo
        for s, e in used:
            if s - cursor >= d:
                windows.append((cursor, s - d))
            cursor = max(cursor, e)
        if hi - cursor >= d:
            windows.append((cursor, hi - d))
        if windows:
            a, b = rng.choices(windows, weights=[b - a + 0.01 for a, b in windows], k=1)[0]
            start = rng.uniform(a, b)
        else:  # footage exhausted: re-show, but somewhere random
            start = rng.uniform(lo, max(lo, hi - d))
        project["slots"][i] = {"clip": c["id"], "in": round(start, 3)}


def assign_all(project: dict, clips: list[dict], shuffle_seed: int | None) -> None:
    pool = pool_of(project, clips)
    n = len(project["cuts"]) - 1
    durs = slot_durs(project)
    project["slots"] = [None] * n
    byid = {c["id"]: c for c in pool}
    free = list(range(n))
    first = project.get("first")
    if first:
        fc = clip_by_id(clips, first)
        lo = HEAD_TRIM if fc["duration"] > 1.0 else 0.0
        if fc["duration"] - TAIL_PAD - lo < durs[0]:
            die(f"clip {first} ({fc['duration']:.1f}s) can't hold slot 1 ({durs[0]:.2f}s)")
        # the opener takes the START of its clip, so a story can continue from there
        project["slots"][0] = {"clip": first, "in": round(lo, 3)}
        free.remove(0)
    story = [cid for cid in (project.get("story") or []) if cid in byid]
    if story:
        assign_story(project, clips, story, free, project.get("seed"))
        return
    if project.get("random"):
        assign_random(project, clips, free, project.get("seed"))
        return
    order = sorted(free, key=lambda i: -durs[i])
    clip_order = sorted(pool, key=lambda c: -c["duration"])
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(clip_order)
    hero = byid.get(project.get("hero")) or max(pool, key=lambda c: c["duration"])
    hero_slot = next(
        (i for i in free if any(abs(project["cuts"][i] - d["time"]) < 1e-3 for d in project["_drops"])),
        None,
    )
    if hero_slot is not None and place(project, hero_slot, hero):
        order.remove(hero_slot)
        clip_order = [c for c in clip_order if c["id"] != hero["id"]] + [hero]
    L, ci = len(clip_order), 0
    for i in order:
        for _ in range(L):
            clip = clip_order[ci % L]
            ci += 1
            prev_c = project["slots"][i - 1]["clip"] if i > 0 and project["slots"][i - 1] else None
            next_c = project["slots"][i + 1]["clip"] if i + 1 < n and project["slots"][i + 1] else None
            if L > 2 and clip["id"] in (prev_c, next_c):
                continue
            if place(project, i, clip):
                break
        else:
            if not place(project, i, max(pool, key=lambda c: c["duration"])):
                die(f"slot {i + 1} ({durs[i]:.2f}s) is longer than every clip")


def replan(project: dict, clips: list[dict], shuffle_seed: int | None = None) -> None:
    info = load_json(ROOT / project["beats"])
    pool = pool_of(project, clips)
    max_slot = max(c["duration"] for c in pool) - TAIL_PAD - HEAD_TRIM
    first_max = None
    if project.get("first"):
        fc = clip_by_id(clips, project["first"])
        first_max = fc["duration"] - TAIL_PAD - (HEAD_TRIM if fc["duration"] > 1.0 else 0.0)
    project["cuts"] = build_cuts(info, project["audio_start"], project["length"], project["density"], max_slot, first_max)
    project["_drops"] = [d for d in info["drops"] if project["cuts"][0] <= d["time"] <= project["cuts"][-1]]
    assign_all(project, clips, shuffle_seed)


def parse_ids(s: str | None) -> list[int]:
    return [int(x) for x in re.split(r"[,\s]+", s.strip()) if x] if s else []


def cmd_plan(args) -> None:
    if args.sound:
        cmd_sound(argparse.Namespace(source=args.sound, cookies=args.cookies))
    cur = current_sound()
    info = load_json(ROOT / cur["beats"])
    clip_paths: list[str] = []
    if args.clips_dir:
        d = Path(args.clips_dir).expanduser()
        d = d if d.is_absolute() else ROOT / d
        clip_paths = [str(p.relative_to(ROOT)) for p in list_dir_clips(d)]
    if args.clips:
        for c in args.clips:
            p = Path(c).expanduser()
            p = p if p.is_absolute() else ROOT / p
            if not p.exists():
                die(f"no such clip: {c}")
            clip_paths.append(str(p.relative_to(ROOT)))
    project = {"name": out_name({}), "clips": clip_paths}
    clips = scan_clips(project)
    start = info["suggested_start"] if args.start is None else float(args.start)
    length = float(args.length) if args.length else min(30.0, info["duration"] - start)
    density = dict(DENSITY_PRESETS[args.preset]) if args.preset else dict(DEFAULT_DENSITY)
    project.update({
        "sound": cur["sound"],
        "beats": cur["beats"],
        "audio_start": round(start, 3),
        "length": round(length, 3),
        "density": density,
        "excluded": [int(x) for x in (args.exclude or [])],
        "hero": int(args.hero) if args.hero else None,
        "first": int(args.first) if args.first else None,
        "story": parse_ids(args.story),
        "random": bool(args.random),
        "seed": args.seed,
        "caption": None,
    })
    replan(project, clips, args.seed if args.shuffle else None)
    save_project(project)
    show(project, clips)
    pfx = f"-p {CUR} " if CUR != "default" else ""
    print(f"\nnext: uv run beatcut.py {pfx}render        (then open {rel(out_dir(project) / (out_name(project) + '.mp4'))})")


# -------------------------------------------------------------------- show

def show(project: dict, clips: list[dict]) -> None:
    byid = {c["id"]: c for c in clips}
    cuts, durs = project["cuts"], slot_durs(project)
    t0 = cuts[0]
    drops = {round(d["time"], 3) for d in project.get("_drops", [])}
    hero_id = project.get("hero")
    cap = f'"{project["caption"]}"' if project.get("caption") else "none"
    extras = []
    if project.get("first"):
        extras.append(f"opens on clip {project['first']}")
    if project.get("story"):
        extras.append("story " + ">".join(map(str, project["story"])) + (f" seed {project['seed']}" if project.get("seed") is not None else ""))
    print(
        f"edit '{out_name(project)}': {Path(project['sound']).stem} · audio from {t0:.2f}s · {cuts[-1] - t0:.1f}s long · "
        f"{len(durs)} slots · density {project['density']} · caption {cap}"
        + (" · " + " · ".join(extras) if extras else "")
    )
    print("  slot   time (s)      dur   clip  file          in     note")
    counts: dict[int, int] = {}
    for s in project["slots"]:
        counts[s["clip"]] = counts.get(s["clip"], 0) + 1
    for i, (s, d) in enumerate(zip(project["slots"], durs), 1):
        c = byid[s["clip"]]
        notes = []
        if round(cuts[i - 1], 3) in drops:
            notes.append("DROP")
        if s["clip"] == hero_id:
            notes.append("hero")
        if counts[s["clip"]] > 1:
            notes.append(f"clip used x{counts[s['clip']]}")
        if s.get("reused"):
            notes.append("overlaps another use")
        print(
            f"  {i:>3}  {cuts[i - 1] - t0:6.2f}-{cuts[i] - t0:6.2f} {d:5.2f}   {c['id']:>3}  "
            f"{Path(c['name']).stem:<12} {s['in']:5.1f}   {' · '.join(notes)}"
        )
    unused = [c["id"] for c in clips if c["id"] not in counts and c["id"] not in project.get("excluded", [])]
    if unused:
        print(f"  not used: clips {', '.join(map(str, unused))}")
    if project.get("excluded"):
        print(f"  excluded: clips {', '.join(map(str, project['excluded']))}")


def cmd_show(_args) -> None:
    show(load_project(), scan_clips())


def cmd_board(_args) -> None:
    project, clips = load_project(), scan_clips()
    byid = {c["id"]: c for c in clips}
    out = out_dir(project) / f"_{out_name(project)}_board.jpg"
    durs = slot_durs(project)
    tile(
        [(byid[s["clip"]]["path"], s["in"] + durs[i] / 2) for i, s in enumerate(project["slots"])],
        [f"{i + 1}  clip {s['clip']}  {durs[i]:.1f}s" for i, s in enumerate(project["slots"])],
        out, cols=6,
    )
    print(f"storyboard, one frame per slot: {rel(out)}")


# ------------------------------------------------------------------- edits

def parse_ref(token: str, project: dict, kind: str) -> int:
    """`7` -> slot 7 (0-based 6); `c7` -> the slot holding clip 7 (must be unique)."""
    n = len(project["slots"])
    if token.lower().startswith("c"):
        cid = int(token[1:])
        hits = [i for i, s in enumerate(project["slots"]) if s["clip"] == cid]
        if len(hits) != 1:
            die(f"clip {cid} sits in {len(hits)} slots — name the slot number instead (see `show`)")
        return hits[0]
    i = int(token) - 1
    if not 0 <= i < n:
        die(f"{kind} {token} is out of range (1-{n})")
    return i


def clip_by_id(clips: list[dict], cid: int) -> dict:
    for c in clips:
        if c["id"] == cid:
            return c
    die(f"no clip {cid} (see `clips`)")


def finish(project: dict, clips: list[dict], msg: str) -> None:
    save_project(project)
    print(msg)
    show(project, clips)
    print(f"\nnext: uv run beatcut.py {'-p ' + CUR + ' ' if CUR != 'default' else ''}render")


def cmd_swap(args) -> None:
    project, clips = load_project(), scan_clips()
    a, b = parse_ref(args.a, project, "slot"), parse_ref(args.b, project, "slot")
    sa, sb = project["slots"][a], project["slots"][b]
    ca, cb = clip_by_id(clips, sa["clip"]), clip_by_id(clips, sb["clip"])
    project["slots"][a], project["slots"][b] = None, None
    if not place(project, a, cb):
        die(f"clip {cb['id']} ({cb['duration']:.1f}s) is shorter than slot {a + 1} ({slot_durs(project)[a]:.2f}s)")
    if not place(project, b, ca):
        die(f"clip {ca['id']} ({ca['duration']:.1f}s) is shorter than slot {b + 1} ({slot_durs(project)[b]:.2f}s)")
    finish(project, clips, f"swapped slots {a + 1} and {b + 1}")


def cmd_move(args) -> None:
    project, clips = load_project(), scan_clips()
    a, b = parse_ref(args.a, project, "slot"), parse_ref(args.b, project, "slot")
    order = [s["clip"] for s in project["slots"]]
    cid = order.pop(a)
    order.insert(b, cid)
    old = project["slots"]
    project["slots"] = [None] * len(order)
    for i, c in enumerate(order):
        if not place(project, i, clip_by_id(clips, c)):
            project["slots"] = old
            die(f"clip {c} is shorter than slot {i + 1} after the move")
    finish(project, clips, f"moved slot {a + 1} to position {b + 1}")


def cmd_set(args) -> None:
    project, clips = load_project(), scan_clips()
    i = parse_ref(args.slot, project, "slot")
    clip = clip_by_id(clips, int(args.clip))
    project["slots"][i] = None
    if not place(project, i, clip):
        die(f"clip {clip['id']} ({clip['duration']:.1f}s) is shorter than slot {i + 1} ({slot_durs(project)[i]:.2f}s)")
    if args.at is not None:
        project["slots"][i]["in"] = round(max(0.0, min(float(args.at), clip["duration"] - slot_durs(project)[i] - TAIL_PAD)), 3)
    finish(project, clips, f"slot {i + 1} now shows clip {clip['id']}")


def cmd_in(args) -> None:
    project, clips = load_project(), scan_clips()
    i = parse_ref(args.slot, project, "slot")
    clip = clip_by_id(clips, project["slots"][i]["clip"])
    hi = clip["duration"] - slot_durs(project)[i] - TAIL_PAD
    project["slots"][i]["in"] = round(max(0.0, min(float(args.seconds), hi)), 3)
    finish(project, clips, f"slot {i + 1} now starts {project['slots'][i]['in']:.2f}s into clip {clip['id']} (max {hi:.2f})")


def cmd_drop(args) -> None:
    project, clips = load_project(), scan_clips()
    ids = [int(x) for x in args.clips]
    for cid in ids:
        clip_by_id(clips, cid)
        if cid not in project["excluded"]:
            project["excluded"].append(cid)
    for i, s in enumerate(project["slots"]):
        if s["clip"] in ids:
            rep = best_replacement(project, clips, i, set(ids))
            if rep is None or not place(project, i, rep):
                die(f"nothing left that fits slot {i + 1} — try `merge {i + 1}` or `restore`")
    finish(project, clips, f"dropped clip(s) {', '.join(map(str, ids))} and refilled their slots")


def cmd_restore(args) -> None:
    project, clips = load_project(), scan_clips()
    project["excluded"] = [c for c in project["excluded"] if c not in {int(x) for x in args.clips}]
    finish(project, clips, "restored — they're back in the pool (use `set` to put one in a slot)")


def cmd_hero(args) -> None:
    project, clips = load_project(), scan_clips()
    hero = clip_by_id(clips, int(args.clip))
    project["hero"] = hero["id"]
    drop_slot = next(
        (i for i in range(len(project["slots"])) if any(abs(project["cuts"][i] - d["time"]) < 1e-3 for d in project["_drops"])),
        None,
    )
    if drop_slot is None:
        finish(project, clips, f"hero = clip {hero['id']} (no drop in range, so nothing moved)")
        return
    old = project["slots"][drop_slot]["clip"]
    holder = [i for i, s in enumerate(project["slots"]) if s["clip"] == hero["id"]]
    project["slots"][drop_slot] = None
    if not place(project, drop_slot, hero):
        die(f"clip {hero['id']} is shorter than the drop slot ({slot_durs(project)[drop_slot]:.2f}s)")
    if holder and holder[0] != drop_slot:
        project["slots"][holder[0]] = None
        if not place(project, holder[0], clip_by_id(clips, old)):
            place(project, holder[0], best_replacement(project, clips, holder[0], set()) or hero)
    finish(project, clips, f"clip {hero['id']} now lands on the drop (slot {drop_slot + 1})")


def cmd_merge(args) -> None:
    project, clips = load_project(), scan_clips()
    i = parse_ref(args.slot, project, "slot")
    if i == 0:
        die("slot 1 has nothing before it to merge into — use `merge 2`")
    keep = project["slots"][i - 1]
    del project["cuts"][i]
    del project["slots"][i]
    project["slots"][i - 1] = None
    if not place(project, i - 1, clip_by_id(clips, keep["clip"])):
        rep = best_replacement(project, clips, i - 1, set())
        if rep is None or not place(project, i - 1, rep):
            die("no clip is long enough to hold the merged slot")
        print(f"(clip {keep['clip']} was too short for the longer hold — slot {i} now shows clip {rep['id']})")
    finish(project, clips, f"merged slot {i + 1} into slot {i} — the shot holds longer")


def cmd_split(args) -> None:
    project, clips = load_project(), scan_clips()
    i = parse_ref(args.slot, project, "slot")
    info = load_json(ROOT / project["beats"])
    a, b = project["cuts"][i], project["cuts"][i + 1]
    inside = [t for t in info["beats"] if a + 1e-3 < t < b - 1e-3]
    if not inside:
        die(f"slot {i + 1} is a single beat — it can't be split")
    mid = min(inside, key=lambda t: abs(t - (a + b) / 2))
    orig = clip_by_id(clips, project["slots"][i]["clip"])
    project["cuts"].insert(i + 1, mid)
    project["slots"].insert(i + 1, None)
    project["slots"][i] = None
    # the original clip keeps the first half; the second half gets something else
    place(project, i, orig)
    rep = best_replacement(project, clips, i + 1, {orig["id"]}) or orig
    place(project, i + 1, rep)
    finish(project, clips, f"split slot {i + 1} at {mid - project['cuts'][0]:.2f}s — slot {i + 2} shows clip {rep['id']}")


def cmd_caption(args) -> None:
    project, clips = load_project(), scan_clips()
    text = " ".join(args.text).strip()
    project["caption"] = None if text.lower() in ("", "none", "off") else text
    finish(project, clips, "caption cleared" if project["caption"] is None else f"caption set: {project['caption']}")


def cmd_retime(args) -> None:
    """length / start / density all change the cut grid, so the edit is rebuilt."""
    project, clips = load_project(), scan_clips()
    if args.what == "length":
        project["length"] = float(args.value[0])
    elif args.what == "start":
        project["audio_start"] = float(args.value[0])
    elif args.what == "density":
        for kv in args.value:
            if kv in DENSITY_PRESETS:
                project["density"] = dict(DENSITY_PRESETS[kv])
                continue
            k, v = kv.split("=")
            if k not in project["density"]:
                die(f"density keys are {', '.join(project['density'])} (or a preset: {', '.join(DENSITY_PRESETS)})")
            project["density"][k] = int(v)
    replan(project, clips, int(args.seed) if args.seed is not None else None)
    finish(project, clips, f"{args.what} changed — the cut grid and the clip order were rebuilt")


def cmd_shuffle(args) -> None:
    project, clips = load_project(), scan_clips()
    seed = int(args.seed) if args.seed is not None else random.randrange(10_000)
    assign_all(project, clips, seed)
    finish(project, clips, f"reshuffled the clip order (seed {seed}) — same cuts, different clips in them")


# ------------------------------------------------------------------ render

def cmd_render(args) -> None:
    project, clips = load_project(), scan_clips()
    byid = {c["id"]: c for c in clips}
    OUT.mkdir(exist_ok=True)
    cuts, start = project["cuts"], project["cuts"][0]
    fps = FPS
    w, h = (540, 960) if args.draft else (W, H)
    frames = [round((cuts[i + 1] - start) * fps) - round((cuts[i] - start) * fps) for i in range(len(cuts) - 1)]
    total_frames = sum(frames)
    total = total_frames / fps

    cmd = ["ffmpeg", "-y", "-v", "error"]
    filters = []
    hw = ["-hwaccel", "videotoolbox"] if sys.platform == "darwin" and not args.no_hwaccel else []
    for i, (slot, nf) in enumerate(zip(project["slots"], frames)):
        c = byid[slot["clip"]]
        cmd += hw + ["-ss", f"{slot['in']:.3f}", "-t", f"{nf / fps + 0.6:.3f}", "-i", c["path"]]
        filters.append(
            f"[{i}:v]fps={fps},setpts=PTS-STARTPTS,"
            f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
            f"trim=end_frame={nf},setpts=PTS-STARTPTS[v{i}]"
        )
    n = len(frames)
    cmd += ["-i", str(ROOT / project["sound"])]
    filters.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
    if project.get("caption"):
        cap = OUT / ".caption.png"
        caption_png(project["caption"], w, h, cap)
        cmd += ["-i", str(cap)]  # input n+1; the sound stays input n
        filters.append(f"[vc][{n + 1}:v]overlay=0:0:format=auto,format=yuv420p[vo]")
    else:
        filters.append("[vc]format=yuv420p[vo]")
    fade = min(0.4, total / 4)
    filters.append(
        f"[{n}:a]atrim=start={start:.3f}:end={start + total:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=out:st={total - fade:.3f}:d={fade:.3f}[ao]"
    )
    cmd += ["-filter_complex", ";".join(filters), "-map", "[vo]", "-map", "[ao]", "-r", str(fps), "-frames:v", str(total_frames)]
    name = args.name or out_name(project)
    out_path = out_dir(project) / f"{name}.mp4"
    tail = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(out_path)]
    vt = ["-c:v", "h264_videotoolbox", "-b:v", "4M" if args.draft else "12M", "-profile:v", "high", "-allow_sw", "1"]
    x264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23" if args.draft else "19"]
    if args.verbose:
        print(" ".join(cmd + vt + tail))
    p = subprocess.run(cmd + vt + tail, text=True, capture_output=True)
    if p.returncode and hw:  # hardware decode refused the source: plain decode
        cmd = [a for a in cmd if a not in ("-hwaccel", "videotoolbox")]
        p = subprocess.run(cmd + vt + tail, text=True, capture_output=True)
    if p.returncode:
        p = subprocess.run(cmd + x264 + tail, text=True, capture_output=True)
        if p.returncode:
            die(f"ffmpeg failed:\n{p.stderr[-3000:]}")
    # keep a numbered copy in versions/ so earlier renders survive the next one
    vdir = out_path.parent / "versions"
    vdir.mkdir(exist_ok=True)
    vers = sorted(vdir.glob(f"{name}.v*.mp4"), key=lambda p: natural_key(p.name))
    nxt = (int(re.search(r"\.v(\d+)\.mp4$", vers[-1].name).group(1)) + 1) if vers else 1
    shutil.copy2(out_path, vdir / f"{name}.v{nxt}.mp4")
    size = out_path.stat().st_size / 1e6
    print(f"rendered {rel(out_path)} · {total:.2f}s · {n} cuts · {w}x{h} · {size:.1f} MB (copy: versions/{name}.v{nxt}.mp4)")


# ------------------------------------------------------------------ export

CAPCUT_DRAFTS = Path.home() / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"


def capcut_bin() -> list[str]:
    """capcut-cli (npm) — the community tool that writes CapCut's on-disk drafts and
    tracks the format drift between CapCut versions. Installed with
    `npm install -g capcut-cli`; nvm keeps it out of a bare PATH, so look there too."""
    found = shutil.which("capcut")
    if found:
        return [found]
    for p in sorted((Path.home() / ".nvm" / "versions" / "node").glob("*/bin/capcut")):
        return [str(p)]
    if shutil.which("npx"):
        return ["npx", "-y", "capcut-cli"]
    die("capcut-cli isn't installed — run: npm install -g capcut-cli")


def capcut_running() -> bool:
    return subprocess.run(["pgrep", "-f", "CapCut.app/Contents/MacOS/CapCut"], capture_output=True).returncode == 0


def quit_capcut(timeout: float = 20.0) -> None:
    import time
    try:  # the quit can hang behind a dialog; don't let it hang the export
        subprocess.run(["osascript", "-e", 'tell application "CapCut" to quit'], capture_output=True, timeout=15)
    except subprocess.TimeoutExpired:
        pass
    t0 = time.time()
    while capcut_running() and time.time() - t0 < timeout:
        time.sleep(0.5)
    if capcut_running():  # a fresh draft has nothing unsaved; the app just ignores AppleScript
        subprocess.run(["pkill", "-x", "CapCut"], capture_output=True)
        time.sleep(2)


def osa(script: str) -> str:
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return (p.stdout or p.stderr).strip()


def mouse_click(x: float, y: float) -> None:
    """A REAL mouse click via Quartz (move, down, up). CapCut's home screen is a
    canvas that ignores accessibility `click at`, but takes this."""
    import time
    from Quartz import (CGEventCreateMouseEvent, CGEventPost, kCGEventLeftMouseDown,
                        kCGEventLeftMouseUp, kCGEventMouseMoved, kCGHIDEventTap, kCGMouseButtonLeft)
    pt = (x, y)
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventMouseMoved, pt, kCGMouseButtonLeft))
    time.sleep(0.15)
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft))
    time.sleep(0.05)
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft))


# Where the FIRST project tile sits on CapCut 9.5's home screen, relative to the
# window's top-left, in points. The sidebar is fixed-width and the sections above
# the Projects grid have fixed heights, so this holds for any normal window size;
# the newest project (ours, just written) is always the first tile.
CAPCUT_FIRST_TILE = (306, 782)


def open_in_capcut(name: str, draft_dir: Path) -> bool:
    """Launch CapCut and click the newest project tile; True when CapCut starts
    writing into the draft folder (Timelines/, draft_settings…), which it does the
    moment it opens a project — the window title stays "CapCut" in both views.
    Needs Accessibility for the Claude Code runtime (see CLAUDE.md); without it
    this just launches CapCut."""
    import time
    before = set(p.name for p in draft_dir.iterdir())
    subprocess.run(["open", "-a", "CapCut"], check=False)
    win = 'tell application "System Events" to tell process "CapCut" to get {position, size} of (first window whose subrole is "AXStandardWindow")'
    geo = ""
    for _ in range(40):  # wait for the home window
        time.sleep(0.5)
        geo = osa(win)
        if geo and "error" not in geo:
            break
    if not geo or "error" in geo:
        print("  (couldn't reach CapCut's window — Accessibility not granted? The project is at the top of its list.)")
        return False
    time.sleep(3)  # let the home screen settle
    # a first-launch / update dialog in front? its close button honours AX clicks
    osa('tell application "System Events" to tell process "CapCut" to click (first button of (first window whose subrole is "AXDialog") whose description is "close button")')
    osa('tell application "System Events" to tell process "CapCut" to set frontmost to true')
    time.sleep(0.5)
    geo = osa(win)
    try:
        x, y, w, h = [int(v) for v in geo.replace(" ", "").split(",")]
    except ValueError:
        return False
    # the home screen can still be loading (sign-in sync, project list) when the
    # window first appears, and a click then is swallowed — so click, wait for
    # CapCut to start writing into the draft, and try again a couple of times
    for attempt in range(4):
        try:
            mouse_click(x + CAPCUT_FIRST_TILE[0], y + CAPCUT_FIRST_TILE[1])
        except Exception as e:  # noqa: BLE001 — pyobjc missing or event tap refused
            print(f"  (couldn't click: {e})")
            return False
        for _ in range(12):
            time.sleep(0.5)
            if set(p.name for p in draft_dir.iterdir()) - before:
                return True
        time.sleep(3)
    return False


def capcut_spec(project: dict, clips: list[dict]) -> tuple[dict, float]:
    """The edit as a capcut-cli compile spec: one video track with every slot as a
    segment (same frame-exact timing as `render`), one audio track with the sound."""
    byid = {c["id"]: c for c in clips}
    cuts, start = project["cuts"], project["cuts"][0]
    frames = [round((cuts[i + 1] - start) * FPS) - round((cuts[i] - start) * FPS) for i in range(len(cuts) - 1)]
    # CapCut stores microseconds; capcut-cli rounds each value on its own, so starts
    # must be the running sum of the ROUNDED durations or 1 µs gaps appear between
    # segments — and CapCut closes main-track gaps on open by shifting clips left.
    items, t_us = [], 0
    for slot, nf in zip(project["slots"], frames):
        d_us = round(nf / FPS * 1_000_000)
        items.append({
            "path": str(Path(byid[slot["clip"]]["path"]).resolve()),
            "start": t_us / 1_000_000,
            "duration": d_us / 1_000_000,
            "sourceStart": slot["in"],
            "type": "video",
        })
        t_us += d_us
    total = t_us / 1_000_000
    spec = {
        "name": out_name(project),
        "width": W, "height": H, "fps": FPS, "ratio": "9:16",
        "tracks": [
            {"type": "video", "name": "beatcut", "items": items},
            {"type": "audio", "name": "sound", "items": [{
                "path": str((ROOT / project["sound"]).resolve()),
                "start": 0, "duration": total, "sourceStart": round(start, 6), "volume": 1,
            }]},
        ],
    }
    return spec, total


def cmd_export(args) -> None:
    project, clips = load_project(), scan_clips()
    spec, total = capcut_spec(project, clips)
    name = out_name(project)
    spec_path = out_dir(project) / f"{name}.capcut.json"
    save_json(spec_path, spec)
    drafts = Path(args.drafts).expanduser() if args.drafts else CAPCUT_DRAFTS
    if not drafts.exists():
        die(f"CapCut's draft folder isn't there yet ({drafts}). Open CapCut once and create any "
            "empty project — that also gives capcut-cli a real project to seed ours from.")
    dest = drafts / name
    # Ernest's rule (2026-10-07): a re-run ALWAYS starts the template over — the old
    # project of the same name is deleted, CapCut edits included. Only our own dayN_V
    # names are ever touched, never CapCut's seed project.
    cc = capcut_bin()
    # capcut-cli refuses to write a managed draft while the editor is open (the app may
    # overwrite it), so quit CapCut first — and only THEN replace an earlier export
    if capcut_running():
        print("CapCut is open — quitting it so the draft can be written…")
        quit_capcut()
        if capcut_running():
            die("CapCut wouldn't quit (an unsaved project dialog?). Close it and re-run export.")
    if dest.exists():
        shutil.rmtree(dest)
        print(f"  replaced the earlier '{name}' project (a re-run starts the template over)")
    p = run(cc + ["compile", str(spec_path), "--out", str(dest), "--template", "auto"], check=False)
    if p.returncode:
        die(f"capcut compile failed:\n{(p.stderr or p.stdout)[-1500:]}")
    # the CapCut 9.x-on-macOS recipe: mirror the timeline into the nested documents the
    # app actually reads, register the media so it isn't 'file inaccessible', then lint
    steps = [["sync-timelines", str(dest), "--nested", "--apply"],
             ["register", str(dest), "--materials", "--apply"],
             ["lint", str(dest), "--fix", "--no-check-paths"]]
    notes = []
    for s in steps:
        q = run(cc + s, check=False)
        if q.returncode:
            notes.append(f"{s[0]}: {(q.stderr or q.stdout).strip()[-300:]}")
    save_json(dest / ".beatcut.json", {"project": CUR, "spec": str(spec_path.relative_to(ROOT)), "total": total})
    print(f"CapCut project '{name}' written: {dest}")
    print(f"  {len(spec['tracks'][0]['items'])} clips on the video track, the sound on an audio track, {total:.2f}s, 1080x1920 @ {FPS}")
    for n in notes:
        print(f"  note — {n}")
    if args.open:
        if open_in_capcut(name, dest):
            print(f"  CapCut is open on '{name}' — edit away")
        else:
            print(f"  CapCut is open — '{name}' is the first tile under Projects; click it")
    else:
        print("  open it: uv run beatcut.py -p <name> export --open   (or open -a CapCut and click the first tile)")


# -------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(prog="beatcut", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--project", default="default", metavar="NAME",
                    help="which edit to work on (projects/NAME.json, renders to out/NAME.mp4); default: 'default' -> out/final.mp4")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sound", help="download a sound (TikTok video or sound-page link, Instagram reel, YouTube, local file) and find its beats + drops")
    s.add_argument("source")
    s.add_argument("--cookies", metavar="BROWSER", help="chrome / safari / firefox — lets yt-dlp use that browser's login (Instagram)")
    s.set_defaults(fn=cmd_sound)
    sub.add_parser("setup", help="one-time: check ffmpeg / yt-dlp / font and install the headless browser").set_defaults(fn=cmd_setup)

    sub.add_parser("clips", help="list the clips in clips/ with their numbers").set_defaults(fn=cmd_clips)
    sub.add_parser("sheet", help="contact sheet of the numbered clips -> out/_clips.jpg").set_defaults(fn=cmd_sheet)
    s = sub.add_parser("frames", help="timestamped frame sheet per clip -> out/_frames_<clip>.jpg (read it before planning)")
    s.add_argument("clips", nargs="*", help="clip paths (default: the project's clips)")
    s.add_argument("--n", type=int, help="frames per clip (default: one every ~4 s, 6-30)")
    s.set_defaults(fn=cmd_frames)

    s = sub.add_parser("plan", help="build the edit: cut grid from the beats + a clip in every slot")
    s.add_argument("--clips", nargs="*", metavar="PATH", help="the clips for this edit, in order (numbered 1..N); default: the files in clips/")
    s.add_argument("--clips-dir", metavar="DIR", help="use every clip in a folder, e.g. clips/day2")
    s.add_argument("--sound", metavar="LINK", help="fetch + analyze this sound first (same as running `sound`)")
    s.add_argument("--cookies", metavar="BROWSER", help="for --sound on Instagram, see `sound --cookies`")
    s.add_argument("--length", type=float, metavar="SECONDS",
                   help="ideal length of the video in seconds, e.g. 10 or 60 — it ends on the nearest downbeat (default 30)")
    s.add_argument("--start", type=float, help="where in the sound to begin (default: the suggested start)")
    s.add_argument("--preset", choices=list(DENSITY_PRESETS), help="how often to cut: tight (default), loose, chill")
    s.add_argument("--first", type=int, metavar="CLIP", help="clip number that always opens the video (slot 1 is cut to fit it)")
    s.add_argument("--story", metavar="IDS", help="clip numbers in story order, e.g. 2,1,3 — footage is used chronologically across the video")
    s.add_argument("--random", action="store_true", help="random clip + random in-point per slot, no footage re-shown (use --seed to vary / repeat)")
    s.add_argument("--hero", type=int, help="clip number that lands on the drop (default: the longest; ignored with --story)")
    s.add_argument("--exclude", nargs="*", help="clip numbers to leave out")
    s.add_argument("--shuffle", action="store_true", help="random clip order instead of longest-to-longest (no --story)")
    s.add_argument("--seed", type=int, default=None, help="vary the combination: jitters --story in-points / seeds --shuffle")
    s.set_defaults(fn=cmd_plan)

    sub.add_parser("show", help="print the edit").set_defaults(fn=cmd_show)
    sub.add_parser("board", help="storyboard, one frame per slot -> out/_board.jpg").set_defaults(fn=cmd_board)

    s = sub.add_parser("export", help="write the edit as a CapCut project (every cut editable) into CapCut's drafts folder")
    s.add_argument("--open", action="store_true", help="launch CapCut afterwards")
    s.add_argument("--drafts", metavar="DIR", help="CapCut draft folder (default: CapCut's own on macOS)")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("render", help="write out/<project>.mp4")
    s.add_argument("--draft", action="store_true", help="540x960 quick check")
    s.add_argument("--name", help="output name (default: the project name, or final)")
    s.add_argument("--no-hwaccel", action="store_true", help="decode on the CPU")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("swap", help="swap two slots (7 = slot 7, c7 = the slot holding clip 7)")
    s.add_argument("a"); s.add_argument("b"); s.set_defaults(fn=cmd_swap)
    s = sub.add_parser("move", help="move slot A to position B")
    s.add_argument("a"); s.add_argument("b"); s.set_defaults(fn=cmd_move)
    s = sub.add_parser("set", help="put clip N into a slot, optionally at a given in-point")
    s.add_argument("slot"); s.add_argument("clip"); s.add_argument("--at", type=float); s.set_defaults(fn=cmd_set)
    s = sub.add_parser("in", help="set where in its clip a slot starts (seconds)")
    s.add_argument("slot"); s.add_argument("seconds"); s.set_defaults(fn=cmd_in)
    s = sub.add_parser("drop", help="remove clip(s) from the video entirely; their slots are refilled")
    s.add_argument("clips", nargs="+"); s.set_defaults(fn=cmd_drop)
    s = sub.add_parser("restore", help="un-exclude clip(s)")
    s.add_argument("clips", nargs="+"); s.set_defaults(fn=cmd_restore)
    s = sub.add_parser("hero", help="which clip lands on the drop")
    s.add_argument("clip"); s.set_defaults(fn=cmd_hero)
    s = sub.add_parser("merge", help="join a slot into the previous one (the shot holds longer)")
    s.add_argument("slot"); s.set_defaults(fn=cmd_merge)
    s = sub.add_parser("split", help="cut a slot in two on its middle beat")
    s.add_argument("slot"); s.set_defaults(fn=cmd_split)
    s = sub.add_parser("caption", help="burn a hook caption into the video (`caption none` clears)")
    s.add_argument("text", nargs="*"); s.set_defaults(fn=cmd_caption)
    s = sub.add_parser("shuffle", help="same cuts, re-randomize which clip is in each")
    s.add_argument("--seed", default=None); s.set_defaults(fn=cmd_shuffle)
    for what in ("length", "start", "density"):
        s = sub.add_parser(what, help={
            "length": "change the video length in seconds (rebuilds the edit)",
            "start": "change where in the sound the video begins (rebuilds the edit)",
            "density": "calm=4 hype=2 burst=4 hold=4 — beats per cut (rebuilds the edit)",
        }[what])
        s.add_argument("value", nargs="+")
        s.add_argument("--seed", default=None)
        s.set_defaults(fn=cmd_retime, what=what)

    args = ap.parse_args()
    global CUR
    CUR = re.sub(r"[^A-Za-z0-9_.-]", "_", args.project) or "default"
    args.fn(args)


if __name__ == "__main__":
    main()
