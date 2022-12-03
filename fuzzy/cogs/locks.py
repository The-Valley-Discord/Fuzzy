from datetime import datetime, timezone
from typing import List, Optional
import typing

import discord
from discord.ext import commands, tasks

from fuzzy import Fuzzy
from fuzzy.customizations import ParseableTimedelta
from fuzzy.models import DBUser, Lock, ThreadLock


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
                overwrite = channel.overwrites_for(everyone_role)
                overwrite.update(send_messages=lock.previous_value)
                await channel.set_permissions(everyone_role, overwrite=overwrite)
                await self.bot.post_log(
                    guild,
                    msg=f"{channel.mention} was unlocked by {self.bot.user.display_name}",
                    color=self.bot.Context.Color.GOOD,
                )
            self.bot.db.locks.delete(lock.channel_id)

        thread_locks = self.bot.db.thread_locks.find_expired_locks()
        for thread_lock in thread_locks:
            guild: discord.Guild = self.bot.get_guild(thread_lock.guild.id)
            # noinspection PyTypeChecker
            channel: discord.Thread = None
            if guild:
                channel = guild.get_thread(thread_lock.channel_id)
                await self.bot.post_log(
                    guild,
                    msg=f"{channel.mention} was unlocked by {self.bot.user.display_name}",
                    color=self.bot.Context.Color.GOOD,
                )
            self.bot.db.thread_locks.delete(thread_lock.channel_id)

    @commands.has_permissions(manage_messages=True)
    @commands.command()
    async def lock(
        self,
        ctx: Fuzzy.Context,
        channel: Optional[typing.Union[discord.TextChannel, discord.Thread]],
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
        
        if not channel:
            channel = ctx.channel
        # if not channel.permissions_for(ctx.author).manage_messages:
        #     await ctx.reply("Insufficient permissions to lock channel.")
        #     return
        if channel in ctx.guild.channels:
            lock = await self._lock_channel(ctx, channel, time, reason)
        elif channel in ctx.guild.threads:
            lock = self._lock_thread_channel(ctx, channel, time, reason)
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

    async def _lock_channel(self, ctx: Fuzzy.Context, channel: discord.TextChannel, time: ParseableTimedelta, reason: str):
        everyone_role: discord.Role = ctx.guild.get_role(ctx.guild.id)
        overwrite = channel.overwrites_for(everyone_role)
        lock = ctx.db.locks.save(
                Lock(
                    channel.id or ctx.channel.id,
                    overwrite.send_messages,
                    DBUser(
                        ctx.author.id, f"{ctx.author.name}#{ctx.author.discriminator}"
                    ),
                    ctx.db.guilds.find_by_id(ctx.guild.id),
                    reason,
                    datetime.now(timezone.utc) + time,
                )
            )
        overwrite.update(send_messages=False)
        await channel.set_permissions(everyone_role, overwrite=overwrite)
        return lock

    def _lock_thread_channel(self, ctx: Fuzzy.Context, channel: discord.TextChannel, time: ParseableTimedelta, reason: str):

        lock = ctx.db.thread_locks.save(
                ThreadLock(
                    channel.id or ctx.channel.id,
                    DBUser(
                        ctx.author.id, f"{ctx.author.name}#{ctx.author.discriminator}"
                    ),
                    ctx.db.guilds.find_by_id(ctx.guild.id),
                    reason,
                    datetime.now(timezone.utc) + time,
                )
            )
        return lock

    @commands.command()
    async def unlock(
        self,
        ctx: Fuzzy.Context,
        channel: Optional[discord.TextChannel],
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
            overwrite = channel.overwrites_for(everyone_role)
            overwrite.update(send_messages=lock.previous_value)
            await channel.set_permissions(everyone_role, overwrite=overwrite)
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
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Deletes any messages sent in a locked thread."""
        thread: ThreadLock = self.bot.db.thread_locks.find_by_id(message.channel.id)
        if thread and not message.channel.permissions_for(message.author).manage_messages:
            await message.delete()



async def setup(bot):
    await bot.add_cog(Locks(bot))
