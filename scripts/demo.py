"""Submit N jobs concurrently and watch them complete over the websocket feed.

    uv run python scripts/demo.py --count 20 --kind primes

Measures submit latency (HTTP) and end-to-end time until the last job finishes.
Stdlib + `websockets` only, so it runs anywhere the project does.
"""

import argparse
import asyncio
import json
import statistics
import time
import urllib.request

import websockets

PAYLOADS = {
    "primes": {"limit": 2_000_000},
    "sleep": {"seconds": 1, "steps": 5},
    "checksum": {"text": "jobflow", "rounds": 200_000},
}


def submit(base: str, kind: str) -> tuple[str, float]:
    body = json.dumps({"kind": kind, "payload": PAYLOADS[kind]}).encode()
    req = urllib.request.Request(
        f"{base}/api/jobs/", data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=10) as res:
        job_id = json.load(res)["id"]
    return job_id, time.perf_counter() - t0


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--kind", choices=sorted(PAYLOADS), default="primes")
    args = ap.parse_args()
    ws_url = args.base.replace("http", "ws", 1) + "/ws/jobs/"

    async with websockets.connect(ws_url, origin=args.base) as ws:
        loop = asyncio.get_running_loop()
        t_start = time.perf_counter()
        results = await asyncio.gather(
            *(loop.run_in_executor(None, submit, args.base, args.kind) for _ in range(args.count))
        )
        pending = {job_id for job_id, _ in results}
        latencies = [lat for _, lat in results]
        print(
            f"submitted {args.count} jobs in {time.perf_counter() - t_start:.2f}s  "
            f"p50={statistics.median(latencies) * 1000:.1f}ms  "
            f"max={max(latencies) * 1000:.1f}ms"
        )

        while pending:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
            job = msg["job"]
            if job["id"] in pending:
                print(f"  {job['id'][:8]}  {job['status']:<9} {job['progress']:>3}%")
                if job["status"] in {"succeeded", "failed"}:
                    pending.discard(job["id"])
        print(f"all done in {time.perf_counter() - t_start:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
