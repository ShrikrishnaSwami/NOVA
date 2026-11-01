"""Benchmark models exposed by a local OpenAI-compatible runtime.

This script sends prompts directly to the runtime; it does not use NOVA's
conversation API, write to memory, or print generated response text.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Any

import httpx


SHORT_PROMPT = "In one sentence, explain what RAM does in a computer."
LONG_PROMPT = (
    "Explain how an operating system manages memory. Cover virtual memory, "
    "paging, page faults, and why applications cannot normally access each "
    "other's memory. Use clear examples and organize the answer with headings."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure TTFT and response latency for local model IDs."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:1235/v1",
        help="OpenAI-compatible API base URL (default: Bionic local endpoint).",
    )
    parser.add_argument("--api-key", default="", help="Optional local API key.")
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Model ID to test. Repeat to test multiple IDs. Defaults to /models.",
    )
    parser.add_argument("--runs", type=int, default=3, help="Measured runs per prompt.")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help="Maximum generated tokens per test (default: 256).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Request timeout in seconds.",
    )
    return parser.parse_args()


def get_models(client: httpx.Client, base_url: str) -> list[str]:
    response = client.get(f"{base_url.rstrip('/')}/models")
    response.raise_for_status()
    data = response.json().get("data", [])
    return [item["id"] for item in data if isinstance(item, dict) and item.get("id")]


def run_once(
    client: httpx.Client,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
) -> dict[str, float | int]:
    content_parts: list[str] = []
    first_token_at: float | None = None
    started = time.perf_counter()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "top_p": 0.8,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if "qwen3" in model.lower():
        payload["messages"][0]["content"] += "\n/no_think"

    with client.stream(
        "POST",
        f"{base_url.rstrip('/')}/chat/completions",
        json=payload,
    ) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()

        if "text/event-stream" not in content_type:
            body = response.read()
            data = json.loads(body)
            text = data["choices"][0]["message"].get("content", "")
            if text:
                first_token_at = time.perf_counter()
                content_parts.append(text)
        else:
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                event_data = line[5:].strip()
                if event_data == "[DONE]":
                    break
                try:
                    event = json.loads(event_data)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if isinstance(piece, str) and piece:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    content_parts.append(piece)

    ended = time.perf_counter()
    return {
        "ttft_ms": round(((first_token_at or ended) - started) * 1000),
        "total_ms": round((ended - started) * 1000),
        "characters": sum(len(part) for part in content_parts),
    }


def median(results: list[dict[str, float | int]], key: str) -> int:
    return round(statistics.median(float(item[key]) for item in results))


def main() -> int:
    args = parse_args()
    if args.runs < 1 or args.max_tokens < 16:
        raise SystemExit("--runs must be >= 1 and --max-tokens must be >= 16.")

    headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else {}
    timeout = httpx.Timeout(args.timeout, connect=10.0)

    with httpx.Client(headers=headers, timeout=timeout) as client:
        try:
            models = args.models or get_models(client, args.base_url)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise SystemExit(
                f"Could not read model IDs from {args.base_url}/models: {exc}\n"
                "Pass one or more explicit IDs with --model MODEL_ID."
            ) from exc

        if not models:
            raise SystemExit("The runtime returned no model IDs. Load a model first.")

        print(f"Endpoint: {args.base_url}")
        print(f"Measured runs: {args.runs}; max output tokens: {args.max_tokens}")
        print("Warm-up: one short request per model (not included in results).")

        for model in models:
            print(f"\n=== {model} ===")
            try:
                run_once(client, args.base_url, model, SHORT_PROMPT, min(48, args.max_tokens))
                for label, prompt in (("short", SHORT_PROMPT), ("detailed", LONG_PROMPT)):
                    results = [
                        run_once(client, args.base_url, model, prompt, args.max_tokens)
                        for _ in range(args.runs)
                    ]
                    print(
                        f"{label:8} median TTFT {median(results, 'ttft_ms'):>6} ms | "
                        f"total {median(results, 'total_ms'):>6} ms | "
                        f"output {median(results, 'characters'):>4} chars"
                    )
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                print(f"FAILED: {exc}")

    print("\nTip: load one candidate model in your runtime, rerun this script,")
    print("and compare the detailed-prompt median. Keep the prompt and settings fixed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
