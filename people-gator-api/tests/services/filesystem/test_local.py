import io
import json
from pathlib import Path

import pytest

from people_gator_api.filesystem import Filesystem, FilesystemEntry, LocalFilesystem


@pytest.mark.asyncio
async def test_bytes_round_trip_and_overwrite(tmp_path: Path) -> None:
    fs = LocalFilesystem(tmp_path / "storage")
    assert isinstance(fs, Filesystem)
    await fs.write_bytes("nested/data.bin", b"\x00\xfflong content")
    assert await fs.read_bytes("nested/data.bin") == b"\x00\xfflong content"
    await fs.write_bytes("nested/data.bin", b"short")
    assert await fs.read_bytes("nested/data.bin") == b"short"
    await fs.write_bytes("empty.bin", b"")
    assert await fs.read_bytes("empty.bin") == b""
    assert not list(fs.root.rglob(".filesystem-*"))


@pytest.mark.asyncio
async def test_file_contexts_are_compatible_with_sync_consumers(tmp_path: Path) -> None:
    fs = LocalFilesystem(tmp_path)
    payload = {"name": "Žluťoučký"}
    async with fs.open_file("data.json", "w") as file:
        assert isinstance(file, io.StringIO)
        json.dump(payload, file, ensure_ascii=False)
        assert not (tmp_path / "data.json").exists()
    async with fs.open_file("data.json", "r") as file:
        assert json.load(file) == payload
    async with fs.open_file("data.bin", "wb") as file:
        file.write(b"\xff\x00")
    async with fs.open_file("data.bin") as file:
        assert isinstance(file, io.BytesIO)
        assert file.read() == b"\xff\x00"


@pytest.mark.asyncio
async def test_writes_commit_on_body_error_like_s3(tmp_path: Path) -> None:
    fs = LocalFilesystem(tmp_path)
    with pytest.raises(RuntimeError):
        async with fs.open_file("data.txt", "w") as file:
            file.write("saved")
            raise RuntimeError("body failed")
    assert await fs.read_bytes("data.txt") == b"saved"


@pytest.mark.asyncio
async def test_directory_and_fnmatch_semantics(tmp_path: Path) -> None:
    fs = LocalFilesystem(tmp_path)
    await fs.write_bytes("data/a.txt", b"a")
    await fs.write_bytes("data/nested/b.txt", b"bb")
    await fs.write_bytes("data/nested/c.json", b"{}")
    assert await fs.lsdir() == [FilesystemEntry("data/", True, None)]
    assert await fs.lsdir("data/") == [
        FilesystemEntry("data/a.txt", False, 1),
        FilesystemEntry("data/nested/", True, None),
    ]
    assert [entry.key for entry in await fs.glob("data/*.txt")] == [
        "data/a.txt", "data/nested/b.txt",
    ]
    assert await fs.glob("data/nested/[b].txt") == [FilesystemEntry("data/nested/b.txt", False, 2)]
    assert await fs.glob("data/a.txt") == [FilesystemEntry("data/a.txt", False, 1)]
    assert await fs.glob("missing/*") == []


@pytest.mark.asyncio
async def test_missing_files_and_invalid_keys(tmp_path: Path) -> None:
    fs = LocalFilesystem(tmp_path / "storage")
    with pytest.raises(FileNotFoundError):
        await fs.read_bytes("missing.bin")
    for key in ("../escape", "/absolute", "nested/../../escape"):
        with pytest.raises(ValueError):
            await fs.write_bytes(key, b"invalid")
        with pytest.raises(ValueError):
            await fs.read_bytes(key)
        with pytest.raises(ValueError):
            await fs.lsdir(key)
        with pytest.raises(ValueError):
            await fs.glob(key)
    assert not (tmp_path / "escape").exists()


@pytest.mark.asyncio
async def test_symlink_cannot_escape_root(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    (root / "outside").symlink_to(tmp_path, target_is_directory=True)
    fs = LocalFilesystem(root)
    with pytest.raises(ValueError):
        await fs.write_bytes("outside/escape", b"invalid")
    assert not (tmp_path / "escape").exists()


@pytest.mark.asyncio
async def test_failed_aio_write_preserves_original_and_cleans_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aiofile import AIOFile

    fs = LocalFilesystem(tmp_path)
    await fs.write_bytes("file.bin", b"original")

    async def fail(*args: object, **kwargs: object) -> int:
        raise OSError("write failed")

    monkeypatch.setattr(AIOFile, "write", fail)
    with pytest.raises(OSError, match="write failed"):
        await fs.write_bytes("file.bin", b"replacement")
    assert await fs.read_bytes("file.bin") == b"original"
    assert not list(tmp_path.glob(".filesystem-*"))
