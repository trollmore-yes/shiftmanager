import logging

import discord
from discord.ext import commands

from shiftbot.config import tz
from shiftbot.parsing import parse_duration
from shiftbot.timeutil import now

log = logging.getLogger(__name__)


class ShiftCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(name="shift", description="Start a writing shift")
    async def shift(
        self,
        ctx: discord.ApplicationContext,
        length: discord.Option(str, description="Shift length e.g. 1h30m"),
        goal: discord.Option(int, description="Word count goal for this shift"),
        starting: discord.Option(int, description="Starting word count", required=False, default=0),
        every: discord.Option(str, description="Update frequency e.g. 30m", required=False, default="30m"),
    ):
        if ctx.guild_id is None:
            await ctx.respond("❌ This command can only be used in a server.")
            return
        await ctx.defer()
        try:
            length_min = parse_duration(length)
            freq_min = parse_duration(every)
        except ValueError as e:
            await ctx.respond(f"❌ {e}")
            return

        if length_min <= 0 or freq_min <= 0:
            await ctx.respond("❌ Length and frequency must be positive.")
            return

        if goal <= 0:
            await ctx.respond("❌ Word count goal must be positive.")
            return

        if starting < 0:
            await ctx.respond("❌ Starting word count cannot be negative.")
            return

        existing = await self.bot.db.get_active_shift(ctx.author.id, ctx.guild_id)
        if existing is not None:
            await ctx.respond(
                "❌ You already have an active shift! End it with `/endshift` first."
            )
            return

        start_ts = now(tz()).timestamp()
        end_ts = start_ts + length_min * 60
        freq_sec = freq_min * 60

        await self.bot.db.create_shift(
            user_id=ctx.author.id,
            guild_id=ctx.guild_id,
            start_ts=start_ts,
            end_ts=end_ts,
            wc_goal=goal,
            start_wc=starting,
            update_freq=freq_sec,
            channel_id=ctx.channel_id,
        )

        rate_needed = goal / length_min if length_min > 0 else 0
        await ctx.respond(
            f"✅ **Shift started!**\n"
            f"Length: **{length_min} min** | Goal: **{goal} words**\n"
            f"Starting at: **{starting}** | Update every **{freq_min} min**\n"
            f"Required pace: **{rate_needed:.1f} words/min**\n"
            f"I'll ping you here for updates. Good luck! 🚀"
        )

    @discord.slash_command(name="words", description="Report your current word count")
    async def words(
        self,
        ctx: discord.ApplicationContext,
        wc: discord.Option(int, description="Your current total word count"),
    ):
        if ctx.guild_id is None:
            await ctx.respond("❌ This command can only be used in a server.")
            return
        await ctx.defer()
        shift = await self.bot.db.get_active_shift(ctx.author.id, ctx.guild_id)
        if shift is None:
            await ctx.respond("❌ You don't have an active shift. Start one with `/shift`.")
            return

        now_ts = now(tz()).timestamp()
        elapsed = now_ts - shift["start_ts"]

        if elapsed <= 0:
            projected = shift["start_wc"] + shift["wc_goal"]
            await ctx.respond(f"📝 Just started! Current: **{wc}**. Goal by end: **{projected}**.")
            await self.bot.db.update_last_wc(shift["id"], wc, now_ts)
            return

        rate = (wc - shift["start_wc"]) / elapsed
        total_length = shift["end_ts"] - shift["start_ts"]
        projected_end_wc = shift["start_wc"] + rate * total_length

        remaining_wc = shift["wc_goal"] - (wc - shift["start_wc"])
        if remaining_wc < 0:
            remaining_wc = 0
        remaining_time = shift["end_ts"] - now_ts
        remaining_min = remaining_time / 60

        pace_needed = remaining_wc / remaining_min if remaining_min > 0 else 0
        current_pace = rate * 60  # words per minute

        if projected_end_wc >= shift["start_wc"] + shift["wc_goal"]:
            status = "✅ **On track!**"
        elif current_pace > 0:
            status = "⚠️ **Behind** — pick up the pace!"
        else:
            status = "ℹ️ Getting started..."

        await ctx.respond(
            f"📝 **Word count update**\n"
            f"Current: **{wc}** (Δ **{wc - shift['start_wc']}** from start)\n"
            f"Projected end: **{projected_end_wc:.0f}** (goal: **{shift['start_wc'] + shift['wc_goal']}**)\n"
            f"Pace: **{current_pace:.1f}** wpm | Needed: **{pace_needed:.1f}** wpm\n"
            f"{status}"
        )
        await self.bot.db.update_last_wc(shift["id"], wc, now_ts)

    @discord.slash_command(name="endshift", description="End your active shift early")
    async def endshift(self, ctx: discord.ApplicationContext):
        if ctx.guild_id is None:
            await ctx.respond("❌ This command can only be used in a server.")
            return
        await ctx.defer()
        shift = await self.bot.db.get_active_shift(ctx.author.id, ctx.guild_id)
        if shift is None:
            await ctx.respond("❌ You don't have an active shift.")
            return

        await self.bot.conclude_shift(shift)
        await ctx.respond("🏁 Shift ended early.")
