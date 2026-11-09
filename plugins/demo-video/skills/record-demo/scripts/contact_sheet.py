# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Grab one still per scene (from its closing hold) so the whole take can be checked by eye.

Usage: contact_sheet.py WORKDIR VIDEO

Writes WORKDIR/qc/NN-<scene>.png (1280 px wide) and WORKDIR/qc/sheet.png (all scenes tiled).
Look at every still: is the pointer beside its target, is anything cut off, is anything sensitive visible?
"""
import glob, json, math, os, subprocess, sys

if len(sys.argv) < 3: sys.exit(__doc__)
W, V = os.path.abspath(sys.argv[1]), sys.argv[2]
tl = json.load(open(f"{W}/timeline.json")); sc = tl["scenes"]; end = tl["end"] - tl["start"]
os.makedirs(f"{W}/qc", exist_ok=True)
for f in glob.glob(f"{W}/qc/*.png"): os.remove(f)
for i, s in enumerate(sc):
    b = (sc[i + 1]["t"] - tl["start"]) if i + 1 < len(sc) else end
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(b - 0.7, 0):.2f}", "-i", V, "-frames:v", "1",
                    "-vf", "scale=1280:-1", f"{W}/qc/{i + 1:02d}-{s['id']}.png"], check=True)
cols = 4; rows = math.ceil(len(sc) / cols)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-pattern_type", "glob", "-i", f"{W}/qc/[0-9]*.png",
                "-vf", f"scale=640:-1,tile={cols}x{rows}:padding=8:color=white", "-frames:v", "1", f"{W}/qc/sheet.png"], check=True)
print(f"{len(sc)} stills in {W}/qc, sheet at {W}/qc/sheet.png")
