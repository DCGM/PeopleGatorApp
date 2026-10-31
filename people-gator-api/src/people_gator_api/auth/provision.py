"""Explicit one-time account/actor bridge; never imported by the running issuer."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from people_gator_api.auth.accounts import Account, _adapter
from people_gator_api.auth.settings import settings as auth_settings


async def provision(source: Path):
    from people_gator_api.schemas.users import UserCreateRequest
    from people_gator_api.services.database_service import init_db, close_db, get_database_context
    records = json.loads(source.read_bytes())
    destination = auth_settings.state_dir / "accounts.json"
    existing = _adapter.validate_json(destination.read_bytes()) if destination.exists() else {}
    await init_db()
    try:
        async with get_database_context() as database:
            for username, record in records.items():
                if username in existing:
                    continue
                user = await database.users.get_or_create(UserCreateRequest(
                    display_name=username, is_active=True,
                    external_subject=username, external_issuer=auth_settings.issuer,
                ))
                existing[username] = Account(hash=record["hash"], scopes=record["scopes"],
                                            user_id=user.user_id, is_active=user.is_active)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        with temporary.open("w") as stream:
            os.chmod(temporary, 0o600)
            stream.write(_adapter.dump_json(existing).decode())
        temporary.replace(destination)
    finally:
        await close_db()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("users", type=Path, help="Retained or explicitly supplied credential JSON")
    asyncio.run(provision(parser.parse_args().users))


if __name__ == "__main__":
    main()
