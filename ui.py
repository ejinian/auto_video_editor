#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["flask>=3.0"]
# ///
"""beatcut UI — buttons for the pipeline. Run `uv run ui.py`, open http://127.0.0.1:8765.

Nothing clever lives here: every button shells out to `uv run beatcut.py …` exactly the
way the command reference says, and the pages read the same files the CLI writes
(projects/<name>.json, out/dayN/…). Close the tab and the CLI still works the same.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template_string, request, send_file, url_for

ROOT = Path(__file__).resolve().parent
CLIPS, SOUND, OUT, PROJECTS = ROOT / "clips", ROOT / "sound", ROOT / "out", ROOT / "projects"
PRESETS = ["tight", "loose", "chill"]
app = Flask(__name__)
JOBS: dict[str, dict] = {}


# ----------------------------------------------------------------- helpers

def beatcut(*argv: str) -> list[str]:
    return ["uv", "run", str(ROOT / "beatcut.py"), *argv]


def natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def days() -> list[dict]:
    out = []
    for d in sorted(CLIPS.glob("day*"), key=lambda p: natural(p.name)):
        if d.is_dir():
            clips = day_clips(d.name)
            out.append({"name": d.name, "n": len(clips), "projects": [p["name"] for p in projects() if p["day"] == d.name]})
    return out


def day_clips(day: str) -> list[Path]:
    d = CLIPS / day
    return sorted((p for p in d.iterdir() if p.suffix.lower() in (".mov", ".mp4", ".m4v")), key=lambda p: natural(p.name))


def project_day(name: str) -> str | None:
    m = re.match(r"(day\d+)_", name)
    return m.group(1) if m else None


def project_out(name: str) -> Path:
    day = project_day(name)
    return OUT / day if day else OUT


def projects() -> list[dict]:
    out = []
    for p in sorted(PROJECTS.glob("*.json"), key=lambda p: natural(p.name)):
        if p.name.endswith(".sound.json"):
            continue
        name = p.stem
        mp4 = project_out(name) / f"{name}.mp4"
        data = json.loads(p.read_text())
        out.append({
            "name": name, "day": project_day(name), "rendered": mp4.exists(),
            "stale": mp4.exists() and p.stat().st_mtime > mp4.stat().st_mtime + 1,
            "length": data.get("length"), "slots": len(data.get("slots", [])),
            "caption": data.get("caption"), "sound": sound_title(name),
        })
    return out


def sound_title(name: str) -> str:
    sp = PROJECTS / f"{name}.sound.json"
    if not sp.exists():
        return ""
    meta = json.loads(sp.read_text()).get("meta") or {}
    t = meta.get("title") or Path(json.loads(sp.read_text()).get("sound", "")).stem
    return f"{t} — {meta['author']}" if meta.get("author") else t


def next_project_name(day: str) -> str:
    n = [int(m.group(1)) for p in PROJECTS.glob(f"{day}_*.json") if (m := re.match(rf"{day}_(\d+)\.json$", p.name))]
    return f"{day}_{(max(n) + 1) if n else 1}"


def sounds() -> list[dict]:
    out = []
    for mp3 in sorted(SOUND.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True):
        src = mp3.with_suffix(".source.json")
        meta = json.loads(src.read_text()).get("meta", {}) if src.exists() else {}
        title = meta.get("title") or mp3.stem
        out.append({"path": f"sound/{mp3.name}", "title": f"{title} — {meta['author']}" if meta.get("author") else title})
    return out


def link_sound(project: str, mp3_rel: str) -> None:
    """Point a project at a sound already in sound/ by writing its pointer file.
    Running `sound sound/x.mp3` instead would re-import the file onto itself and
    truncate it (seen 2026-10-08), so the pointer is written directly."""
    mp3 = ROOT / mp3_rel
    beats = mp3.parent / (mp3.stem + ".beats.json")
    if not (mp3.exists() and beats.exists()):
        abort(400, f"{mp3_rel} has no beat analysis next to it")
    src = mp3.parent / (mp3.stem + ".source.json")
    meta = json.loads(src.read_text()).get("meta", {}) if src.exists() else {"source": mp3_rel, "title": mp3.stem}
    (PROJECTS / f"{project}.sound.json").write_text(json.dumps(
        {"sound": f"sound/{mp3.name}", "beats": f"sound/{beats.name}", "meta": meta}, indent=1))


def thumb(clip: Path) -> Path:
    """One 320px-tall frame from 1 s in, cached next to the project outputs."""
    day = clip.parent.name
    t = OUT / day / ".thumbs" / f"{clip.stem}.jpg"
    if not t.exists():
        t.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(clip), "-frames:v", "1",
                        "-vf", "scale=-2:320", str(t)], check=False)
    return t


def duration(clip: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(clip)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def load(name: str) -> dict:
    p = PROJECTS / f"{name}.json"
    if not p.exists():
        abort(404)
    return json.loads(p.read_text())


def slot_rows(pr: dict) -> list[dict]:
    cuts, a0 = pr["cuts"], pr["cuts"][0]
    rows = []
    for i, s in enumerate(pr["slots"]):
        t0, t1 = cuts[i] - a0, cuts[i + 1] - a0
        rows.append({"n": i + 1, "t0": t0, "t1": t1, "dur": t1 - t0, "clip": s["clip"],
                     "file": Path(pr["clips"][s["clip"] - 1]).name, "in": s["in"],
                     "drop": any(abs((d["time"] if isinstance(d, dict) else d) - cuts[i]) < 0.35 for d in pr.get("_drops", []))})
    return rows


# -------------------------------------------------------------------- jobs

def start_job(title: str, cmds: list[list[str]], then: str) -> str:
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"title": title, "log": "", "done": False, "ok": True, "then": then}

    def run():
        j = JOBS[jid]
        for cmd in cmds:
            j["log"] += "$ " + " ".join(c if " " not in c else f'"{c}"' for c in cmd[3:] if c != str(ROOT / "beatcut.py")) + "\n"
            p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                j["log"] += line
            if p.wait() != 0:
                j["ok"] = False
                j["log"] += f"\n✗ stopped: that step failed (exit {p.returncode})\n"
                break
        j["done"] = True

    threading.Thread(target=run, daemon=True).start()
    return jid


@app.get("/job/<jid>")
def job_json(jid):
    j = JOBS.get(jid) or abort(404)
    return jsonify(j)


@app.get("/jobs/<jid>")
def job_page(jid):
    j = JOBS.get(jid) or abort(404)
    return page(f"""
    <h1>{j['title']}</h1>
    <p id="status" class="muted">running… this page updates itself. A 30 s render takes about a minute.</p>
    <pre id="log" class="log"></pre>
    <p><a id="then" class="btn hidden" href="{j['then']}">Open the result →</a></p>
    <script>
    async function tick(){{
      const r = await fetch('/job/{jid}'); const j = await r.json();
      const log = document.getElementById('log'); log.textContent = j.log; log.scrollTop = log.scrollHeight;
      if (j.done) {{
        document.getElementById('status').textContent = j.ok ? 'done.' : 'stopped on an error — read the last lines.';
        document.getElementById('then').classList.remove('hidden');
        if (j.ok) setTimeout(()=>location.href='{j['then']}', 900);
      }} else setTimeout(tick, 1200);
    }}
    tick();
    </script>""")


# ------------------------------------------------------------------- pages

CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#e8eaf0;--muted:#8b93a7;--acc:#5ad1b0;--warn:#f0b35a;--bad:#f06a6a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,Inter,Helvetica,sans-serif}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 60px}
nav{display:flex;gap:18px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line);background:var(--card)}
nav b{letter-spacing:.04em}nav a{color:var(--muted)}nav a:hover{color:var(--fg)}
h1{font-size:22px;margin:18px 0 8px}h2{font-size:16px;margin:26px 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.clip img{width:100%;border-radius:8px;display:block;aspect-ratio:9/16;object-fit:cover;background:#000}
.clip .n{position:absolute;top:6px;left:6px;background:#000c;color:#fff;font-weight:700;padding:2px 8px;border-radius:6px}
.clip{position:relative}.clip small{color:var(--muted);display:block;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
label{display:block;color:var(--muted);font-size:13px;margin:10px 0 4px}
input[type=text],input[type=number],select,textarea{width:100%;background:#0b0d12;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 10px;font:inherit}
textarea{min-height:70px}.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.btn{display:inline-block;background:var(--acc);color:#07110d;font-weight:700;border:0;border-radius:9px;padding:10px 16px;cursor:pointer;font:inherit}
.btn.sec{background:transparent;color:var(--fg);border:1px solid var(--line)}.btn.warn{background:var(--warn);color:#1a1200}
.btn:hover{filter:brightness(1.08);text-decoration:none}.hidden{display:none}.muted{color:var(--muted)}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:14px}
th{color:var(--muted);font-weight:600}tr.drop td{background:#5ad1b018}
.log{background:#0b0d12;border:1px solid var(--line);border-radius:10px;padding:12px;max-height:60vh;overflow:auto;font:13px/1.4 ui-monospace,Menlo,monospace;white-space:pre-wrap}
.tag{display:inline-block;font-size:12px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--muted);margin-left:6px}
.tag.ok{color:var(--acc);border-color:var(--acc)}.tag.warn{color:var(--warn);border-color:var(--warn)}
video{width:100%;max-height:70vh;background:#000;border-radius:10px}.two{display:grid;grid-template-columns:minmax(260px,360px) 1fr;gap:18px}
@media(max-width:800px){.two{grid-template-columns:1fr}}
.inline{display:flex;gap:8px;align-items:end;flex-wrap:wrap}.inline>*{flex:1 1 90px}.inline .btn{flex:0 0 auto}
code{background:#0b0d12;padding:1px 5px;border-radius:5px;font-size:13px}
"""


def page(body: str, title: str = "beatcut") -> str:
    return render_template_string("""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{{title}}</title><style>{{css|safe}}</style></head><body>
<nav><b><a href="/" style="color:var(--fg)">beatcut</a></b><a href="/">days</a><a href="/#projects">videos</a><a href="/howto">how to</a></nav>
<div class=wrap>{{body|safe}}</div></body></html>""", title=title, css=CSS, body=body)


@app.get("/")
def home():
    ds, ps = days(), projects()
    cards = ""
    for d in ds:
        vids = ", ".join(f'<a href="/p/{n}">{n}</a>' for n in d["projects"]) or '<span class=muted>no video yet</span>'
        cards += f'<div class=card><b><a href="/day/{d["name"]}">{d["name"]}</a></b> <span class=tag>{d["n"]} clips</span><div class=muted style="margin-top:6px">videos: {vids}</div></div>'
    if not ds:
        cards = '<div class=card>No clips yet. Make a folder <code>clips/day4/</code> and drop the phone clips in it, then refresh.</div>'
    rows = ""
    for p in ps:
        st = '<span class="tag ok">rendered</span>' if p["rendered"] and not p["stale"] else ('<span class="tag warn">edited, needs render</span>' if p["rendered"] else '<span class=tag>not rendered</span>')
        rows += f'<tr><td><a href="/p/{p["name"]}">{p["name"]}</a></td><td>{p["sound"]}</td><td>{p["length"]:.0f} s · {p["slots"]} shots</td><td>{(p["caption"] or "")[:50]}</td><td>{st}</td></tr>'
    body = f"""<h1>Days</h1>{cards}
    <h2 id=projects>Videos</h2><div class=card><table><tr><th>video</th><th>sound</th><th>cut</th><th>on-screen hook</th><th></th></tr>{rows or '<tr><td colspan=5 class=muted>none yet</td></tr>'}</table></div>
    <h2>New day</h2><div class=card><p class=muted>In Finder: <code>~/Desktop/beatcut/clips/dayN/</code>, AirDrop the clips in, come back here and refresh. Then open the day and press <b>Cut it</b>.</p></div>"""
    return page(body)


@app.get("/day/<day>")
def day_page(day):
    clips = day_clips(day) if (CLIPS / day).is_dir() else abort(404)
    grid = ""
    for i, c in enumerate(clips, 1):
        thumb(c)
        grid += f'<div class=clip><img src="/thumb/{day}/{c.stem}" loading=lazy><span class=n>{i}</span><small>{c.name} · {duration(c):.0f}s</small></div>'
    sopts = "".join(f'<option value="{s["path"]}">{s["title"]}</option>' for s in sounds())
    popts = "".join(f'<option value="{p}" {"selected" if p == "tight" else ""}>{p}</option>' for p in PRESETS)
    copts = "".join(f'<option value="{i}">{i} · {c.name}</option>' for i, c in enumerate(clips, 1))
    existing = ", ".join(f'<a href="/p/{p["name"]}">{p["name"]}</a>' for p in projects() if p["day"] == day) or "none yet"
    body = f"""<h1>{day} <span class=tag>{len(clips)} clips</span></h1>
    <p class=muted>Clip numbers are what the edit buttons use. Videos from this day so far: {existing}.</p>
    <div class=grid>{grid}</div>
    <h2>Cut a video from these clips</h2>
    <form class=card method=post action="/day/{day}/cut">
      <div class=row>
        <div><label>Video name</label><input type=text name=name value="{next_project_name(day)}"></div>
        <div><label>Length (seconds, ends on the nearest downbeat)</label><input type=number name=length value=30 min=5 max=90 step=1></div>
        <div><label>How often to cut</label><select name=preset>{popts}</select></div>
      </div>
      <div class=row>
        <div><label>Sound link (TikTok video / sound page, Instagram reel, YouTube)</label><input type=text name=link placeholder="https://www.tiktok.com/…"></div>
        <div><label>…or a sound already downloaded</label><select name=existing><option value="">— pick —</option>{sopts}</select></div>
      </div>
      <div class=row>
        <div><label>Opens with clip (always from its start)</label><select name=first><option value="">let the tool choose</option>{copts}</select></div>
        <div><label>Story order, clip numbers (blank = all clips, in order)</label><input type=text name=story placeholder="e.g. 3,1,5,2"></div>
        <div><label>Mode</label><select name=mode><option value=story>story: footage plays out in order</option><option value=random>random angles in random order</option><option value=auto>auto: longest clip gets the longest shot</option></select></div>
        <div><label>Seed (change it for another variation of the same choices)</label><input type=number name=seed placeholder="blank = none"></div>
      </div>
      <label>On-screen hook (burned in, lowercase, top-centre; blank = none)</label><input type=text name=caption placeholder="claude code takes 10 minutes a prompt so we started lifting between prompts">
      <p><button class=btn>Cut it</button> <span class=muted>downloads the sound if needed, plans, builds the storyboard and renders. About 1–2 minutes.</span></p>
    </form>"""
    return page(body, day)


@app.post("/day/<day>/cut")
def day_cut(day):
    f = request.form
    name = re.sub(r"[^\w\-]", "", f.get("name") or next_project_name(day)) or next_project_name(day)
    cmds = []
    link, existing = (f.get("link") or "").strip(), f.get("existing") or ""
    if link:
        cmds.append(beatcut("-p", name, "sound", link))
    elif existing:
        link_sound(name, existing)  # never re-import a file that already lives in sound/
    elif not (PROJECTS / f"{name}.sound.json").exists():
        return page('<div class=card>Pick a sound: paste a link or choose one already downloaded. <a href="javascript:history.back()">Back</a></div>')
    plan = ["-p", name, "plan", "--clips-dir", f"clips/{day}", "--length", f.get("length") or "30", "--preset", f.get("preset") or "tight"]
    if f.get("first"):
        plan += ["--first", f["first"]]
    mode = f.get("mode")
    if mode == "random":
        plan += ["--random"]
    elif mode == "story":
        story = re.sub(r"[^\d,]", "", f.get("story") or "")
        if not story:
            n = len(day_clips(day))
            story = ",".join(str(i) for i in range(1, n + 1) if str(i) != f.get("first"))
        plan += ["--story", story]
    if f.get("seed"):
        plan += ["--seed", f["seed"]]
    cmds.append(beatcut(*plan))
    if (cap := (f.get("caption") or "").strip()):
        cmds.append(beatcut("-p", name, "caption", cap))
    cmds += [beatcut("-p", name, "board"), beatcut("-p", name, "render")]
    return redirect(url_for("job_page", jid=start_job(f"Cutting {name}", cmds, f"/p/{name}")))


@app.get("/p/<name>")
def project_page(name):
    pr = load(name)
    od = project_out(name)
    mp4, board = od / f"{name}.mp4", od / f"_{name}_board.jpg"
    pj = PROJECTS / f"{name}.json"
    stale = mp4.exists() and pj.stat().st_mtime > mp4.stat().st_mtime + 1
    rows = "".join(
        f'<tr class="{"drop" if r["drop"] else ""}"><td>{r["n"]}</td><td>{r["t0"]:.2f}–{r["t1"]:.2f}</td><td>{r["dur"]:.2f}</td>'
        f'<td><b>{r["clip"]}</b> <span class=muted>{r["file"]}</span></td><td>{r["in"]:.1f}</td><td>{"DROP" if r["drop"] else ""}</td></tr>'
        for r in slot_rows(pr))
    clips = "".join(f'<div class=clip><img src="/thumb/{Path(c).parent.name}/{Path(c).stem}" loading=lazy><span class=n>{i}</span><small>{Path(c).name}{" · out" if i in pr.get("excluded", []) else ""}</small></div>'
                    for i, c in enumerate(pr["clips"], 1))
    cap_txt = (od / f"{name}.caption.txt")
    status = ('<span class="tag warn">edited since the last render — press Render</span>' if stale else
              ('<span class="tag ok">rendered</span>' if mp4.exists() else '<span class=tag>not rendered yet</span>'))
    video = f'<video controls playsinline src="/file/{od.relative_to(OUT)}/{name}.mp4"></video>' if mp4.exists() else '<div class=card class=muted>not rendered yet</div>'
    boardimg = f'<a href="/file/{od.relative_to(OUT)}/_{name}_board.jpg" target=_blank><img src="/file/{od.relative_to(OUT)}/_{name}_board.jpg" style="width:100%;border-radius:10px"></a>' if board.exists() else '<p class=muted>no storyboard yet</p>'
    body = f"""<h1>{name} {status}</h1>
    <p class=muted>{sound_title(name)} · {pr['length']:.0f} s asked · {len(pr['slots'])} shots · hook: {pr.get('caption') or '<i>none</i>'}
    &nbsp;·&nbsp; file: <code>~/Desktop/beatcut/out/{od.relative_to(OUT) if od != OUT else ''}/{name}.mp4</code></p>
    <div class=two>
      <div>{video}
        <p>{f'<a class=btn href="/file/{od.relative_to(OUT)}/{name}.mp4" download>Download mp4</a> ' if mp4.exists() else ''}
           <form style="display:inline" method=post action="/p/{name}/run"><input type=hidden name=cmd value=render><button class="btn {'warn' if stale else 'sec'}">Render</button></form>
           <form style="display:inline" method=post action="/p/{name}/run"><input type=hidden name=cmd value=export><button class="btn sec" title="writes a CapCut project and opens it (quit CapCut first)">Open in CapCut</button></form></p>
      </div>
      <div>{boardimg}<p class=muted>Storyboard: one frame per shot, labelled slot · clip.</p></div>
    </div>

    <h2>Shots</h2><div class=card><table><tr><th>slot</th><th>time (s)</th><th>dur</th><th>clip</th><th>in at</th><th></th></tr>{rows}</table></div>

    <h2>Edit</h2>
    <div class=card>
      <p class=muted>Each button changes the plan and rebuilds the storyboard. Press <b>Render</b> when it looks right. Every render is kept under <code>versions/</code>.</p>
      <div class=row>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=swap><label>Swap two slots</label><div class=inline><input type=text name=a placeholder="slot" required><input type=text name=b placeholder="slot" required><button class="btn sec">Swap</button></div></form>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=set><label>Put a clip in a slot</label><div class=inline><input type=text name=slot placeholder="slot" required><input type=text name=clip placeholder="clip" required><input type=text name=at placeholder="start s (opt)"><button class="btn sec">Set</button></div></form>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=in><label>Start a slot later in its clip</label><div class=inline><input type=text name=slot placeholder="slot" required><input type=text name=sec placeholder="seconds" required><button class="btn sec">Set in-point</button></div></form>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=merge><label>Hold a shot longer (join slot into the previous)</label><div class=inline><input type=text name=slot placeholder="slot" required><button class="btn sec">Merge</button></div></form>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=split><label>Cut faster there (split a slot)</label><div class=inline><input type=text name=slot placeholder="slot" required><button class="btn sec">Split</button></div></form>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=drop><label>Get rid of a clip (its slots refill)</label><div class=inline><input type=text name=clip placeholder="clip" required><button class="btn sec">Drop</button></div></form>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=restore><label>Put a clip back</label><div class=inline><input type=text name=clip placeholder="clip" required><button class="btn sec">Restore</button></div></form>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=hero><label>Clip on the drop (not in story mode)</label><div class=inline><input type=text name=clip placeholder="clip" required><button class="btn sec">Hero</button></div></form>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=shuffle><label>Same cuts, different clips in them</label><div class=inline><input type=text name=seed placeholder="seed (opt)"><button class="btn sec">Shuffle</button></div></form>
      </div>
      <div class=row style="margin-top:8px">
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=caption><label>On-screen hook (rebuild + render needed)</label><div class=inline><input type=text name=text value="{(pr.get('caption') or '').replace('"', '&quot;')}" placeholder="blank = remove"><button class="btn sec">Set hook</button></div></form>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=length><label>Length (rebuilds the whole edit)</label><div class=inline><input type=number name=value value="{pr['length']:.0f}" step=1 min=5 max=90><button class="btn sec">Change length</button></div></form>
        <form method=post action="/p/{name}/run"><input type=hidden name=cmd value=density><label>Cut density (rebuilds)</label><div class=inline><select name=value>{''.join(f'<option value={p}>{p}</option>' for p in PRESETS)}</select><button class="btn sec">Change</button></div></form>
        <form method=post action="/p/{name}/variation"><label>New variation (same clips, new seed; optional new sound link)</label><div class=inline><input type=text name=link placeholder="sound link (opt)"><button class=btn>Make variation</button></div></form>
      </div>
    </div>

    <h2>Caption for the post</h2>
    <form class=card method=post action="/p/{name}/caption-file">
      <p class=muted>Written by the caption skill in Claude (<code>/ig-caption</code>) or by hand. Saved next to the mp4 as <code>{name}.caption.txt</code>.</p>
      <textarea name=text>{cap_txt.read_text() if cap_txt.exists() else ''}</textarea>
      <p><button class="btn sec">Save caption</button></p>
    </form>

    <h2>Clips in this video</h2><div class=grid>{clips}</div>"""
    return page(body, name)


@app.post("/p/<name>/run")
def project_run(name):
    load(name)
    f = request.form
    c = f.get("cmd")
    argv = None
    if c == "render":
        argv = ["render"]
    elif c == "export":
        argv = ["export", "--open"]
    elif c == "swap":
        argv = ["swap", f["a"], f["b"]]
    elif c == "set":
        argv = ["set", f["slot"], f["clip"]] + (["--at", f["at"]] if f.get("at") else [])
    elif c == "in":
        argv = ["in", f["slot"], f["sec"]]
    elif c in ("merge", "split"):
        argv = [c, f["slot"]]
    elif c in ("drop", "restore", "hero"):
        argv = [c, f["clip"]]
    elif c == "shuffle":
        argv = ["shuffle"] + (["--seed", f["seed"]] if f.get("seed") else [])
    elif c == "caption":
        argv = ["caption", (f.get("text") or "").strip() or "none"]
    elif c in ("length", "density"):
        argv = [c, f["value"]]
    if argv is None:
        abort(400)
    cmds = [beatcut("-p", name, *argv)]
    if c not in ("render", "export"):
        cmds.append(beatcut("-p", name, "board"))
    return redirect(url_for("job_page", jid=start_job(f"{name}: {' '.join(argv)}", cmds, f"/p/{name}")))


@app.post("/p/<name>/variation")
def project_variation(name):
    pr = load(name)
    day = project_day(name) or "misc"
    new = next_project_name(day)
    link = (request.form.get("link") or "").strip()
    cmds = []
    if link:
        cmds.append(beatcut("-p", new, "sound", link))
    else:
        link_sound(new, pr["sound"])
    plan = ["-p", new, "plan", "--clips", *pr["clips"], "--length", str(pr["length"])]
    if pr.get("first"):
        plan += ["--first", str(pr["first"])]
    if pr.get("random"):
        plan += ["--random"]
    elif pr.get("story"):
        plan += ["--story", ",".join(map(str, pr["story"]))]
    plan += ["--seed", str((pr.get("seed") or 0) + 1)]
    d = pr.get("density", {})
    for k, v in {"tight": {"calm": 4, "hype": 2}, "loose": {"calm": 8, "hype": 4}}.items():
        if all(d.get(a) == b for a, b in v.items()):
            plan += ["--preset", k]
    cmds.append(beatcut(*plan))
    if pr.get("caption"):
        cmds.append(beatcut("-p", new, "caption", pr["caption"]))
    cmds += [beatcut("-p", new, "board"), beatcut("-p", new, "render")]
    return redirect(url_for("job_page", jid=start_job(f"Variation {new} of {name}", cmds, f"/p/{new}")))


@app.post("/p/<name>/caption-file")
def caption_file(name):
    load(name)
    od = project_out(name)
    od.mkdir(parents=True, exist_ok=True)
    (od / f"{name}.caption.txt").write_text(request.form.get("text", "").strip() + "\n")
    return redirect(f"/p/{name}#")


@app.get("/thumb/<day>/<stem>")
def thumb_route(day, stem):
    t = OUT / day / ".thumbs" / f"{stem}.jpg"
    if not t.exists():
        for c in day_clips(day):
            if c.stem == stem:
                thumb(c)
    return send_file(t) if t.exists() else abort(404)


@app.get("/file/<path:rel>")
def file_route(rel):
    p = (OUT / rel).resolve()
    if OUT.resolve() not in p.parents or not p.exists():
        abort(404)
    return send_file(p, conditional=True)


@app.get("/howto")
def howto():
    md = (ROOT / "HOWTO.md").read_text() if (ROOT / "HOWTO.md").exists() else "HOWTO.md is missing."

    def inline(t):
        t = t.replace("&", "&amp;").replace("<", "&lt;")
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)

    out = []
    for block in re.split(r"\n\s*\n", md):
        lines = block.strip("\n").splitlines()
        if not lines:
            continue
        if lines[0].startswith("#"):
            level = len(lines[0]) - len(lines[0].lstrip("#"))
            out.append(f"<h{min(level, 3)}>{inline(lines[0].lstrip('#').strip())}</h{min(level, 3)}>")
            lines = lines[1:]
            if not lines:
                continue
        if lines[0].startswith("|"):
            rows = [l for l in lines if l.startswith("|") and not re.match(r"^\|\s*-", l)]
            cells = lambda l: [inline(c.strip()) for c in l.strip("|").split("|")]
            head = "".join(f"<th>{c}</th>" for c in cells(rows[0]))
            body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in cells(r)) + "</tr>" for r in rows[1:])
            out.append(f"<table><tr>{head}</tr>{body}</table>")
            continue
        if re.match(r"^(- |\d+\. )", lines[0]):
            items, ordered = [], lines[0][0].isdigit()
            for l in lines:
                if re.match(r"^(- |\d+\. )", l):
                    items.append(re.sub(r"^(- |\d+\. )", "", l))
                else:
                    items[-1] += " " + l.strip()
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>")
            continue
        out.append(f"<p>{inline(' '.join(l.strip() for l in lines))}</p>")
    return page(f"<div class=card>{''.join(out)}</div>", "how to")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"beatcut UI → http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
