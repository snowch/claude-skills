# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright"]
# ///
"""Record a scripted browser tour as a clean 4K take (a 1280x720 page at 3x = 3840x2160).

Usage: record.py WORKDIR BASE_URL

WORKDIR holds scenes.json, audio/durations.json (written by tts.py) and tour.py, which defines

    CONFIG = {...}            # optional, see DEFAULTS below
    async def tour(r): ...    # r is a Recorder: drive the app scene by scene

Writes WORKDIR/frames/NNNNN.jpg and WORKDIR/timeline.json, which build.py turns into video.
Exits non-zero if any frame has the wrong size or anything matching CONFIG["leak"] was on screen.
"""
import asyncio, base64, contextlib, importlib.util, json, math, os, re, shutil, struct, sys, time, platform
from playwright.async_api import async_playwright

DEFAULTS = {
    "width": 1280, "height": 720, "dpr": 3,
    "header": 0,          # px of the page covered by a sticky top bar, so scrolling clears it
    "hold": 1.4,          # still pause at the end of every scene: a clean cut point for the editor
    "color_scheme": "light",
    "executable_path": os.environ.get("DEMO_CHROME_EXECUTABLE"),
    "channel": "chrome",  # installed Google Chrome; None uses Playwright's bundled Chromium
    "scrub": [],          # [[js_regex, replacement], ...] applied to every text node and href/title/value/placeholder
    "leak": None,         # Python regex: fail the take if it matches the visible page text at the end of any scene
    "init_js": "",        # extra JS run before every page load (e.g. "localStorage.setItem('theme','light')")
    "scroll_speed": 650,  # px per second for the eased scroll
}

PAGE = r"""
(() => {
  const rules = __RULES__.map(([p, t]) => [new RegExp(p, "g"), t]);
  const fix = s => rules.reduce((t, [re, to]) => t.replace(re, to), s);
  const walk = n => {
    if (n.nodeType === 3) { const t = fix(n.nodeValue); if (t !== n.nodeValue) n.nodeValue = t; return; }
    if (n.nodeType !== 1) return;
    for (const a of ["href", "title", "value", "placeholder"]) if (n.hasAttribute(a)) { const v = n.getAttribute(a), t = fix(v); if (t !== v) n.setAttribute(a, t); }
    n.childNodes.forEach(walk);
  };
  if (rules.length) new MutationObserver(ms => ms.forEach(m => m.type === "characterData" ? walk(m.target) : m.addedNodes.forEach(walk)))
    .observe(document, {subtree: true, childList: true, characterData: true});
  try { __INIT__ } catch (e) {}
  const ease = t => t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  const glide = (sc, d, pxPerSec, done) => {
    const y0 = sc.scrollTop; if (Math.abs(d) < 2) return done();
    const ms = Math.min(2600, Math.max(700, Math.abs(d) / pxPerSec * 1000)), t0 = performance.now();
    const step = now => { const t = Math.min(1, (now - t0) / ms); sc.scrollTop = y0 + d * ease(t); t < 1 ? requestAnimationFrame(step) : done(); };
    requestAnimationFrame(step);
  };
  window.__scrollTo = (y, pxPerSec) => new Promise(done => { const sc = document.scrollingElement;
    glide(sc, Math.max(0, Math.min(y, sc.scrollHeight - innerHeight)) - sc.scrollTop, pxPerSec, done); });
  // The nearest thing that scrolls: the page, or a panel or dialog with its own scrollbar.
  window.__scroller = e => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
      const o = getComputedStyle(p).overflowY; if (/(auto|scroll)/.test(o) && p.scrollHeight > p.clientHeight + 5) return p; }
    return document.scrollingElement; };
  window.__visible = (e, header) => { const sc = __scroller(e);
    if (sc === document.scrollingElement) return [header, innerHeight];
    const r = sc.getBoundingClientRect(); return [Math.max(r.top, 0), Math.min(r.bottom, innerHeight)]; };
  window.__scrollToEl = (e, frac, header, pxPerSec) => new Promise(done => {
    const sc = __scroller(e), [top, bottom] = __visible(e, header);
    const y1 = Math.max(0, Math.min(sc.scrollTop + e.getBoundingClientRect().top - top - (bottom - top) * frac, sc.scrollHeight - sc.clientHeight));
    glide(sc, y1 - sc.scrollTop, pxPerSec, done);
  });
  // Where the text actually ends inside an element (a block can be much wider than its words).
  window.__textBox = e => { const r = document.createRange(); r.selectNodeContents(e); const b = r.getBoundingClientRect();
    return b.width ? {x: b.left, y: b.top, w: b.width, h: b.height} : null; };
  // A headless browser draws no pointer: draw the standard arrow, nothing added on click.
  addEventListener("DOMContentLoaded", () => {
    const c = document.createElement("div"); c.id = "rec-pointer";
    c.innerHTML = '<svg width="19" height="28" viewBox="0 0 19 28"><path d="M1.5 1.5 V22.5 L6.6 17.6 L10.2 26 L13.7 24.5 L10.2 16.4 H17.2 Z" fill="#000" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';
    c.style.cssText = "position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;filter:drop-shadow(0 1px 1.5px rgba(0,0,0,.35))";
    const at = p => c.style.transform = `translate(${p[0] - 1.5}px,${p[1] - 1.5}px)`;
    at(window.__lastMouse || [-50, -50]); document.body.appendChild(c);
    addEventListener("mousemove", e => at([e.clientX, e.clientY]), true);
    // A modal dialog draws above everything else in the page, so the pointer moves into it while it is open.
    setInterval(() => { const host = document.querySelector("dialog[open]") || document.body; if (c.parentElement !== host) host.appendChild(c); }, 50);
  });
})();
"""


def jpeg_size(b):
    i = 2
    while i < len(b):
        if b[i] != 0xFF: i += 1; continue
        if b[i + 1] in (0xC0, 0xC2): h, w = struct.unpack(">HH", b[i + 5:i + 9]); return w, h
        i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]


class Recorder:
    def __init__(self, workdir, base, cfg, durs):
        self.dir, self.base, self.c, self.durs = workdir, base.rstrip("/"), cfg, durs
        self.W, self.H, self.DPR = cfg["width"], cfg["height"], cfg["dpr"]
        self.leak = re.compile(cfg["leak"]) if cfg["leak"] else None
        self.frames, self.timeline, self.leaks, self.problems, self.badsize = [], [], set(), [], []
        self.size, self.t_start, self.current = None, None, ""
        self.mouse = [self.W * 0.62, self.H * 0.55]

    # --- setup
    async def open(self, p):
        W, H, DPR = self.W, self.H, self.DPR
        args = [f"--window-size={W},{H + 200}", f"--force-device-scale-factor={DPR}"]
        executable = self.c["executable_path"]
        if not executable and platform.system() == "Linux": executable = shutil.which("chromium") or shutil.which("google-chrome")
        if executable: self.browser = await p.chromium.launch(executable_path=executable, args=args)
        else:
            try: self.browser = await p.chromium.launch(channel=self.c["channel"], args=args)
            except Exception: self.browser = await p.chromium.launch(args=args)
        self.ctx = await self.browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=DPR, color_scheme=self.c["color_scheme"])
        await self.ctx.add_init_script(PAGE.replace("__RULES__", json.dumps(self.c["scrub"])).replace("__INIT__", self.c["init_js"] or ";"))
        self.pg = await self.ctx.new_page()
        self.cdp = await self.ctx.new_cdp_session(self.pg)
        # The screencast sometimes captures the real window instead of the emulated page, and the real window loses
        # about 121px to the browser's own top bar: size the window so both are exactly W x H.
        try:
            if platform.system() != "Darwin": raise RuntimeError("No macOS window correction on Linux")
            win = await self.cdp.send("Browser.getWindowForTarget")
            await self.cdp.send("Browser.setWindowBounds", {"windowId": win["windowId"], "bounds": {"width": W, "height": H + 121}})
        except Exception: pass
        self.cdp.on("Page.screencastFrame", lambda ev: asyncio.ensure_future(self._frame(ev)))
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": W * DPR, "maxHeight": H * DPR})

    async def _frame(self, ev):
        n = len(self.frames); data = base64.b64decode(ev["data"]); self.frames.append(time.time())
        self.size = jpeg_size(data)
        if self.size != (self.W * self.DPR, self.H * self.DPR) and self.t_start and self.frames[-1] >= self.t_start:
            self.badsize.append((n, self.size)); asyncio.ensure_future(self._repaint())
        open(f"{self.dir}/frames/{n:05d}.jpg", "wb").write(data)
        try: await self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception: pass

    async def _repaint(self):
        """Frames only come when the page changes: after a wrong-size frame, change something invisible so a
        full-size frame replaces it at once instead of whenever the page next changes."""
        await asyncio.sleep(0.03)
        try: await self.pg.evaluate("(() => { const c = document.getElementById('rec-pointer'); if (c) c.style.opacity = c.style.opacity === '0.99' ? '1' : '0.99'; })()")
        except Exception: pass

    async def goto(self, path="/", wait_for=None, timeout=90000):
        await self.pg.goto(self.base + path)
        if wait_for: await self.pg.wait_for_selector(wait_for, timeout=timeout)

    async def warm(self, views):
        """Load every view the tour uses once, so nothing is slow on camera. views: [(path, selector), ...]"""
        for path, sel in views:
            await self.pg.goto(self.base + path); await self.pg.reload(); await self.pg.wait_for_selector(sel, timeout=90000)

    async def start(self):
        """Call once the first view is ready: everything before this is cut from the video. Waits until the
        capture has been steady at full size for a second (on macOS the window resize animates for a while)."""
        await self.pg.wait_for_timeout(1500); await self._remember()
        want, steady, k, t0 = (self.W * self.DPR, self.H * self.DPR), 0, 0, time.time()
        while steady < 4:
            if time.time() - t0 > 20: sys.exit(f"capture is {self.size}, not {want[0]}x{want[1]}: the frames would be cropped or stretched")
            n, k = len(self.frames), k + 1; await self.pg.mouse.move(self.mouse[0] + k % 2, self.mouse[1]); await asyncio.sleep(0.25)
            steady = steady + 1 if len(self.frames) > n and self.size == want else 0
        self.t_start = time.time()

    # --- scenes
    @contextlib.asynccontextmanager
    async def scene(self, sid):
        """Run the actions inside, then wait until this scene's narration has finished, plus the hold."""
        if sid not in self.durs: sys.exit(f"scene {sid!r} has no narration: run tts.py after editing scenes.json")
        self.current = sid; t0 = time.time(); self.timeline.append({"id": sid, "t": t0}); print("scene", sid, flush=True)
        yield
        if self.leak: self.leaks |= {m.group(0) for m in self.leak.finditer(await self.pg.inner_text("body"))}
        scene_hold = self.c.get("scene_holds", {}).get(sid, self.c["hold"])
        rest = t0 + self.durs[sid] + scene_hold - time.time()
        if rest > 0: await asyncio.sleep(rest)
        else:
            await self.hold(); print(f"  actions ran {-rest + self.c['hold']:.1f}s past the narration: trim them or lengthen the line", flush=True)

    async def hold(self, s=None):
        await asyncio.sleep(self.c["hold"] if s is None else s)

    # --- pointer and page
    async def _remember(self):
        await self.pg.evaluate("m => window.__lastMouse = m", self.mouse)

    async def glide(self, x, y):
        """One smooth, eased path to (x, y), at a pace a viewer can follow."""
        x0, y0 = self.mouse; dist = math.hypot(x - x0, y - y0)
        if dist < 2: return
        n = max(18, min(60, int(dist / 14)))
        for i in range(1, n + 1):
            t = i / n; e = t * t * (3 - 2 * t)
            await self.pg.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e); await asyncio.sleep(0.014)
        self.mouse[:] = [x, y]; await self._remember()

    async def box(self, loc):
        bb = await loc.bounding_box()
        if bb is None: self.problems.append(f"{self.current}: not found {loc}")
        return bb

    async def scroll_to(self, loc, frac=0.3):
        """Steady scroll (of the page, or of the panel or dialog holding the element) that puts it about
        `frac` of the way down the visible area."""
        await loc.evaluate(f"e => window.__scrollToEl(e, {frac}, {self.c['header']}, {self.c['scroll_speed']})")
        await asyncio.sleep(0.25)

    async def scroll_y(self, y):
        """Steady scroll of the page to y (use 10**6 for the bottom)."""
        await self.pg.evaluate(f"y => window.__scrollTo(y, {self.c['scroll_speed']})", y); await asyncio.sleep(0.25)

    async def _onscreen(self, loc, bb):
        top, bottom = await loc.evaluate(f"e => window.__visible(e, {self.c['header']})")
        return bb["y"] >= top + 8 and bb["y"] + bb["height"] <= bottom - 16

    async def visible(self, loc, frac=0.35):
        """Scroll only if the element is not already comfortably on screen."""
        bb = await self.box(loc)
        if bb and not await self._onscreen(loc, bb):
            await self.scroll_to(loc, frac); bb = await self.box(loc)
            if bb and not await self._onscreen(loc, bb): self.problems.append(f"{self.current}: off screen at y={round(bb['y'])}")
        return bb

    async def point(self, loc, side="right"):
        """Rest the pointer just beside the element's text, never on top of it."""
        await self.visible(loc)
        tb = await loc.evaluate("e => window.__textBox(e)")
        if not tb:
            bb = await self.box(loc)
            if not bb: return
            tb = {"x": bb["x"], "y": bb["y"], "w": bb["width"], "h": bb["height"]}
        x = tb["x"] + tb["w"] + 14 if side == "right" and tb["x"] + tb["w"] + 40 < self.W else max(8, tb["x"] - 26)
        await self.glide(x, tb["y"] + tb["h"] * 0.55)

    async def click(self, loc, after=0.5):
        if not await loc.evaluate("e => !!e.closest('header')"): await self.visible(loc)
        bb = await self.box(loc)
        await self.glide(bb["x"] + min(bb["width"] / 2, 48), bb["y"] + bb["height"] / 2)
        await asyncio.sleep(0.25); await self.pg.mouse.down(); await self.pg.mouse.up(); await asyncio.sleep(after)

    async def type_in(self, loc, text, delay=65):
        """Click the field, then type the whole text in one go."""
        await self.click(loc, 0.3); await self.pg.keyboard.type(text, delay=delay)

    async def select(self, loc, value):
        await self.click(loc, 0.3); await loc.select_option(value); await self.hold(0.6)

    async def blur(self):
        """Drop the focus ring a dialog puts on its first button."""
        await self.pg.evaluate("document.activeElement && document.activeElement.blur()")

    async def close(self):
        await self.hold(1.5)
        await self.cdp.send("Page.stopScreencast"); await asyncio.sleep(0.5)
        await self.browser.close()


async def main():
    if len(sys.argv) < 3: sys.exit(__doc__)
    workdir, base = os.path.abspath(sys.argv[1]), sys.argv[2]
    spec = importlib.util.spec_from_file_location("tour", f"{workdir}/tour.py"); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    cfg = {**DEFAULTS, **getattr(mod, "CONFIG", {})}
    cfg["scene_holds"] = {s["id"]: float(s.get("hold", cfg["hold"])) for s in json.load(open(f"{workdir}/scenes.json"))}
    durs = json.load(open(f"{workdir}/audio/durations.json"))["durations"]
    shutil.rmtree(f"{workdir}/frames", ignore_errors=True); os.makedirs(f"{workdir}/frames")
    r = Recorder(workdir, base, cfg, durs)
    async with async_playwright() as p:
        await r.open(p)
        await mod.tour(r)
        await r.close()
    if r.t_start is None: sys.exit("tour() never called r.start()")
    W, H = r.W * r.DPR, r.H * r.DPR
    json.dump({"start": r.t_start, "frames": r.frames, "scenes": r.timeline, "end": time.time(), "size": [W, H]}, open(f"{workdir}/timeline.json", "w"))
    ids = [s["id"] for s in json.load(open(f"{workdir}/scenes.json"))]
    if [s["id"] for s in r.timeline] != ids: r.problems.append(f"scenes recorded {[s['id'] for s in r.timeline]} differ from scenes.json {ids}")
    print("PROBLEMS:", r.problems or "none")
    # A blink of wrong-size frames (Chrome briefly resizing the capture) is dropped by build.py, which holds the frame
    # before it. A longer run would show, so it fails the take.
    bad = [i for i, _ in r.badsize]; runs, longest = [], 0.0
    for i in bad:
        if runs and i == runs[-1][-1] + 1: runs[-1].append(i)
        else: runs.append([i])
    for run in runs:
        end = r.frames[run[-1] + 1] if run[-1] + 1 < len(r.frames) else r.frames[-1]
        longest = max(longest, end - r.frames[run[0]])
    tl = json.load(open(f"{workdir}/timeline.json")); tl["bad"] = bad; json.dump(tl, open(f"{workdir}/timeline.json", "w"))
    print(len(r.frames), "frames;", f"all {W}x{H}" if not bad else f"{len(bad)} not {W}x{H} (e.g. {r.badsize[0][1]}), longest run {longest:.2f}s" + (": dropped in the build" if longest <= 0.3 else ": TOO LONG, re-record"))
    print("LEAKS ON SCREEN: " + ", ".join(sorted(r.leaks)) if r.leaks else "no leaks on screen")
    if longest > 0.3 or r.leaks or r.problems: sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
