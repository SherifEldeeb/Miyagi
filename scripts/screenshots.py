"""Regenerate the README screenshots: docs/screenshot-light.png and docs/screenshot-dark.png.

    uv run --with playwright python scripts/screenshots.py

Starts the app on a spare port and drives the installed Google Chrome with its fake camera
(a test pattern, no person), so no real camera or image is involved. The fake camera has no
face, so for the light shot the page rewrites the server's per-frame results to stage a
beard-stroking alert; the dark shot is the real, unstaged state (Habits tab).
"""

from __future__ import annotations

import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Browser, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = 8766
URL = f"http://127.0.0.1:{PORT}"
VIEWPORT = {"width": 1400, "height": 900}

# Wraps WebSocket so results can be overridden once window.__miyagiStage(stage) is called.
STAGE_JS = """
(() => {
  const Real = window.WebSocket;
  let stage = null;
  window.__miyagiStage = (s) => { stage = { ...s, fresh: true }; };
  window.WebSocket = class extends Real {
    set onmessage(fn) {
      super.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "result" && stage) {
          Object.assign(msg, {
            calibrated: true, calibrating: false, elapsed: stage.elapsed, face_box: stage.face_box,
            counts: { ...msg.counts, ...stage.counts }, alerts: [{ ...stage.alert, new: stage.fresh }],
          });
          stage.fresh = false;
        }
        fn({ data: JSON.stringify(msg) });
      };
    }
  };
})();
"""

# Beard stroking, third time in a few minutes (severity 2), at 02:05 into the session.
STAGE_BEARD = """
async () => {
  const { conditions } = await (await fetch("/api/conditions")).json();
  const c = conditions.find((x) => x.id === "beard_stroke");
  window.__miyagiStage({
    elapsed: 125,
    counts: { beard_stroke: 3, chin_touch: 1 },
    face_box: { x: 0.415, y: 0.07, w: 0.17, h: 0.26 },
    alert: { id: c.id, label: c.label, emoji: c.emoji, tip: c.tip, styles: c.styles,
             severity: 2, count: 3, box: { x: 0.37, y: 0.5, w: 0.26, h: 0.22 } },
  });
}
"""


def wait_for_server() -> None:
    for _ in range(150):
        try:
            urllib.request.urlopen(f"{URL}/api/conditions", timeout=1)
            return
        except OSError:
            time.sleep(0.2)
    raise SystemExit(f"Miyagi did not start on {URL}")


def shoot(browser: Browser, scheme: str, out: Path, *, staged: bool, tab: str) -> None:
    ctx = browser.new_context(viewport=VIEWPORT, color_scheme=scheme)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.add_init_script(STAGE_JS)
    page.goto(URL)
    page.click("#btnStart")
    page.wait_for_function("document.querySelector('#status .txt')?.textContent.startsWith('Live')")
    if staged:
        page.evaluate(STAGE_BEARD)
    page.click(f'.tab-btn[data-tab="{tab}"]')
    page.mouse.move(VIEWPORT["width"] - 1, VIEWPORT["height"] - 1)  # no hover highlight on the tab
    page.wait_for_timeout(1500)  # a few frames: toast up, counts and log rendered
    page.screenshot(path=str(out))
    ctx.close()
    if errors:
        raise SystemExit(f"console errors in the {scheme} shot: {errors}")
    print(f"wrote {out.relative_to(ROOT)}")


def main() -> None:
    server = subprocess.Popen(["miyagi", "--no-browser", "--port", str(PORT)], cwd=ROOT)
    try:
        wait_for_server()
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel="chrome",
                args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
            )
            shoot(browser, "light", ROOT / "docs" / "screenshot-light.png", staged=True, tab="live")
            shoot(browser, "dark", ROOT / "docs" / "screenshot-dark.png", staged=False, tab="habits")
            browser.close()
    finally:
        server.terminate()
        server.wait()


if __name__ == "__main__":
    main()
