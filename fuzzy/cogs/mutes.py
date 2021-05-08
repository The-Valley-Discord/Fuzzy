import typing
from datetime import datetime, timedelta
from typing import List, Optional

import discord
from discord.ext import commands, tasks

from fuzzy import Fuzzy
from fuzzy.models import DBUser, Infraction, InfractionType, Mute
from ..customizations import ParseableTimedelta


class Mutes(Fuzzy.Cog):
    def __init__(self, *args):
        self.execute_expired_mutes.start()  # pylint: disable=no-member
        super().__init__(*args)

    @tasks.loop(seconds=0.5)
    async def execute_expired_mutes(self):
        """Finds expired mutes and unmutes the user"""
        mutes: List[Mute] = self.bot.db.mutes.find_expired_mutes()
        for mute in mutes:
            guild: discord.Guild = await self.bot.fetch_guild(mute.infraction.guild.id)
            # noinspection PyTypeChecker
            user: discord.Member = None
            # noinspection PyTypeChecker
            mute_role: discord.Role = None
            if guild:
                user = await guild.fetch_member(mute.user.id)
                mute_role = guild.get_role(mute.infraction.guild.mute_role)
            if user and mute_role:
                await user.remove_roles(mute_role)
                try:
                    await self.bot.direct_message(
                        user, msg=f"Your mute on {guild.name} has expired."
                    )
                except discord.Forbidden or discord.HTTPException:
                    pass
            self.bot.db.mutes.delete(mute.infraction.id)
            await self.bot.post_log(
                guild,
                msg=f"{mute.user.name} mute expired.",
                color=self.bot.Context.Color.AUTOMATIC_BLUE,
            )

    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def mute(
        self,
        ctx: Fuzzy.Context,
        who: commands.Greedy[typing.Union[discord.Member, discord.User]],
        time: ParseableTimedelta,
        *,
        reason: Optional[str] = "",
    ):
        """Mutes users for the specified amount of time.

        `who` is a space-separated list of discord users that are to be muted. This can be an ID, a user mention,
        or their name.

        `time` is a time delta in (d)ays (h)ours (m)inutes (s)econds.
        Number first, and type second i.e.`5h` for 5 hours

        `reason` is the reason for the mute. This is optional and can be updated later with `${pfx}reason`"""

        if isinstance(time, timedelta):
            if time == timedelta():
                raise commands.BadArgument("Time difference may not be zero.")

        muted_members = []
        error_sending_dm = []
        mute_role: discord.Role = ctx.guild.get_role(
            ctx.db.guilds.find_by_id(ctx.guild.id).mute_role
        )
        if not mute_role:
            await ctx.reply(
                "Could not find a mute role for this server.", color=ctx.Color.I_GUESS
            )
            return
        for member in who:  # type: discord.User
            if member.id != ctx.author.id:
                active_mute = ctx.db.mutes.find_active_mute(member.id, ctx.guild.id)
                if active_mute:
                    ctx.db.mutes.delete(active_mute.infraction.id)

                infraction = Infraction.create(ctx, member, reason, InfractionType.MUTE)
                infraction = ctx.db.infractions.save(infraction)

                if infraction.id:
                    end_time = datetime.utcnow() + time
                    mute = Mute(
                        infraction,
                        end_time,
                        DBUser(member.id, f"{member.name}#{member.discriminator}"),
                    )
                    ctx.db.mutes.save(mute)

                    if isinstance(member, discord.Member):
                        await member.add_roles(mute_role)
                    muted_members.append(
                        f"{member.mention}: Mute **ID {infraction.id}**"
                    )
                    try:
                        await self.bot.direct_message(
                            member,
                            title=f"Mute ID {infraction.id}",
                            msg=f"You have been muted on {ctx.guild.name} "
                            + (f'for "{reason}"' if reason else "")
                            + f"for {time}",
                        )
                    except discord.Forbidden or discord.HTTPException:
                        error_sending_dm.append(member)
            else:
                await ctx.reply("You cant mute yourself.")
        if error_sending_dm:
            await ctx.reply(
                f"Could not send direct message to the following users: "
                f"{' '.join(member.mention for member in error_sending_dm)}"
            )
        if muted_members:
            mute_string = "\n".join(muted_members)
            await ctx.reply(
                title="Mute",
                msg=(f"**Reason:** {reason}\n" if reason else "")
                + f"**Length:** {time}\n{mute_string}",
                color=ctx.Color.BAD,
            )
            await self.bot.post_log(
                ctx.guild,
                title="Mute",
                msg=f"**Mod:** {ctx.author.name}#{ctx.author.discriminator}\n"
                + (f"**Reason:** {reason}\n" if reason else "")
                + f"**Length:** {time}\n{mute_string}",
                color=ctx.Color.BAD,
            )

    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def unmute(
        self,
        ctx: Fuzzy.Context,
        who: commands.Greedy[typing.Union[discord.Member, discord.User]],
    ):
        """Unmutes a user.
        `who` is a space-separated list of discord users that are to be unmuted. This can be an ID< a user mention, or
        their name."""
        unmuted_members = []
        all_errors = []
        for member in who:  # type: discord.User
            active_mute = ctx.db.mutes.find_active_mute(member.id, ctx.guild.id)
            if active_mute:
                ctx.db.mutes.delete(active_mute.infraction.id)
            else:
                all_errors.append(member.mention)
            mute_role: discord.Role = ctx.guild.get_role(
                ctx.db.guilds.find_by_id(ctx.guild.id).mute_role
            )

            if mute_role is None:
                await ctx.reply("Error fetching mute role:")
                return
            if isinstance(member, discord.Member):
                if mute_role in member.roles:
                    await member.remove_roles(mute_role)
                    try:
                        await self.bot.direct_message(
                            member, msg=f"Your mute on {ctx.guild.name} was removed."
                        )
                    except discord.Forbidden or discord.HTTPException:
                        pass
            unmuted_members.append(member.mention)

        msg = ""
        if all_errors:
            msg += f"Could not find active mutes for: {' '.join(all_errors)}\n"
        if unmuted_members:
            msg += f"Unmuted the following users: {' '.join(unmuted_members)}"
            await ctx.reply(msg)
            await self.bot.post_log(
                ctx.guild,
                msg=f"{ctx.author.mention} " f"unmuted {' '.join(unmuted_members)}",
                color=ctx.Color.AUTOMATIC_BLUE,
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Checks if a member who joined the server, had a pre=existing mute and reapplies it if necessary."""
        active_mute = self.bot.db.mutes.find_active_mute(member.id, member.guild.id)
        if active_mute:

            mute_role: discord.Role = member.guild.fetch_role(
                self.bot.db.guilds.find_by_id(member.guild.id).mute_role
            )
            if mute_role:
                await member.add_roles(mute_role)
