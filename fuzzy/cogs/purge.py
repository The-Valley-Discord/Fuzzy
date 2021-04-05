from discord.ext import commands

from fuzzy import Fuzzy


class Purges(Fuzzy.Cog):
    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx: Fuzzy.Context, amount: int):
        """Deletes the most recent messages in a channel.
        `amount` is the number of messages to delete."""
        amount += 1
        deleted = await ctx.channel.purge(limit=amount, bulk=True,)
        await ctx.reply(
            f"Purged {len(deleted) - 1} messages from {ctx.channel.mention}.",
            delete_after=5,
        )
