from typing import Optional

import discord
from discord.ext import commands

from fuzzy import Fuzzy
from fuzzy.models import Infraction, InfractionType


class Warns(Fuzzy.Cog):
    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def warn(
        self, ctx: Fuzzy.Context, who: discord.User, *, reason: Optional[str] = "",
    ):
        """Issue a warning to a user.
        `who` the person to be warned. This can be an ID, a user mention, or
        their name.
        `reason` is the reason why they are being warned. This is optional and can be updated
        later with `${pfx}reason`"""
        infraction = None
        if who.id != ctx.author.id:
            infraction = Infraction.create(ctx, who, reason, InfractionType.WARN)
            infraction = ctx.db.infractions.save(infraction)
            if infraction:
                try:
                    await self.bot.direct_message(
                        who,
                        title=f"Warning ID {infraction.id}",
                        msg=f"You have been warned on {ctx.guild.name} "
                        + (f'for "{reason}"' if reason else ""),
                    )
                except discord.Forbidden or discord.HTTPException:
                    await ctx.reply(f"Could not send direct message to {who.mention}")
        else:
            await ctx.reply("You cant warn yourself.")
            return

        warn_string = f"{who.mention}: Warning **ID {infraction.id}**"
        await ctx.reply(
            title="Warning",
            msg=(f"**Reason:** {reason}\n" if reason else "") + f"{warn_string}",
            color=ctx.Color.I_GUESS,
        )
        await self.bot.post_log(
            ctx.guild,
            title="Warn",
            msg=f"**Mod:** {ctx.author.mention}\n"
            + (f"**Reason:** {reason}\n" if reason else "")
            + f"{warn_string} ",
            color=ctx.Color.I_GUESS,
        )
