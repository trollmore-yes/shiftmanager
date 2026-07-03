import logging

import discord
from discord.ext import commands

log = logging.getLogger(__name__)


class ConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(
        name="setchannel",
        description="Set the channel for daily reminders and weekly wrapups",
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def setchannel(
        self,
        ctx: discord.ApplicationContext,
        channel: discord.Option(discord.TextChannel, description="The reminder channel"),
    ):
        await ctx.defer()
        await self.bot.db.set_reminder_channel(ctx.guild_id, channel.id)
        await ctx.respond(f"Reminder channel set to {channel.mention}")
