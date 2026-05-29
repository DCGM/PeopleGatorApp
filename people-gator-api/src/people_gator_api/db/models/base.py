from collections.abc import Callable
from functools import lru_cache
import uuid

import uuid6
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


@lru_cache(maxsize=1)
def get_clock_seq() -> Callable[[], int]:
    """Return a function that generates a random clock sequence for UUID version 6.

    The clock sequence is a 14-bit value that is used to help ensure uniqueness
    of UUIDs generated on the same timestamp. It should be randomly generated
    once per process and then reused for all subsequent UUID generation.

    This function uses an LRU cache to ensure that the random clock sequence is
    generated only once per process and then reused for all subsequent calls.
    """
    starting_clock_seq = uuid6.uuid6().clock_seq
    def generate_clock_seq() -> int:
        nonlocal starting_clock_seq
        starting_clock_seq = (starting_clock_seq + 1) % 0x4000
        return starting_clock_seq 
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
    return uuid6.uuid6().node

def new_uuid6() -> uuid.UUID:
    """Return a new UUID version 6 (time-ordered, k-sortable, Gregorian epoch)."""
    clock_seq = get_clock_seq()()
    node = get_node()
    return uuid6.uuid6(clock_seq=clock_seq, node=node)
