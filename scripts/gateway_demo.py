from __future__ import annotations

import argparse
import json
import os
import sys

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cairn M1 网关链路演示")
    parser.add_argument("--base-url", default=os.getenv("CAIRN_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--email", default=os.getenv("CAIRN_DEMO_EMAIL", "demo@cairn.local"))
    parser.add_argument("--password", default=os.getenv("CAIRN_DEMO_PASSWORD", "password123"))
    parser.add_argument(
        "--provider",
        default=os.getenv("CAIRN_DEMO_PROVIDER", "openai_compat"),
    )
    parser.add_argument("--model", default=os.getenv("CAIRN_DEMO_MODEL"))
    parser.add_argument("--endpoint", default=os.getenv("CAIRN_DEMO_ENDPOINT"))
    parser.add_argument(
        "--use-env-credential",
        action="store_true",
        help="使用服务端本地环境变量凭证，密钥不经过 API 传输、不落库",
    )
    return parser.parse_args()


def request(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        print(f"{method} {path} failed: {response.status_code} {response.text}", file=sys.stderr)
        raise SystemExit(1)
    return response


def main() -> None:
    args = parse_args()
    api_key = os.getenv("CAIRN_DEMO_API_KEY")
    if not args.use_env_credential and not api_key:
        print(
            "请设置 CAIRN_DEMO_API_KEY，或使用 --use-env-credential 让服务端读取本地环境变量",
            file=sys.stderr,
        )
        raise SystemExit(2)

    base = args.base_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=120) as client:
        request(
            client,
            "POST",
            "/api/v1/auth/register",
            json={"email": args.email, "password": args.password},
        )
        token = request(
            client,
            "POST",
            "/api/v1/auth/login",
            json={"email": args.email, "password": args.password},
        ).json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        call_payload: dict = {
            "task": "extract",
            "messages": [{"role": "user", "content": "Reply with a short JSON object."}],
            "options": {
                "response_format": "json_object",
                "schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
            },
        }

        if args.use_env_credential:
            call_payload["provider"] = args.provider
            if args.model:
                call_payload["model"] = args.model
            print("using server-side environment credential; key is never sent over API")
        else:
            created = request(
                client,
                "POST",
                "/api/v1/credentials",
                headers={"X-Confirm-Action": "confirm"},
                json={
                    "name": "demo-credential",
                    "provider": args.provider,
                    "api_key": api_key,
                    "base_url": args.endpoint,
                    "model": args.model,
                },
            ).json()
            credential_id = created["id"]
            print("created credential:", json.dumps(created, ensure_ascii=False))

            probed = request(
                client,
                "POST",
                f"/api/v1/credentials/{credential_id}/test",
            ).json()
            print("capabilities:", json.dumps(probed, ensure_ascii=False))
            call_payload["credential_id"] = credential_id

        called = request(
            client,
            "POST",
            "/api/v1/gateway/complete",
            json=call_payload,
        ).json()
        print("gateway response:", json.dumps(called, ensure_ascii=False))

        usage = request(client, "GET", "/api/v1/usage/summary").json()
        print("usage summary:", json.dumps(usage, ensure_ascii=False))


if __name__ == "__main__":
    main()
