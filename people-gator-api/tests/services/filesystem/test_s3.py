from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from people_gator_api.filesystem import FilesystemEntry, S3Filesystem
from people_gator_api.settings import S3Settings


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> tuple[S3Filesystem, MagicMock]:
    filesystem = S3Filesystem(S3Settings(
        access_key_id="test", secret_access_key="test",
        bucket_name="test-bucket", region="eu-central-1",
    ))
    client = MagicMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(filesystem, "_client", lambda: context)
    return filesystem, client


@pytest.mark.asyncio
async def test_s3_byte_io_and_buffered_contexts(adapter: tuple[S3Filesystem, MagicMock]) -> None:
    filesystem, client = adapter
    body = MagicMock()
    body.read = AsyncMock(return_value=b"hello")
    client.get_object = AsyncMock(return_value={"Body": body})
    client.put_object = AsyncMock()
    async with filesystem.open_file("data.txt", "r") as file:
        assert file.read() == "hello"
    client.get_object.assert_awaited_once_with(Bucket="test-bucket", Key="data.txt")
    async with filesystem.open_file("data.txt", "w") as file:
        file.write("Žluťoučký")
    client.put_object.assert_awaited_once_with(
        Bucket="test-bucket", Key="data.txt", Body="Žluťoučký".encode(),
    )


@pytest.mark.asyncio
async def test_s3_paginated_listings(adapter: tuple[S3Filesystem, MagicMock]) -> None:
    filesystem, client = adapter

    async def pages(**kwargs: object) -> AsyncIterator[dict[str, object]]:
        yield {"Contents": [{"Key": "data/a.txt", "Size": 1}]}
        yield {
            "Contents": [{"Key": "data/nested/b.json", "Size": 2}],
            "CommonPrefixes": [{"Prefix": "data/nested/"}],
        }

    paginator = MagicMock()
    paginator.paginate.side_effect = pages
    client.get_paginator.return_value = paginator
    assert await filesystem.lsdir("data/") == [
        FilesystemEntry("data/a.txt", False, 1),
        FilesystemEntry("data/nested/b.json", False, 2),
        FilesystemEntry("data/nested/", True, None),
    ]
    paginator.paginate.assert_called_with(
        Bucket="test-bucket", Prefix="data/", Delimiter="/",
    )
    assert await filesystem.glob("data/*.txt") == [FilesystemEntry("data/a.txt", False, 1)]
    paginator.paginate.assert_called_with(Bucket="test-bucket", Prefix="data/")
