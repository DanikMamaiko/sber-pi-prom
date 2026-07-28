import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://sberpi:sberpi@localhost:5433/sberpi_test",
)
database_name = urlparse(TEST_DATABASE_URL.replace("postgresql+asyncpg", "postgresql")).path.lstrip("/")
if not database_name.endswith("_test"):
    raise RuntimeError("Integration tests may only use a database whose name ends with _test")

# Alembic and the application settings must resolve the dedicated test DB before
# importing app.main/app.db.session.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ENV"] = "test"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.base import Base  # noqa: E402
import app.models  # noqa: E402,F401
from app.db.session import get_session  # noqa: E402
from app.main import app  # noqa: E402


engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
SessionForTests = async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def migrate_test_database() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    command.upgrade(config, "head")


@pytest_asyncio.fixture(autouse=True)
async def clean_test_database(migrate_test_database: None) -> AsyncIterator[None]:
    table_names = [table.name for table in reversed(Base.metadata.sorted_tables)]
    quoted = ", ".join(f'"{name}"' for name in table_names)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
    yield
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture(scope="session", autouse=True)
async def dispose_test_engine(migrate_test_database: None) -> AsyncIterator[None]:
    yield
    await engine.dispose()


async def override_session() -> AsyncIterator[AsyncSession]:
    async with SessionForTests() as session:
        yield session


class VersionedApiClient:
    """Test client that behaves like the UI and carries the latest aggregate version."""

    def __init__(self, raw: AsyncClient):
        self.raw = raw

    def __getattr__(self, name):
        return getattr(self.raw, name)

    async def _cycle_version(self, path: str) -> int:
        match = re.match(r"/pi-cycles/([^/]+)", path)
        if match is None:
            raise AssertionError(f"Cannot extract cycle ID from {path}")
        cycle_id = match.group(1)
        response = await self.raw.get("/pi-cycles")
        response.raise_for_status()
        return next(row["version"] for row in response.json() if row["id"] == cycle_id)

    async def _with_version(self, path: str, kwargs: dict, *, backlog: bool = False) -> dict:
        body = dict(kwargs.get("json") or {})
        if "expected_version" not in body:
            if backlog:
                response = await self.raw.get("/backlog-board")
                response.raise_for_status()
                body["expected_version"] = response.json()["version"]
            else:
                body["expected_version"] = await self._cycle_version(path)
        return {**kwargs, "json": body}

    async def put(self, path: str, **kwargs):
        if path == "/backlog-board" or path.startswith("/backlog-board/"):
            kwargs = await self._with_version(path, kwargs, backlog=True)
        elif path.startswith("/pi-cycles/"):
            kwargs = await self._with_version(path, kwargs)
        return await self.raw.put(path, **kwargs)

    async def patch(self, path: str, **kwargs):
        if path.startswith("/backlog-board/"):
            kwargs = await self._with_version(path, kwargs, backlog=True)
        elif path.startswith("/pi-cycles/"):
            kwargs = await self._with_version(path, kwargs)
        return await self.raw.patch(path, **kwargs)

    async def post(self, path: str, **kwargs):
        if path.startswith("/backlog-board/"):
            kwargs = await self._with_version(path, kwargs, backlog=True)
        elif path.startswith("/pi-cycles/") and (
            path.endswith("/backlog/dispatch") or path.endswith("/pre-pi/submit")
        ):
            kwargs = await self._with_version(path, kwargs)
        return await self.raw.post(path, **kwargs)

    async def delete(self, path: str, **kwargs):
        if path.startswith("/backlog-board/"):
            kwargs = await self._with_version(path, kwargs, backlog=True)
        return await self.raw.request("DELETE", path, **kwargs)


@pytest_asyncio.fixture
async def api_client(clean_test_database: None) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver/api",
    ) as client:
        yield VersionedApiClient(client)
    app.dependency_overrides.clear()
