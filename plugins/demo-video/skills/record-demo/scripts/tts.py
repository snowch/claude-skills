# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["mlx-audio", "soundfile", "numpy", "misaki[en]", "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"]
# ///
"""Narrate every scene with Kokoro-82M, locally on Apple Silicon (MLX).

Usage: tts.py WORKDIR [voice] [speed]       e.g. tts.py demo af_heart 1.0

Speaks each scene's "say" (or its "text" when there is no "say") from WORKDIR/scenes.json.
Writes WORKDIR/audio/<id>.wav (24 kHz mono) and WORKDIR/audio/durations.json, which record.py uses
to make each scene last as long as its narration.

Pronunciation: spell things for speech in "say" ("Jason" for JSON, "S D K"), or give exact phonemes
inline with Kokoro's markup: [Croissant](/kɹwɑːsˈɒnt/). Check with phonemes.py, then asr.py.
"""
import json, os, sys
import numpy as np, soundfile as sf
from mlx_audio.tts.utils import load_model

if len(sys.argv) < 2: sys.exit(__doc__)
W = os.path.abspath(sys.argv[1])
voice = sys.argv[2] if len(sys.argv) > 2 else "af_heart"
speed = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
only = set(os.environ.get("SCENES", "").split(",")) - {""}     # SCENES=intro,close redoes just those
os.makedirs(f"{W}/audio", exist_ok=True)
m = load_model("mlx-community/Kokoro-82M-bf16")
old = json.load(open(f"{W}/audio/durations.json"))["durations"] if only and os.path.exists(f"{W}/audio/durations.json") else {}
durs = {}
for s in json.load(open(f"{W}/scenes.json")):
    if only and s["id"] not in only and s["id"] in old: durs[s["id"]] = old[s["id"]]; continue
    parts = [np.array(r.audio) for r in m.generate(text=s.get("say", s["text"]), voice=voice, speed=speed, lang_code=voice[0])]
    a = np.concatenate(parts).astype(np.float32)
    sf.write(f"{W}/audio/{s['id']}.wav", a, 24000)
    durs[s["id"]] = round(len(a) / 24000, 3)
    print(f"{s['id']:14} {durs[s['id']]:6.2f}s")
json.dump({"voice": voice, "speed": speed, "durations": durs}, open(f"{W}/audio/durations.json", "w"), indent=1)
print("total", round(sum(durs.values()), 1), "s of narration")
