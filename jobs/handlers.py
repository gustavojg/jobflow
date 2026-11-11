"""Job kinds. Each handler is a plain function: (payload, report) -> result.

`report(progress)` is called with 0-100 so the worker can stream progress.
Handlers are deliberately CPU/IO-flavoured toys; swap in real work here.
"""

import hashlib
import time
from collections.abc import Callable

Report = Callable[[int], None]


def sleep(payload: dict, report: Report) -> dict:
    """IO-bound stand-in: wait `seconds` in `steps` increments."""
    seconds = float(payload.get("seconds", 2))
    steps = max(1, int(payload.get("steps", 10)))
    for i in range(1, steps + 1):
        time.sleep(seconds / steps)
        report(int(i * 100 / steps))
    return {"slept": seconds}


def primes(payload: dict, report: Report) -> dict:
    """CPU-bound: count primes below `limit` with a segmented sieve, reporting per segment."""
    limit = int(payload.get("limit", 1_000_000))
    if limit < 2:
        return {"count": 0, "limit": limit}
    segment = 65_536
    count = 0
    for start in range(2, limit, segment):
        end = min(start + segment, limit)
        sieve = bytearray([1]) * (end - start)
        p = 2
        while p * p < end:
            first = max(p * p, (start + p - 1) // p * p)
            sieve[first - start :: p] = bytearray(len(range(first, end, p)))
            p += 1
        count += sum(sieve)
        report(int(end * 100 / limit))
    return {"count": count, "limit": limit}


def checksum(payload: dict, report: Report) -> dict:
    """Hash `text` `rounds` times; a stand-in for processing an upload."""
    text = str(payload.get("text", "")).encode()
    rounds = max(1, int(payload.get("rounds", 1000)))
    digest = text
    for i in range(1, rounds + 1):
        digest = hashlib.sha256(digest).digest()
        if i % max(1, rounds // 20) == 0:
            report(int(i * 100 / rounds))
    return {"sha256": digest.hex(), "rounds": rounds}


HANDLERS: dict[str, Callable[[dict, Report], dict]] = {
    "sleep": sleep,
    "primes": primes,
    "checksum": checksum,
}
