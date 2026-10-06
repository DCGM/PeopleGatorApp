# Filesystem

`Filesystem` is the backend-neutral abstract class. `LocalFilesystem` and
`S3Filesystem` implement `read_bytes`, `write_bytes`, `open_file`, `lsdir`, and
`glob`. Adapters are loaded lazily, following the persistence package pattern.
Importing the local adapter does not load application settings or S3 clients.

```python
import json

from people_gator_api.filesystem import Filesystem, LocalFilesystem

filesystem: Filesystem = LocalFilesystem("./storage")
await filesystem.write_bytes("documents/example.bin", b"example")

async with filesystem.open_file("documents/example.json", "w") as file:
    json.dump({"example": True}, file)

entries = await filesystem.lsdir("documents/")
matching_files = await filesystem.glob("documents/*.json")
```

Keys are relative to the local root or the S3 bucket. Local storage creates
parent directories on writes and rejects absolute paths, parent traversal, and
symlinks resolving outside the root. The root should be managed by trusted code;
path validation is not a security boundary against concurrent symlink changes.

`open_file` yields ordinary `io.BytesIO` / `io.StringIO` buffers so synchronous
consumers such as `json.load` work. Text uses UTF-8. Files are buffered entirely
in memory, matching the original S3 interface. Write modes commit on context
exit even when the body raises, also matching the original interface. Buffers
close on exit.

Local content reads, writes, and fsync use `aiofile.AIOFile`, whose underlying
caio backend selects native Linux AIO where supported and has platform fallbacks.
Directory and metadata operations run through `asyncio.to_thread`; content I/O
does not use that wrapper. Writes use a temporary file in the destination
directory, fsync it, then atomically replace the destination. Filesystem errors
such as `FileNotFoundError` propagate; S3 retains botocore errors.

`lsdir` returns immediate children with full relative keys; directories have
`is_prefix=True`, trailing `/`, and `size=None`. `glob` returns files only,
matching full keys using `fnmatch` (so `*` can match `/`, as it does on S3).

## Configuration and dependency

S3 remains the default backend and requires the existing `storage.s3` credentials.
To use local storage, set:

```dotenv
PEOPLE_GATOR_API__STORAGE__BACKEND=local
PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT=/var/lib/people-gator/storage
```

The local root defaults to `./storage`, relative to the process working directory.
Local mode does not require S3 settings. To select S3, set
`PEOPLE_GATOR_API__STORAGE__BACKEND=s3` and supply the existing S3 settings.

Application media, derivative caches, page layouts, and JWK loading use this
selection through `people_gator_api.services.filesystem_service`. Services can
call `get_filesystem()` directly; FastAPI routes can inject the same provider:

```python
from people_gator_api.services.filesystem_service import FilesystemDependency

@app.get("/stored-content")
async def stored_content(filesystem: FilesystemDependency):
    return {"content": (await filesystem.read_bytes("example.txt")).decode()}
```

FastAPI overrides are supported with
`app.dependency_overrides[get_filesystem] = lambda: test_filesystem` for routes
using the dependency. Direct service calls use current application settings;
patch the provider or settings when testing those calls.

Adapters hold configuration without opening persistent clients, so the provider
returns a fresh instance and requires no request cleanup. The configured helpers
(`read_bytes`, `write_bytes`, `open_file`, `lsdir`, `glob`) are also available from
`filesystem_service` for callers outside FastAPI.

For explicit S3 access, pass `S3Settings` to `S3Filesystem(config)`.
Application callers use the configured `filesystem_service` provider.
