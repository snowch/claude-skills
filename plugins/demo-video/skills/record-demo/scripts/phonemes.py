# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["mlx-audio; sys_platform == 'darwin' and platform_machine == 'arm64'", "kokoro-onnx==0.4.9; sys_platform != 'darwin' or platform_machine != 'arm64'", "misaki[en]; sys_platform == 'darwin' and platform_machine == 'arm64'", "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl ; sys_platform == 'darwin' and platform_machine == 'arm64'"]
# ///
"""Show how Kokoro will pronounce the narration, before listening to it.

Usage: phonemes.py WORKDIR [scene_id ...] [--all]

By default prints only the words most likely to go wrong: names, acronyms, numbers, mixed case and
words with digits or punctuation inside. --all prints every word. Fix a bad one in the scene's "say"
by respelling it ("Jason", "S D K", "Tess") or with exact phonemes: [Croissant](/kɹwɑːsˈɒnt/).
"""
import json, os, re, sys
from speech_backend import SpeechBackend

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args: sys.exit(__doc__)
W, ids, every = os.path.abspath(args[0]), set(args[1:]), "--all" in sys.argv
p = SpeechBackend()
risky = re.compile(r"[A-Z].*[A-Z]|\d|[a-z][A-Z]|^[A-Z]|[-_./]")
for s in json.load(open(f"{W}/scenes.json")):
    if ids and s["id"] not in ids: continue
    say = re.sub(r"\[pause[^\]]*\]", " ", s.get("say", s["text"]))   # pauses are silence, not words
    toks = p.phonemes(say)
    show = [f"{text} /{phonemes}/" for text, phonemes in toks if every or risky.search(text)]
    if show: print(f"[{s['id']}]  " + "   ".join(show))
