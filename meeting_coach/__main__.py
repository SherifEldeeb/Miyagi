"""``python -m meeting_coach`` - download models (first run) and start the app."""

from __future__ import annotations

import argparse
import logging
import os
import threading
import webbrowser


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def main() -> None:
    parser = argparse.ArgumentParser(description="Meeting Coach - real-time body-language coaching")
    parser.add_argument(
        "--host",
        default=os.environ.get("MEETING_COACH_HOST", "127.0.0.1"),
        help="bind address; camera access needs localhost or HTTPS (env MEETING_COACH_HOST, default 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MEETING_COACH_PORT", "8000")),
        help="port (env MEETING_COACH_PORT, default 8000)",
    )
    parser.add_argument(
        "--coach",
        action="store_true",
        default=_env_true("MEETING_COACH_COACH_VIEW"),
        help="open the coach-only view (camera + cues, nothing else) instead of the full UI "
        "(env MEETING_COACH_COACH_VIEW=1)",
    )
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    import uvicorn

    from .models import ensure_models
    from .server import create_app

    ensure_models()
    base = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    url = f"{base}/coach" if args.coach else base
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"Meeting Coach running at {base}  (settings: {base}/  ·  coach view: {base}/coach)")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
