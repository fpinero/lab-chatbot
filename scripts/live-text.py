"""Run exactly one bounded text test through an authenticated application API."""

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
    limit = int((args.max_usd * 1_000_000).to_integral_value(rounding=ROUND_FLOOR))
    if limit < 1:
        raise SystemExit("The allowance must be at least one micro-USD.")
    if not args.execute:
        print(
            "Plan: one authenticated text run, capped at 32 output tokens and the supplied allowance."
        )
        return
    origin = os.environ.get("APP_ORIGIN", "http://127.0.0.1:5173")
    url = urlsplit(origin)
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
                "Cannot read sign-in configuration. Check the configured identity layer."
            )
        info = configuration.json()
        if info.get("provider_mode") != "openrouter":
            raise SystemExit(
                "Live verification requires the application's live provider mode."
            )
        body = {
            "password": getpass("Owner passphrase: ")
            if info["auth_mode"] == "password"
            else "",
            "code": getpass("Application code: ") if info["requires_code"] else "",
        }
        response = client.post("/api/auth/login", json=body)
        if response.status_code != 200:
            raise SystemExit("Authentication failed.")
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        conversation = client.post(
            "/api/conversations", json={"title": "Bounded live text verification"}
        )
        if conversation.status_code != 201:
            raise SystemExit("Cannot create the verification conversation.")
        response = client.post(
            "/api/runs",
            json={
                "conversation_id": conversation.json()["id"],
                "model_id": args.model,
                "idempotency_key": uuid4().hex,
                "max_tokens": 32,
                "request_allowance_microusd": limit,
                "verification_run": True,
                "prompt": "Reply with the word ready.",
            },
        )
        if response.status_code != 202:
            raise SystemExit(
                "Dispatch rejected. Check key restrictions, catalog compatibility and budgets."
            )
        run_id = response.json()["id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            result = client.get(f"/api/runs/{run_id}")
            if result.status_code != 200:
                raise SystemExit(
                    "Cannot inspect the existing run. Do not resubmit it automatically."
                )
            run = result.json()
            if run["status"] in {"succeeded", "failed", "cancelled", "interrupted"}:
                evidence = {
                    key: run[key]
                    for key in [
                        "id",
                        "model_id",
                        "provider",
                        "status",
                        "accounting_state",
                        "reserved_microusd",
                        "actual_microusd",
                        "elapsed_ms",
                    ]
                }
                path = Path("artifacts/live-text.json")
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(evidence, indent=2) + "\n")
                print(json.dumps(evidence))
                if run["status"] != "succeeded" or run["actual_microusd"] is None:
                    raise SystemExit(
                        "Live verification is incomplete. Inspect the saved status and billing evidence."
                    )
                if run["actual_microusd"] > limit:
                    raise SystemExit(
                        "Reported cost exceeded the allowance. Do not run another test."
                    )
                return
            time.sleep(1)
        raise SystemExit(
            "The existing run is still pending. Inspect it before any explicit retry."
        )


if __name__ == "__main__":
    main()
