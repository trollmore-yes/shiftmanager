import sqlite3
import time
import logging
from pathlib import Path

import aiosqlite

from shiftbot.config import db_path as _db_path

log = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str | None = None):
        self._conn: aiosqlite.Connection | None = None
        self._db_path = db_path

    async def connect(self):
        path = self._db_path or _db_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(path)
        self._conn.row_factory = sqlite3.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        log.info("Database connected and schema ready")

    async def execute(self, sql: str, params: tuple = ()):
        cur = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cur.lastrowid

    async def fetchone(self, sql: str, params: tuple = ()):
        cur = await self._conn.execute(sql, params)
        return await cur.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()):
        cur = await self._conn.execute(sql, params)
        return await cur.fetchall()

    # -- Shifts --

    async def create_shift(
        self,
        user_id: int,
        guild_id: int,
        start_ts: float,
        end_ts: float,
        wc_goal: int,
        start_wc: int,
        update_freq: int,
        channel_id: int,
    ) -> int:
        return await self.execute(
            """INSERT INTO shifts
               (user_id, guild_id, start_ts, end_ts, wc_goal, start_wc,
                update_freq, channel_id, last_prompt_ts, active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (user_id, guild_id, start_ts, end_ts, wc_goal, start_wc,
             update_freq, channel_id, start_ts),
        )

    async def get_active_shift(self, user_id: int, guild_id: int):
        return await self.fetchone(
            "SELECT * FROM shifts WHERE user_id=? AND guild_id=? AND active=1",
            (user_id, guild_id),
        )

    async def get_shifts_needing_prompt(self, now_ts: float):
        return await self.fetchall(
            "SELECT * FROM shifts WHERE active=1 AND last_prompt_ts + update_freq <= ?",
            (now_ts,),
        )

    async def get_ended_shifts(self, now_ts: float):
        return await self.fetchall(
            "SELECT * FROM shifts WHERE active=1 AND end_ts <= ?",
            (now_ts,),
        )

    async def update_prompt_time(self, shift_id: int, ts: float):
        await self.execute(
            "UPDATE shifts SET last_prompt_ts=? WHERE id=?",
            (ts, shift_id),
        )

    async def update_last_wc(self, shift_id: int, wc: int, ts: float):
        await self.execute(
            "UPDATE shifts SET last_wc=?, last_prompt_ts=? WHERE id=?",
            (wc, ts, shift_id),
        )

    async def extend_shift(self, shift_id: int, added_seconds: int, added_goal: int):
        await self.execute(
            "UPDATE shifts SET end_ts=end_ts + ?, wc_goal=wc_goal + ? WHERE id=?",
            (added_seconds, added_goal, shift_id),
        )

    async def conclude_shift(self, shift_id: int, wc: int):
        await self.execute(
            "UPDATE shifts SET final_wc=?, active=0 WHERE id=?",
            (wc, shift_id),
        )

    async def get_shifts_in_range(self, guild_id: int, start: float, end: float):
        return await self.fetchall(
            "SELECT * FROM shifts WHERE guild_id=? AND start_ts>=? AND start_ts<?"
            " AND active=0 AND final_wc IS NOT NULL ORDER BY start_ts",
            (guild_id, start, end),
        )

    async def get_user_weekly_total(
        self, user_id: int, guild_id: int, week_start_ts: float, week_end_ts: float
    ) -> int:
        row = await self.fetchone(
            "SELECT COALESCE(SUM(final_wc - start_wc), 0) FROM shifts"
            " WHERE user_id=? AND guild_id=? AND active=0"
            " AND start_ts>=? AND start_ts<? AND final_wc IS NOT NULL",
            (user_id, guild_id, week_start_ts, week_end_ts),
        )
        return row[0] if row else 0

    async def get_guild_weekly_total(
        self, guild_id: int, week_start_ts: float, week_end_ts: float
    ) -> int:
        row = await self.fetchone(
            "SELECT COALESCE(SUM(final_wc - start_wc), 0) FROM shifts"
            " WHERE guild_id=? AND active=0"
            " AND start_ts>=? AND start_ts<? AND final_wc IS NOT NULL",
            (guild_id, week_start_ts, week_end_ts),
        )
        return row[0] if row else 0

    # -- Deliverables --

    async def create_deliverable(self, user_id: int, guild_id: int, name: str, deadline: str):
        try:
            return await self.execute(
                "INSERT INTO deliverables (user_id, guild_id, name, deadline) VALUES (?, ?, ?, ?)",
                (user_id, guild_id, name, deadline),
            )
        except sqlite3.IntegrityError:
            return None

    async def complete_deliverable(self, user_id: int, guild_id: int, name: str, wc: int | None):
        await self.execute(
            "UPDATE deliverables SET completed=1, completed_ts=?, wc=? WHERE user_id=? AND guild_id=? AND name=?",
            (time.time(), wc, user_id, guild_id, name),
        )

    async def get_incomplete_deliverables(self, user_id: int, guild_id: int):
        return await self.fetchall(
            "SELECT * FROM deliverables WHERE user_id=? AND guild_id=? AND completed=0 ORDER BY deadline",
            (user_id, guild_id),
        )

    async def get_upcoming_deliverables(self, guild_id: int, end_date: str):
        return await self.fetchall(
            """SELECT * FROM deliverables
               WHERE guild_id=? AND completed=0 AND deadline<=?
               ORDER BY deadline""",
            (guild_id, end_date),
        )

    async def get_deliverables_in_range(self, guild_id: int, start: str, end: str):
        return await self.fetchall(
            "SELECT * FROM deliverables WHERE guild_id=? AND deadline>=? AND deadline<=? ORDER BY deadline",
            (guild_id, start, end),
        )

    # -- Guild settings --

    async def set_reminder_channel(self, guild_id: int, channel_id: int):
        await self.execute(
            "INSERT OR REPLACE INTO guild_settings (guild_id, reminder_channel_id) VALUES (?, ?)",
            (guild_id, channel_id),
        )

    async def get_reminder_channel(self, guild_id: int) -> int | None:
        row = await self.fetchone(
            "SELECT reminder_channel_id FROM guild_settings WHERE guild_id=?",
            (guild_id,),
        )
        return row["reminder_channel_id"] if row else None

    async def get_all_guild_settings(self):
        return await self.fetchall("SELECT * FROM guild_settings")


SCHEMA = """
CREATE TABLE IF NOT EXISTS shifts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  guild_id INTEGER NOT NULL,
  start_ts REAL NOT NULL,
  end_ts REAL NOT NULL,
  wc_goal INTEGER,
  start_wc INTEGER DEFAULT 0,
  update_freq INTEGER DEFAULT 1800,
  last_wc INTEGER,
  final_wc INTEGER,
  channel_id INTEGER,
  last_prompt_ts REAL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_shifts_user ON shifts(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_shifts_guild_ts ON shifts(guild_id, start_ts);

CREATE TABLE IF NOT EXISTS deliverables (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  guild_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  deadline TEXT NOT NULL,
  completed INTEGER NOT NULL DEFAULT 0,
  completed_ts REAL,
  wc INTEGER,
  UNIQUE(user_id, guild_id, name)
);
CREATE INDEX IF NOT EXISTS idx_deliv_guild ON deliverables(guild_id);

CREATE TABLE IF NOT EXISTS guild_settings (
  guild_id INTEGER PRIMARY KEY,
  reminder_channel_id INTEGER
);
"""
