# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["mlx-audio; sys_platform == 'darwin' and platform_machine == 'arm64'", "kokoro-onnx==0.4.9; sys_platform != 'darwin' or platform_machine != 'arm64'", "soundfile", "numpy", "misaki[en]; sys_platform == 'darwin' and platform_machine == 'arm64'", "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl ; sys_platform == 'darwin' and platform_machine == 'arm64'"]
# ///
"""Narrate every scene with Kokoro-82M, locally on Apple Silicon (MLX) or Linux (ONNX CPU).

Usage: tts.py WORKDIR [voice] [speed]       e.g. tts.py demo af_heart 1.0

The defaults are Kokoro-82M, voice af_heart, speed 1.0 (MLX on Apple Silicon; ONNX CPU on Linux). It reads
clearly and naturally for product narration. Keep it unless the user asks for another voice, and use the same
voice and speed for every clip of a project (demo and deck alike), so spliced videos sound like one speaker.

Speaks each scene's "say" (or its "text" when there is no "say") from WORKDIR/scenes.json.
Writes WORKDIR/audio/<id>.wav (24 kHz mono) and WORKDIR/audio/durations.json, which record.py uses
to make each scene last as long as its narration.

Pronunciation: spell things for speech in "say" ("Jason" for JSON, "Tess" for TESS), or give exact phonemes
inline with Kokoro's markup: [Croissant](/kɹwɑːsˈɒnt/). Check with phonemes.py, then asr.py.

Pauses: Kokoro leaves only a short gap between sentences. "[pause]" in "say" inserts 0.5 s of silence there,
"[pause 1.2]" that many seconds, e.g. "They write over S3 or NFS. [pause 0.6] An element trigger reacts."
"""
import json, os, re, sys
import numpy as np, soundfile as sf
from speech_backend import SpeechBackend

if len(sys.argv) < 2: sys.exit(__doc__)
W = os.path.abspath(sys.argv[1])
voice = sys.argv[2] if len(sys.argv) > 2 else "af_heart"
speed = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
only = set(os.environ.get("SCENES", "").split(",")) - {""}     # SCENES=intro,close redoes just those
PAUSE = re.compile(r"\[pause(?:\s+(\d*\.?\d+))?\]")
os.makedirs(f"{W}/audio", exist_ok=True)
m = SpeechBackend(voice[0])
old = json.load(open(f"{W}/audio/durations.json"))["durations"] if only and os.path.exists(f"{W}/audio/durations.json") else {}
durs = {}
for s in json.load(open(f"{W}/scenes.json")):
    if only and s["id"] not in only and s["id"] in old: durs[s["id"]] = old[s["id"]]; continue
    parts = []
    for i, chunk in enumerate(PAUSE.split(s.get("say", s["text"]))):
        if i % 2:   # a pause marker's length (empty: the default)
            parts.append(np.zeros(int(float(chunk or 0.5) * 24000), dtype=np.float32))
        elif chunk.strip():
            parts.append(m.audio(chunk.strip(), voice, speed))
    a = np.concatenate(parts).astype(np.float32) if parts else np.zeros(2400, dtype=np.float32)
    if not np.isfinite(a).all() or np.max(np.abs(a)) >= 1: raise ValueError("Invalid or clipping speech")
    sf.write(f"{W}/audio/{s['id']}.wav", a, 24000)
    durs[s["id"]] = round(len(a) / 24000, 3)
    print(f"{s['id']:14} {durs[s['id']]:6.2f}s")
json.dump({"voice": voice, "speed": speed, "engine": m.provenance, "durations": durs}, open(f"{W}/audio/durations.json", "w"), indent=1)
print("total", round(sum(durs.values()), 1), "s of narration")
