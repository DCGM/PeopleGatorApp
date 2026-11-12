"""Order collected cases so slow ones neither cluster nor land on one shard."""

from collections.abc import Callable, Sequence


def schedule[T](
    items: Sequence[T], is_slow: Callable[[T], bool], shard: tuple[int, int] | None,
) -> list[T]:
    """Select shard ``(index, count)`` and spread its slow cases evenly.

    Round robin over slow cases, then fast cases, gives every shard an equal
    share of each. Within the selection both groups keep collection order and
    slow cases are evenly spaced, so each xdist worker's initial share holds
    some and the progress counter (which counts cases) tracks elapsed time.
    """
    slow = [item for item in items if is_slow(item)]
    fast = [item for item in items if not is_slow(item)]
    if shard is not None:
        index, count = shard
        # Continue fast cases' round robin where the slow cases' one stopped.
        slow, fast = slow[index - 1::count], fast[(index - 1 - len(slow)) % count::count]
    # Place the jth of n cases of each group at fraction (j + 0.5) / n of the run.
    keyed = [((j + 0.5) / len(slow), 0, item) for j, item in enumerate(slow)]
    keyed += [((j + 0.5) / len(fast), 1, item) for j, item in enumerate(fast)]
    return [item for *_, item in sorted(keyed, key=lambda entry: entry[:2])]
