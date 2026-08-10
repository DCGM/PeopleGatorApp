from collections.abc import Callable
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from functools import lru_cache
import uuid
import uuid6


def uuid6_to_datetime(value: uuid.UUID) -> datetime:
    """Convert a UUIDv6's embedded timestamp to a timezone-aware datetime."""
    gregorian_epoch = datetime(1582, 10, 15, tzinfo=timezone.utc)
    return gregorian_epoch + timedelta(microseconds=value.time // 10)


@lru_cache(maxsize=1)
def get_clock_seq() -> Callable[[], int]:
    """Return a function that generates a random clock sequence for UUID version 6.

    The clock sequence is a 14-bit value that is used to help ensure uniqueness
    of UUIDs generated on the same timestamp. It should be randomly generated
    once per process and then reused for all subsequent UUID generation.

    This function uses an LRU cache to ensure that the random clock sequence is
    generated only once per process and then reused for all subsequent calls.
    """
    last_uuid = uuid6.uuid6()
    last_time = last_uuid.time
    last_clock_seq = 0

    def generate_clock_seq() -> int:
        nonlocal last_clock_seq
        nonlocal last_time
        current_uuid = uuid6.uuid6()
        current_time = current_uuid.time
        if current_time == last_time:
            last_clock_seq = (last_clock_seq + 1) & 0x3FFF  # 14 bits
        else:
            last_clock_seq = 0
            last_time = current_time
        return last_clock_seq

    return generate_clock_seq


@lru_cache(maxsize=1)
def get_node() -> int:
    """Return a random 48-bit node value for UUID version 6.

    The node value is a 48-bit value that is used to help ensure uniqueness
    of UUIDs generated on different machines. It should be randomly generated
    once per process and then reused for all subsequent UUID generation.

    This function uses an LRU cache to ensure that the random node value is
    generated only once per process and then reused for all subsequent calls.
    """
    node = uuid.getnode() & 0xFFFFFFFFFFFF  # 48 bits
    return node


def new_uuid6() -> uuid.UUID:
    """Return a new UUID version 6 (time-ordered, k-sortable, Gregorian epoch)."""
    clock_seq = get_clock_seq()()
    node = get_node()
    return uuid6.uuid6(clock_seq=clock_seq, node=node)
