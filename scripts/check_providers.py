"""Opt-in live API smoke check. Sends only a synthetic, featureless image.

Defaults to Gemini. Consumes a small amount of provider quota. Never prints secrets.
uv run python scripts/check_providers.py
uv run python scripts/check_providers.py --provider anthropic --auth vertex_adc
"""
import argparse
import io
import json

from PIL import Image

from miyagi.providers.cloud import ReviewRequest, SDKReviewer


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--provider",choices=["gemini","openai","anthropic"],default="gemini")
    parser.add_argument("--auth",choices=["api_key","vertex_adc","vertex_api_key"],default="api_key")
    parser.add_argument("--model",default="")
    args=parser.parse_args()
    buffer=io.BytesIO()
    Image.new("RGB",(128,128),(180,180,180)).save(buffer,"JPEG")
    try:
        request=ReviewRequest(provider=args.provider,auth=args.auth,model=args.model,consent=True,frames=["synthetic"])
        review=SDKReviewer().review(request,[buffer.getvalue()])
        print(json.dumps({"provider":args.provider,"auth":args.auth,"ok":True,
                          "observation_count":len(review.observations),"input":"synthetic gray image"}))
        return 0
    except Exception as exc:
        print(json.dumps({"provider":args.provider,"auth":args.auth,"ok":False,"error_type":type(exc).__name__,
                          "status_code":getattr(exc,"status_code",getattr(exc,"code",None))}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
