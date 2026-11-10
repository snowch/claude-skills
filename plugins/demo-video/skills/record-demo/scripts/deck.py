# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "soundfile"]
# ///
"""Turn slide images and their narration into a narrated deck walkthrough.

Usage: deck.py WORKDIR NAME "Title"        e.g. deck.py deck acme-webinar "Acme webinar"

Reads WORKDIR/scenes.json (one scene per narrated slide, in playing order), WORKDIR/audio/ from tts.py, and
the slides from WORKDIR/slides/: PNGs with the slide number in the name (s-01.png, Slide3.png …), or, if there
are none, WORKDIR/slides/deck.pdf, rendered to 3840×2160 PNGs with poppler's pdftoppm. Each scene names its
slide with "slide": 7, or by the number in its id ("s07"). Slides with no scene are left out.

Optional per scene: "part": "part1" splits the walkthrough into separate videos (for example either side of
a demo that gets spliced in), and "hold": 2.0 holds that slide longer after its narration (default 1.0 s).
Every slide appears 0.5 s before its narration, so each boundary is a clean cut point.

Writes, in WORKDIR/out/, for each part (NAME-<part>, or just NAME without parts) and, with several parts,
NAME-full (all of them back to back):
  …-4k-narrated.mp4   H.264 30 fps + AAC narration (-16 LUFS, as build.py) + soft English captions
  …-4k-silent.mp4     the same picture, video stream only
  ….srt
and NAME-shot-list.md, with WORKDIR/shotlist-notes.md (if present) before the tables.
"""
import glob, json, os, re, subprocess, sys
import numpy as np, soundfile as sf

if len(sys.argv) < 4: sys.exit(__doc__)
W, NAME, TITLE = os.path.abspath(sys.argv[1]), sys.argv[2], sys.argv[3]
OUT, SL = f"{W}/out", f"{W}/slides"; os.makedirs(OUT, exist_ok=True)
LEAD, HOLD, SR = 0.5, 1.0, 24000
num = lambda p: int(re.findall(r"\d+", os.path.basename(p))[-1])


def slides():
    pngs = [p for p in glob.glob(f"{SL}/*.png") if re.search(r"\d", os.path.basename(p))]
    if not pngs and os.path.exists(f"{SL}/deck.pdf"):
        print("rendering slides/deck.pdf at 3840×2160 …")
        subprocess.run(["pdftoppm", "-png", "-scale-to-x", "3840", "-scale-to-y", "2160", f"{SL}/deck.pdf", f"{SL}/s"], check=True)
        pngs = glob.glob(f"{SL}/s-*.png")
    if not pngs: sys.exit(f"no slides: put numbered PNGs or deck.pdf in {SL}")
    return {num(p): p for p in pngs}


img = slides()
scenes = json.load(open(f"{W}/scenes.json")); durs = json.load(open(f"{W}/audio/durations.json"))["durations"]
for s in scenes:
    s["_slide"] = int(s.get("slide") or num(s["id"]))
    if s["_slide"] not in img: sys.exit(f"scene {s['id']}: no image for slide {s['_slide']} in {SL}")
    if s["id"] not in durs: sys.exit(f"scene {s['id']}: no narration, run tts.py")
w, h = map(int, subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                "-of", "csv=p=0", img[scenes[0]["_slide"]]], capture_output=True, text=True).stdout.split(","))
if w < 3840: print(f"warning: slides are {w}×{h}, so the video is upscaled. Export them at 3840×2160 for sharp text.")

parts = {}
for s in scenes: parts.setdefault(s.get("part"), []).append(s)
runs = {NAME: scenes} if list(parts) == [None] else {**{f"{NAME}-{p}": v for p, v in parts.items()}, f"{NAME}-full": scenes}
tc = lambda x: f"{int(x // 60)}:{x % 60:04.1f}"
srt_t = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(x * 1000 % 1000):03d}"
fit = "scale=3840:2160:force_original_aspect_ratio=decrease,pad=3840:2160:(ow-iw)/2:(oh-ih)/2:white,fps=30,format=yuv420p"
tables = []
for name, items in runs.items():
    t, cuts, srt = 0.0, [], []
    lengths = [LEAD + durs[s["id"]] + float(s.get("hold", HOLD)) for s in items]
    track = np.zeros(int(sum(lengths) * SR) + SR, dtype=np.float32)
    with open(f"{OUT}/{name}.txt", "w") as lst:
        for n, (s, length) in enumerate(zip(items, lengths), 1):
            a, sr = sf.read(f"{W}/audio/{s['id']}.wav", dtype="float32")
            o = int((t + LEAD) * SR); track[o:o + len(a)] += a
            lst.write(f"file '{img[s['_slide']]}'\nduration {length:.3f}\n")
            srt.append(f"{n}\n{srt_t(t + LEAD)} --> {srt_t(t + LEAD + durs[s['id']])}\n{s['text']}\n")
            cuts.append((s, t, t + length)); t += length
        lst.write(f"file '{img[items[-1]['_slide']]}'\n")   # concat needs the last file twice to honour its duration
    track = track[: int(t * SR)]; track *= 0.89 / max(np.abs(track).max(), 1e-9)
    sf.write(f"{OUT}/{name}.wav", track, SR); open(f"{OUT}/{name}.srt", "w").write("\n".join(srt))
    narr, silent = f"{OUT}/{name}-4k-narrated.mp4", f"{OUT}/{name}-4k-silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{OUT}/{name}.txt",
                    "-i", f"{OUT}/{name}.wav", "-i", f"{OUT}/{name}.srt", "-map", "0:v", "-map", "1:a", "-map", "2:s",
                    "-vf", fit, "-c:v", "libx264", "-preset", os.environ.get("DEMO_FFMPEG_PRESET", "slow"), "-threads", os.environ.get("DEMO_FFMPEG_THREADS", "4"), "-crf", "18", "-tune", "stillimage",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "160k",
                    "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-movflags", "+faststart", "-t", f"{t:.3f}", narr], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", narr, "-map", "0:v", "-c", "copy", "-movflags", "+faststart", silent], check=True)
    os.remove(f"{OUT}/{name}.txt"); os.remove(f"{OUT}/{name}.wav")
    print(f"{name:24} {tc(t):>7}  {os.path.getsize(narr) / 1e6:6.1f} MB")
    if not name.endswith("-full") or len(runs) == 1:
        tables += [f"## {name} ({tc(t)})", "", "| Slide | Time | Narration |", "|---|---|---|"]
        tables += [f"| {s['_slide']} | {tc(a)} – {tc(b)} | {s['text']} |" for s, a, b in cuts] + [""]

notes = open(f"{W}/shotlist-notes.md").read().strip() + "\n\n" if os.path.exists(f"{W}/shotlist-notes.md") else ""
md = (f"# {TITLE}: narrated deck walkthrough, shot list\n\n"
      f"Each slide appears {LEAD} s before its narration and holds after it, so every boundary is a clean cut point. "
      "3840×2160, 30 fps, narration at -16 LUFS (the same as the demo video). Each video comes narrated, with soft "
      "English captions, and silent.\n\n" + notes + "\n".join(tables))
open(f"{OUT}/{NAME}-shot-list.md", "w").write(md.rstrip() + "\n"); print(f"{OUT}/{NAME}-shot-list.md")
