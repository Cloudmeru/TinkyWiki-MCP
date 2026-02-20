from __future__ import annotations

import pytest

from tinkywiki_mcp import session_pool


class _Closable:
    def __init__(self, should_fail: bool = False):
        self.closed = False
        self.should_fail = should_fail

    async def close(self):
        if self.should_fail:
            raise RuntimeError("close fail")
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_pool():
    session_pool._pool.clear()
    yield
    session_pool._pool.clear()


@pytest.mark.asyncio
async def test_close_entry_swallows_errors():
    entry = session_pool._PoolEntry(
        url="https://codewiki.google/github.com/microsoft/vscode",
        context=_Closable(should_fail=True),
        page=_Closable(should_fail=True),
        uses=3,
    )
    await session_pool._close_entry(entry)


@pytest.mark.asyncio
async def test_evict_oldest_removes_first(mocker):
    one = session_pool._PoolEntry("u1", _Closable(), _Closable(), 1)
    two = session_pool._PoolEntry("u2", _Closable(), _Closable(), 1)
    session_pool._pool["u1"] = one
    session_pool._pool["u2"] = two
    closer = mocker.patch("tinkywiki_mcp.session_pool._close_entry")

    await session_pool._evict_oldest()

    assert list(session_pool._pool.keys()) == ["u2"]
    closer.assert_called_once_with(one)


@pytest.mark.asyncio
async def test_get_or_create_reuses_existing():
    entry = session_pool._PoolEntry("u1", _Closable(), _Closable(), 0)
    session_pool._pool["u1"] = entry

    out = await session_pool._get_or_create("u1")

    assert out is entry
    assert out.uses == 1


@pytest.mark.asyncio
async def test_get_or_create_creates_and_evicts(mocker):
    mocker.patch("tinkywiki_mcp.session_pool.config.SESSION_POOL_SIZE", 1)
    old = session_pool._PoolEntry("old", _Closable(), _Closable(), 1)
    session_pool._pool["old"] = old

    async def _fake_evict():
        """Remove the oldest entry so the while-loop terminates."""
        if session_pool._pool:
            session_pool._pool.popitem(last=False)

    evicted = mocker.patch(
        "tinkywiki_mcp.session_pool._evict_oldest", side_effect=_fake_evict
    )
    created = session_pool._PoolEntry("new", _Closable(), _Closable(), 0)
    mocker.patch("tinkywiki_mcp.session_pool._create_entry", return_value=created)

    out = await session_pool._get_or_create("new")

    evicted.assert_called_once()
    assert out.url == "new"
    assert out.uses == 1


@pytest.mark.asyncio
async def test_release_broken_evicts(mocker):
    entry = session_pool._PoolEntry("u1", _Closable(), _Closable(), 2)
    session_pool._pool["u1"] = entry
    closer = mocker.patch("tinkywiki_mcp.session_pool._close_entry")

    await session_pool._release("u1", broken=True)

    assert "u1" not in session_pool._pool
    closer.assert_called_once_with(entry)


@pytest.mark.asyncio
async def test_cleanup_all_closes_and_clears(mocker):
    session_pool._pool["u1"] = session_pool._PoolEntry(
        "u1", _Closable(), _Closable(), 1
    )
    session_pool._pool["u2"] = session_pool._PoolEntry(
        "u2", _Closable(), _Closable(), 1
    )
    closer = mocker.patch("tinkywiki_mcp.session_pool._close_entry")

    await session_pool._cleanup_all()

    assert session_pool._pool == {}
    assert closer.call_count == 2


def test_sync_wrappers_delegate(mocker):
    def _fake_run(coro):
        coro.close()  # Prevent "coroutine was never awaited" warning
        return "ok"

    mocked = mocker.patch(
        "tinkywiki_mcp.session_pool.run_in_browser_loop", side_effect=_fake_run
    )

    out = session_pool.get_or_create_session("u")
    assert out == "ok"

    session_pool.release_session("u", broken=True)
    session_pool.cleanup_pool()

    assert mocked.call_count == 3


def test_pool_stats_shape():
    stats = session_pool.pool_stats()
    assert "size" in stats
    assert "max_size" in stats
    assert "urls" in stats
