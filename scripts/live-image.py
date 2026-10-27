"""Generate exactly one image through the authenticated app within approved allowances."""

import argparse
import json
import os
import time
from decimal import ROUND_FLOOR, Decimal
from getpass import getpass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--max-usd", required=True, type=Decimal)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    approved = Decimal(os.environ.get("LIVE_TEST_BUDGET_USD", "0"))
    if (
        not approved.is_finite()
        or not args.max_usd.is_finite()
        or not 0 < args.max_usd <= approved
    ):
        raise SystemExit(
            "Set an approved LIVE_TEST_BUDGET_USD and a positive --max-usd within it."
        )
    limit = int((args.max_usd * 1000000).to_integral_value(rounding=ROUND_FLOOR))
    if limit < 1:
        raise SystemExit("The allowance must be at least one micro-USD.")
    if not args.execute:
        print(
            "Plan: one authenticated image job with the smallest advertised tier and supplied allowance."
        )
        return
    origin = os.environ.get("APP_ORIGIN", "http://127.0.0.1:5173")
    url = urlsplit(origin)
    if (
        url.path
        or url.query
        or url.fragment
        or url.username
        or url.password
        or not url.hostname
    ):
        raise SystemExit(
            "Configure an exact application origin without credentials or a path."
        )
    if url.scheme != "https" and (
        url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise SystemExit("Live tests require HTTPS or a loopback application origin.")
    headers = {"Origin": origin}
    if os.environ.get("CF_ACCESS_TOKEN_FILE"):
        headers["Cf-Access-Jwt-Assertion"] = (
            Path(os.environ["CF_ACCESS_TOKEN_FILE"]).read_text().strip()
        )
    with httpx.Client(
        base_url=origin,
        headers=headers,
        timeout=20,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        configuration = client.get("/api/auth/login")
        if configuration.status_code != 200:
            raise SystemExit(
                "Cannot read sign-in configuration. Check the identity layer."
            )
        info = configuration.json()
        if info.get("provider_mode") != "openrouter":
            raise SystemExit(
                "Live verification requires the application's live provider mode."
            )
        response = client.post(
            "/api/auth/login",
            json={
                "password": getpass("Owner passphrase: ")
                if info["auth_mode"] == "password"
                else "",
                "code": getpass("Application code: ") if info["requires_code"] else "",
            },
        )
        if response.status_code != 200:
            raise SystemExit("Authentication failed.")
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        response = client.get(
            "/api/images/capabilities", params={"model_id": args.model}
        )
        if response.status_code != 200:
            raise SystemExit("Cannot read dedicated image capabilities for this model.")
        endpoint = next(
            (
                item
                for item in response.json()["endpoints"]
                if item["provider_tag"] == args.provider
            ),
            None,
        )
        if not endpoint:
            raise SystemExit(
                "The selected provider is not available for this image model."
            )
        options = {}
        preferences = {
            "resolution": ["512", "768", "1K", "1.5K", "2K", "4K"],
            "aspect_ratio": ["1:1"],
            "quality": ["low", "medium", "auto", "high"],
            "output_format": ["png", "webp", "jpeg"],
        }
        for key, preferred in preferences.items():
            descriptor = endpoint["parameters"].get(key, {})
            values = descriptor.get("values", [])
            if key == "output_format":
                values = [value for value in values if value in {"png", "webp", "jpeg"}]
            if descriptor.get("type") == "enum" and values:
                options[key] = next(
                    (value for value in preferred if value in values), values[0]
                )
        request = {
            "model_id": args.model,
            "provider_tag": args.provider,
            "prompt": "Draw one simple blue circle on a plain white background.",
            "options": options,
            "count": 1,
            "verification_run": True,
            "request_allowance_microusd": limit,
        }
        quote = client.post("/api/images/quote", json=request)
        if quote.status_code != 200 or not quote.json().get("ready"):
            raise SystemExit(
                "The quote is blocked. Check compatibility and approved allowances."
            )
        response = client.post(
            "/api/images/jobs", json={**request, "idempotency_key": uuid4().hex}
        )
        if response.status_code != 202:
            raise SystemExit(
                "Dispatch rejected. Check restricted credentials and approved budgets."
            )
        identifier = response.json()["id"]
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            response = client.get(f"/api/images/jobs/{identifier}")
            if response.status_code != 200:
                raise SystemExit(
                    "Cannot inspect the saved job. Do not resubmit automatically."
                )
            job = response.json()
            if job["status"] not in {
                "queued",
                "submitting",
                "running",
                "cancel_requested",
            }:
                evidence = {
                    key: job[key]
                    for key in [
                        "id",
                        "model_id",
                        "provider_name",
                        "generation_id",
                        "status",
                        "accounting_state",
                        "reserved_microusd",
                        "actual_microusd",
                        "elapsed_ms",
                    ]
                }
                evidence["assets"] = job["assets"]
                downloads = []
                for asset in job["assets"]:
                    binary = client.get(f"/api/media/{asset['id']}?download=true")
                    downloads.append(
                        binary.status_code == 200
                        and binary.headers.get("content-type") == "image/webp"
                        and binary.content[:4] == b"RIFF"
                    )
                evidence["authenticated_downloads_valid"] = bool(downloads) and all(
                    downloads
                )
                path = Path("artifacts/live-image.json")
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(evidence, indent=2) + "\n")
                print(json.dumps(evidence))
                if (
                    job["status"] != "succeeded"
                    or job["actual_microusd"] is None
                    or not evidence["authenticated_downloads_valid"]
                ):
                    raise SystemExit(
                        "Live verification is incomplete. Inspect saved status and billing evidence."
                    )
                if job["actual_microusd"] > limit:
                    raise SystemExit(
                        "Reported cost exceeded the allowance. Do not run another test."
                    )
                return
            time.sleep(2)
        raise SystemExit(
            "The saved job remains pending. Inspect it before any deliberate retry."
        )


if __name__ == "__main__":
    main()
