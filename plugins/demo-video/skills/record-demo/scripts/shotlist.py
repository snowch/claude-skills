# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Write the editor's timecoded shot list.

Usage: shotlist.py WORKDIR NAME "Title"

Reads timeline.json and scenes.json (each scene's "step" and "text"). If WORKDIR/shotlist-notes.md
exists, its content goes before the table (what is on screen, what is not in the demo) and
WORKDIR/shotlist-facts.md, if present, after it (figures on screen, for the talk track).
Writes WORKDIR/out/NAME-shot-list.md.
"""
import json, os, sys

if len(sys.argv) < 4: sys.exit(__doc__)
W, NAME, TITLE = os.path.abspath(sys.argv[1]), sys.argv[2], sys.argv[3]
t = json.load(open(f"{W}/timeline.json")); sc = t["scenes"]; S = {s["id"]: s for s in json.load(open(f"{W}/scenes.json"))}
end = t["end"] - t["start"]
tc = lambda x: f"{int(x // 60)}:{x % 60:04.1f}"
read = lambda f: open(f"{W}/{f}").read().strip() + "\n\n" if os.path.exists(f"{W}/{f}") else ""
rows = []
for i, s in enumerate(sc):
    a = s["t"] - t["start"]; b = (sc[i + 1]["t"] - t["start"]) if i + 1 < len(sc) else end
    rows.append(f"| {i + 1} | {tc(a)} – {tc(b)} | {S[s['id']].get('step', s['id'])} | {S[s['id']]['text']} |")
md = f"""# {TITLE}: shot list

Silent master: `{NAME}-4k-silent.mp4` (3840×2160, 30 fps, {tc(end)}). The narrated reference copy `{NAME}-4k-narrated.mp4` has the same picture and timing, with soft captions.

Recorded in one continuous automated take.
- **Pointer:** a standard arrow. It rests just beside whatever is being discussed and moves in one smooth path. Nothing is added on click.
- **Scrolling:** steady, at a fixed speed.
- **Holds:** every step ends with a still hold, so each boundary below is a clean cut point.

{read("shotlist-notes.md")}| # | Time | Step | Reference narration (what is happening, and why it matters) |
|---|---|---|---|
""" + "\n".join(rows) + "\n\n" + read("shotlist-facts.md")
os.makedirs(f"{W}/out", exist_ok=True)
open(f"{W}/out/{NAME}-shot-list.md", "w").write(md.rstrip() + "\n"); print(f"{W}/out/{NAME}-shot-list.md")
