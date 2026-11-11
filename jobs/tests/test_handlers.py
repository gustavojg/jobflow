import pytest

from jobs.handlers import HANDLERS, checksum, primes


def naive_prime_count(limit: int) -> int:
    return sum(all(n % d for d in range(2, int(n**0.5) + 1)) for n in range(2, limit))


@pytest.mark.parametrize("limit", [0, 2, 3, 100, 1000, 70_000, 200_000])
def test_primes_matches_naive(limit):
    assert primes({"limit": limit}, lambda _: None)["count"] == naive_prime_count(limit)


def test_primes_reports_monotonic_progress_ending_at_100():
    seen = []
    primes({"limit": 300_000}, seen.append)
    assert seen == sorted(seen)
    assert seen[-1] == 100


def test_checksum_is_deterministic():
    a = checksum({"text": "hola", "rounds": 50}, lambda _: None)
    b = checksum({"text": "hola", "rounds": 50}, lambda _: None)
    assert a == b and len(a["sha256"]) == 64


def test_every_handler_is_registered_with_a_name():
    assert set(HANDLERS) == {"sleep", "primes", "checksum"}
