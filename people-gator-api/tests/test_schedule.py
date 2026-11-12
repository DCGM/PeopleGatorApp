"""Protect CI sharding and slow-case spreading without collecting the real suite."""

import pytest

from case_schedule import schedule


def cases(slow: int, fast: int) -> list[str]:
    # Collection order: fast modules first, the slow module last (as in the suite).
    return [f"fast{i}" for i in range(fast)] + [f"slow{i}" for i in range(slow)]


def is_slow(case: str) -> bool:
    return case.startswith("slow")


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5])
def test_shards_partition_the_collection_with_even_slow_shares(count):
    items = cases(slow=101, fast=770)
    shards = [schedule(items, is_slow, (index, count)) for index in range(1, count + 1)]

    assert sorted(case for shard in shards for case in shard) == sorted(items)
    slow_shares = [sum(map(is_slow, shard)) for shard in shards]
    assert max(slow_shares) - min(slow_shares) <= 1
    assert max(map(len, shards)) - min(map(len, shards)) <= 1


def test_slow_cases_are_spread_through_the_run_in_collection_order():
    items = cases(slow=10, fast=90)
    ordered = schedule(items, is_slow, None)

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
