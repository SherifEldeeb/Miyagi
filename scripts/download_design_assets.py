"""Refresh self-hosted, openly licensed Google typography and icons."""
import re
from pathlib import Path
from urllib.request import Request, urlopen

DEST = Path(__file__).parents[1] / "miyagi" / "static" / "fonts"
ICONS = sorted(["add","arrow_forward","auto_awesome","check","close","download","expand_more",
                "face","filter_center_focus","fullscreen","help","labs","lock","notifications_none",
                "pause","play_arrow","psychology","restart_alt","shield","stop","tune","videocam","visibility"])


def fetch(url):
    request = Request(url, headers={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"})
    with urlopen(request, timeout=45) as response:
        return response.read()


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    families = {
        "google-sans-flex": "https://fonts.googleapis.com/css2?family=Google+Sans+Flex:opsz,wght@8..144,400..700&display=swap",
        "material-symbols-rounded": "https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0&icon_names=" + ",".join(ICONS) + "&display=block",
    }
    for name, url in families.items():
        css = fetch(url).decode()
        # The final Google Sans block is the Latin subset. Symbols use one subset.
        urls = re.findall(r"src:\s*url\(([^)]+)\)", css)
        if not urls:
            raise ValueError(f"Font URL missing for {name}")
        data = fetch(urls[-1])
        if data[:4] != b"wOF2":
            raise ValueError("Expected a WOFF2 font; inspect the Google Fonts response before updating assets.")
        extension = ".woff2"
        (DEST / (name + extension)).write_bytes(data)
        print(f"Saved {name}{extension}: {len(data)} bytes")
    for name, url in {
        "Google-Sans-Flex-OFL.txt": "https://raw.githubusercontent.com/google/fonts/main/ofl/googlesansflex/OFL.txt",
        "Material-Symbols-LICENSE.txt": "https://raw.githubusercontent.com/google/material-design-icons/master/LICENSE",
    }.items():
        (DEST / name).write_text("\n".join(line.rstrip() for line in fetch(url).decode().splitlines()) + "\n")


if __name__ == "__main__":
    main()
