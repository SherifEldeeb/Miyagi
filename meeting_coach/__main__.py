"""``python -m meeting_coach`` - download models (first run) and start the app."""

from __future__ import annotations

import argparse
import logging
import threading
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="Meeting Coach - real-time body-language coaching")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (camera access needs localhost or HTTPS)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    import uvicorn

    from .models import ensure_models
    from .server import create_app

    ensure_models()
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"Meeting Coach running at {url}")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
