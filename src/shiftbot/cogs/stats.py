import io
import logging
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from shiftbot.config import tz
from shiftbot.timeutil import now, week_start

log = logging.getLogger(__name__)


class StatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(name="trend", description="Show weekly word counts for the past 6 weeks")
    async def trend(self, ctx: discord.ApplicationContext):
        if ctx.guild_id is None:
            await ctx.respond("❌ This command can only be used in a server.")
            return
        await ctx.defer()
        now_dt = now(tz())
        ws = week_start(now_dt)
        six_weeks_ago_ts = (ws - timedelta(weeks=6)).timestamp()

        shifts = await self.bot.db.fetchall(
            "SELECT start_ts, final_wc, start_wc FROM shifts"
            " WHERE guild_id=? AND active=0 AND start_ts>=? AND final_wc IS NOT NULL"
            " ORDER BY start_ts",
            (ctx.guild_id, six_weeks_ago_ts),
        )

        if not shifts:
            await ctx.respond("No completed shifts yet.")
            return

        weekly = {}
        for s in shifts:
            dt = datetime.fromtimestamp(s["start_ts"], tz())
            wk = week_start(dt).strftime("%Y-%m-%d")
            delta = (s["final_wc"] or 0) - (s["start_wc"] or 0)
            weekly[wk] = weekly.get(wk, 0) + delta

        sorted_weeks = sorted(weekly.items())
        max_total = max(t for _, t in sorted_weeks) or 1
        bar_width = 20
        lines = ["📊 **Weekly Word Count Trend**\n"]
        for label, total in sorted_weeks:
            filled = int((total / max_total) * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            lines.append(f"`{label:>10}` {bar} **{total}**")

        await ctx.respond("\n".join(lines))

    @discord.slash_command(name="history", description="Export word count history as a text file")
    async def history(
        self,
        ctx: discord.ApplicationContext,
        mode: discord.Option(
            str, description="Detail level",
            choices=["simple", "verbose"], default="verbose",
        ) = "verbose",
        start: discord.Option(
            str, description="Start date YYYY-MM-DD (optional)",
            required=False, default=None,
        ) = None,
        end: discord.Option(
            str, description="End date YYYY-MM-DD (default today)",
            required=False, default=None,
        ) = None,
    ):
        await ctx.defer()

        now_dt = now(tz())
        start_str = start or "2000-01-01"
        end_str = end or now_dt.strftime("%Y-%m-%d")

        # Convert date strings to timestamps (timezone-aware)
        try:
            from datetime import date as date_class
            sy, sm, sd = map(int, start_str.split("-"))
            ey, em, ed = map(int, end_str.split("-"))
            start_date = date_class(sy, sm, sd)
            end_date = date_class(ey, em, ed)
            start_ts = datetime.combine(start_date, datetime.min.time(), tzinfo=tz()).timestamp()
            end_ts = datetime.combine(end_date, datetime.min.time(), tzinfo=tz()).timestamp() + 86400
        except (ValueError, IndexError):
            await ctx.respond("❌ Invalid date format. Use YYYY-MM-DD.")
            return

        shifts = await self.bot.db.get_shifts_in_range(ctx.guild_id, start_ts, end_ts)
        deliverables = await self.bot.db.get_deliverables_in_range(ctx.guild_id, start_str, end_str)

        buf = io.StringIO()

        # Header
        buf.write(f"Word Count History — {start_str} to {end_str}\n")
        buf.write("=" * 50 + "\n\n")

        # Weekly & monthly aggregates
        weekly = {}
        monthly = {}
        yearly = {}
        for s in shifts:
            dt = datetime.fromtimestamp(s["start_ts"], tz())
            wk = week_start(dt).strftime("%Y-%m-%d")
            mo = dt.strftime("%Y-%m")
            yr = dt.strftime("%Y")
            delta = (s["final_wc"] or 0) - (s["start_wc"] or 0)
            weekly[wk] = weekly.get(wk, 0) + delta
            monthly[mo] = monthly.get(mo, 0) + delta
            yearly[yr] = yearly.get(yr, 0) + delta

        if weekly:
            buf.write("Weekly Totals:\n")
            for wk, total in sorted(weekly.items()):
                buf.write(f"  {wk}: {total} words\n")
            buf.write("\n")

        if monthly:
            buf.write("Monthly Totals:\n")
            for mo, total in sorted(monthly.items()):
                buf.write(f"  {mo}: {total} words\n")
            buf.write("\n")

        if yearly:
            buf.write("Yearly Totals:\n")
            for yr, total in sorted(yearly.items()):
                buf.write(f"  {yr}: {total} words\n")
            buf.write("\n")

        # Deliverables
        if deliverables:
            buf.write("Deliverables / Chapter Deadlines:\n")
            for d in deliverables:
                status = "✅ Complete" if d["completed"] else "⏳ Pending"
                wc_info = f" — {d['wc']} words" if d["wc"] is not None else ""
                buf.write(f"  {d['name']}: due {d['deadline']} [{status}]{wc_info}\n")
            buf.write("\n")

        # Verbose: individual shifts
        if mode == "verbose" and shifts:
            buf.write("Individual Shifts:\n")
            for s in shifts:
                dt = datetime.fromtimestamp(s["start_ts"], tz()).strftime("%Y-%m-%d %H:%M")
                wc = s["final_wc"] or 0
                start_wc = s["start_wc"] or 0
                buf.write(f"  [{dt}] start={start_wc} final={wc} delta={wc - start_wc}\n")

        content = buf.getvalue()
        buf.close()

        if not content.strip():
            await ctx.respond("No data found in the given range.")
            return

        file = discord.File(
            io.BytesIO(content.encode("utf-8")),
            filename=f"wordcount_history_{start_str}_to_{end_str}.txt",
        )
        await ctx.respond(file=file)
