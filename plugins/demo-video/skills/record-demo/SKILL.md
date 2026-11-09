---
name: record-demo
description: Record a narrated product demo video of a web app, scripted with Playwright, as a clean 4K "golden take" with a local TTS voice. Delivers a silent 4K master for an editor, a narrated reference copy with captions, and a timecoded shot list. Use when someone wants a demo video, screen recording, walkthrough or product tour of a web app, wants it narrated or voiced, wants footage for marketing or a launch video, or wants to re-record an existing demo after the app changed.
---

# Record a demo video

The result is one continuous, automated take of the real app. It's scripted, so it can be re-recorded any time the app changes, and every take is identical apart from the change. Narration comes from Kokoro-82M, running locally.

**Deliverables**, all in `WORKDIR/out/`:
1. `NAME-4k-silent.mp4`: the master, 3840×2160 at 30 fps, picture only. An editor cuts this and adds their own voice-over.
2. `NAME-4k-narrated.mp4`: the same picture with the narration and soft English captions. It's the reference for the talk track.
3. `NAME-shot-list.md`: every step with its timecode, what's on screen, and the narration.

**Requirements:** macOS on Apple Silicon (the TTS uses MLX), `uv`, `ffmpeg`, and Google Chrome (otherwise it falls back to Playwright's Chromium). Every script declares its own dependencies, so `uv run scripts/X.py` is all you need. The first TTS run downloads Kokoro (about 330 MB) and spaCy's small English model. The first Whisper run downloads `small` (about 460 MB). After that, set `HF_HUB_OFFLINE=1` to work offline. For a first Playwright run, use `uv run --with playwright playwright install chromium` if Chrome isn't installed.

`scripts/` below means this skill's `scripts/` folder. The working directory holds one demo, and it lives in the user's project (for example `demo/`) or in the scratchpad, never in this skill.

## Workflow

### 1. Scout the app, before writing anything
- Open each view the tour will use, and take screenshots (1280×720). Note stable selectors (ids, `data-*` attributes, visible text), anything slow to load, sticky headers (their height becomes `CONFIG["header"]`), and modal dialogs.
- **List everything sensitive that could appear:** IPs, internal hostnames, account and user names, model or service names, emails, tokens, file-system paths, cluster or bucket lists, customer names. Each one becomes a `scrub` rule (rewritten on the page while recording) and part of the `leak` regex (which fails the take if it ever shows). Panels that are mostly paths or lists stay closed; don't scrub them into nonsense.
- Choose demo data whose numbers tell the story, for example a "before" state that's clearly bad and an "after" that's clearly better. Check the numbers you'll quote.
- **Keep the tour read-only.** Never click anything that saves, publishes, sends or deletes on a shared or live system. Point beside the button instead, and say what it would do.

### 2. Write the talk track, then get it approved
Copy `templates/scenes.json` and write one scene per step:
- `id`: short and unique.
- `step`: the shot-list label.
- `text`: what is happening **and why it matters**. This is also the caption.
- `say` (optional): the same line spelled for speech.

Rules:
- Lead with the benefit. Take the positioning, product names and figures from the user's deck, blog or README. Never name or compare against alternatives unless the user asks.
- Only claim what the app actually does. Check the code when unsure. If something is designed but not built, say so on screen and in the narration.
- Show the user the talk track (`id`, `step` and `text` for every scene) and get a yes before recording. Wording changes after a take mean another take.

### 3. Make the narration and check every word of it
```bash
uv run scripts/tts.py WORKDIR af_heart 1.0
uv run scripts/phonemes.py WORKDIR
uv run scripts/asr.py WORKDIR
```
- **tts.py** writes `audio/<id>.wav` and `audio/durations.json`. To redo just some scenes: `SCENES=intro,close uv run scripts/tts.py WORKDIR`.
- **phonemes.py** prints how names, acronyms and numbers will sound (`--all` prints every word). Whisper can't hear these differences, so read the output. Fix problems in `say`:
  - Leave plain capitals as they are: Kokoro reads `API`, `SDK`, `HTTP` and `NFS` as letters, with natural stress. Don't space them out. `A P I` turned the last letter into the pronoun "I" and came out as "AP, I".
  - Respell words that should be said as a word: `Jason` for JSON, `Tess` for TESS. Mixed forms need help too: `R O Crate`.
  - Write numbers as words when they're read out: "forty-four", "twenty thousand and seventy-six".
  - Split compounds the model runs together: "Data Engine", "Data Base".
  - Or give exact phonemes: `[Croissant](/kɹwɑːsˈɒnt/)`, `[AI](/ˌAˈI/)`.
  - Commas add short pauses, and rewording beats fighting a word ("can load directly" instead of "read directly", which came out as "red").
- **asr.py** transcribes each clip with Whisper and flags any scene that doesn't match the script (`!!`). Fix those and re-run.
- Voices: `af_heart` (US, warm) is the default. Others to try include `af_bella`, `am_michael`, `bf_emma` and `bm_george`.

### 4. Script the tour
Copy `templates/tour.py` to `WORKDIR/tour.py`. It defines `CONFIG` and `async def tour(r)`, which calls `r.start()` once the first view is ready and then runs one `async with r.scene("id"):` block per scene, in the same order as `scenes.json`. The Recorder (`scripts/record.py`) gives you:

| Call | What it does |
|---|---|
| `r.pg` | The Playwright page, for locators and `wait_for_selector`. |
| `r.goto(path, wait_for=sel)`, `r.warm([(path, sel), …])` | Load views. Warm every view once before `r.start()`, so nothing is slow on camera. |
| `r.start()` | Starts the take. Everything before it is cut, and it aborts unless frames are exactly 3840×2160. |
| `r.scene(id)` | Runs the actions inside, then waits out that scene's narration plus `hold` seconds, so picture and voice stay in sync. |
| `r.point(loc, side="right")` | Glides the pointer to rest just beside the element's text, never on top of it. |
| `r.click(loc, after=0.5)`, `r.type_in(loc, text)`, `r.select(loc, value)` | Each glides there first. Typing goes in one go, at a steady speed. |
| `r.scroll_to(loc, frac)`, `r.scroll_y(y)` | Steady, eased scrolling of the page, or of the panel or dialog that holds the element. |
| `r.hold(s)`, `r.blur()` | A still pause; drop a focus ring (for example on a dialog's Close button). |

Pacing: within a scene, point at what the narration is talking about, roughly when it says it. Pause between points with `r.hold(…)` so the pointer is still while each thing is mentioned. If a scene's actions take longer than its narration, the recorder says by how much. Trim the actions or lengthen the line.

### 5. Record
```bash
uv run scripts/record.py WORKDIR BASE_URL
```
- It prints `PROBLEMS` (elements not found, or scrolled off screen), the frame size, and any leaks. It exits non-zero on a run of wrong-size frames or a leak. Fix the cause and record again; never ship a take with a leak.
- A 5-minute tour takes about 5 minutes to record. Run it in the background.

### 6. Build, then look at it
```bash
uv run scripts/build.py WORKDIR NAME
uv run scripts/contact_sheet.py WORKDIR WORKDIR/out/NAME-4k-narrated.mp4
uv run scripts/shotlist.py WORKDIR NAME "Title"
```
- Look at `qc/sheet.png`, plus any `qc/NN-<scene>.png` worth a closer look. Check each one: the pointer is beside its target; nothing is cut off; the app is in the theme the user wanted; text wraps cleanly; and **nothing sensitive is visible**, including in screenshots of URLs, code samples and citations.
- For the shot list, put notes in `WORKDIR/shotlist-notes.md` (what's on screen, what's not built, what stays closed and why) and `WORKDIR/shotlist-facts.md` (the figures on screen, for the talk track). Both are optional.

### 7. Deliver
Send the three files in `out/` with a short note: the length, what changed since the last take, and anything the editor must keep, such as "not built in this demo" qualifiers.

## The recording checklist (from a marketing team's brief)
- The talk track says what is happening and why it matters, at every step.
- A standard mouse arrow only: no custom cursor, click rings or highlights. It rests beside the target, not on it, and moves in one smooth path with no back and forth.
- Steady scrolling at a pace a viewer can follow.
- Text is typed in one go, using "demo" or non-personal names.
- Never show IPs, configs, credentials, or file-system and cluster lists.
- On-brand colours, and the app's own theme (light mode usually looks best on video).
- One clean golden take, with no slips or retries.

## Why it's built this way (don't undo these)
- **CDP screencast at device scale factor 3** gives real 4K text, rather than an upscale, from a 1280×720 layout that reads well at any size.
- **The window is resized to the viewport size plus 121 px.** The screencast sometimes captures the real window, which loses about 121 px to Chrome's top bar, and the bottom of every frame went missing. Every frame's size is checked, and the build refuses frames of the wrong size rather than stretching them.
- **Frames arrive only when the screen changes.** The build holds each one until the next, pads the end, and cuts at the true duration, so the video doesn't end early.
- **A stray wrong-size frame is replaced at once.** Chrome sometimes emits one or two slightly smaller frames when the page changes. The recorder forces an invisible repaint so a full-size frame follows within about 0.05 s, and the build drops the stray frames. A longer wrong-size run fails the take. `r.start()` also waits until the capture has been steady at full size, because on macOS the window resize animates for a moment.
- **The pointer is drawn into the page,** because headless Chrome has none. It moves into an open `<dialog>`, because a modal draws above everything else.
- **A custom eased scroll,** because the browser's smooth scrolling gets interrupted and jumps.
- **Each scene waits for its narration,** so the silent master already has the narration's timing, with a still hold at every cut point.
- **Whisper is fed arrays, not files,** because faster-whisper's own decoder breaks with some PyAV versions.
