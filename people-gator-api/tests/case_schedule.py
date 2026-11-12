"""Order collected cases so slow ones neither cluster nor land on one shard."""

from collections.abc import Callable, Sequence


def schedule[T](
    items: Sequence[T], tier: Callable[[T], int], shard: tuple[int, int] | None,
) -> list[T]:
    """Select shard ``(index, count)`` and spread each cost tier evenly.

    ``tier`` groups cases of similar cost (0 for fast cases). Round robin over
    each tier in turn, heaviest first, gives every shard an equal share of
    each. Within the selection every tier keeps collection order and is evenly
    spaced, so each xdist worker's initial share holds some slow cases and the
    progress counter (which counts cases) tracks elapsed time.
    """
    tiers: dict[int, list[T]] = {}
    for item in items:
        tiers.setdefault(tier(item), []).append(item)
    groups = [tiers[key] for key in sorted(tiers, reverse=True)]
    if shard is not None:
        index, count = shard
        selected, offset = [], 0
        for group in groups:
            # Continue the round robin where the previous tier stopped.
            selected.append(group[(index - 1 - offset) % count::count])
            offset += len(group)
        groups = selected
    # Place the jth of n cases of each tier at fraction (j + 0.5) / n of the run.
    keyed = [
        ((j + 0.5) / len(group), rank, item)
        for rank, group in enumerate(groups) for j, item in enumerate(group)
    ]
    return [item for *_, item in sorted(keyed, key=lambda entry: entry[:2])]
