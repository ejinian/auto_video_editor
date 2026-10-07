# /// script
# dependencies = ["pyobjc-framework-Quartz"]
# ///
"""Capture an app's largest on-screen window by its CGWindowID (works even when
another window covers it). Usage: winshot.py <app name> <out.png>"""
import subprocess, sys
from Quartz import CGWindowListCopyWindowInfo
kCGWindowListOptionOnScreen, kCGNullWindowID = 1, 0
app, out = sys.argv[1], sys.argv[2]
wins = [w for w in CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreen, kCGNullWindowID)
        if w.get("kCGWindowOwnerName") == app and w.get("kCGWindowLayer", 0) == 0]
if not wins:
    sys.exit(f"no on-screen window for {app}")
w = max(wins, key=lambda w: w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"])
b = w["kCGWindowBounds"]
print(f"window id {w['kCGWindowNumber']} title={w.get('kCGWindowName')!r} bounds={int(b['X'])},{int(b['Y'])} {int(b['Width'])}x{int(b['Height'])}")
subprocess.run(["screencapture", "-x", "-o", "-l", str(w["kCGWindowNumber"]), out], check=True)
