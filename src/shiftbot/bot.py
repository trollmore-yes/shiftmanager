import logging
from datetime import timedelta, date

import discord
from discord.ext import tasks

from shiftbot.config import discord_token, tz, log_level
from shiftbot.db import Database
from shiftbot.timeutil import now, is_noon, week_start

logging.basicConfig(
    level=getattr(logging, log_level().upper(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)


class ShiftBot(discord.Bot):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.db = Database()
        self._last_reminder_date: date | None = None
        self._initialized = False

        from shiftbot.cogs.shift import ShiftCog
        from shiftbot.cogs.deliverables import DeliverablesCog
        from shiftbot.cogs.stats import StatsCog
        from shiftbot.cogs.config_cog import ConfigCog

        self.add_cog(ShiftCog(self))
        self.add_cog(DeliverablesCog(self))
        self.add_cog(StatsCog(self))
        self.add_cog(ConfigCog(self))
        log.info("Cogs loaded (%d application commands pending)", len(self._pending_application_commands))

    async def on_ready(self):
        log.info("Bot logged in as %s", self.user)
        if not self._initialized:
            self._initialized = True
            await self.db.connect()
            self.manage_shifts.start()
            self.daily_reminders.start()
            log.info("Background loops started")
        await self.sync_commands()
        log.info(
            "Slash commands synced (%d registered globally / %d pending)",
            len(self._application_commands),
            len(self._pending_application_commands),
        )
        log.info("Cogs loaded and background loops started")

    # ---- Shift manager: prompt updates & auto-conclude ----

    @tasks.loop(seconds=30)
    async def manage_shifts(self):
        try:
            now_ts = now(tz()).timestamp()

            ended = await self.db.get_ended_shifts(now_ts)
            for row in ended:
                await self.conclude_shift(row)

            needs_prompt = await self.db.get_shifts_needing_prompt(now_ts)
            for row in needs_prompt:
                channel = self.get_channel(row["channel_id"])
                if channel:
                    try:
                        await channel.send(
                            f"<@{row['user_id']}> Time for an update! "
                            f"Use `/words` to report your current word count."
                        )
                    except discord.Forbidden:
                        log.warning("Can't send to channel %s", row["channel_id"])
                await self.db.update_prompt_time(row["id"], now_ts)
        except Exception:
            log.exception("Shift manager loop failed")

    @manage_shifts.before_loop
    async def _before_manage_shifts(self):
        await self.wait_until_ready()

    async def conclude_shift(self, row):
        final_wc = row["last_wc"] if row["last_wc"] is not None else row["start_wc"]
        await self.db.conclude_shift(row["id"], final_wc)
        channel = self.get_channel(row["channel_id"])
        if channel is None:
            return
        delta = final_wc - row["start_wc"]
        now_dt = now(tz())
        ws = week_start(now_dt)
        we = ws + timedelta(days=7)
        ws_ts, we_ts = ws.timestamp(), we.timestamp()
        weekly_total = await self.db.get_user_weekly_total(
            row["user_id"], row["guild_id"], ws_ts, we_ts
        )
        last_week_total = await self.db.get_user_weekly_total(
            row["user_id"], row["guild_id"],
            (ws - timedelta(days=7)).timestamp(), ws_ts,
        )
        try:
            await channel.send(
                f"<@{row['user_id']}> **Shift concluded!**\n"
                f"Words written this shift: **{delta}**\n"
                f"Your total this week: **{weekly_total}**\n"
                f"Your total last week: **{last_week_total}**"
            )
        except discord.Forbidden:
            log.warning("Can't send conclusion to channel %s", row["channel_id"])

    # ---- Daily reminder loop (fires once per day at noon in configured TZ) ----

    @tasks.loop(minutes=1)
    async def daily_reminders(self):
        try:
            n = now(tz())
            if not is_noon(n):
                return
            if n.date() == self._last_reminder_date:
                return
            self._last_reminder_date = n.date()

            settings_list = await self.db.get_all_guild_settings()
            for settings in settings_list:
                channel = self.get_channel(settings["reminder_channel_id"])
                if channel is None:
                    continue

                ws = week_start(n)
                we = ws + timedelta(days=7)
                ws_ts, we_ts = ws.timestamp(), we.timestamp()
                lws = ws - timedelta(days=7)
                lwe = ws
                lws_ts, lwe_ts = lws.timestamp(), lwe.timestamp()

                if n.weekday() == 6:  # Sunday – weekly wrapup
                    last_week_total = await self.db.get_guild_weekly_total(
                        channel.guild.id, lws_ts, lwe_ts
                    )
                    two_weeks = (ws + timedelta(days=14)).strftime("%Y-%m-%d")
                    upcoming = await self.db.get_upcoming_deliverables(
                        channel.guild.id, two_weeks
                    )
                    this_week = []
                    next_week = []
                    week_end_date = (ws + timedelta(days=7)).date()
                    for d in upcoming:
                        try:
                            parts = d["deadline"].split("-")
                            deadline_dt = date(int(parts[0]), int(parts[1]), int(parts[2]))
                        except (IndexError, ValueError):
                            continue
                        if deadline_dt < week_end_date:
                            this_week.append(d)
                        else:
                            next_week.append(d)

                    lines = [f"**Weekly Wrapup** — Last week's total: **{last_week_total}** words"]
                    if this_week:
                        lines.append("\n**Due this week:**")
                        for d in this_week:
                            lines.append(f"  • {d['name']} — due {d['deadline']}")
                    if next_week:
                        lines.append("\n**Due next week:**")
                        for d in next_week:
                            lines.append(f"  • {d['name']} — due {d['deadline']}")
                    try:
                        await channel.send("\n".join(lines))
                    except discord.Forbidden:
                        log.warning("Can't send to channel %s", channel.id)

                elif n.weekday() != 5:  # Mon–Fri (skip Saturday)
                    weekly_total = await self.db.get_guild_weekly_total(
                        channel.guild.id, ws_ts, we_ts
                    )
                    last_week_total = await self.db.get_guild_weekly_total(
                        channel.guild.id, lws_ts, lwe_ts
                    )
                    try:
                        await channel.send(
                            f"**Daily Writing Update**\n"
                            f"This week's total: **{weekly_total}** words\n"
                            f"Last week's total: **{last_week_total}** words"
                        )
                    except discord.Forbidden:
                        log.warning("Can't send to channel %s", channel.id)
        except Exception:
            log.exception("Daily reminder loop failed")

    @daily_reminders.before_loop
    async def _before_daily_reminders(self):
        await self.wait_until_ready()


def main():
    bot = ShiftBot()
    bot.run(discord_token())
