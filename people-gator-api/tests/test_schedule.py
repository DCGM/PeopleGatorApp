"""Protect CI sharding and slow-case spreading without collecting the real suite."""

import pytest

from case_schedule import schedule


def cases(slow: int, fast: int, heavy: int = 0) -> list[str]:
    # Collection order: fast modules first, the slow module last (as in the suite).
    slow_cases = [f"slow{i}" for i in range(slow)]
    for i in range(heavy):  # heavier cases are interleaved in the slow module
        slow_cases.insert(i * 4, f"heavy{i}")
    return [f"fast{i}" for i in range(fast)] + slow_cases


def is_slow(case: str) -> bool:
    return not case.startswith("fast")


def tier(case: str) -> int:
    return 2 if case.startswith("heavy") else int(is_slow(case))


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 6])
def test_shards_partition_the_collection_with_even_tier_shares(count):
    items = cases(slow=82, fast=770, heavy=20)
    shards = [schedule(items, tier, (index, count)) for index in range(1, count + 1)]

    assert sorted(case for shard in shards for case in shard) == sorted(items)
    for level in (1, 2):
        shares = [sum(tier(case) == level for case in shard) for shard in shards]
        assert max(shares) - min(shares) <= 1, level
    assert max(map(len, shards)) - min(map(len, shards)) <= 1


def test_slow_cases_are_spread_through_the_run_in_collection_order():
    items = cases(slow=10, fast=90)
    ordered = schedule(items, tier, None)

    assert sorted(ordered) == sorted(items)
    assert [case for case in ordered if is_slow(case)] == [f"slow{i}" for i in range(10)]
    assert [case for case in ordered if not is_slow(case)] == [f"fast{i}" for i in range(90)]
    # One slow case in every tenth of the run, so no worker's initial share or
    # the progress counter's last 15% holds a cluster of them.
    positions = [index for index, case in enumerate(ordered) if is_slow(case)]
    assert [position // 10 for position in positions] == list(range(10))


@pytest.mark.parametrize("shard", ["0/3", "4/3", "1", "a/b", "1/0"])
def test_invalid_shards_are_rejected(shard):
    from conftest import parse_shard

    with pytest.raises(pytest.UsageError, match="--shard"):
        parse_shard(shard)
