"""The tour: what the pointer does in each scene. Run by scripts/record.py WORKDIR BASE_URL.

One `async with r.scene(id)` block per scene, in the same order as scenes.json. Each block only has to do
its actions: the recorder waits out the scene's narration and a still hold afterwards.
"""

CONFIG = {
    "header": 64,   # height of the app's sticky top bar, in CSS px
    # Rewritten on screen while recording: [JS regex, replacement]. Add every internal name you found while scouting.
    "scrub": [
        [r"https?://\d{1,3}(\.\d{1,3}){3}(:\d+)?", "https://app.example.org"],   # URLs first, then bare IPs
        [r"\b\d{1,3}(\.\d{1,3}){3}\b", "app.example.org"],
        [r"internal-host-name", "app.example.org"],
    ],
    # Fails the take if any of this is visible at the end of any scene.
    "leak": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|internal-host-name",
    # Run before every page load, e.g. force the light theme the app stores in localStorage.
    "init_js": "localStorage.setItem('theme', 'light')",
}


async def tour(r):
    pg = r.pg
    await r.goto("/")
    # Load every view once so nothing is slow on camera, then land on the opening view.
    await r.warm([("/#api", "#api pre"), ("/#requests", "#list .item")])
    await r.start()

    async with r.scene("intro"):
        await r.hold(1.5)                                   # open on a still frame
        await r.point(pg.locator("#list .item .title").first)

    async with r.scene("triage"):
        await r.click(pg.get_by_role("button", name="Sort by impact"), after=1.0)
        await r.point(pg.locator("#list .item .title").first); await r.hold(2.0)
        await r.point(pg.locator("#list .item .why").first)  # rests beside the explanation, not on it

    async with r.scene("api"):
        await r.click(pg.get_by_role("tab", name="API"), after=0.8)
        code = pg.locator("#api pre").first
        await r.scroll_to(code, 0.2); await r.hold(0.4)
        await r.point(code)
