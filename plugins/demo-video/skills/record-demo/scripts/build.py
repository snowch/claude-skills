# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "soundfile"]
# ///
"""Turn the recorded frames and the narration into the deliverables.

Usage: build.py WORKDIR NAME         e.g. build.py demo acme-demo-tour

Writes, in WORKDIR/out/:
  NAME-4k-narrated.mp4   H.264 30 fps + AAC narration (-16 LUFS) + soft English captions (reference copy)
  NAME-4k-silent.mp4     the same picture, video stream only (the master an editor cuts from)
  captions.srt, narration.wav
"""
import json, os, subprocess, sys
import numpy as np, soundfile as sf

if len(sys.argv) < 3: sys.exit(__doc__)
W, NAME = os.path.abspath(sys.argv[1]), sys.argv[2]
os.makedirs(f"{W}/out", exist_ok=True)
tl = json.load(open(f"{W}/timeline.json"))
scenes = {s["id"]: s for s in json.load(open(f"{W}/scenes.json"))}
durs = json.load(open(f"{W}/audio/durations.json"))["durations"]
t0, end = tl["start"], tl["end"] - tl["start"]
# Frames only arrive when the screen changes: open on the last frame captured before the start, held from 0.
bad = set(tl.get("bad", []))     # a blink of wrong-size frames: hold the frame before instead
fr = [(i, t - t0) for i, t in enumerate(tl["frames"]) if t >= t0 and i not in bad]
before = [i for i, t in enumerate(tl["frames"]) if t < t0]
if before: fr.insert(0, (before[-1], 0.0))
want = ",".join(map(str, tl.get("size", [3840, 2160])))
size = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", f"{W}/frames/{fr[0][0]:05d}.jpg"],
                      capture_output=True, text=True).stdout.strip()
if size != want: sys.exit(f"frames are {size}, not {want}: re-record rather than stretch them")

# Video: each frame holds until the next one arrives.
with open(f"{W}/frames/list.txt", "w") as f:
    for k, (i, t) in enumerate(fr):
        nxt = fr[k + 1][1] if k + 1 < len(fr) else end
        f.write(f"file '{i:05d}.jpg'\nduration {max(nxt - max(t, 0), 0.001):.4f}\n")
    f.write(f"file '{fr[-1][0]:05d}.jpg'\n")

# Audio: each scene's narration starts with its scene. Captions use the written "text", not the spoken "say".
SR = 24000
track = np.zeros(int((end + 1) * SR), dtype=np.float32)
ts = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(x * 1000 % 1000):03d}"
srt = []
for n, s in enumerate(tl["scenes"], 1):
    a, _ = sf.read(f"{W}/audio/{s['id']}.wav", dtype="float32")
    o = int((s["t"] - t0) * SR); track[o:o + len(a)] += a[: len(track) - o]
    st = s["t"] - t0
    srt.append(f"{n}\n{ts(st)} --> {ts(st + durs[s['id']])}\n{scenes[s['id']]['text']}\n")
peak = np.abs(track).max(); track *= 0.89 / peak if peak else 1
sf.write(f"{W}/out/narration.wav", track, SR)
open(f"{W}/out/captions.srt", "w").write("\n".join(srt))

narr, silent = f"{W}/out/{NAME}-4k-narrated.mp4", f"{W}/out/{NAME}-4k-silent.mp4"
# tpad + -t: the last frame holds to the true end instead of the video stopping early.
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{W}/frames/list.txt",
                "-i", f"{W}/out/narration.wav", "-i", f"{W}/out/captions.srt",
                "-map", "0:v", "-map", "1:a", "-map", "2:s",
                "-vf", "fps=30,tpad=stop_mode=clone:stop_duration=6,format=yuv420p", "-c:v", "libx264", "-preset", os.environ.get("DEMO_FFMPEG_PRESET", "slow"), "-threads", os.environ.get("DEMO_FFMPEG_THREADS", "4"), "-crf", "18",
                "-tune", "stillimage", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "160k",
                "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-movflags", "+faststart", "-t", f"{end:.3f}", narr], check=True)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", narr, "-map", "0:v", "-c", "copy", "-movflags", "+faststart", silent], check=True)
for f in (narr, silent): print(f, f"{end:.1f}s", f"{os.path.getsize(f) / 1e6:.1f} MB")
