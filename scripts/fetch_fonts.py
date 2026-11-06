"""Download the bundled Google fonts into meeting_coach/static/fonts.

The UI must not make third-party requests, so fonts are vendored:
  - Google Sans Flex (variable, latin subset), SIL Open Font License 1.1
  - Roboto Mono (latin, 400-500), SIL Open Font License 1.1
  - Material Symbols Rounded (variable), subset to the icons in fonts/icons.txt, Apache License 2.0

Run after editing icons.txt:  uv run python scripts/fetch_fonts.py
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path

FONTS = Path(__file__).resolve().parents[1] / "meeting_coach" / "static" / "fonts"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
LATIN = "U+0000-00FF"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed Google Fonts URLs
        return r.read()


def woff2_url(css: str, must_contain: str | None) -> str:
    for block in css.split("@font-face")[1:]:
        if must_contain is None or must_contain in block:
            return re.search(r"url\((.*?)\)", block).group(1)
    raise RuntimeError("font block not found")


def icons() -> list[str]:
    lines = (FONTS / "icons.txt").read_text().splitlines()
    return sorted({ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")})


def main() -> None:
    api = "https://fonts.googleapis.com/css2?family="
    jobs = {
        "google-sans-flex-latin.woff2": (api + "Google+Sans+Flex:opsz,wght@6..144,1..1000&display=swap", LATIN),
        "roboto-mono-latin.woff2": (api + "Roboto+Mono:wght@400;500&display=swap", LATIN),
        "material-symbols-rounded.woff2": (
            api
            + "Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
            + "&icon_names="
            + ",".join(icons())
            + "&display=block",
            None,
        ),
    }
    for name, (css_url, subset) in jobs.items():
        data = get(woff2_url(get(css_url).decode(), subset))
        (FONTS / name).write_bytes(data)
        print(f"{name}: {len(data) // 1024} KB")


if __name__ == "__main__":
    main()
