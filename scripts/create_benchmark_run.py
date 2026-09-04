"""Queue a local benchmark run through the Vision Bill API."""

import argparse
import os
import sys
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.getenv("VB_API_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--username", default=os.getenv("VB_USERNAME"))
    parser.add_argument("--password", default=os.getenv("VB_PASSWORD"))
    parser.add_argument("--model", dest="model_ids", action="append")
    parser.add_argument("--receipt-id", dest="receipt_ids", action="append")
    parser.add_argument("--category")
    parser.add_argument("--max-source-confidence", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--request-timeout-seconds", type=int, default=300)
    parser.add_argument("--council-policy", choices=("all", "material", "custom"), default="all")
    parser.add_argument("--council-absolute-threshold")
    parser.add_argument("--council-relative-threshold")
    parser.add_argument("--apply-council-flags", action="store_true")
    return parser.parse_args()


def request_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model_ids": args.model_ids,
        "receipt_ids": args.receipt_ids,
        "category": args.category,
        "max_source_confidence": args.max_source_confidence,
        "limit": args.limit,
        "request_timeout_seconds": args.request_timeout_seconds,
        "council_policy": args.council_policy,
        "council_absolute_threshold": args.council_absolute_threshold,
        "council_relative_threshold": args.council_relative_threshold,
        "apply_council_flags": args.apply_council_flags,
    }
    return {key: value for key, value in payload.items() if value is not None}


def main() -> int:
    args = parse_args()
    endpoint = f"{args.api_url.rstrip('/')}/api/v1/benchmarks"
    if bool(args.username) != bool(args.password):
        print("Provide both --username and --password (or VB_USERNAME and VB_PASSWORD).", file=sys.stderr)
        return 2
    try:
        with httpx.Client(timeout=30) as client:
            if args.username:
                login = client.post(
                    f"{args.api_url.rstrip('/')}/api/v1/auth/login",
                    json={"username": args.username, "password": args.password},
                )
                login.raise_for_status()
            response = client.post(endpoint, json=request_payload(args))
            response.raise_for_status()
    except httpx.HTTPError as error:
        print(f"Unable to queue benchmark: {error}", file=sys.stderr)
        return 1

    run = response.json()
    print(run["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
