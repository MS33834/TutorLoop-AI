"""Lightweight load test for the chat endpoint."""

import argparse
import asyncio
import time
from statistics import mean

import httpx


async def one_chat(base_url: str, client: httpx.AsyncClient) -> dict:
    start = time.perf_counter()
    response = await client.post(
        f"{base_url}/api/chat",
        json={"messages": [{"role": "user", "content": "你好"}]},
        timeout=60,
    )
    elapsed = time.perf_counter() - start
    response.raise_for_status()
    content = ""
    first_token_time = None
    token_start = time.perf_counter()
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            text = line.removeprefix("data: ")
            if text == "[DONE]":
                break
            content += text
            if first_token_time is None:
                first_token_time = time.perf_counter() - token_start
    total = time.perf_counter() - start
    return {
        "status": response.status_code,
        "first_token_ms": (first_token_time or 0) * 1000,
        "total_ms": total * 1000,
        "chars": len(content),
    }


async def worker(base_url: str, count: int, results: list):
    async with httpx.AsyncClient() as client:
        for _ in range(count):
            try:
                results.append(await one_chat(base_url, client))
            except Exception as exc:
                results.append({"error": str(exc)})


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--requests", type=int, default=20)
    args = parser.parse_args()

    per_worker = args.requests // args.concurrency
    results: list[dict] = []
    start = time.perf_counter()
    await asyncio.gather(
        *[worker(args.base_url, per_worker, results) for _ in range(args.concurrency)]
    )
    duration = time.perf_counter() - start

    errors = [r for r in results if "error" in r]
    ok = [r for r in results if "error" not in r]
    print(f"Total requests: {len(results)}")
    print(f"Success: {len(ok)}  Errors: {len(errors)}")
    print(f"Duration: {duration:.1f}s  RPS: {len(results) / duration:.2f}")
    if ok:
        print(f"Avg first token: {mean(r['first_token_ms'] for r in ok):.0f}ms")
        print(f"Avg total: {mean(r['total_ms'] for r in ok):.0f}ms")
    if errors:
        print("Sample error:", errors[0]["error"])


if __name__ == "__main__":
    asyncio.run(main())
