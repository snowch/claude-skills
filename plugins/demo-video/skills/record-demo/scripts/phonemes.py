# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["mlx-audio", "misaki[en]", "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"]
# ///
"""Show how Kokoro will pronounce the narration, before listening to it.

Usage: phonemes.py WORKDIR [scene_id ...] [--all]

By default prints only the words most likely to go wrong: names, acronyms, numbers, mixed case and
words with digits or punctuation inside. --all prints every word. Fix a bad one in the scene's "say"
by respelling it ("Jason", "S D K", "Tess") or with exact phonemes: [Croissant](/kɹwɑːsˈɒnt/).
"""
import json, os, re, sys
from mlx_audio.tts.utils import load_model

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args: sys.exit(__doc__)
W, ids, every = os.path.abspath(args[0]), set(args[1:]), "--all" in sys.argv
p = load_model("mlx-community/Kokoro-82M-bf16")._get_pipeline("a")
risky = re.compile(r"[A-Z].*[A-Z]|\d|[a-z][A-Z]|^[A-Z]|[-_./]")
for s in json.load(open(f"{W}/scenes.json")):
    if ids and s["id"] not in ids: continue
    toks = [t for t in p.g2p(s.get("say", s["text"]))[1] if t.phonemes and re.search(r"\w", t.text)]
    show = [f"{t.text} /{t.phonemes}/" for t in toks if every or risky.search(t.text)]
    if show: print(f"[{s['id']}]  " + "   ".join(show))
