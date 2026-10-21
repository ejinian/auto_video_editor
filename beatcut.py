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
import os
import math
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIPS, SOUND, OUT = ROOT / "clips", ROOT / "sound", ROOT / "out"
PROJECTS = ROOT / "projects"
FINAL = ROOT / "final"  # finished videos only, flat — the folder Ernest opens; out/ is the workspace
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
    if clip_path:  # any shoot folder under clips/ (day4, tennis, gym_oct9…)
        m = re.search(r"/clips/([^/]+)/", clip_path)
        day = m.group(1) if m else None
    if day is None and project is not None:  # project <folder>_V → out/<folder>/
        m = re.match(r"(.+)_\d+$", out_name(project))
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
        p = p.resolve()
        if p.parent == SOUND.resolve() and p.suffix == ".mp3":
            # already one of ours: analyze IN PLACE. Christian hit the alternative on
            # 2026-10-08 — ffmpeg re-encoding a file onto itself truncated DUNG DING
            # BREGA to 1.4 s (Path equality missed the same file spelled two ways).
            meta = {"source": str(p), "title": p.stem}
            save_json(p.with_suffix(".source.json"), meta)
            return p, meta
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
    # the CapCut export is optional — report, don't fail
    cc = shutil.which("capcut") or next((str(p) for p in (Path.home() / ".nvm" / "versions" / "node").glob("*/bin/capcut")), None)
    print(f"capcut-cli: {cc or 'missing — npm install -g capcut-cli   (only for `export`)'}")
    if Path("/Applications/CapCut.app").exists():
        seeds = [p for p in CAPCUT_DRAFTS.glob("*/draft_meta_info.json")] if CAPCUT_DRAFTS.exists() else []
        print(f"CapCut: installed · projects in its store: {len(seeds)}"
              + ("" if seeds else " — open CapCut, click Create project once, quit (the export needs that seed)"))
    else:
        print("CapCut: not installed (only needed for `export`: brew install --cask capcut)")
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

HDR_TRANSFERS = {"arib-std-b67", "smpte2084"}  # HLG, PQ — what iPhones shoot since ~2020


def sdr_proxy(p: Path) -> Path:
    """An HDR phone clip rendered straight to SDR comes out flat and grey (Ernest:
    'I hate the lighting changes'). This ffmpeg has no zscale/libplacebo, so the HDR→SDR
    tone mapping is done ONCE per clip by macOS's own AVFoundation (`avconvert`), which
    is the same mapping QuickTime and Photos use to show the clip — i.e. the phone look.
    The proxy (H.264 4K, same length) lives next to the clip in .sdr/ and every stage
    (frames, board, render, export) reads it instead of the original."""
    out = p.parent / ".sdr" / (p.stem + ".mov")
    if out.exists() and out.stat().st_mtime >= p.stat().st_mtime:
        return out
    out.parent.mkdir(exist_ok=True)
    print(f"  tone-mapping {p.name} to SDR once (Apple avconvert)…", file=sys.stderr)
    r = subprocess.run(["avconvert", "--preset", "Preset3840x2160", "--source", str(p), "--output", str(out)],
                       capture_output=True, text=True)
    if r.returncode or not out.exists():
        die(f"avconvert failed on {p.name}: {(r.stderr or r.stdout)[-400:]}")
    return out


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
        if key not in cache or "hdr" not in cache[key]:
            out = run([
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,color_transfer:stream_side_data=rotation:format=duration",
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
            cache[key] = {"duration": float(j["format"]["duration"]), "w": w, "h": h,
                          "hdr": s.get("color_transfer") in HDR_TRANSFERS}
        c = dict(cache[key])
        c.update(id=i, name=p.name, src=str(p), path=str(sdr_proxy(p) if c["hdr"] else p))
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


def caption_png(text: str, w: int, h: int, path: Path, y_frac: float = 0.17, size_frac: float = 0.036) -> None:
    """A transparent w×h layer with the hook caption in TikTok Sans, white with the
    classic black outline, centred at 17% down — the same look the app bakes.
    (`y_frac` / `size_frac`: the narrated reformat puts its lines lower and larger.)"""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = int(h * size_frac)
    fnt = font(size)
    stroke = max(2, int(size * 0.13))
    gap = int(size * 0.28)
    y = int(h * y_frac)
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
    # Per-process temp dir: several agents run frames/board at once, and a shared
    # out/.frames that each caller rmtree'd wiped the others' half-written frames.
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".frames-", dir=OUT))
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
        clips = []
        for p in paths:
            tr = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=color_transfer", "-of", "csv=p=0", str(p)]).stdout.strip()
            media = sdr_proxy(p) if tr in HDR_TRANSFERS else p
            clips.append({"path": str(media), "name": p.name,
                          "duration": float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).stdout)})
    else:
        clips = scan_clips()
    for c in clips:
        n = args.n or max(6, min(30, round(c["duration"] / 4)))
        # never sample past the last frame (a dense --n on a 1.5 s clip did, and ffmpeg
        # fails with a misleading "Non full-range YUV" error)
        times = [min(c["duration"] * i / n + 0.05, max(0.0, c["duration"] - 0.1)) for i in range(n)]
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


FREE_RANGES = {"tight": (0.6, 1.4), "loose": (1.4, 3.2), "chill": (3.0, 6.0)}  # seconds per shot


def build_free_cuts(start: float, length: float, duration: float, preset: str, seed: int | None,
                    max_slot: float, first_max: float | None) -> list[float]:
    """Cuts that ignore the beats (Ernest's default since 2026-10-09: the sound just plays
    underneath). Shot lengths are drawn from the preset's range, seeded, so a re-plan
    repeats and a new seed is a new rhythm. The video still plays the sound to its end
    when the sound is shorter than the asked length."""
    rng = random.Random(seed if seed is not None else 0)
    lo, hi = FREE_RANGES.get(preset, FREE_RANGES["tight"])
    hi = min(hi, max_slot)
    lo = min(lo, hi)
    end = min(start + length, duration)
    cuts, t = [start], start
    if first_max is not None:
        d = min(rng.uniform(lo, hi), first_max)
        cuts.append(t + d)
        t += d
    while end - t > hi * 1.5:
        d = rng.uniform(lo, hi)
        cuts.append(t + d)
        t += d
    while end - t > max_slot:  # the remainder must still fit the clips
        cuts.append(t + max_slot * 0.9)
        t += max_slot * 0.9
    cuts.append(end)
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
    if project.get("sync"):
        project["cuts"] = build_cuts(info, project["audio_start"], project["length"], project["density"], max_slot, first_max)
        project["_drops"] = [d for d in info["drops"] if project["cuts"][0] <= d["time"] <= project["cuts"][-1]]
    else:
        project["cuts"] = build_free_cuts(project["audio_start"], project["length"], info["duration"],
                                          project.get("preset", "tight"), project.get("seed"), max_slot, first_max)
        project["_drops"] = []
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
    # a remix that is re-planned (another opener, another sound) stays a remix of its source
    prev = load_json(project_path()) if project_path().exists() else {}
    for k in ("remix_of", "remix"):
        if prev.get(k):
            project[k] = prev[k]
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
        "preset": args.preset or "tight",
        "sync": bool(args.sync),
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


# ------------------------------------------------------------------- remix

REMIX_RECIPES = {
    "hook": "8 s, tight, opens on the strongest shot, random angles — the watch-it-again cut",
    "sound": "the same story on another sound from the pool, loose pace",
    "reorder": "15 s, random angles with a new seed, a different opener",
    "long": "30 s, chill, the footage the original used least, first — on a second other sound if the pool has one",
}


def pool_sounds(exclude: set[str]) -> list[dict]:
    """Other sounds in sound/, the ones with a clear drop first, then newest first."""
    out = []
    for mp3 in SOUND.glob("*.mp3"):
        beats = mp3.with_suffix(".beats.json")
        if rel(mp3) in exclude or not beats.exists():
            continue
        info = load_json(beats)
        src = mp3.with_suffix(".source.json")
        out.append({"sound": rel(mp3), "beats": rel(beats), "meta": load_json(src) if src.exists() else {},
                    "drops": len(info.get("drops", [])), "mtime": mp3.stat().st_mtime})
    out.sort(key=lambda s: (-(s["drops"] > 0), -s["mtime"]))
    return out


def video_duration(p: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).stdout.strip()
    return float(out or 0)


def split_video(video: Path, folder: Path, min_shot: float = 1.5, threshold: float = 0.3) -> list[Path]:
    """Cut a finished video into its shots (ffmpeg scene detection), one clip per shot in
    `folder` — shot_01.mp4, shot_02.mp4… in order. Scene changes closer than `min_shot`
    to the previous cut are skipped, so every shot is long enough to hold a slot (a
    0.6 s shot would be unusable after the head/tail margins). Audio is dropped: the
    remixes get their own sound. Re-encoded (H.264, videotoolbox when it works) because a
    stream copy can only cut on keyframes."""
    dur = video_duration(video)
    if dur < 2:
        die(f"{video.name} is {dur:.1f} s — nothing to split")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    times = sorted(float(m) for m in re.findall(r"pts_time:\s*([0-9.]+)", r.stderr))
    cuts, last = [0.0], 0.0
    for t in times:
        if t - last >= min_shot and dur - t >= min_shot:
            cuts.append(t)
            last = t
    cuts.append(dur)
    folder.mkdir(parents=True, exist_ok=True)
    shots: list[Path] = []
    for i in range(len(cuts) - 1):
        s, e = cuts[i], cuts[i + 1]
        out = folder / f"shot_{i + 1:02d}.mp4"
        base = ["ffmpeg", "-y", "-v", "error", "-ss", f"{s:.3f}", "-i", str(video), "-t", f"{e - s:.3f}", "-an", "-pix_fmt", "yuv420p"]
        p = subprocess.run(base + ["-c:v", "h264_videotoolbox", "-b:v", "12M", str(out)], capture_output=True, text=True)
        if p.returncode or not out.exists():
            run(base + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)])
        shots.append(out)
    print(f"split {video.name} ({dur:.1f} s) into {len(shots)} shots → {rel(folder)}/ (scene changes ≥ {min_shot} s apart)")
    return shots


def fetch_video(url: str, into: Path, cookies: str | None = None) -> Path:
    """Download a posted video to `into/<slug>.mp4`: TikTok through tikwm (the same
    keyless API `sound` uses; `hdplay`/`play` is the post without the watermark),
    everything else (Instagram reels, YouTube) through yt-dlp as an mp4."""
    into.mkdir(parents=True, exist_ok=True)
    if "tiktok.com" in url:
        _, final = http_get(url)
        canonical = final.split("?")[0]
        if "/music/" in canonical:
            die("that is a sound page, not a post — paste a video link that uses the sound")
        last = None
        for candidate in dict.fromkeys([canonical, final, url]):
            try:
                body, _ = http_get("https://www.tikwm.com/api/?url=" + urllib.parse.quote(candidate, safe=""))
                j = json.loads(body)
            except Exception as e:  # noqa: BLE001
                last = str(e)
                continue
            if j.get("code") == 0 and j.get("data"):
                d = j["data"]
                play = d.get("hdplay") or d.get("play")
                if not play:
                    die("tikwm resolved the post but it carries no video url")
                if play.startswith("/"):
                    play = "https://www.tikwm.com" + play
                author = (d.get("author") or {}).get("unique_id") or "tiktok"
                out = into / f"{slugify(author)}-{str(d.get('id') or '')[-8:]}.mp4"
                data, _ = http_get(play, binary=True, timeout=300)
                if len(data) < 50_000:
                    die("the video download came back empty — the CDN link may have expired, re-run")
                out.write_bytes(data)
                print(f"downloaded @{author}'s post ({len(data) / 1e6:.1f} MB) → {rel(out)}")
                return out
            last = j.get("msg")
        die(f"could not resolve {url} via tikwm ({last})")
    yd = ytdlp_bin()
    if not yd:
        die("yt-dlp isn't installed — run: uv tool install yt-dlp")
    hint = ("\nInstagram often wants a logged-in browser: re-run with `--cookies chrome` "
            "(or safari / firefox)" if "instagram.com" in url and not cookies else "")
    base = [yd, "--no-warnings"] + (["--cookies-from-browser", cookies] if cookies else [])
    p = run(base + ["--skip-download", "--print", "%(id)s\t%(uploader)s", url], check=False)
    if p.returncode:
        die(f"yt-dlp couldn't read that link:\n{p.stderr.strip()[-600:]}{hint}")
    vid, uploader = (p.stdout.strip().split("\t") + [""])[:2]
    out = into / f"{(slugify(uploader)[:20] + '-' if uploader else '')}{slugify(vid)[-12:]}.mp4"
    p = run(base + ["-q", "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b", "--merge-output-format", "mp4", "-o", str(out), url], check=False)
    if p.returncode or not out.exists():
        die(f"yt-dlp couldn't download the video:\n{p.stderr.strip()[-600:]}{hint}")
    print(f"downloaded {url} ({out.stat().st_size / 1e6:.1f} MB) → {rel(out)}")
    return out


def fetch_comments(url: str, count: int = 30) -> list[dict]:
    """The top comments of a posted video: TikTok through tikwm's comment list (keyless,
    the same API the download uses), others through yt-dlp's comments when it has them.
    Each: {user, text, likes}, most liked first."""
    out: list[dict] = []
    if "tiktok.com" in url:
        _, final = http_get(url)
        canonical = final.split("?")[0]
        for candidate in dict.fromkeys([canonical, final, url]):
            try:
                body, _ = http_get(f"https://www.tikwm.com/api/comment/list?url={urllib.parse.quote(candidate, safe='')}&count={count}")
                j = json.loads(body)
            except Exception:  # noqa: BLE001
                continue
            if j.get("code") == 0 and j.get("data"):
                for c in (j["data"].get("comments") or []):
                    text = (c.get("text") or "").strip()
                    if text:
                        out.append({"user": (c.get("user") or {}).get("unique_id") or "", "text": text, "likes": int(c.get("digg_count") or 0)})
                break
    else:
        yd = ytdlp_bin()
        if yd:
            p = run([yd, "--no-warnings", "--skip-download", "--write-comments", "--no-write-info-json", "-j", url], check=False)
            try:
                info = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}
            except ValueError:
                info = {}
            for c in (info.get("comments") or [])[:count]:
                text = (c.get("text") or "").strip()
                if text:
                    out.append({"user": c.get("author") or "", "text": text, "likes": int(c.get("like_count") or 0)})
    out.sort(key=lambda c: -c["likes"])
    return out[:count]


def cmd_comments(args) -> None:
    cs = fetch_comments(args.link, args.count)
    if not cs:
        die("no comments found (TikTok posts work keylessly; Instagram needs yt-dlp with a login and often gives none)")
    for i, c in enumerate(cs, 1):
        print(f"{i:>3}. {c['likes']:>6} ♥  @{c['user']}: {c['text'][:140]}")
    print(f"COMMENTS: {len(cs)}")


def pick_comment(project: dict, n: int) -> None:
    cs = project.get("comments") or []
    if not 1 <= n <= len(cs):
        die(f"--pick {n}: this video has {len(cs)} fetched comments (comments <link> lists them)")
    c = cs[n - 1]
    project["comment"] = {"text": c["text"], "user": c["user"] or None, "likes": c.get("likes", 0), "pick": n}


def cmd_shots(args) -> None:
    video = Path(args.video).expanduser()
    video = video if video.is_absolute() else ROOT / video
    if not video.exists():
        die(f"no such video: {args.video}")
    folder = CLIPS / (args.into or re.sub(r"[^A-Za-z0-9_-]+", "_", video.stem).strip("_").lower() or "shots")
    split_video(video, folder, args.min_shot)
    print(f"next: uv run beatcut.py -p {folder.name}_1 plan --clips-dir {rel(folder)} --story {','.join(map(str, range(1, len(list_dir_clips(folder)) + 1)))}")


def import_video(video: Path, name: str | None) -> str:
    """A finished video (an old post) as a project of its own shots: split it, its audio
    becomes a pool sound, and a project <folder>_N replays the shots in order on that
    sound — so `remix` has a source to work from. Returns the project name."""
    global CUR
    folder_name = name or re.sub(r"[^A-Za-z0-9_-]+", "_", video.stem).strip("_").lower() or "remix"
    folder = CLIPS / folder_name
    shots = list_dir_clips(folder) if folder.is_dir() else []
    if shots:
        print(f"using the {len(shots)} shots already in {rel(folder)}/")
    else:
        shots = split_video(video, folder)
    proj = next_name(folder_name)
    CUR = proj
    cmd_sound(argparse.Namespace(source=str(video), cookies=None))
    durs = sorted(video_duration(s) for s in shots)
    med = durs[len(durs) // 2]
    preset = cap_preset("tight" if med < 1.4 else "loose" if med < 3.2 else "chill", durs)
    # story order replays the shots in sequence; when the shots are too few or too short to
    # hold the slots that way (a two-shot talking head), the plain assignment reuses footage
    plan_args = dict(clips=[rel(s) for s in shots], clips_dir=None, sound=None, cookies=None, start=0.0, preset=preset, sync=False,
                     first=1, story=",".join(map(str, range(1, len(shots) + 1))), random=False, hero=None, exclude=[], shuffle=False,
                     seed=None, length=round(video_duration(video), 3))
    print(f"\n=== {proj}: {video.name} as its own {len(shots)} shots, in order ({preset})")
    try:
        cmd_plan(argparse.Namespace(**plan_args))
    except SystemExit:
        print("  (the shots can't replay in story order at this pace — footage is reused instead)")
        cmd_plan(argparse.Namespace(**{**plan_args, "story": None}))
    project = load_project()
    project["imported_from"] = rel(video)
    save_project(project)
    cmd_board(argparse.Namespace())
    return proj


def cap_preset(preset: str, durations: list[float]) -> str:
    """The pace a set of clips can hold: chill wants 3–6 s shots, loose 1.4–3.2, tight
    0.6–1.4 — a preset whose longest shot no clip could fill is stepped down (a 10 s
    talking-head reel split into two shots cannot play chill)."""
    longest = max(durations) - HEAD_TRIM - TAIL_PAD - 0.3
    for p in ("chill", "loose", "tight"):
        if p == preset or preset not in FREE_RANGES or FREE_RANGES[preset][1] > FREE_RANGES[p][1]:
            if FREE_RANGES[p][1] <= longest or p == "tight":
                return p
    return "tight"


def next_folder(prefix: str) -> str:
    """remix1, remix2… — the first with no clips folder and no project."""
    n = 1
    while (CLIPS / f"{prefix}{n}").exists() or list(PROJECTS.glob(f"{prefix}{n}_*.json")):
        n += 1
    return f"{prefix}{n}"


def next_name(prefix: str) -> str:
    PROJECTS.mkdir(exist_ok=True)
    ns = [int(m.group(1)) for q in PROJECTS.glob(f"{prefix}_*.json")
          if (m := re.fullmatch(rf"{re.escape(prefix)}_(\d+)", q.stem))]
    return f"{prefix}_{max(ns) + 1 if ns else 1}"


def cmd_remix(args) -> None:
    """Four new videos from the clips of a video that worked, each different enough to be
    a new post: a hook cut, the same story on another sound, a reorder, a long version.
    Each is a normal project (projects/<folder>_N.json, tagged remix_of / remix) that
    every other command edits as usual."""
    global CUR
    if args.video:
        if re.match(r"https?://", args.video):
            # a posted video: downloaded into the folder's .source/ first, then imported like a file
            name = args.name or next_folder("remix")
            video = fetch_video(args.video, CLIPS / name / ".source", args.cookies)
            CUR = import_video(video, name)
        else:
            video = Path(args.video).expanduser()
            video = video if video.is_absolute() else ROOT / video
            if not video.exists():
                die(f"no such video: {args.video}")
            CUR = import_video(video, args.name)
    src_name = CUR
    src = load_project()
    if src.get("kind") == "reformat":
        die(f"{CUR} is a reformat of {src['source']} — remix that video instead: remix --video {src['source']}")
    clips = scan_clips()
    pointer = current_sound()
    pointer_meta = pointer.get("meta", {})
    only = [x.strip() for x in (args.only or "").split(",") if x.strip()] or list(REMIX_RECIPES)
    for k in only:
        if k not in REMIX_RECIPES:
            die(f"unknown remix '{k}' — have: {', '.join(REMIX_RECIPES)}")

    # what the source did with its footage
    uses: dict[int, int] = {c["id"]: 0 for c in clips}
    for s in src["slots"]:
        uses[s["clip"]] = uses.get(s["clip"], 0) + 1
    excluded = set(src.get("excluded", []))
    usable = [c for c in clips if c["id"] not in excluded]
    if not usable:
        die("every clip of the source is excluded")
    drop_times = {round(d["time"], 3) for d in src.get("_drops", [])}
    drop_clip = next((s["clip"] for t, s in zip(src["cuts"], src["slots"]) if round(t, 3) in drop_times), None)
    longest = max(usable, key=lambda c: c["duration"])["id"]
    most_used = max(usable, key=lambda c: (uses.get(c["id"], 0), c["duration"]))["id"]
    strongest = drop_clip or src.get("hero") or src.get("first") or most_used or longest
    least_first = [c["id"] for c in sorted(usable, key=lambda c: (uses.get(c["id"], 0), -c["duration"]))]
    other_opener = next((s["clip"] for s in src["slots"][1:] if s["clip"] != src.get("first")), least_first[0])
    seed0 = int(src.get("seed") or 0)

    # other sounds: --sounds in order, else the pool minus the source's sound
    alts: list[dict] = []
    for sp in (args.sounds or []):
        p = Path(sp)
        p = p if p.is_absolute() else ROOT / p
        if not p.exists() or not p.with_suffix(".beats.json").exists():
            die(f"no analysed sound at {sp} (run `sound {sp}` first)")
        srcj = p.with_suffix(".source.json")
        alts.append({"sound": rel(p), "beats": rel(p.with_suffix(".beats.json")), "meta": load_json(srcj) if srcj.exists() else {}})
    alts += pool_sounds({src["sound"]} | {a["sound"] for a in alts})
    same = {"sound": src["sound"], "beats": src["beats"], "meta": pointer_meta}

    m = re.fullmatch(r"(.+)_\d+", src_name)
    prefix = m.group(1) if m else (re.search(r"^clips/([^/]+)/", src["clips"][0]).group(1) if src["clips"] else "remix")

    base = dict(clips=src["clips"], clips_dir=None, sound=None, cookies=None, start=None, preset=src.get("preset") or "tight",
                sync=bool(src.get("sync")), first=src.get("first"), story=None, random=False, hero=src.get("hero"),
                exclude=[str(x) for x in excluded], shuffle=False, seed=None, length=src.get("length") or 30)
    recipes = {
        "hook": (same, dict(length=8, preset="tight", first=strongest, random=True, seed=seed0 + 11)),
        "sound": (alts[0] if alts else same,
                  dict(preset="loose", story=",".join(map(str, src["story"])) if src.get("story") else None,
                       random=bool(src.get("random")) or not src.get("story"), seed=seed0 + 1)),
        "reorder": (same, dict(length=15, first=other_opener, random=True, seed=seed0 + 23)),
        "long": (alts[1] if len(alts) > 1 else (alts[0] if alts else same),
                 dict(length=30, preset="chill", first=least_first[0], story=",".join(map(str, least_first)), random=False, seed=seed0 + 5)),
    }
    if not alts:
        print("note: no other sound in sound/ — the 'sound' and 'long' remixes keep the source's sound (add one with `sound <link>`)", file=sys.stderr)

    def fit_start(snd: dict, length: float) -> float:
        """The sound's suggested start, unless the video would not fit before the sound ends
        (a drop near the end would leave a 6 s video) — then as late as the length allows."""
        info = load_json(ROOT / snd["beats"])
        s, d = float(info.get("suggested_start", 0.0)), float(info["duration"])
        return round(s if d - s >= length - 0.5 else max(0.0, d - length), 3)

    made: list[str] = []
    clip_durs = [c["duration"] for c in usable]
    for kind in only:
        snd, over = recipes[kind]
        over["start"] = fit_start(snd, float(over.get("length", base["length"])))
        over["preset"] = cap_preset(over.get("preset", base["preset"]), clip_durs)
        name = next_name(prefix)
        CUR = name
        save_json(PROJECTS / f"{name}.sound.json", {"sound": snd["sound"], "beats": snd["beats"], "meta": snd.get("meta", {})})
        print(f"\n=== {name}: {kind} remix of {src_name} — {REMIX_RECIPES[kind]}")
        try:
            cmd_plan(argparse.Namespace(**{**base, **over}))
        except SystemExit:
            # too little footage for that order (a short reel split into two shots):
            # the plain assignment reuses footage rather than giving up on the remix
            print(f"  (not enough footage for the {kind} recipe's order — footage is reused instead)")
            try:
                cmd_plan(argparse.Namespace(**{**base, **over, "story": None, "random": False}))
            except SystemExit:
                print(f"  skipped the {kind} remix: the source's clips can't fill it", file=sys.stderr)
                (PROJECTS / f"{name}.sound.json").unlink(missing_ok=True)
                continue
        project = load_project()
        project.update({"remix_of": src_name, "remix": kind, "caption": src.get("caption")})
        save_project(project)
        cmd_board(argparse.Namespace())
        if args.render:
            cmd_render(argparse.Namespace(draft=False, name=None, no_hwaccel=False, verbose=False))
        made.append(name)
    CUR = src_name
    print(f"\nremixes of {src_name}: {' '.join(made)}" + ("" if args.render else f"\nnext: uv run beatcut.py -p {made[0]} render   (each one)"))
    if args.video:
        print(f"SOURCE: {src_name}")
    print(f"REMIXES: {' '.join(made)}")


# ---------------------------------------------------------------- reformat
#
# A posted reel is already its best cut: re-dealing its shots only makes a worse
# version. A REFORMAT keeps the cut and changes the framing, each one a format TikTok
# viewers know: a new hook line on screen, a voice-over in the platform's own
# text-to-speech style, or the video as the answer to a comment. Each is a project of
# kind "reformat" (no cuts/slots: a source mp4 + overlays) that `render` bakes.

REFORMATS = {
    "hook": "the same video with a new hook line on screen",
    "narrated": "a voice-over in the TikTok text-to-speech style (2-3 lines, each shown as it is said; the original audio ducked under it)",
    "reply": "the video as the answer to a comment, with the comment bubble on top",
    "reaction": "an avatar reacting in the corner, silent (short image-to-video clips of the character, switched at the moments that earn a reaction; the original audio untouched)",
}
STYLES = {   # reformats that change the FEEL of the same cut (no AI generation; ffmpeg + the sound pool)
    "goofy": "the meme treatment: punch-zooms and a shake on the moments, a boom / a 'bruh' on the reveal, crunchy bass-boosted audio, big caption",
    "cinematic": "a trailer: slow motion on the key moment, letterbox bars, warm grade and grain, fades, a dramatic sound instead of the original audio",
}
STYLES["hype"] = ("the one that parlays the others (Christian, 2026-10-19): cinematic's slow motion, bars and grade with the ORIGINAL audio kept "
                  "and the song ducked under it, goofy's punch-zooms and booms, pop-in text, emoji, and snapshots — a polaroid of a frame "
                  "that pops in at an angle; the narration lines too, if it has any")
REFORMATS.update(STYLES)
HYPE_HOOK_HOLD = 4.0   # seconds the hook line stays on a hype (project `hook_hold`; 0 = the whole video)
STYLE_FX = {"goofy": ("zoom", "boom", "bruh", "nah", "whoosh"), "cinematic": ("slow", "riser"),
            "hype": ("zoom", "boom", "slow", "pop", "snap", "emoji", "riser", "whoosh", "bruh", "nah")}
SFX_DIR = SOUND / "_sfx"   # synthesized once (ffmpeg lavfi; 'bruh'/'nah' said by the narration voice)
AVATARS = CLIPS / "_avatar"   # clips/_avatar/<name>/<reaction>.mp4 — generated once, reused by every reaction reformat
REACTIONS = {   # what the avatar does; one short clip per key, image-to-video from the character's picture.
    # Calm, "presenting a product" reactions — nothing theatrical. Every prompt keeps the green screen.
    "nod": "the person nods gently in agreement with a small smile, looking at the camera, subtle natural movement, "
           "the solid green screen background stays unchanged, same framing",
    "agree": "the person smiles and nods once, then keeps looking at the camera calmly, subtle natural movement, "
             "the solid green screen background stays unchanged, same framing",
    "present": "the person gestures with an open hand toward the side as if showing something, warm smile, then looks back at the camera, "
               "subtle natural movement, the solid green screen background stays unchanged, same framing",
    "thumbs": "the person gives a relaxed thumbs up with a small smile, looking at the camera, subtle natural movement, "
              "the solid green screen background stays unchanged, same framing",
    "listen": "the person listens attentively with a slight head tilt and a soft smile, blinking naturally, "
              "the solid green screen background stays unchanged, same framing",
    "shocked": "the person's eyes widen in mild surprise and eyebrows go up, a small 'oh' expression, looking at the camera, "
               "the solid green screen background stays unchanged, same framing",
    "laugh": "the person laughs softly, genuinely amused, looking at the camera, subtle movement, "
             "the solid green screen background stays unchanged, same framing",
    "point": "the person points at the viewer with raised eyebrows and a knowing smile, "
             "the solid green screen background stays unchanged, same framing",
    "think": "the person thinks for a moment, eyes up, then raises an eyebrow at the camera, "
             "the solid green screen background stays unchanged, same framing",
}
HF_VIDEO_MODELS = {   # image-to-video endpoints, cheapest first (per second of output, list price)
    "kling-2.5": ("https://api.higgsfield.ai/kling-video/v2.5-turbo/standard/image-to-video", 0.042),
    "kling-3": ("https://api.higgsfield.ai/kling-video/v3.0/std/image-to-video", 0.112),
}
DEFAULT_VIDEO_MODEL = "kling-2.5"
HF_TEXT_TO_IMAGE = "https://api.higgsfield.ai/higgsfield-ai/soul/standard"
GENERIC_AVATAR = ("candid phone photo of a friendly guy in his early twenties in a black hoodie, headphones around his neck, "
                  "sitting in a gym with a laptop open, looking straight at the camera, natural light, slight smile, "
                  "head and shoulders, plain background, no text")


def hf_headers() -> dict:
    """Higgsfield auth: HF_KEY as the console hands it out (key-id:key-secret), or the
    pair HIGGSFIELD_KEY_ID / HIGGSFIELD_KEY_SECRET — in web/.env.local, never printed."""
    hf = web_env("HF_KEY") or web_env("HF_CREDENTIALS")
    if hf and ":" in hf:
        kid, secret = hf.split(":", 1)
    else:
        kid, secret = web_env("HIGGSFIELD_KEY_ID"), web_env("HIGGSFIELD_KEY_SECRET")
    if not kid or not secret:
        die("no Higgsfield key: put HF_KEY=key-id:key-secret in web/.env.local (console: open.higgsfield.ai → API keys)")
    return {"Authorization": f"Key {kid.strip()}:{secret.strip()}", "Content-Type": "application/json", "Accept": "application/json"}


def hf_json(url: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=hf_headers(), method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        die(f"Higgsfield refused ({e.code}): {e.read()[:400].decode('utf-8', 'replace')}")


def image_ref(image: str) -> str:
    """What Higgsfield gets as `image_url`: a public https URL as is; a local file as a
    data URL (accepted by the API's `uri` field; if it ever is not, host the picture
    somewhere public — the TikTok profile picture's URL works)."""
    if re.match(r"https?://", image):
        return image
    p = Path(image).expanduser()
    p = p if p.is_absolute() else ROOT / p
    if not p.exists():
        die(f"no such image: {image}")
    import base64
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(p.suffix.lower(), "image/png")
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def hf_wait(handle: dict, what: str) -> dict:
    """Poll a submitted Higgsfield request's status_url until it is completed."""
    status_url = handle.get("status_url")
    if not status_url:
        die(f"Higgsfield gave no status url for the {what}: {json.dumps(handle)[:300]}")
    print(f"  {what}: queued ({handle.get('request_id')})…", flush=True)
    state = "queued"
    for _ in range(240):
        time.sleep(5)
        st = hf_json(status_url)
        state = str(st.get("status", "")).lower()
        if state == "completed":
            return st
        if state in ("failed", "cancelled", "canceled", "error", "nsfw"):
            die(f"Higgsfield failed the {what}: {json.dumps(st)[:400]}")
    die(f"Higgsfield took too long on the {what} (still {state})")


def avatar_image(name: str, prompt: str) -> str:
    """The character's picture from a prompt (Soul, 1:1), kept as clips/_avatar/<name>/
    character.png; returns the hosted URL the video model takes as its first frame."""
    out = AVATARS / name / "character.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    st = hf_wait(hf_json(HF_TEXT_TO_IMAGE, {"prompt": prompt, "aspect_ratio": "9:16", "resolution": "720p"}), f"{name}'s picture")
    imgs = st.get("images") or []
    url = (imgs[0] or {}).get("url") if imgs else None
    if not url:
        die(f"Higgsfield finished but gave no image url: {json.dumps(st)[:300]}")
    data, _ = http_get(url, binary=True, timeout=120)
    out.write_bytes(data)
    (out.parent / "character.json").write_text(json.dumps({"prompt": prompt, "url": url, "green": "green screen" in prompt.lower() or "chroma" in prompt.lower()}, indent=1))
    print(f"  {name}'s picture → {rel(out)}")
    return url


def avatar_clip(name: str, reaction: str, image: str, seconds: int = 5, model: str = DEFAULT_VIDEO_MODEL) -> Path:
    """One reaction clip of the character via Higgsfield image-to-video (Kling 2.5 turbo
    standard by default, ≈ $0.21 for 5 s; `kling-3` is the pricier, steadier one), polled
    until done and downloaded to clips/_avatar/<name>/<reaction>.mp4."""
    out = AVATARS / name / f"{reaction}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    url, _ = HF_VIDEO_MODELS[model]
    body = {"image_url": image_ref(image), "prompt": REACTIONS[reaction] + ", no text, no captions", "duration": seconds, "cfg_scale": 0.5,
            "negative_prompt": "text, captions, watermark, background change, camera movement, extra people"}
    if model == "kling-3":
        body["sound"] = "off"
    st = hf_wait(hf_json(url, body), f"{name}/{reaction}")
    url = (st.get("video") or {}).get("url")
    if not url:
        die(f"Higgsfield finished but gave no video url: {json.dumps(st)[:300]}")
    data, _ = http_get(url, binary=True, timeout=300)
    out.write_bytes(data)
    print(f"  {name}/{reaction}: {len(data) / 1e6:.1f} MB → {rel(out)}")
    return out


def avatars() -> dict[str, list[str]]:
    """{name: [reactions that exist]} for every character under clips/_avatar/."""
    out: dict[str, list[str]] = {}
    if AVATARS.is_dir():
        for d in sorted(AVATARS.iterdir()):
            if d.is_dir() and not d.name.startswith(".") and (any(d.glob("*.mp4")) or (d / "character.png").exists()):
                out[d.name] = sorted(p.stem for p in d.glob("*.mp4"))
    return out


def cmd_avatar(args) -> None:
    """`avatar NAME [--image URL|FILE | --prompt TEXT] [--reactions nod,shocked,laugh]`
    generates the character's reaction clips once (Higgsfield, ~$0.4 each; without a
    picture Higgsfield draws the character first, Soul 1:1); `avatar --list` shows them."""
    if args.list or not args.name:
        have = avatars()
        if not have:
            print("no avatars yet — avatar <name> --image <url or file> makes one (needs HIGGSFIELD_KEY_ID/SECRET in web/.env.local)")
        for n, rs in have.items():
            print(f"{n}: {', '.join(rs) or '(no clips)'}")
        return
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", args.name).strip("_").lower()
    want = [x.strip() for x in (args.reactions or "").split(",") if x.strip()] or ["agree", "present", "listen"]
    for r in want:
        if r not in REACTIONS:
            die(f"unknown reaction '{r}' — have: {', '.join(REACTIONS)}")
    have = avatars().get(name, [])
    todo = [r for r in want if r not in have or args.redo]
    if not todo:
        print(f"{name} already has {', '.join(want)} — --redo to generate again")
        return
    image = args.image
    if args.image_only:
        # a cheap round: just the picture (a cent), to judge the character before any video
        print(f"drawing {name} with Higgsfield (Soul), picture only…")
        url = avatar_image(name, args.prompt or GENERIC_AVATAR)
        print(f"AVATAR_IMAGE: {rel(AVATARS / name / 'character.png')}")
        return
    if not image:
        # no picture given: Higgsfield draws the character (a generic one, or --prompt)
        meta = AVATARS / name / "character.json"
        if meta.exists() and not args.redo and not args.prompt:
            image = json.loads(meta.read_text()).get("url")
        if not image:
            print(f"drawing {name} with Higgsfield (Soul)…")
            image = avatar_image(name, args.prompt or GENERIC_AVATAR)
    model = args.model or DEFAULT_VIDEO_MODEL
    if model not in HF_VIDEO_MODELS:
        die(f"unknown model '{model}' — have: {', '.join(HF_VIDEO_MODELS)}")
    print(f"making {len(todo)} reaction clip{'s' if len(todo) != 1 else ''} of {name} ({', '.join(todo)}) with Higgsfield {model} (≈ ${HF_VIDEO_MODELS[model][1] * 5 * len(todo):.2f})…")
    for r in todo:
        avatar_clip(name, r, image, model=model)
    print(f"AVATAR: {name} {' '.join(sorted(set(have) | set(todo)))}")


def parse_reactions(spec: str | None, avatar: str, dur: float) -> list[dict]:
    """"0:nod,2.5:shocked,6:laugh" → [{t, kind}], sorted; empty → the avatar's reactions
    spread evenly over the video."""
    have = avatars().get(avatar) or []
    if not have:
        if (AVATARS / avatar / "character.png").exists() and not spec:
            return []   # a picture-only character: it stays on for the whole video
        die(f"avatar '{avatar}' has no clips — avatar {avatar} --image … first (or avatar --list)")
    out = []
    for item in [x.strip() for x in (spec or "").split(",") if x.strip()]:
        if ":" not in item:
            die(f"reaction '{item}' needs a time: 2.5:shocked")
        t, kind = item.split(":", 1)
        kind = kind.strip()
        if kind not in have:
            die(f"avatar '{avatar}' has no '{kind}' clip (has: {', '.join(have)})")
        out.append({"t": round(float(t), 2), "kind": kind})
    if not out:
        n = max(1, min(len(have), int(dur // 3)))
        out = [{"t": round(i * dur / n, 2), "kind": have[i % len(have)]} for i in range(n)]
    out.sort(key=lambda r: r["t"])
    if out[0]["t"] > 0:
        out.insert(0, {"t": 0.0, "kind": out[0]["kind"]})
    return out


def avatar_is_green(name: str) -> bool:
    meta = AVATARS / name / "character.json"
    try:
        return bool(json.loads(meta.read_text()).get("green"))
    except (OSError, ValueError):
        return False


def pip_mask(size: int, path: Path) -> None:
    from PIL import Image, ImageDraw
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.18), fill=255)
    m.save(path)

DEFAULT_VOICE = "Samantha"   # macOS `say`; the closest built-in to the TikTok voice
ELEVEN_MODEL = "eleven_multilingual_v2"


def web_env(key: str) -> str | None:
    """A setting from the environment or, failing that, web/.env.local — the one place
    keys live (ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID), so the CLI and the app agree."""
    if os.environ.get(key):
        return os.environ[key]
    f = ROOT / "web" / ".env.local"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def default_voice() -> str:
    """"eleven" (the ElevenLabs voice in web/.env.local) when a key is set, else the Mac voice."""
    return "eleven" if web_env("ELEVENLABS_API_KEY") and web_env("ELEVENLABS_VOICE_ID") else DEFAULT_VOICE


def eleven_tts(text: str, voice_id: str, out: Path) -> None:
    """ElevenLabs text to speech → mp3 at `out`. The key and the default voice come from
    web/.env.local; ELEVENLABS_MODEL overrides the model."""
    key = web_env("ELEVENLABS_API_KEY")
    if not key:
        die("ELEVENLABS_API_KEY is not set in web/.env.local (or use a macOS voice: --voice Samantha)")
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
        data=json.dumps({"text": text, "model_id": web_env("ELEVENLABS_MODEL") or ELEVEN_MODEL}).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        die(f"ElevenLabs refused the request ({e.code}): {e.read()[:300].decode('utf-8', 'replace')}")
    if len(data) < 1000:
        die("ElevenLabs returned no audio")
    out.write_bytes(data)


def has_audio(p: Path) -> bool:
    return bool(run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(p)]).stdout.strip())


def tts(text: str, voice: str, out: Path) -> float:
    """Say `text` into a 44.1 kHz stereo wav; returns its length. `voice` is "eleven"
    (the ElevenLabs voice in web/.env.local), "eleven:<voice_id>", or a macOS `say`
    voice name (Samantha…)."""
    if voice == "eleven" or voice.startswith("eleven:"):
        vid = voice.split(":", 1)[1] if ":" in voice else web_env("ELEVENLABS_VOICE_ID")
        if not vid:
            die("ELEVENLABS_VOICE_ID is not set in web/.env.local (or --voice eleven:<voice_id>)")
        raw = out.with_suffix(".mp3")
        eleven_tts(text, vid, raw)
    else:
        raw = out.with_suffix(".aiff")
        p = subprocess.run(["say", "-v", voice, "-r", "185", "-o", str(raw), text], capture_output=True, text=True)
        if p.returncode or not raw.exists():
            die(f"`say` failed for voice {voice!r}: {p.stderr.strip()[-300:]} (list voices with `say -v '?'`)")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-ar", "44100", "-ac", "2", str(out)])
    raw.unlink()
    return video_duration(out)


def bubble_png(text: str, user: str | None, w: int, h: int, path: Path, y_frac: float = 0.13) -> None:
    """The comment-reply bubble TikTok draws over a reply video: a white rounded card,
    a small grey "Reply to @user's comment" line (only when a real user is given) and
    the comment in black, centred at 13% down."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = int(h * 0.028)
    fnt, small = font(size), font(int(size * 0.72))
    pad, maxw = int(w * 0.045), int(w * 0.74)
    lines = wrap_px(text, fnt, maxw)
    line_h = int(size * 1.3)
    head = f"Reply to @{user}'s comment" if user else "replying to a comment"
    inner_w = max([fnt.getlength(x) for x in lines] + [small.getlength(head)])
    bw = int(inner_w + 2 * pad)
    bh = int(small.size * 1.6 + len(lines) * line_h + 2 * pad - int(size * 0.3))
    x0, y0 = (w - bw) // 2, int(h * y_frac)
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=int(size * 0.9), fill=(255, 255, 255, 242))
    d.text((x0 + pad, y0 + pad * 0.8), head, font=small, fill=(110, 110, 110, 255))
    y = y0 + pad * 0.8 + small.size * 1.6
    for ln in lines:
        d.text((x0 + pad, y), ln, font=fnt, fill=(16, 16, 16, 255))
        y += line_h
    img.save(path)


def quiet_y(src: Path, dur: float, band: float, candidates: list[float]) -> float:
    """Where to put an overlay so it does not sit on the source's own on-screen text:
    the candidate height (fraction of the frame) whose band has the least edge detail
    across four sampled frames."""
    import numpy as np
    from PIL import Image
    tmp = Path(tempfile.mkdtemp(prefix=".quiet-", dir=OUT))
    rows = None
    for i, f in enumerate((0.15, 0.35, 0.55, 0.8)):
        jpg = tmp / f"{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{dur * f:.3f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=180:320", str(jpg)], capture_output=True)
        if not jpg.exists():
            continue
        a = np.asarray(Image.open(jpg).convert("L"), dtype=np.float32)
        edges = np.abs(np.diff(a, axis=1)).sum(axis=1)
        rows = edges if rows is None else rows + edges
    shutil.rmtree(tmp, ignore_errors=True)
    if rows is None:
        return candidates[0]
    n = len(rows)
    best, best_score = candidates[0], None
    for y in candidates:
        a, b = int(y * n), min(n, int((y + band) * n))
        score = float(rows[a:b].sum())
        if best_score is None or score < best_score:
            best, best_score = y, score
    return best


def sfx(name: str) -> Path:
    """A sound effect from the shelf, made on first use: boom (a deep hit), whoosh, riser
    (a 2.5 s sweep up), scratch (a noisy stop); bruh / nah are said by the narration voice."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    out = SFX_DIR / f"{name}.wav"
    if out.exists():
        return out
    base = ["ffmpeg", "-y", "-v", "error"]
    if name == "boom":
        run(base + ["-f", "lavfi", "-i", "sine=frequency=52:duration=0.9", "-f", "lavfi", "-i", "anoisesrc=d=0.18:color=brown:amplitude=0.9",
                    "-filter_complex", "[0]afade=t=out:st=0.05:d=0.85:curve=exp,volume=4,alimiter=limit=0.95[a];[1]lowpass=f=300,afade=t=out:d=0.18[b];[a][b]amix=inputs=2:normalize=0,aformat=sample_rates=44100:channel_layouts=stereo[o]",
                    "-map", "[o]", str(out)])
    elif name == "whoosh":
        run(base + ["-f", "lavfi", "-i", "anoisesrc=d=0.7:color=white:amplitude=0.7",
                    "-af", "bandpass=f=1400:w=900,afade=t=in:d=0.3,afade=t=out:st=0.3:d=0.4,aformat=sample_rates=44100:channel_layouts=stereo", str(out)])
    elif name == "riser":
        run(base + ["-f", "lavfi", "-i", "aevalsrc=sin(2*PI*t*(70+140*t))*(t/2.5)*0.8:d=2.5:s=44100",
                    "-af", "aecho=0.6:0.4:60:0.3,aformat=sample_rates=44100:channel_layouts=stereo", str(out)])
    elif name == "scratch":
        run(base + ["-f", "lavfi", "-i", "anoisesrc=d=0.35:color=pink:amplitude=0.8",
                    "-af", "bandpass=f=2200:w=1500,tremolo=f=28:d=0.9,afade=t=out:st=0.15:d=0.2,aformat=sample_rates=44100:channel_layouts=stereo", str(out)])
    elif name in ("bruh", "nah"):
        tts(name, default_voice(), out)
    else:
        die(f"no such sound effect '{name}' — have: boom, whoosh, riser, scratch, bruh, nah")
    return out


def parse_moments(spec: str | None, kind: str) -> list[dict]:
    """"1.2:zoom,3:boom,4:pop:NO WAY" → [{t, fx, text?, frame?}] for a style; fx must be one
    of the style's effects; pop / emoji carry their text after a third colon, a snap the
    time of the frame it shows (else the frame at its own time)."""
    out = []
    for item in [x.strip() for x in (spec or "").split(",") if x.strip()]:
        if ":" not in item:
            die(f"moment '{item}' needs a time: 2.5:zoom")
        parts = item.split(":", 2)
        t, fx = parts[0], parts[1].strip()
        if fx not in STYLE_FX.get(kind, ()):
            die(f"'{fx}' is not a {kind} effect — have: {', '.join(STYLE_FX.get(kind, ()))}")
        m = {"t": round(float(t), 2), "fx": fx}
        if len(parts) > 2 and parts[2].strip():
            if fx == "snap":   # 9.5:snap:7.7 = shown at 9.5 s, the frame from 7.7 s
                m["frame"] = round(float(parts[2]), 2)
            else:
                m["text"] = parts[2].strip()
        elif fx in ("pop", "emoji"):
            die(f"{fx} needs its text: {t}:{fx}:NO WAY")
        out.append(m)
    return sorted(out, key=lambda m: m["t"])


def fraction_moments(kind: str, dur: float) -> list[dict]:
    """The last resort when the footage cannot be read: moments at fixed fractions of the
    length. (This was the default until 2026-10-20 — effects that reacted to nothing made
    the first hype test feel odd; `content_moments` is the default now.)"""
    if kind == "goofy":
        return [{"t": round(dur * 0.25, 2), "fx": "zoom"}, {"t": round(dur * 0.55, 2), "fx": "boom"}, {"t": round(dur * 0.55, 2), "fx": "zoom"}]
    if kind == "hype":
        return [{"t": round(dur * 0.2, 2), "fx": "zoom"}, {"t": round(dur * 0.55, 2), "fx": "slow"}, {"t": round(dur * 0.55, 2), "fx": "boom"},
                {"t": round(dur * 0.8, 2), "fx": "snap", "frame": round(dur * 0.55, 2)}]
    return [{"t": round(dur * 0.45, 2), "fx": "slow"}]


def motion_profile(src: Path, fps: int = 10) -> tuple[list[float], list[float], list[tuple[float, float]]]:
    """How much moves in the source, `fps` times a second at thumbnail size (the mean
    absolute difference between consecutive frames). Returns (times, motion, cuts):
    `motion` smoothed over ~0.8 s with the cut spikes taken out, `cuts` the hard cuts as
    (time, how far above its neighbours the spike was)."""
    import numpy as np
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".motion-", dir=OUT))
    log = tmp / "m.txt"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf",
                    f"fps={fps},scale=96:-1,format=gray,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={log}",
                    "-f", "null", "-"], capture_output=True)
    times: list[float] = []
    vals: list[float] = []
    t = None
    for line in (log.read_text().splitlines() if log.exists() else []):
        if line.startswith("frame:"):
            m = re.search(r"pts_time:([0-9.]+)", line)
            t = float(m.group(1)) if m else None
        elif line.startswith("lavfi.signalstats.YAVG=") and t is not None:
            times.append(t)
            vals.append(float(line.split("=", 1)[1]))
    shutil.rmtree(tmp, ignore_errors=True)
    if len(vals) < 2 * fps:
        return times, vals, []
    d = np.array(vals, dtype=np.float32)
    d[0] = d[1]   # tblend's first frame is the frame itself, not a difference
    k = 5
    nb = np.array([np.median(np.concatenate([d[max(0, i - k):i], d[i + 1:i + 1 + k]])) for i in range(len(d))], dtype=np.float32)
    is_cut = d > np.maximum(3.0 * nb, 2.0 * float(np.median(d)) + 1.0)
    cuts = [(float(times[i]), float(d[i] / max(float(nb[i]), 1e-3))) for i in range(len(d)) if is_cut[i] and times[i] > 0.2]
    clean = d.copy()
    clean[is_cut] = nb[is_cut]
    win = max(1, int(0.8 * fps))
    smooth = np.convolve(clean, np.ones(win) / win, mode="same")
    return times, [float(x) for x in smooth], cuts


def content_moments(kind: str, src: Path, dur: float) -> list[dict]:
    """Moments picked from what HAPPENS in the footage, never from fractions of its length
    (2026-10-20): the biggest sustained burst of motion is the main moment — slow motion
    (starting just before the peak) with a boom; the hardest cuts (else the next motion
    peaks) get the punch-zooms; the snapshot shows the MAIN moment's frame a few seconds
    AFTER it (a polaroid of the frame on screen read as a glitch). No pop words or emoji
    here: those must react to what is on screen at that second, so Claude or the editor
    adds them (`t:pop:WORDS`, `t:emoji:😭`)."""
    import numpy as np
    times, motion, cuts = motion_profile(src)
    if not motion:
        return fraction_moments(kind, dur)
    t = np.array(times)
    m = np.array(motion)
    gap = max(2.5, dur / 6)
    usable = (t > 1.0) & (t < dur - 1.6)
    peaks: list[float] = []
    for i in np.argsort(-m):
        if not usable[i]:
            continue
        if all(abs(float(t[i]) - q) >= gap for q in peaks):
            peaks.append(float(t[i]))
        if len(peaks) >= 6:
            break
    if not peaks:
        return fraction_moments(kind, dur)
    main = peaks[0]
    slows = [main] + ([q for q in peaks[1:] if abs(q - main) >= 8][:1] if dur > 20 else [])

    def landing(q: float) -> float:
        # a motion peak in phone footage is usually the CAMERA whipping to something; the
        # moment worth slowing is what it lands on — the first time after the peak the
        # motion has settled (below 65 % of the peak), within 1.5 s
        i0 = int(np.argmin(np.abs(t - q)))
        top = float(m[i0])
        for i in range(i0 + 1, len(t)):
            if t[i] - q > 1.5:
                break
            if m[i] < 0.65 * top:
                return float(t[i])
        return q + 0.3

    slow_ts = [round(min(landing(q), dur - 1.6), 2) for q in slows]
    if kind == "cinematic":
        return sorted([{"t": q, "fx": "slow"} for q in slow_ts], key=lambda x: x["t"])
    n_hits = max(1, min(4, round(dur / 9)))
    far = lambda x: all(abs(x - q) > 2.0 for q in slows + slow_ts) and 1.0 < x < dur - 1.2
    hits = [c for c, _ in sorted(cuts, key=lambda c: -c[1]) if far(c)][:n_hits]
    if len(hits) < n_hits:
        hits += [q for q in peaks[1:] if far(q) and all(abs(q - x) > 1.5 for x in hits)][:n_hits - len(hits)]
    out: list[dict] = []
    if kind == "goofy":
        out.append({"t": round(main, 2), "fx": "boom"})
        out.append({"t": round(main, 2), "fx": "zoom"})
        out += [{"t": round(x, 2), "fx": "zoom"} for x in hits]
        return sorted(out, key=lambda x: x["t"])
    for q in slow_ts:
        out.append({"t": q, "fx": "slow"})
        out.append({"t": q, "fx": "boom"})
    out += [{"t": round(x, 2), "fx": "zoom"} for x in hits]
    main_t = slow_ts[0]
    later = [x for x in sorted(hits + peaks[1:]) if x >= main_t + 3.0 and x < dur - 2.0]
    snap_t = later[0] if later else min(dur - 2.0, main_t + 4.5)
    if snap_t > main_t + 2.0:
        out.append({"t": round(snap_t, 2), "fx": "snap", "frame": round(main_t + 0.5, 2)})   # the moment at its clearest, shown later
    return sorted(out, key=lambda x: x["t"])


def default_moments(kind: str, dur: float, src: Path | None = None) -> list[dict]:
    """A style's moments when the project names none: read off the footage when the
    source is given, else at fixed fractions."""
    if src is not None and src.exists():
        return content_moments(kind, src, dur)
    return fraction_moments(kind, dur)


def pop_png(text: str, w: int, h: int, path: Path) -> tuple[int, int]:
    """A pop-in word: big, white with a thick black outline, slightly tilted. Returns its size."""
    from PIL import Image, ImageDraw
    size = int(h * 0.075)
    fnt = font(size)
    stroke = max(3, int(size * 0.16))
    lines = wrap_px(text.upper(), fnt, int(w * 0.8))
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    boxes = [d0.textbbox((0, 0), ln, font=fnt, stroke_width=stroke) for ln in lines]
    tw = max(b[2] - b[0] for b in boxes) + 40
    th = sum(b[3] - b[1] for b in boxes) + int(size * 0.25) * len(lines) + 40
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 20
    for ln, bb in zip(lines, boxes):
        d.text(((tw - (bb[2] - bb[0])) / 2 - bb[0], y - bb[1]), ln, font=fnt, fill="white", stroke_width=stroke, stroke_fill="black")
        y += (bb[3] - bb[1]) + int(size * 0.25)
    img = img.rotate(-4, expand=True, resample=Image.BICUBIC)
    img.save(path)
    return img.size


def emoji_png(text: str, path: Path, px: int) -> bool:
    """Apple's color emoji at `px` pixels (the font only renders at 160; scaled)."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        fnt = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", 160)
        n = max(1, len(text))
        img = Image.new("RGBA", (190 * n, 200), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((10, 10), text, font=fnt, embedded_color=True)
        img = img.crop(img.getbbox() or (0, 0, 190, 200))
        scale = px / max(img.height, 1)
        img = img.resize((max(1, int(img.width * scale)), px), Image.LANCZOS)
        img.save(path)
        return True
    except Exception:  # noqa: BLE001 — no color emoji support: skip the emoji
        return False


def polaroid_png(src: Path, t: float, w: int, h: int, path: Path) -> tuple[int, int]:
    """A frame of the video at `t` as a polaroid: white border, a thicker bottom, tilted,
    with a soft shadow. Returns its size."""
    from PIL import Image, ImageFilter
    grab = path.with_suffix(".grab.jpg")
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=540:720:force_original_aspect_ratio=increase,crop=540:720", str(grab)])
    photo = Image.open(grab).convert("RGB")
    grab.unlink()
    b, bb = 26, 96
    card = Image.new("RGBA", (photo.width + 2 * b, photo.height + b + bb), (252, 252, 250, 255))
    card.paste(photo, (b, b))
    card = card.rotate(-7, expand=True, resample=Image.BICUBIC)
    shadow = Image.new("RGBA", (card.width + 60, card.height + 60), (0, 0, 0, 0))
    sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 150), (0, 0), card.split()[3])
    shadow.paste(sh, (36, 42), sh)
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    shadow.paste(card, (30, 30), card)
    out = shadow
    scale = (w * 0.62) / out.width
    out = out.resize((int(out.width * scale), int(out.height * scale)), Image.LANCZOS)
    out.save(path)
    return out.size


def render_hype(project: dict, args) -> None:
    """The combined style — see STYLES["hype"]. Slow motion retimes the video AND the
    original audio (atempo), every other moment is mapped through that retiming."""
    src = ROOT / project["source"]
    w, h = (540, 960) if args.draft else (W, H)
    dur = float(project["length"])
    name = args.name or out_name(project)
    od = out_dir(project)
    work = od / f".reformat_{name}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    moments = project.get("moments") or default_moments("hype", dur, src)
    slow_factor, slow_len = 2.2, 1.0
    cuts, segs = 0.0, []
    for t in sorted(m["t"] for m in moments if m["fx"] == "slow"):
        if t <= cuts or t + slow_len > dur:
            continue
        segs.append((cuts, t, 1.0))
        segs.append((t, t + slow_len, slow_factor))
        cuts = t + slow_len
    segs.append((cuts, dur, 1.0))
    total = sum((b - a) * f for a, b, f in segs)

    def remap(t: float) -> float:
        return sum((min(b, max(a, t)) - a) * f for a, b, f in segs if a < t)

    # the song starts where its DROP lands on the main moment (the first slow, else the
    # first boom), and every hit is snapped to the nearest beat of it (2026-10-20)
    snd = style_sound(project)
    song_start, song_beats, song_why = 0.0, [], ""
    if snd:
        anchors = [remap(m["t"]) for m in moments if m["fx"] == "slow"] or [remap(m["t"]) for m in moments if m["fx"] == "boom"]
        song_start, song_beats, song_why = song_offset(snd, anchors[0] if anchors else 0.0, total)
    beat_grid = sorted(b - song_start for b in song_beats if b >= song_start)

    def on_beat(t_out: float) -> float:
        near = min(beat_grid, key=lambda b: abs(b - t_out), default=None)
        return round(near, 3) if near is not None and abs(near - t_out) <= 0.3 else t_out

    has_src_audio = has_audio(src)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    n_in = 1
    if not has_src_audio:
        cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        src_audio = "[1:a]"
        n_in = 2
    else:
        src_audio = "[0:a]"
    filters: list[str] = []
    # --- video: retime, then the goofy zooms/shake in output time, a lighter cinematic grade and bars
    filters.append(f"[0:v]fps={FPS},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,split={len(segs)}" + "".join(f"[p{i}]" for i in range(len(segs))))
    for i, (a, b, f) in enumerate(segs):
        filters.append(f"[p{i}]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)*{f}[s{i}]")
    filters.append("".join(f"[s{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[vc]")
    zooms = [on_beat(remap(m["t"])) for m in moments if m["fx"] == "zoom"]
    booms = [on_beat(remap(m["t"])) for m in moments if m["fx"] == "boom"]
    z = "1" + "".join(f"+0.2*between(t,{t:.3f},{t + 0.5:.3f})" for t in zooms)
    shake = "".join(f"+7*sin(t*140)*between(t,{t:.3f},{t + 0.3:.3f})" for t in booms)
    bar = int(h * 0.06)
    filters.append(
        f"[vc]scale=w='iw*({z})':h='ih*({z})':eval=frame,crop={w}:{h}:x='(iw-ow)/2{shake}':y='(ih-oh)/2',"
        f"eq=contrast=1.1:saturation=1.08,vignette=PI/5,noise=alls=6:allf=t,"
        f"drawbox=x=0:y=0:w={w}:h={bar}:color=black:t=fill,drawbox=x=0:y={h - bar}:w={w}:h={bar}:color=black:t=fill,"
        f"fade=t=in:d=0.4,fade=t=out:st={max(0.0, total - 0.6):.3f}:d=0.6[vg]"
    )
    last = "vg"
    k = 0

    def pop_in(png: Path, t_out: float, hold: float, x: str, y: str, rise: float = 0.14) -> None:
        nonlocal last, n_in, k
        cmd.extend(["-loop", "1", "-t", f"{hold + 0.3:.3f}", "-i", str(png)])
        # scales up from 55 % with a tiny overshoot, then sits; the main timeline is `t`, the input's own clock starts at 0
        filters.append(f"[{n_in}:v]format=rgba,scale=w='iw*(0.55+0.5*min(1,t/{rise:.3f})-0.05*between(t,{rise:.3f},{rise + 0.08:.3f}))':h=-1:eval=frame,setpts=PTS-STARTPTS+{t_out:.3f}/TB[o{k}]")
        filters.append(f"[{last}][o{k}]overlay=x='{x}':y='{y}':format=auto:eof_action=pass:enable='between(t,{t_out:.3f},{t_out + hold:.3f})'[w{k}]")
        last = f"w{k}"
        n_in += 1
        k += 1

    if project.get("hook"):
        cap = work / "hook.png"
        # ONE hook, as written (not shouted), for the first seconds only — a second line
        # competing with the source's own text for the whole video was the oddest part of
        # the first test (2026-10-20); below any text the source carries up top: the quiet
        # band of the middle third
        hold = float(project.get("hook_hold") if project.get("hook_hold") is not None else HYPE_HOOK_HOLD)
        # the quiet band is measured on the frames the hook is actually ON (its first seconds,
        # not the whole video — it landed on a face that way), from just under the top bar down
        span = hold if 0 < hold < total - 0.5 else dur
        caption_png(project["hook"], w, h, cap, y_frac=quiet_y(src, span, 0.1, [0.1, 0.16, 0.22, 0.28, 0.34, 0.4, 0.46, 0.52]), size_frac=0.04)
        if hold <= 0 or hold >= total - 0.5:
            cmd += ["-i", str(cap)]
            filters.append(f"[{last}][{n_in}:v]overlay=0:0:format=auto[hk]")
        else:
            cmd += ["-loop", "1", "-t", f"{hold + 0.3:.3f}", "-i", str(cap)]
            filters.append(f"[{n_in}:v]format=rgba,fade=t=in:st=0.2:d=0.15:alpha=1,fade=t=out:st={hold - 0.25:.3f}:d=0.25:alpha=1[hkp]")
            filters.append(f"[{last}][hkp]overlay=0:0:format=auto:eof_action=pass:enable='between(t,0.2,{hold:.3f})'[hk]")
        last = "hk"
        n_in += 1
    for i, m in enumerate(moments):
        t_out = on_beat(remap(m["t"]))
        if m["fx"] == "pop":
            if not m.get("text"):
                continue   # a pop with nothing to say is noise, not a default
            png = work / f"pop{i}.png"
            pw, ph = pop_png(m["text"], w, h, png)
            pop_in(png, t_out, 1.2, "(W-w)/2", f"H*0.44-h/2")
        elif m["fx"] == "emoji":
            png = work / f"emoji{i}.png"
            if m.get("text") and emoji_png(m["text"], png, int(h * 0.16)):
                pop_in(png, t_out, 1.1, "W*0.68-w/2", "H*0.3-h/2", rise=0.1)
        elif m["fx"] == "snap":
            png = work / f"snap{i}.png"
            polaroid_png(src, float(m.get("frame", m["t"])), w, h, png)
            pop_in(png, t_out, 1.4, "(W-w)/2", "(H-h)/2", rise=0.18)
    # narration lines (the third rendition's trick), if the project has any: said by the
    # narration voice at even spacing, each shown while it is said
    line_mixes: list[str] = []
    lines = [x for x in (project.get("lines") or []) if x.strip()]
    if lines:
        voice = project.get("voice") or default_voice()
        slot = max(0.0, total - 0.8) / len(lines)
        for i, line in enumerate(lines):
            wav = work / f"line{i}.wav"
            dl = tts(line, voice, wav)
            start = min(i * slot + 0.4, max(0.4, total - dl - 0.2))
            cmd += ["-i", str(wav)]
            line_mixes.append(f"[{n_in}:a]adelay={int(start * 1000)}|{int(start * 1000)}[x{n_in}]")
            n_in += 1
            png = work / f"line{i}.png"
            caption_png(line, w, h, png, y_frac=0.66, size_frac=0.04)
            cmd += ["-loop", "1", "-t", f"{dl + 0.4:.3f}", "-i", str(png)]
            filters.append(f"[{last}][{n_in}:v]setpts=PTS-STARTPTS+{start:.3f}/TB[lp{i}];[{last}][lp{i}]overlay=0:0:format=auto:eof_action=pass:enable='between(t,{start:.3f},{start + dl + 0.15:.3f})'[ln{i}]".replace(f"[{last}][{n_in}:v]setpts", f"[{n_in}:v]setpts"))
            last = f"ln{i}"
            n_in += 1
    filters.append(f"[{last}]format=yuv420p[vo]")

    # --- audio: the ORIGINAL retimed with the picture, a little bass; the song ducked under it by the original (sidechain);
    # the hits on their moments; narration lines if the project has any
    filters.append(f"{src_audio}asplit={len(segs)}" + "".join(f"[q{i}]" for i in range(len(segs))))
    for i, (a, b, f) in enumerate(segs):
        tempo = "" if f == 1.0 else ",atempo=0.5,atempo=" + f"{1 / (f * 0.5):.4f}"   # 2.2× slower = 0.4545: 0.5 × 0.909
        filters.append(f"[q{i}]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS{tempo}[r{i}]")
    filters.append("".join(f"[r{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1,bass=g=4,asplit=2[oa][oa_sc]")
    mix_in = ["[oa]"]
    if snd:
        cmd += ["-i", str(snd)]
        filters.append(f"[{n_in}:a]atrim={song_start:.3f}:{song_start + total:.3f},asetpts=PTS-STARTPTS,volume=0.55,afade=t=in:d=0.4,afade=t=out:st={max(0.0, total - 0.8):.3f}:d=0.8[song]")
        filters.append("[song][oa_sc]sidechaincompress=threshold=0.03:ratio=8:attack=15:release=500:makeup=1[sd]")
        mix_in.append("[sd]")
        n_in += 1
    else:
        filters.append("[oa_sc]anullsink")
    for m in moments:
        fx = m["fx"]
        if fx == "slow" or fx == "riser":
            start = max(0.0, remap(m["t"]) - 2.0)
            cmd += ["-i", str(sfx("riser"))]
            filters.append(f"[{n_in}:a]atrim=0.5:2.5,asetpts=PTS-STARTPTS,volume=0.6,adelay={int(start * 1000)}|{int(start * 1000)}[x{n_in}]")
            mix_in.append(f"[x{n_in}]")
            n_in += 1
        elif fx in ("boom", "bruh", "nah", "whoosh", "snap", "pop"):
            which = "whoosh" if fx in ("snap", "pop") else fx
            cmd += ["-i", str(sfx(which))]
            vol = 1.5 if which == "boom" else 0.9
            t0 = on_beat(remap(m["t"]))
            filters.append(f"[{n_in}:a]volume={vol},adelay={int(t0 * 1000)}|{int(t0 * 1000)}[x{n_in}]")
            mix_in.append(f"[x{n_in}]")
            n_in += 1
    for lm in line_mixes:
        filters.append(lm)
        mix_in.append(lm.split("[")[-1].rstrip("]").join(["[", "]"]))
    # the mix came out ~8 dB under the cinematic cut (the duck pulls the song down, the original is
    # phone audio): +6 dB into the limiter brings it to posting level without crushing the hits
    filters.append("".join(mix_in) + f"amix=inputs={len(mix_in)}:duration=first:normalize=0,volume=6dB,alimiter=limit=0.95:attack=5:release=80[ao]")

    cmd += ["-filter_complex", ";".join(filters), "-map", "[vo]", "-map", "[ao]", "-r", str(FPS), "-t", f"{total:.3f}"]
    out_path = od / f"{name}.mp4"
    tail = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(out_path)]
    vt = ["-c:v", "h264_videotoolbox", "-b:v", "4M" if args.draft else "12M", "-profile:v", "high", "-allow_sw", "1"]
    x264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23" if args.draft else "19"]
    if args.verbose:
        print(" ".join(cmd + vt + tail))
    p = subprocess.run(cmd + vt + tail, text=True, capture_output=True)
    if p.returncode:
        p = subprocess.run(cmd + x264 + tail, text=True, capture_output=True)
        if p.returncode:
            die(f"ffmpeg failed:\n{p.stderr[-3000:]}")
    shutil.rmtree(work, ignore_errors=True)
    if snd:
        print(f"  song {snd.stem} from {song_start:.1f}s — {song_why}" + (f"; hits snapped to its beats" if beat_grid else ""))
    keep_render(out_path, name, args.draft, f"hype style · {total:.1f}s · {w}x{h}")


def style_sound(project: dict) -> Path | None:
    """The style's own sound: the project's pick, else (cinematic) the first pool sound
    that is not the source's audio, else none."""
    if project.get("style_sound"):
        p = ROOT / project["style_sound"]
        return p if p.exists() else None
    if project["reformat"] in ("cinematic", "hype"):
        for cand in pool_sounds({project.get("sound") or ""}):
            return ROOT / cand["sound"]
    return None


def song_offset(snd: Path, at: float, total: float) -> tuple[float, list[float], str]:
    """Where to start a pool song under a `total`-second video so its DROP lands at `at`
    seconds of it: the first drop that can (the song must still run to the end), else the
    suggested start, as late as the length allows. Returns (start, the song's beat times, why)."""
    bj = snd.with_suffix(".beats.json")
    if not bj.exists():
        return 0.0, [], "no beat file for it"
    b = load_json(bj)
    sdur = float(b.get("duration") or 0)
    beats = [float(x) for x in b.get("beats", [])]
    for d in b.get("drops", []):
        off = float(d["time"]) - at
        if off >= 0 and (not sdur or off + total <= sdur + 0.3):
            return round(off, 3), beats, f"its drop ({d['time']:.1f}s in) lands on the main moment at {at:.1f}s"
    off = float(b.get("suggested_start") or 0)
    if sdur:
        off = min(off, max(0.0, sdur - total))
    return round(off, 3), beats, "no drop of it can land on the main moment — the suggested start"


def render_style(project: dict, args) -> None:
    """goofy / cinematic: the same cut, a different feel (see STYLES)."""
    src = ROOT / project["source"]
    kind = project["reformat"]
    w, h = (540, 960) if args.draft else (W, H)
    dur = float(project["length"])
    name = args.name or out_name(project)
    od = out_dir(project)
    work = od / f".reformat_{name}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    moments = project.get("moments") or default_moments(kind, dur, src)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    n_in = 1
    has_src_audio = has_audio(src)
    if not has_src_audio:
        cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        src_audio = "[1:a]"
        n_in = 2
    else:
        src_audio = "[0:a]"
    filters: list[str] = []
    mixes: list[str] = []
    snd = style_sound(project)
    total = dur

    if kind == "goofy":
        zooms = [m["t"] for m in moments if m["fx"] == "zoom"]
        booms = [m["t"] for m in moments if m["fx"] == "boom"]
        z = "1" + "".join(f"+0.22*between(t,{t:.3f},{t + 0.55:.3f})" for t in zooms)
        shake = "".join(f"+8*sin(t*140)*between(t,{t:.3f},{t + 0.3:.3f})" for t in booms)
        filters.append(
            f"[0:v]fps={FPS},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"scale=w='iw*({z})':h='ih*({z})':eval=frame,crop={w}:{h}:x='(iw-ow)/2{shake}':y='(ih-oh)/2',"
            f"eq=saturation=1.35:contrast=1.08[vg]"
        )
        last = "vg"
        if project.get("hook"):
            cap = work / "hook.png"
            caption_png(project["hook"].upper(), w, h, cap, y_frac=quiet_y(src, dur, 0.14, [0.08, 0.14, 0.2, 0.27, 0.34]), size_frac=0.05)
            cmd += ["-i", str(cap)]
            filters.append(f"[{last}][{n_in}:v]overlay=0:0:format=auto[vh]")
            last = "vh"
            n_in += 1
        filters.append(f"[{last}]format=yuv420p[vo]")
        # audio: the original, crunchy; the hits on their moments; a meme sound under it if chosen
        filters.append(f"{src_audio}bass=g=7,acrusher=bits=10:mix=0.15,alimiter=limit=0.9[a0]")
        mix_in = ["[a0]"]
        for m in moments:
            if m["fx"] in ("boom", "bruh", "nah", "whoosh"):
                cmd += ["-i", str(sfx(m["fx"]))]
                filters.append(f"[{n_in}:a]volume={1.6 if m['fx'] == 'boom' else 1.2},adelay={int(m['t'] * 1000)}|{int(m['t'] * 1000)}[x{n_in}]")
                mix_in.append(f"[x{n_in}]")
                n_in += 1
        if snd:
            cmd += ["-i", str(snd)]
            filters.append(f"[{n_in}:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume=0.45,afade=t=out:st={max(0.0, dur - 0.5):.3f}:d=0.5[m]")
            mix_in.append("[m]")
            n_in += 1
        filters.append("".join(mix_in) + f"amix=inputs={len(mix_in)}:duration=first:normalize=0[ao]")

    else:  # cinematic
        slow_factor, slow_len = 2.5, 1.2
        slows = [m["t"] for m in moments if m["fx"] == "slow"]
        cuts, segs = 0.0, []
        for t in slows:
            if t <= cuts or t + slow_len > dur:
                continue
            segs.append((cuts, t, 1.0))
            segs.append((t, t + slow_len, slow_factor))
            cuts = t + slow_len
        segs.append((cuts, dur, 1.0))
        total = sum((b - a) * f for a, b, f in segs)
        base = f"[0:v]fps={FPS},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,split={len(segs)}" + "".join(f"[p{i}]" for i in range(len(segs)))
        filters.append(base)
        for i, (a, b, f) in enumerate(segs):
            filters.append(f"[p{i}]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)*{f}[s{i}]")
        filters.append("".join(f"[s{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[vc]")
        bar = int(h * 0.09)
        filters.append(
            f"[vc]eq=contrast=1.12:saturation=0.82:brightness=-0.02,colorbalance=rs=0.05:bs=-0.05,vignette=PI/4.5,noise=alls=9:allf=t,"
            f"drawbox=x=0:y=0:w={w}:h={bar}:color=black:t=fill,drawbox=x=0:y={h - bar}:w={w}:h={bar}:color=black:t=fill,"
            f"fade=t=in:d=0.6,fade=t=out:st={max(0.0, total - 0.8):.3f}:d=0.8[vg]"
        )
        last = "vg"
        if project.get("hook"):
            cap = work / "hook.png"
            caption_png(project["hook"], w, h, cap, y_frac=0.80, size_frac=0.03)
            cmd += ["-i", str(cap)]
            filters.append(f"[{last}][{n_in}:v]overlay=0:0:format=auto[vh]")
            last = "vh"
            n_in += 1
        filters.append(f"[{last}]format=yuv420p[vo]")
        # audio: the dramatic sound carries the whole thing (the original audio would not survive the retiming)
        if snd:
            cmd += ["-i", str(snd)]
            filters.append(f"[{n_in}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.5,afade=t=out:st={max(0.0, total - 1.0):.3f}:d=1.0[m]")
            n_in += 1
            mix_in = ["[m]"]
        else:
            cmd += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
            filters.append(f"[{n_in}:a]anull[m]")
            n_in += 1
            mix_in = ["[m]"]
        for m in moments:
            if m["fx"] == "riser" or (m["fx"] == "slow" and True):
                # a riser leads into every slow moment (ends on it) and on explicit riser moments
                t_src = m["t"]
                t_out = sum((min(b, t_src) - a) * f for a, b, f in segs if a < t_src)  # time in the retimed video
                start = max(0.0, t_out - 2.5)
                cmd += ["-i", str(sfx("riser"))]
                filters.append(f"[{n_in}:a]volume=0.7,adelay={int(start * 1000)}|{int(start * 1000)}[x{n_in}]")
                mix_in.append(f"[x{n_in}]")
                n_in += 1
        filters.append("".join(mix_in) + f"amix=inputs={len(mix_in)}:duration=first:normalize=0[ao]")

    cmd += ["-filter_complex", ";".join(filters), "-map", "[vo]", "-map", "[ao]", "-r", str(FPS), "-t", f"{total:.3f}"]
    out_path = od / f"{name}.mp4"
    tail = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(out_path)]
    vt = ["-c:v", "h264_videotoolbox", "-b:v", "4M" if args.draft else "12M", "-profile:v", "high", "-allow_sw", "1"]
    x264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23" if args.draft else "19"]
    if args.verbose:
        print(" ".join(cmd + vt + tail))
    p = subprocess.run(cmd + vt + tail, text=True, capture_output=True)
    if p.returncode:
        p = subprocess.run(cmd + x264 + tail, text=True, capture_output=True)
        if p.returncode:
            die(f"ffmpeg failed:\n{p.stderr[-3000:]}")
    shutil.rmtree(work, ignore_errors=True)
    keep_render(out_path, name, args.draft, f"{kind} style · {total:.1f}s · {w}x{h}")


def reformat_summary(project: dict) -> str:
    kind = project.get("reformat")
    if kind == "hook":
        return f'hook: {project.get("hook") or "(none yet)"}'
    if kind == "narrated":
        lines = project.get("lines") or []
        return f'{len(lines)} line{"s" if len(lines) != 1 else ""} ({project.get("voice") or default_voice()}): ' + (" | ".join(lines) if lines else "(none yet)")
    if kind in STYLES:
        ms = project.get("moments") or []
        return (f'moments: ' + (", ".join(f"{m['t']}:{m['fx']}" + (f":{m['text']}" if m.get("text") else f":{m['frame']}" if m.get("frame") is not None else "") for m in ms) if ms else "(default)") +
                (f' · sound {Path(project["style_sound"]).stem}' if project.get("style_sound") else "") +
                (f' · hook: {project["hook"]}' if project.get("hook") else ""))
    if kind == "reaction":
        rs = project.get("reactions") or []
        return f'avatar {project.get("avatar") or "(none)"}: ' + (", ".join(f"{r['t']}:{r['kind']}" for r in rs) if rs else "(spread evenly)")
    c = project.get("comment")
    n = len(project.get("comments") or [])
    return f'comment: {c.get("text") if c else "(none yet)"}' + (f' (@{c["user"]})' if c and c.get("user") else "") + (f' · {n} fetched' if n else "")


def render_reformat(project: dict, args) -> None:
    src = ROOT / project["source"]
    if not src.exists():
        die(f"the source video is gone: {project['source']}")
    kind = project["reformat"]
    if kind == "hype":
        render_hype(project, args)
        return
    if kind in STYLES:
        render_style(project, args)
        return
    w, h = (540, 960) if args.draft else (W, H)
    dur = float(project["length"])
    name = args.name or out_name(project)
    od = out_dir(project)
    work = od / f".reformat_{name}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    filters = [f"[0:v]fps={FPS},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0]"]
    audio_in = "[0:a]" if has_audio(src) else None
    if audio_in is None:
        cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        audio_in = "[1:a]"
    n_in = 2 if audio_in == "[1:a]" else 1
    overlays: list[tuple[Path, float | None, float | None]] = []
    mix: list[str] = []
    if kind == "hook":
        if not project.get("hook"):
            die("no hook line yet — `reformat --hook \"…\"` first (or the Claude button in the app)")
        cap = work / "hook.png"
        caption_png(project["hook"], w, h, cap, y_frac=quiet_y(src, dur, 0.12, [0.08, 0.14, 0.20, 0.27, 0.34, 0.42]))
        overlays.append((cap, None, None))
    elif kind == "reply":
        c = project.get("comment")
        if not c or not c.get("text"):
            die("no comment yet — `reformat --comment \"…\" [--user name]` first (or the Claude button in the app)")
        cap = work / "bubble.png"
        bubble_png(c["text"], c.get("user"), w, h, cap, y_frac=quiet_y(src, dur, 0.14, [0.07, 0.13, 0.20, 0.27, 0.34, 0.42]))
        overlays.append((cap, None, None))
    elif kind == "narrated":
        lines = [x for x in (project.get("lines") or []) if x.strip()]
        if not lines:
            die("no narration yet — `reformat --lines \"first|second|third\"` first (or the Claude button in the app)")
        voice = project.get("voice") or default_voice()
        y_lines = quiet_y(src, dur, 0.14, [0.50, 0.58, 0.64, 0.70, 0.76])
        t = 0.4
        slot = max(0.0, (dur - 0.8)) / len(lines)
        for i, line in enumerate(lines):
            wav = work / f"line{i}.wav"
            dl = tts(line, voice, wav)
            start = min(max(t, i * slot + 0.4), max(0.4, dur - dl - 0.2))
            cmd += ["-i", str(wav)]
            mix.append(f"[{n_in}:a]adelay={int(start * 1000)}|{int(start * 1000)}[s{i}]")
            n_in += 1
            png = work / f"line{i}.png"
            caption_png(line, w, h, png, y_frac=y_lines, size_frac=0.042)
            overlays.append((png, start, start + dl + 0.15))
            t = start + dl + 0.25
    elif kind == "reaction" and (avatar_is_green(project.get("avatar") or next(iter(avatars()), "")) or not avatars().get(project.get("avatar") or next(iter(avatars()), ""))):
        # TikTok's green-screen look: the character keyed out of her green background and
        # standing over the video, bottom-centre, shoulders running off the bottom edge.
        # With reaction clips they switch at their moments; a still-only character (the
        # cheap round, no video bought yet) breathes in place for the whole video.
        avatar = project.get("avatar") or next(iter(avatars()), None)
        if not avatar:
            die("no avatar yet — avatar <name> --image <url> makes one")
        clips_have = avatars().get(avatar) or []
        still = AVATARS / avatar / "character.png"
        if not clips_have and not still.exists():
            die(f"avatar '{avatar}' has neither clips nor a picture")
        # "corner" (default): a smaller cutout in the bottom-left corner, the natural reaction
        # placement, above TikTok's caption zone; "center": big, bottom-centre, shoulders off the edge
        corner = (project.get("avatar_pos") or "corner") == "corner"
        cw = int(w * (0.46 if corner else 0.82))
        pos = f"{int(w * 0.03)}:H*0.88-h" if corner else "(W-w)/2:H-h+h*0.04"
        key = "chromakey=0x00ff00:0.28:0.12,despill=type=green"
        if clips_have:
            reactions = parse_reactions(",".join(f"{r['t']}:{r['kind']}" for r in (project.get("reactions") or [])), avatar, dur)
            windows = [(r["t"], reactions[i + 1]["t"] if i + 1 < len(reactions) else dur, AVATARS / avatar / f"{r['kind']}.mp4") for i, r in enumerate(reactions)]
        else:
            windows = [(0.0, dur, still)]
        filters[0] = filters[0].replace("[v0]", "[base]")
        last_v = "base"
        for i, (t0, t1, src_clip) in enumerate(windows):
            if t1 - t0 < 0.2:
                continue
            if src_clip.suffix == ".png":
                cmd += ["-loop", "1", "-t", f"{t1 - t0 + 0.5:.3f}", "-i", str(src_clip)]
                motion = f"crop=w='iw*0.985':h='ih*0.985':x='(iw-ow)/2+3*sin(t*1.3)':y='(ih-oh)/2+2*sin(t*0.9)',"
            else:
                cmd += ["-stream_loop", "-1", "-t", f"{t1 - t0 + 0.5:.3f}", "-i", str(src_clip)]
                motion = ""
            filters.append(f"[{n_in}:v]fps={FPS},{motion}scale={cw}:-2,format=rgba,{key},setpts=PTS-STARTPTS+{t0:.3f}/TB[g{i}]")
            filters.append(f"[{last_v}][g{i}]overlay={pos}:format=auto:eof_action=pass:enable='between(t,{t0:.3f},{t1:.3f})'[r{i}]")
            last_v = f"r{i}"
            n_in += 1
        filters.append(f"[{last_v}]null[v0]")
    elif kind == "reaction":
        avatar = project.get("avatar") or next(iter(avatars()), None)
        if not avatar:
            die("no avatar yet — avatar <name> --image <url> makes one")
        reactions = parse_reactions(",".join(f"{r['t']}:{r['kind']}" for r in (project.get("reactions") or [])), avatar, dur)
        size = int(w * 0.38)
        mask = work / "mask.png"
        pip_mask(size, mask)
        cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(mask)]
        mask_in = n_in
        n_in += 1
        filters.append(f"[{mask_in}:v]format=gray,scale={size}:{size},split={len(reactions)}" + "".join(f"[mk{i}]" for i in range(len(reactions))))
        x, y = int(w * 0.045), int(h * 0.84) - size
        pips: list[tuple[int, float, float]] = []
        for i, r in enumerate(reactions):
            t0 = r["t"]
            t1 = reactions[i + 1]["t"] if i + 1 < len(reactions) else dur
            if t1 - t0 < 0.2:
                continue
            clip = AVATARS / avatar / f"{r['kind']}.mp4"
            cmd += ["-stream_loop", "-1", "-t", f"{t1 - t0 + 0.5:.3f}", "-i", str(clip)]
            filters.append(
                f"[{n_in}:v]fps={FPS},scale={size}:{size}:force_original_aspect_ratio=increase,crop={size}:{size},setsar=1,"
                f"setpts=PTS-STARTPTS+{t0:.3f}/TB[p{i}];[p{i}][mk{i}]alphamerge[q{i}]"
            )
            pips.append((i, t0, t1))
            n_in += 1
        # the scaled source is [base] here; the avatar windows chain onto it and end as [v0]
        filters[0] = filters[0].replace("[v0]", "[base]")
        last_v = "base"
        for j, (i, t0, t1) in enumerate(pips):
            filters.append(f"[{last_v}][q{i}]overlay={x}:{y}:format=auto:eof_action=pass:enable='between(t,{t0:.3f},{t1:.3f})'[r{j}]")
            last_v = f"r{j}"
        filters.append(f"[{last_v}]null[v0]")
    # video: the source scaled, then each overlay (whole video, or a window)
    last = "v0"
    for i, (png, a, b) in enumerate(overlays):
        cmd += ["-i", str(png)]
        window = f":enable='between(t,{a:.3f},{b:.3f})'" if a is not None else ""
        filters.append(f"[{last}][{n_in}:v]overlay=0:0:format=auto{window}[v{i + 1}]")
        last = f"v{i + 1}"
        n_in += 1
    filters.append(f"[{last}]format=yuv420p[vo]")
    # audio: the original as is, or ducked under the voice
    if mix:
        filters.append(f"{audio_in}volume=0.3[a0]")
        filters += mix
        filters.append("[a0]" + "".join(f"[s{i}]" for i in range(len(mix))) + f"amix=inputs={len(mix) + 1}:duration=first:normalize=0[ao]")
    else:
        filters.append(f"{audio_in}anull[ao]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[vo]", "-map", "[ao]", "-r", str(FPS), "-t", f"{dur:.3f}"]
    out_path = od / f"{name}.mp4"
    tail = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(out_path)]
    vt = ["-c:v", "h264_videotoolbox", "-b:v", "4M" if args.draft else "12M", "-profile:v", "high", "-allow_sw", "1"]
    x264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23" if args.draft else "19"]
    if args.verbose:
        print(" ".join(cmd + vt + tail))
    p = subprocess.run(cmd + vt + tail, text=True, capture_output=True)
    if p.returncode:
        p = subprocess.run(cmd + x264 + tail, text=True, capture_output=True)
        if p.returncode:
            die(f"ffmpeg failed:\n{p.stderr[-3000:]}")
    shutil.rmtree(work, ignore_errors=True)
    keep_render(out_path, name, args.draft, f"{kind} reformat · {dur:.1f}s · {w}x{h}")


def keep_render(out_path: Path, name: str, draft: bool, what: str) -> None:
    """versions/<name>.vN.mp4 and final/<name>.mp4 copies of a finished render, as every render keeps."""
    vdir = out_path.parent / "versions"
    vdir.mkdir(exist_ok=True)
    vers = sorted(vdir.glob(f"{name}.v*.mp4"), key=lambda p: natural_key(p.name))
    nxt = (int(re.search(r"\.v(\d+)\.mp4$", vers[-1].name).group(1)) + 1) if vers else 1
    shutil.copy2(out_path, vdir / f"{name}.v{nxt}.mp4")
    if not draft:
        FINAL.mkdir(exist_ok=True)
        shutil.copy2(out_path, FINAL / f"{name}.mp4")
    size = out_path.stat().st_size / 1e6
    print(f"rendered {rel(out_path)} · {what} · {size:.1f} MB" + ("" if draft else f" → final/{name}.mp4") + f" (copy: versions/{name}.v{nxt}.mp4)")


def import_reformat_source(video: str, name: str | None, cookies: str | None) -> tuple[str, Path]:
    """The posted video (a link or a file) under clips/<F>/.source/, its audio in the
    pool (the pointer every reformat of it shares), and a frame sheet of it for Claude
    to read. Returns (F, the source path)."""
    if re.match(r"https?://", video):
        folder = name or next_folder("reel")
        src = fetch_video(video, CLIPS / folder / ".source", cookies)
        (src.parent / "source.json").write_text(json.dumps({"link": video}, indent=1))
        try:
            cs = fetch_comments(video)
        except SystemExit:
            cs = []
        (src.parent / "comments.json").write_text(json.dumps(cs, indent=1))
        if cs:
            print(f"{len(cs)} comments fetched (most liked: @{cs[0]['user']}: {cs[0]['text'][:80]})")
    else:
        p = Path(video).expanduser()
        p = p if p.is_absolute() else ROOT / p
        if not p.exists():
            die(f"no such video: {video}")
        folder = name or re.sub(r"[^A-Za-z0-9_-]+", "_", p.stem).strip("_").lower() or "reel"
        dest_dir = CLIPS / folder / ".source"
        if p.parent.resolve() == dest_dir.resolve():
            src = p
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
            src = dest_dir / p.name
            shutil.copy2(p, src)
    return folder, src


def cmd_reformat(args) -> None:
    """Three reformats of a posted video (hook / narrated / reply) as projects
    <F>_1.._3, or — on one of them — set its copy and re-render."""
    global CUR
    lines = [x.strip() for x in (args.lines or "").split("|") if x.strip()] if args.lines is not None else None
    comment = ({"text": args.comment.strip(), "user": (args.user or "").lstrip("@").strip() or None} if args.comment else None)
    avatar_name = args.avatar   # the reacting avatar only when asked for (Christian dropped it, 2026-10-19)

    def apply_copy(project: dict) -> None:
        if args.hook is not None and project["reformat"] in ("hook", *STYLES):
            project["hook"] = args.hook.strip() or None
            project["caption"] = project["hook"]
        if project["reformat"] in STYLES:
            if args.moments is not None:
                project["moments"] = parse_moments(args.moments, project["reformat"])
            if args.sound is not None:
                sp = Path(args.sound)
                sp = sp if sp.is_absolute() else ROOT / sp
                if args.sound and not sp.exists():
                    die(f"no such sound: {args.sound}")
                project["style_sound"] = rel(sp) if args.sound else None
        if lines is not None and project["reformat"] == "narrated":
            project["lines"] = lines
        if comment is not None and project["reformat"] == "reply":
            project["comment"] = comment
        if args.pick and project["reformat"] == "reply":
            pick_comment(project, int(args.pick))
        if project["reformat"] == "reaction":
            if args.pos:
                project["avatar_pos"] = args.pos
            if args.avatar:
                project["avatar"] = avatar_name
            if args.reactions is not None:
                project["reactions"] = parse_reactions(args.reactions, project.get("avatar") or avatar_name or "", float(project["length"]))
        if args.voice:
            project["voice"] = args.voice

    if not args.video:
        project = load_project()
        if project.get("kind") != "reformat":
            die(f"{CUR} is a cut video, not a reformat — `reformat --video <file|link>` makes reformats of a posted video")
        if args.another:
            # the chain: one more reply to the same video, answering another comment
            if project["reformat"] != "reply":
                die("--another makes another REPLY; run it on a reply reformat")
            m = re.fullmatch(r"(.+)_\d+", CUR)
            new_name = next_name(m.group(1) if m else CUR)
            twin = {**project, "name": new_name, "comment": None, "caption": None}
            shutil.copy2(PROJECTS / f"{CUR}.sound.json", PROJECTS / f"{new_name}.sound.json")
            CUR = new_name
            save_project(twin)
            board = out_dir(project) / f"_{project['name']}_board.jpg"
            if board.exists():
                shutil.copy2(board, out_dir(twin) / f"_{new_name}_board.jpg")
            project = twin
        apply_copy(project)
        save_project(project)
        print(f"{CUR}: {project['reformat']} reformat of {Path(project['source']).name} — {reformat_summary(project)}")
        if args.render:
            render_reformat(project, argparse.Namespace(draft=False, name=None, verbose=False))
        return

    # the three framings, plus the reacting avatar when there is a character to react with
    only = [x.strip() for x in (args.only or "").split(",") if x.strip()] or [k for k in REFORMATS if k != "reaction" or avatar_name]
    for k in only:
        if k not in REFORMATS:
            die(f"unknown reformat '{k}' — have: {', '.join(REFORMATS)}")
    folder, src = import_reformat_source(args.video, args.name, args.cookies)
    dur = video_duration(src)
    cfile = src.parent / "comments.json"
    comments = json.loads(cfile.read_text()) if cfile.exists() else []
    first = next_name(folder)
    CUR = first
    cmd_sound(argparse.Namespace(source=str(src), cookies=None))
    pointer = load_json(PROJECTS / f"{first}.sound.json")
    n = max(6, min(30, round(dur / 4)))
    times = [min(dur * i / n + 0.05, max(0.0, dur - 0.1)) for i in range(n)]
    sheet = out_dir(None, str(src)) / f"_frames_{src.stem}.jpg"
    tile([(str(src), t) for t in times], [f"{t:.1f}s" for t in times], sheet, cols=6)
    print(f"frame sheet of the video: {rel(sheet)}")
    made: list[str] = []
    for kind in only:
        name = next_name(folder)
        CUR = name
        save_json(PROJECTS / f"{name}.sound.json", pointer)
        project = {
            "name": name, "kind": "reformat", "reformat": kind, "source": rel(src), "clips": [],
            "sound": pointer["sound"], "beats": pointer["beats"], "audio_start": 0.0, "length": round(dur, 3),
            "density": dict(DEFAULT_DENSITY), "excluded": [], "hero": None, "caption": None, "cuts": [], "slots": [],
            "hook": None, "lines": [], "comment": None, "voice": args.voice or default_voice(),
            "avatar": avatar_name if kind == "reaction" else None, "reactions": [],
            "comments": comments[:20] if kind == "reply" else [],
            "moments": [], "style_sound": None,
        }
        apply_copy(project)
        if kind in STYLES and not project["moments"]:
            project["moments"] = default_moments(kind, dur, src)
        save_project(project)
        # the feed's poster and the page's storyboard: the video's own frames
        shutil.copy2(sheet, od_board := out_dir(project) / f"_{name}_board.jpg")
        print(f"=== {name}: {kind} reformat of {src.name} — {REFORMATS[kind]} · {reformat_summary(project)} · {rel(od_board)}")
        if args.render:
            try:
                render_reformat(project, argparse.Namespace(draft=False, name=None, verbose=False))
            except SystemExit:
                print(f"  ({name} not rendered yet: it needs its copy first)")
        made.append(name)
    CUR = first
    print(f"\nreformats of {src.name}: {' '.join(made)}")
    print(f"FRAMES: {rel(sheet)}")
    print(f"REFORMATS: {' '.join(made)}")


# -------------------------------------------------------------------- show

def show(project: dict, clips: list[dict]) -> None:
    byid = {c["id"]: c for c in clips}
    cuts, durs = project["cuts"], slot_durs(project)
    t0 = cuts[0]
    drops = {round(d["time"], 3) for d in project.get("_drops", [])}
    hero_id = project.get("hero")
    cap = f'"{project["caption"]}"' if project.get("caption") else "none"
    extras = []
    if project.get("remix_of"):
        extras.append(f"{project.get('remix', 'remix')} remix of {project['remix_of']}")
    if project.get("first"):
        extras.append(f"opens on clip {project['first']}")
    if project.get("story"):
        extras.append("story " + ">".join(map(str, project["story"])) + (f" seed {project['seed']}" if project.get("seed") is not None else ""))
    rhythm = f"synced to beats, density {project['density']}" if project.get("sync") else f"free cuts, {project.get('preset', 'tight')} preset"
    print(
        f"edit '{out_name(project)}': {Path(project['sound']).stem} · audio from {t0:.2f}s · {cuts[-1] - t0:.1f}s long · "
        f"{len(durs)} slots · {rhythm} · caption {cap}"
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
    project = load_project()
    if project.get("kind") == "reformat":
        print(f"{CUR}: {project['reformat']} reformat of {project['source']} · {project['length']:.1f}s · {reformat_summary(project)}")
        return
    show(load_project(), scan_clips())


def cmd_board(_args) -> None:
    project = load_project()
    if project.get("kind") == "reformat":
        src = ROOT / project["source"]
        dur = float(project["length"])
        n = max(6, min(30, round(dur / 4)))
        times = [min(dur * i / n + 0.05, max(0.0, dur - 0.1)) for i in range(n)]
        out = out_dir(project) / f"_{out_name(project)}_board.jpg"
        tile([(str(src), t) for t in times], [f"{t:.1f}s" for t in times], out, cols=6)
        print(f"frames of the source video (a reformat keeps its cut): {rel(out)}")
        return
    clips = scan_clips()
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
    project["slots"][i] = {"clip": clip["id"], "in": round(max(0.0, min(float(args.seconds), hi)), 3)}  # drops a stale `reused` flag
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


def cmd_cut(args) -> None:
    """Split a slot at a time of the VIDEO (seconds from its start, as `show` prints them), or
    `+N` = N seconds into the slot. Not on a beat: this is the free-cut counterpart of `split`.
    The same clip runs on across the new cut — the second half continues where the first ends,
    so the picture is unchanged until you `set`/`in` the new slot."""
    project, clips = load_project(), scan_clips()
    i = parse_ref(args.slot, project, "slot")
    cuts, t0 = project["cuts"], project["cuts"][0]
    a, b = cuts[i], cuts[i + 1]
    tok = str(args.seconds).strip()
    try:
        t = float(tok)
    except ValueError:
        die(f"'{tok}' is not a time — give seconds into the video (e.g. 12.4) or into the slot (e.g. +2)")
    at = a + t if tok.startswith("+") else t0 + t
    where = f"slot {i + 1} runs {a - t0:.2f}-{b - t0:.2f}s of the video ({b - a:.2f}s)"
    if not a < at < b:
        die(f"{at - t0:.2f}s is outside it — {where}; a time inside it, or `cut {i + 1} +<seconds into the slot>`")
    # render rounds every cut to a frame, so check the halves the way render will see them
    f = lambda x: round((x - t0) * FPS)
    if f(at) - f(a) < 1 or f(b) - f(at) < 1:
        die(f"too close to the edge — {where}; each half needs at least one frame ({1 / FPS:.3f}s)")
    s = project["slots"][i]
    cuts.insert(i + 1, round(at, 4))
    project["slots"].insert(i + 1, {**s, "in": round(s["in"] + (at - a), 3)})
    finish(
        project, clips,
        f"cut slot {i + 1} at {at - t0:.2f}s — slots {i + 1} ({a - t0:.2f}-{at - t0:.2f}) and {i + 2} ({at - t0:.2f}-{b - t0:.2f}) "
        f"both show clip {s['clip']}, the footage running on; `set {i + 2} <clip>` or `in {i + 2} <s>` changes the second half",
    )


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
                project["preset"] = kv
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
    project = load_project()
    if project.get("kind") == "reformat":
        render_reformat(project, args)
        return
    clips = scan_clips()
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
    # keep a numbered copy in versions/ so earlier renders survive the next one, and the
    # finished video flat in final/, the one folder Ernest opens
    keep_render(out_path, name, args.draft, f"{total:.2f}s · {n} cuts · {w}x{h}")


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
    s.add_argument("--sync", action="store_true", help="cut ON the beats (default: free cuts, the sound just plays underneath)")
    s.add_argument("--first", type=int, metavar="CLIP", help="clip number that always opens the video (slot 1 is cut to fit it)")
    s.add_argument("--story", metavar="IDS", help="clip numbers in story order, e.g. 2,1,3 — footage is used chronologically across the video")
    s.add_argument("--random", action="store_true", help="random clip + random in-point per slot, no footage re-shown (use --seed to vary / repeat)")
    s.add_argument("--hero", type=int, help="clip number that lands on the drop (default: the longest; ignored with --story)")
    s.add_argument("--exclude", nargs="*", help="clip numbers to leave out")
    s.add_argument("--shuffle", action="store_true", help="random clip order instead of longest-to-longest (no --story)")
    s.add_argument("--seed", type=int, default=None, help="vary the combination: jitters --story in-points / seeds --shuffle")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("remix", help="four new videos from this video's clips (hook cut, another sound, reorder, long version), as projects <folder>_N tagged remix_of")
    s.add_argument("--render", action="store_true", help="render each one too (~1 min each)")
    s.add_argument("--sounds", nargs="*", metavar="MP3", help="sounds to use for the 'sound' and 'long' remixes (default: the pool minus the source's)")
    s.add_argument("--only", metavar="KINDS", help="a subset, e.g. hook,sound")
    s.add_argument("--video", metavar="MP4|LINK", help="remix a finished video instead of a project — a file, or a TikTok / Instagram / YouTube link (downloaded first): it is split into shots (clips/<name>/), its audio joins the pool, and a project <name>_N replays it as the source")
    s.add_argument("--name", metavar="FOLDER", help="with --video: the clips folder / project prefix (default: the file's name, or remixN for a link)")
    s.add_argument("--cookies", metavar="BROWSER", help="with --video <link> on Instagram: chrome / safari / firefox login for yt-dlp")
    s.set_defaults(fn=cmd_remix)
    s = sub.add_parser("reformat", help="reformats of a posted video — hook line / narration / comment reply, plus the styles goofy and cinematic with --only — as projects <F>_N; or, on one of them, set its copy")
    s.add_argument("--video", metavar="MP4|LINK", help="the posted video: a file, or a TikTok / Instagram / YouTube link")
    s.add_argument("--name", metavar="FOLDER", help="with --video: the folder / project prefix (default: the file's name, or reelN for a link)")
    s.add_argument("--cookies", metavar="BROWSER", help="with an Instagram link: chrome / safari / firefox login for yt-dlp")
    s.add_argument("--only", metavar="KINDS", help="a subset, e.g. hook,reply")
    s.add_argument("--hook", metavar="TEXT", help="the hook line on screen (hook reformat)")
    s.add_argument("--lines", metavar="A|B|C", help="the narration, lines separated by | (narrated reformat)")
    s.add_argument("--voice", metavar="VOICE", help=f"the narration voice: eleven (the ElevenLabs voice in web/.env.local, the default when a key is set), eleven:<voice_id>, or a macOS voice name (default {DEFAULT_VOICE} without a key; `say -v '?'` lists them)")
    s.add_argument("--comment", metavar="TEXT", help="the comment the video answers (reply reformat)")
    s.add_argument("--user", metavar="HANDLE", help="who wrote the comment, if real (shown as 'Reply to @user')")
    s.add_argument("--pick", type=int, metavar="N", help="answer the N-th fetched comment of the post (most liked first; `comments <link>` lists them)")
    s.add_argument("--moments", metavar="T:FX,…", help="a style's moments: goofy zoom/boom/bruh/nah/whoosh, cinematic slow/riser — e.g. 1.2:zoom,3:boom (default: a guess)")
    s.add_argument("--sound", metavar="MP3", help="a style's sound from the pool (goofy: under the original audio; cinematic: instead of it; '' = none)")
    s.add_argument("--another", action="store_true", help="on a reply: one more reply to the same video, answering another comment (--pick / --comment)")
    s.add_argument("--avatar", metavar="NAME", help="the character for the reaction reformat (default: the first under clips/_avatar/)")
    s.add_argument("--reactions", metavar="T:KIND,…", help="when the avatar does what, e.g. 0:nod,2.5:shocked,6:laugh (reaction reformat; default: spread evenly)")
    s.add_argument("--pos", choices=["corner", "center"], help="where the green-screen avatar stands: corner (bottom-left, default) or center (big, bottom-centre)")
    s.add_argument("--render", action="store_true", help="render too (each one that has its copy)")
    s.set_defaults(fn=cmd_reformat)
    s = sub.add_parser("avatar", help="a character that reacts in the corner of a reaction reformat: generate its reaction clips once (Higgsfield image-to-video) — or --list")
    s.add_argument("name", nargs="?")
    s.add_argument("--image", metavar="URL|FILE", help="the character's picture (a public https url, or a file sent as a data url); without it Higgsfield draws one")
    s.add_argument("--prompt", metavar="TEXT", help="without --image: what the character looks like (default: a generic one — a guy in a hoodie at the gym with a laptop)")
    s.add_argument("--reactions", metavar="KINDS", help=f"which clips to make (default agree,present,listen; have: {', '.join(REACTIONS)})")
    s.add_argument("--image-only", action="store_true", help="only draw the character (about a cent) — no reaction clips yet")
    s.add_argument("--model", choices=list(HF_VIDEO_MODELS), help=f"image-to-video model (default {DEFAULT_VIDEO_MODEL}, the cheapest)")
    s.add_argument("--redo", action="store_true", help="generate again even if the clips exist")
    s.add_argument("--list", action="store_true")
    s.set_defaults(fn=cmd_avatar)
    s = sub.add_parser("comments", help="the top comments of a posted video (TikTok keylessly), most liked first — what a reply reformat answers")
    s.add_argument("link")
    s.add_argument("--count", type=int, default=30)
    s.set_defaults(fn=cmd_comments)
    s = sub.add_parser("shots", help="cut a finished video into its shots (scene detection) as clips in clips/<name>/")
    s.add_argument("video")
    s.add_argument("--into", metavar="FOLDER", help="clips folder name (default: the file's name)")
    s.add_argument("--min-shot", type=float, default=1.5, help="no shot shorter than this many seconds (default 1.5)")
    s.set_defaults(fn=cmd_shots)

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
    s = sub.add_parser("cut", help="split a slot at a time of the video (seconds from its start, as `show` prints; +N = N s into the slot); the clip runs on across the cut")
    s.add_argument("slot"); s.add_argument("seconds"); s.set_defaults(fn=cmd_cut)
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
