# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["faster-whisper", "soundfile", "numpy"]
# ///
"""Check every narration clip: the words (with a local Whisper model), the pacing and the sound.

Usage: asr.py WORKDIR [model]        model defaults to "small" (run on the CPU, 8-bit)

Works on any WORKDIR with scenes.json and audio/<id>.wav, so a deck's narration is checked the same way
as a demo's. For each scene it prints the similarity to the script, the speaking rate and the transcript,
and marks with !! anything worth listening to:

  words    under 90% similar to both the scene's "text" and its spoken "say" (mumbled, swallowed or misheard
           words: "red" for "read", "Cross-Aunt" for Croissant). Whisper normalises acronyms and spellings, so
           it can't tell "J S O N" from "Jason": check those with phonemes.py.
  pace     outside 120-190 spoken words a minute, not counting [pause] markers (af_heart at 1.0 runs about
           140-185). Lines under 10 words, such as a slide title, are skipped.
  clip     a peak at or near full scale, which distorts
  level    speech more than 3 dB louder or quieter than the median clip, which shows when clips are spliced
  gap      a silence inside the clip longer than 1.5 s, or than its longest [pause] marker plus 1.0 s

Read the transcripts too, even for scenes that pass: a score of 0.92 can still hide a slurred phrase
("nothing cop it out"), and Whisper sometimes invents a "Thank you." in a clip's trailing silence.
None of this replaces listening once, start to finish: whether a name is said the way its community says it
(F-UJI as "Fuji"), and whether the tone is right, only a person can tell.
"""
import difflib, json, os, re, sys
import numpy as np, soundfile as sf
from faster_whisper import WhisperModel

if len(sys.argv) < 2: sys.exit(__doc__)
W = os.path.abspath(sys.argv[1])
m = WhisperModel(sys.argv[2] if len(sys.argv) > 2 else "small", device="cpu", compute_type="int8")
PAUSE = re.compile(r"\[pause(?:\s+(\d*\.?\d+))?\]")
norm = lambda s: re.sub(r"\s+", " ", re.sub(r"\[([^\]]+)\]\(/[^)]*/\)", r"\1", PAUSE.sub(" ", s)).lower())
words = lambda s: re.sub(r"[^a-z0-9 ]", " ", norm(s)).split()
# Whisper writes a spoken "github dot com slash acme dash tools" as "github.com/acme-tools": say the symbols back.
spoken = lambda s: words(re.sub(r"(?<=\w)([./-])(?=\w)", lambda m: {".": " dot ", "/": " slash ", "-": " dash "}[m[1]], s))
similar = lambda a, b: difflib.SequenceMatcher(None, a, b).ratio()
db = lambda x: 20 * np.log10(max(float(x), 1e-9))


def speech(a, sr):
    """RMS level of the voiced 20 ms frames, and the longest silence between the first and last of them."""
    n = int(sr * 0.02); f = a[: len(a) // n * n].reshape(-1, n)
    rms = np.sqrt((f ** 2).mean(axis=1)); voiced = rms > 10 ** (-40 / 20) * max(np.abs(a).max(), 1e-9)
    if not voiced.any(): return -120.0, 0.0
    idx = np.flatnonzero(voiced); gaps = np.diff(idx) - 1
    return db(np.sqrt((rms[voiced] ** 2).mean())), float(gaps.max() * 0.02 if len(gaps) else 0.0)


rows, flagged = [], 0
for s in json.load(open(f"{W}/scenes.json")):
    f = f"{W}/audio/{s['id']}.wav"
    if not os.path.exists(f): print("!!", s["id"], "no audio: run tts.py"); flagged += 1; continue
    a, sr = sf.read(f, dtype="float32"); t = np.arange(0, len(a) / sr, 1 / 16000)
    # Fed as an array: faster-whisper's own decoder trips over some PyAV versions.
    segs, _ = m.transcribe(np.interp(t, np.arange(len(a)) / sr, a).astype(np.float32), language="en", beam_size=5)
    heard = " ".join(x.text.strip() for x in segs)
    say = s.get("say", s["text"]); pauses = [float(p or 0.5) for p in PAUSE.findall(say)]
    level, gap = speech(a, sr)
    said = words(say)   # the words actually spoken, after respelling ("C S V", "github dot com")
    rows.append(dict(id=s["id"], text=s["text"], heard=heard, level=level, gap=gap, peak=float(np.abs(a).max()),
                     # Best of the caption and the spoken line, so a respelt URL or acronym isn't a false alarm.
                     ratio=max(similar(words(s["text"]), words(heard)), similar(said, spoken(heard))),
                     wpm=len(said) / max(len(a) / sr - sum(pauses), 0.1) * 60, short=len(said) < 10,
                     # Kokoro pads each side of a [pause] with its own sentence-end silence.
                     gap_ok=max(1.5, max(pauses, default=0) + 1.0)))

median = float(np.median([r["level"] for r in rows])) if rows else 0.0
for r in rows:
    why = [w for w, bad in (("words", r["ratio"] < 0.9), ("pace", not r["short"] and not 120 <= r["wpm"] <= 190),
                            ("clip", r["peak"] >= 0.99), ("level", abs(r["level"] - median) > 3),
                            ("gap", r["gap"] > r["gap_ok"])) if bad]
    flagged += bool(why)
    print(f"{'!!' if why else '  '} {r['id']:14} {r['ratio']:.2f}  {r['wpm']:3.0f} wpm  {r['heard']}")
    if why:
        print(f"   {'':14} {', '.join(why)}: level {r['level'] - median:+.1f} dB, peak {db(r['peak']):.1f} dBFS, "
              f"longest gap {r['gap']:.1f} s")
        if "words" in why: print(f"   {'script':14} {r['text']}")
print(f"{flagged} scene(s) to listen to" if flagged else "all scenes match the script")

json.dump({"method":"independent Whisper screening; not listening approval", "model":sys.argv[2] if len(sys.argv)>2 else "small", "flagged":flagged, "scenes":rows}, open(f"{W}/audio/asr-report.json", "w"), indent=2)
