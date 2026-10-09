#!/usr/bin/env python3
"""Facts for the /day skill. `python3 tools/day.py status` prints everything the skill
needs to decide what to do next: the next day number, whether the swipe file is stale,
what each day already has (clips, plan, videos, captions). Read-only."""
import json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIPE = Path.home() / ".claude" / "instagram" / "swipe.md"
IDEAS = ROOT / "projects" / "ideas.md"          # one line per shot day: which formula was used

def nat(s): return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]

def days():
    out = {}
    for d in sorted((ROOT / "clips").glob("day*"), key=lambda p: nat(p.name)):
        n = int(d.name[3:])
        clips = [p for p in d.iterdir() if p.suffix.lower() in (".mov", ".mp4", ".m4v")]
        out[n] = {"clips": len(clips)}
    for p in (ROOT / "projects").glob("day*_*.json"):
        if p.name.endswith(".sound.json"): continue
        n = int(re.match(r"day(\d+)_", p.name).group(1))
        out.setdefault(n, {"clips": 0})
        mp4 = ROOT / "out" / f"day{n}" / f"{p.stem}.mp4"
        cap = ROOT / "out" / f"day{n}" / f"{p.stem}.caption.txt"
        out[n].setdefault("videos", []).append({"name": p.stem, "rendered": mp4.exists(), "caption": cap.exists(),
                                                "hook": json.loads(p.read_text()).get("caption")})
    for p in (ROOT / "projects").glob("day*.plan.md"):
        n = int(re.match(r"day(\d+)\.plan", p.name).group(1))
        out.setdefault(n, {"clips": 0})["plan"] = str(p.relative_to(ROOT))
    return dict(sorted(out.items()))

def status():
    ds = days()
    last = max(ds) if ds else 0
    swipe_age = (time.time() - SWIPE.stat().st_mtime) / 86400 if SWIPE.exists() else None
    used = IDEAS.read_text().strip().splitlines() if IDEAS.exists() else []
    print(f"next_day_to_plan: {last + 1 if ds.get(last, {}).get('clips') else last or 1}")
    print(f"swipe_file: {SWIPE if SWIPE.exists() else 'MISSING - run /ig-viral first'}")
    print(f"swipe_age_days: {swipe_age:.0f}" if swipe_age is not None else "swipe_age_days: n/a")
    print(f"swipe_stale: {'yes - refresh with /ig-viral' if swipe_age is None or swipe_age > 30 else 'no'}")
    print("ideas_used:" + ("" if used else " none yet"))
    for u in used: print(f"  {u}")
    print("days:")
    for n, d in ds.items():
        vids = ", ".join(f"{v['name']}{'' if v['rendered'] else ' (not rendered)'}{' +caption' if v['caption'] else ''}" for v in d.get("videos", [])) or "no video"
        print(f"  day{n}: {d['clips']} clips · plan: {d.get('plan', 'none')} · {vids}")

if __name__ == "__main__":
    status()
