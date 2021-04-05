from datetime import datetime
from typing import List, Optional

import discord
from discord.ext import commands, tasks

from fuzzy import Fuzzy
from fuzzy.customizations import ParseableTimedelta
from fuzzy.models import DBUser, Lock


class Locks(Fuzzy.Cog):
    def __init__(self, *args):
        self.execute_expired_locks.start()  # pylint: disable=no-member
        super().__init__(*args)

    @tasks.loop(seconds=0.5)
    async def execute_expired_locks(self):
        """Finds expired locks and unlocks them."""
        locks: List[Lock] = self.bot.db.locks.find_expired_locks()
        for lock in locks:
            guild: discord.Guild = self.bot.get_guild(lock.guild.id)
            # noinspection PyTypeChecker
            channel: discord.TextChannel = None
            # noinspection PyTypeChecker
            everyone_role: discord.Role = None
            if guild:
                channel = guild.get_channel(lock.channel_id)
                everyone_role = guild.get_role(lock.guild.id)
            if channel and everyone_role:
                await channel.set_permissions(
                    everyone_role, send_messages=lock.previous_value
                )
            await self.bot.post_log(
                guild,
                msg=f"{channel.mention} was unlocked by {self.bot.user.display_name}",
                color=self.bot.Context.Color.GOOD,
            )
            self.bot.db.locks.delete(lock.channel_id)

    @commands.command()
    async def lock(
        self,
        ctx: Fuzzy.Context,
        channel: Optional[discord.TextChannel],
        time: ParseableTimedelta,
        *,
        reason: Optional[str] = "",
    ):
        """Prevents users from being able to speak in a channel.
        `channel` is the channel to lock. If left empty the current channel will be used.

        `time` is a time delta in (d)ays (h)ours (m)inutes (s)econds.
        Number first, and type second i.e.`5h` for 5 hours

        `reason` is the reason for the mute. This is optional."""
        lock = None
        everyone_role: discord.Role = ctx.guild.get_role(ctx.guild.id)
        if not channel:
            channel = ctx.channel
        if not channel.permissions_for(ctx.author).manage_messages:
            await ctx.reply("Insufficient permissions to lock channel.")
            return
        if channel in ctx.guild.channels:
            lock = ctx.db.locks.save(
                Lock(
                    channel.id or ctx.channel.id,
                    channel.overwrites_for(everyone_role).read_messages,
                    DBUser(
                        ctx.author.id, f"{ctx.author.name}#{ctx.author.discriminator}"
                    ),
                    ctx.db.guilds.find_by_id(ctx.guild.id),
                    reason,
                    datetime.utcnow() + time,
                )
            )
            await channel.set_permissions(everyone_role, send_messages=False)
        if not lock:
            try:
                await ctx.reply("Could not find a channel with those IDs.")
            except discord.Forbidden:
                pass
            return
        try:
            await ctx.reply(f"Locked {channel.mention} for {time}")
        except discord.Forbidden:
            pass
        await self.bot.post_log(
            ctx.guild,
            msg=f"{ctx.author.name}#{ctx.author.discriminator} "
            f"locked {channel.mention} for {time} for {reason}",
        )

    @commands.command()
    async def unlock(
        self, ctx: Fuzzy.Context, channel: Optional[discord.TextChannel],
    ):
        """Prevents users from being able to speak in a channel.
        channel` is the channel to lock. If left empty the current channel will be used."""
        lock = None
        everyone_role: discord.Role = ctx.guild.get_role(ctx.guild.id)
        if not channel:
            channel = ctx.channel
        if not channel.permissions_for(ctx.author).manage_messages:
            await ctx.reply("Insufficient permissions to unlock channel.")
            return
        if channel in ctx.guild.channels:
            lock = ctx.db.locks.find_by_id(channel.id)
            await channel.set_permissions(
                everyone_role, send_messages=lock.previous_value
            )
            ctx.db.locks.delete(lock.channel_id)
        if not lock:
            await ctx.reply("Could not find a locked channel with that ID.")
            return
        await ctx.reply(f"Unlocked {channel.mention}")
        await self.bot.post_log(
            ctx.guild,
            msg=f"{ctx.author.name}#{ctx.author.discriminator} "
            f"unlocked {channel.mention}",
        )
