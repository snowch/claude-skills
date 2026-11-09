# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["faster-whisper", "soundfile", "numpy"]
# ///
"""Transcribe each narration clip with a local Whisper model and compare it with the script.

Usage: asr.py WORKDIR [model]        model defaults to "small"

Prints each scene whose transcript differs noticeably from what was meant to be said, with both texts.
Whisper normalises acronyms and spellings, so it cannot tell "J S O N" from "Jason": check those with
phonemes.py. It does catch mumbled, swallowed or misheard words ("red" for "read", "Cross-Aunt").
"""
import difflib, glob, json, os, re, sys
import numpy as np, soundfile as sf
from faster_whisper import WhisperModel

if len(sys.argv) < 2: sys.exit(__doc__)
W = os.path.abspath(sys.argv[1])
m = WhisperModel(sys.argv[2] if len(sys.argv) > 2 else "small", device="cpu", compute_type="int8")
norm = lambda s: re.sub(r"\s+", " ", re.sub(r"\[([^\]]+)\]\(/[^)]*/\)", r"\1", s).lower())
words = lambda s: re.sub(r"[^a-z0-9 ]", " ", norm(s)).split()
flagged = 0
for s in json.load(open(f"{W}/scenes.json")):
    f = f"{W}/audio/{s['id']}.wav"
    if not os.path.exists(f): print("!!", s["id"], "no audio: run tts.py"); flagged += 1; continue
    a, sr = sf.read(f, dtype="float32"); t = np.arange(0, len(a) / sr, 1 / 16000)
    # Fed as an array: faster-whisper's own decoder trips over some PyAV versions.
    segs, _ = m.transcribe(np.interp(t, np.arange(len(a)) / sr, a).astype(np.float32), language="en", beam_size=5)
    heard = " ".join(x.text.strip() for x in segs)
    r = difflib.SequenceMatcher(None, words(s["text"]), words(heard)).ratio()
    mark = "  " if r >= 0.9 else "!!"; flagged += r < 0.9
    print(f"{mark} {s['id']:14} {r:.2f}  {heard}")
    if r < 0.9: print(f"   {'script':14}       {s['text']}")
print(f"{flagged} scene(s) to listen to" if flagged else "all scenes match the script")
