import logging
from datetime import date as date_class

import discord
from discord.ext import commands

log = logging.getLogger(__name__)


class DeliverablesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(name="deadline", description="Add a chapter deliverable with a due date")
    async def deadline(
        self,
        ctx: discord.ApplicationContext,
        name: discord.Option(str, description="Chapter / deliverable name"),
        due: discord.Option(str, description="Due date YYYY-MM-DD"),
    ):
        await ctx.defer()
        try:
            parts = due.split("-")
            date_class(int(parts[0]), int(parts[1]), int(parts[2]))
        except (IndexError, ValueError):
            await ctx.respond("❌ Invalid date format. Use YYYY-MM-DD.")
            return
        row_id = await self.bot.db.create_deliverable(ctx.author.id, ctx.guild_id, name, due)
        if row_id is None:
            await ctx.respond(f"❌ Deliverable **{name}** already exists for you.")
        else:
            await ctx.respond(f"✅ Deliverable **{name}** set with due date **{due}**.")

    @discord.slash_command(name="submit", description="Mark a deliverable as complete")
    async def submit(
        self,
        ctx: discord.ApplicationContext,
        name: discord.Option(str, description="Deliverable name"),
        wc: discord.Option(int, description="Word count for this deliverable", required=False, default=None) = None,
    ):
        await ctx.defer()
        items = await self.bot.db.get_incomplete_deliverables(ctx.author.id, ctx.guild_id)
        found = any(r["name"] == name for r in items)
        if not found:
            await ctx.respond(f"❌ No incomplete deliverable named **{name}** found.")
            return
        await self.bot.db.complete_deliverable(ctx.author.id, ctx.guild_id, name, wc)
        parts = [f"✅ **{name}** marked as complete!"]
        if wc is not None:
            parts.append(f"Word count logged: **{wc}**")
        await ctx.respond("\n".join(parts))

    @submit.autocomplete("name")
    async def submit_autocomplete(self, ctx: discord.AutocompleteContext):
        items = await self.bot.db.get_incomplete_deliverables(
            ctx.interaction.user.id, ctx.interaction.guild_id
        )
        matches = [r["name"] for r in items]
        if ctx.value:
            matches = [m for m in matches if ctx.value.lower() in m.lower()]
        return matches[:25]
