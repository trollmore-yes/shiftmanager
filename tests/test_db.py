import pytest

from shiftbot.db import Database


@pytest.fixture
async def db():
    import tempfile
    import os
    tmp = tempfile.mktemp(suffix=".db")
    d = Database(db_path=tmp)
    await d.connect()
    yield d
    await d._conn.close()
    os.unlink(tmp)


@pytest.mark.asyncio
async def test_create_and_conclude_shift(db):
    shift_id = await db.create_shift(
        user_id=1, guild_id=10,
        start_ts=1000.0, end_ts=2000.0,
        wc_goal=500, start_wc=0,
        update_freq=600, channel_id=100,
    )
    assert shift_id is not None

    active = await db.get_active_shift(1, 10)
    assert active is not None
    assert active["wc_goal"] == 500

    ended = await db.get_ended_shifts(3000.0)
    assert len(ended) == 1
    assert ended[0]["id"] == shift_id

    await db.update_last_wc(shift_id, 400, 1500.0)
    await db.conclude_shift(shift_id, 400)

    active2 = await db.get_active_shift(1, 10)
    assert active2 is None


@pytest.mark.asyncio
async def test_weekly_total(db):
    await db.create_shift(
        user_id=1, guild_id=10,
        start_ts=100.0, end_ts=200.0,
        wc_goal=100, start_wc=500,
        update_freq=600, channel_id=100,
    )
    await db.conclude_shift(1, 580)

    total = await db.get_user_weekly_total(1, 10, 0.0, 1000.0)
    assert total == 80  # delta = 580 - 500

    total_outside = await db.get_user_weekly_total(1, 10, 1000.0, 2000.0)
    assert total_outside == 0


@pytest.mark.asyncio
async def test_extend_active_shift(db):
    shift_id = await db.create_shift(
        user_id=1, guild_id=10,
        start_ts=1000.0, end_ts=1600.0,
        wc_goal=500, start_wc=100,
        update_freq=600, channel_id=100,
    )

    await db.extend_shift(shift_id, 1800, 250)

    active = await db.get_active_shift(1, 10)
    assert active is not None
    assert active["end_ts"] == 3400.0
    assert active["wc_goal"] == 750


@pytest.mark.asyncio
async def test_deliverables(db):
    rid = await db.create_deliverable(1, 10, "Chapter 1", "2026-08-01")
    assert rid is not None

    dup = await db.create_deliverable(1, 10, "Chapter 1", "2026-08-15")
    assert dup is None

    items = await db.get_incomplete_deliverables(1, 10)
    assert len(items) == 1
    assert items[0]["name"] == "Chapter 1"

    await db.complete_deliverable(1, 10, "Chapter 1", 5000)
    items2 = await db.get_incomplete_deliverables(1, 10)
    assert len(items2) == 0


@pytest.mark.asyncio
async def test_delete_incomplete_deliverable(db):
    await db.create_deliverable(1, 10, "Chapter 1", "2026-08-01")
    await db.create_deliverable(1, 10, "Chapter 2", "2026-08-15")

    deleted = await db.delete_deliverable(1, 10, "Chapter 1")
    assert deleted == 1

    items = await db.get_incomplete_deliverables(1, 10)
    assert len(items) == 1
    assert items[0]["name"] == "Chapter 2"


@pytest.mark.asyncio
async def test_delete_completed_deliverable_does_not_remove_it(db):
    await db.create_deliverable(1, 10, "Chapter 1", "2026-08-01")
    await db.complete_deliverable(1, 10, "Chapter 1", 5000)

    deleted = await db.delete_deliverable(1, 10, "Chapter 1")
    assert deleted == 0


@pytest.mark.asyncio
async def test_guild_settings(db):
    await db.set_reminder_channel(10, 999)
    ch = await db.get_reminder_channel(10)
    assert ch == 999

    ch_missing = await db.get_reminder_channel(99)
    assert ch_missing is None
