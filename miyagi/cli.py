import argparse
import hashlib
import json
import urllib.request

from miyagi.config import MODEL_DIR, MODEL_URLS


def download_models():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in MODEL_URLS.items():
        path = MODEL_DIR / name
        if not path.exists():
            print(f"Downloading {name}…")
            temporary = path.with_suffix(".part")
            try:
                with urllib.request.urlopen(url, timeout=90) as response:
                    temporary.write_bytes(response.read())
                if temporary.stat().st_size < 100_000:
                    raise ValueError("Unexpected model download size")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        manifest[name] = {"url": url, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (MODEL_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Models ready in {MODEL_DIR.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Miyagi meeting coach")
    parser.add_argument("command", choices=["serve", "download-models"], nargs="?", default="serve")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "download-models":
        download_models()
    else:
        import uvicorn
        uvicorn.run("miyagi.app:app", host="127.0.0.1", port=args.port, ws_max_size=600_000)


if __name__ == "__main__":
    main()
