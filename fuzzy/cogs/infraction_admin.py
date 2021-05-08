from typing import Optional

from discord.ext import commands

from fuzzy.customizations import Fuzzy
from fuzzy.errors import UnableToComply
from fuzzy.models import *


class InfractionAdmin(Fuzzy.Cog):
    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def pardon(
        self, ctx: Fuzzy.Context, infraction_id: int, *, reason: Optional[str],
    ):
        """Pardon a user's infraction. This will leave the infraction in the logs but will mark it as pardoned.
        This command cannot pardon bans as those will automatically be pardoned when a user is unbanned.

        `infraction_ids` is the Infraction ID that is to be pardoned
        """
        all_errors = []
        infraction: Infraction = ctx.db.infractions.find_by_id(
            infraction_id, ctx.guild.id
        )
        if not infraction:
            raise UnableToComply("Could not find any Infractions with those IDs.")
        if infraction.pardon:
            infraction.pardon.reason = reason
        if (
            infraction.infraction_type.value == InfractionType.BAN.value
            and infraction.published_unban
        ):
            channel: discord.TextChannel = ctx.guild.get_channel(
                ctx.db.guilds.find_by_id(ctx.guild.id).public_log
            )
            message: discord.Message = await channel.fetch_message(
                infraction.published_unban.message_id
            )
            if message:
                await message.edit(embed=InfractionAdmin.create_unban_embed(infraction))
            else:
                ctx.db.published_messages.delete_with_type(
                    infraction.id, infraction.published_unban.publish_type
                )
                infraction.published_ban = None
        pardon = infraction.pardon
        if not pardon:
            pardon = Pardon(
                infraction.id,
                DBUser(ctx.author.id, f"{ctx.author.name}#{ctx.author.discriminator}"),
                datetime.utcnow(),
                reason,
            )
        pardon = ctx.db.pardons.save(pardon)
        if pardon:
            infraction.pardon = pardon
        else:
            all_errors.append(str(infraction.id))
        if all_errors:
            msg = ""
            if all_errors:
                msg += "Error Processing Pardons: " + " ".join(all_errors)
            await ctx.reply(msg, color=ctx.Color.I_GUESS)

        if pardon:
            msg = f"**ID:** {infraction.id} **User:** {infraction.user.name}"
            await ctx.reply(title="Pardoned", msg=msg, color=ctx.Color.GOOD)
            await self.bot.post_log(
                ctx.guild,
                msg=f"{ctx.author.name}#{ctx.author.discriminator} "
                f"pardoned: {msg} for {reason}",
            )

    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def forget(self, ctx: Fuzzy.Context, infraction_ids: commands.Greedy[int]):
        """Forgets a user's infraction. This will permanently remove the infraction from the logs.

        `infraction_ids` is a space-separated list of Infraction IDs that are to be forgotten.
        """
        all_infractions = []
        all_errors = []
        for infraction_id in infraction_ids:
            infraction: Infraction = ctx.db.infractions.find_by_id(
                infraction_id, ctx.guild.id
            )
            if infraction:
                all_infractions.append(infraction)
            else:
                all_errors.append(f"{infraction_id}")
        if not all_infractions:
            raise UnableToComply("Could not find any Infractions with those IDs.")

        for infraction in all_infractions:
            if infraction.pardon:
                ctx.db.pardons.delete(infraction.id)
            ctx.db.infractions.delete(infraction.id)
        if all_errors:
            msg = "Error forgetting: " + " ".join(all_errors)
            await ctx.reply(msg, color=ctx.Color.I_GUESS)
        if all_infractions:
            msg = ""
            for infraction in all_infractions:
                msg += f"**ID:** {infraction.id} **User:** {infraction.user.name}\n"

            await ctx.reply(title="Forgot", msg=msg, color=ctx.Color.GOOD)
            await self.bot.post_log(
                ctx.guild,
                msg=f"{ctx.author.name}#{ctx.author.discriminator} ordered {self.bot.user.display_name} to forget:\n"
                f"{msg}",
            )

    @commands.command()
    @commands.has_guild_permissions(manage_messages=True)
    async def reason(self, ctx: Fuzzy.Context, infraction_id: int, *, reason: str):
        """Updates the reason of a user's infraction. This will also update the reason posted in the public ban
        log if if has been `${pfx}publish`ed.

        `infraction_id` is the ID of the Infraction that is to updated.
        `reason` is the new reason to be saved to these infractions
        """
        infraction: Infraction = ctx.db.infractions.find_by_id(
            infraction_id, ctx.guild.id
        )
        if not infraction:
            raise UnableToComply("Could not find any Infraction with that ID.")
        infraction.reason = reason
        if infraction.moderator.id == 0:
            infraction.moderator.id = ctx.author.id
            infraction.moderator.name = f"{ctx.author.name}#{ctx.author.discriminator}"
        ctx.db.infractions.save(infraction)
        if (
            infraction.infraction_type.value == InfractionType.BAN.value
            and infraction.published_ban
        ):
            channel: discord.TextChannel = ctx.guild.get_channel(
                ctx.db.guilds.find_by_id(ctx.guild.id).public_log
            )
            # noinspection PyUnresolvedReferences
            message: discord.Message = await channel.fetch_message(
                infraction.published_ban.message_id
            )
            if message:
                await message.edit(embed=InfractionAdmin.create_ban_embed(infraction))
            else:
                # noinspection PyUnresolvedReferences
                ctx.db.published_messages.delete_with_type(
                    infraction.id, infraction.published_ban.publish_type
                )
                infraction.published_ban = None

        if infraction:
            msg = f"**ID:** {infraction.id} **User:** {infraction.user.name}"
            await ctx.reply(f"Updated Reason to '{reason}' for: \n{msg}")
            await self.bot.post_log(
                ctx.guild,
                msg=f"{ctx.author.name}#{ctx.author.discriminator} updated reason to '{reason}' for : \n{msg}",
            )

    @commands.group()
    @commands.has_guild_permissions(manage_messages=True)
    async def publish(self, ctx: Fuzzy.Context):
        """Publishes a ban or unban to the public ban log channel."""

    @commands.command(parent=publish)
    @commands.has_guild_permissions(manage_messages=True)
    async def ban(self, ctx: Fuzzy.Context, infraction_ids: commands.Greedy[int]):
        """Publishes a ban to the public ban log channel.
        If ban has already been posted you can use ${pfx}reason to update it.
        `infraction_ids` is a space-separated list of infractions"""
        all_bans = []
        all_non_bans = []
        all_errors = []

        for infraction_id in infraction_ids:
            infraction: Infraction = ctx.db.infractions.find_by_id(
                infraction_id, ctx.guild.id
            )
            if infraction:
                if infraction.infraction_type.value == InfractionType.BAN.value:

                    all_bans.append(infraction)
                elif infraction.infraction_type != InfractionType.BAN:
                    all_non_bans.append(str(infraction.id))
            else:
                all_errors.append(str(infraction_id))
        if all_errors or all_non_bans:
            msg = ""
            if all_errors:
                msg += (
                    "Could not find infractions with IDs: "
                    + " ".join(all_errors)
                    + "\n"
                )
            if all_non_bans:
                msg += (
                    "These infractions were not bans and therefore not published: "
                    + " ".join(all_non_bans)
                    + "\n"
                )
            await ctx.reply(msg, color=ctx.Color.I_GUESS)

        guild: GuildSettings = ctx.db.guilds.find_by_id(ctx.guild.id)
        # noinspection PyTypeChecker
        channel: discord.TextChannel = None
        if guild.public_log:
            channel = await ctx.bot.fetch_channel(guild.public_log)
        if channel is None:
            await ctx.reply(msg="Error Fetching Public Log Channel")
            return

        all_published_bans = []
        all_message_errors = []
        for ban in all_bans:
            message = await channel.send(embed=InfractionAdmin.create_ban_embed(ban))
            if message:
                all_published_bans.append(
                    ctx.db.published_messages.save(
                        PublishedMessage(ban.id, message.id, PublishType.BAN)
                    )
                )
            else:
                all_message_errors.append(ban)

        if all_published_bans or all_message_errors:
            msg = ""
            if all_message_errors:
                msg += "Error publishing these Bans:"
                for error in all_message_errors:
                    msg += f" {error.id}"
                msg += "\n"
            if all_published_bans:
                msg += "Successfully published the following bans:"
                bans = ""
                for ban in all_published_bans:
                    msg += f" {ban.infraction_id}"
                    bans += f"{ban.infraction_id} "

                await self.bot.post_log(
                    ctx.guild,
                    msg=f"{ctx.author.name}#{ctx.author.discriminator} published ban reason of: {bans}",
                    color=ctx.Color.AUTOMATIC_BLUE,
                )

            await ctx.reply(msg, color=ctx.Color.AUTOMATIC_BLUE)

    @commands.command(parent=publish)
    @commands.has_guild_permissions(manage_messages=True)
    async def unban(self, ctx: Fuzzy.Context, infraction_ids: commands.Greedy[int]):
        """Publishes an unban to the public ban log channel.
        If unban has already been posted you can use ${pfx}pardon to update it.
        `infraction_ids` is a space-separated list of infractions"""
        all_unbans = []
        all_unpardoned_bans = []
        all_non_bans = []
        all_errors = []

        for infraction_id in infraction_ids:
            infraction: Infraction = ctx.db.infractions.find_by_id(
                infraction_id, ctx.guild.id
            )
            if infraction:
                if (
                    infraction.infraction_type.value == InfractionType.BAN.value
                    and infraction.pardon
                ):
                    all_unbans.append(infraction)
                elif infraction.infraction_type != InfractionType.BAN:
                    all_non_bans.append(str(infraction.id))
                elif not infraction.pardon:
                    all_unpardoned_bans.append(str(infraction.id))
            else:
                all_errors.append(str(infraction_id))
        if all_errors or all_non_bans:
            msg = ""
            if all_errors:
                msg += (
                    "Could not find infractions with IDs: "
                    + " ".join(all_errors)
                    + "\n"
                )
            if all_non_bans:
                msg += (
                    "These infractions were not bans and therefore not published: "
                    + " ".join(all_non_bans)
                    + "\n"
                )
            if all_unpardoned_bans:
                msg += (
                    f"These bans have not been pardoned. Please use `{self.bot.command_prefix}pardon` first: "
                    + " ".join(all_unpardoned_bans)
                    + "\n"
                )
            await ctx.reply(msg, color=ctx.Color.I_GUESS)

        guild: GuildSettings = ctx.db.guilds.find_by_id(ctx.guild.id)
        # noinspection PyTypeChecker
        channel: discord.TextChannel = None
        if guild.public_log:
            channel = await ctx.bot.fetch_channel(guild.public_log)
        if channel is None:
            await ctx.reply(msg="Error Fetching Public Log Channel")
            return

        all_published_unbans = []
        all_message_errors = []
        for ban in all_unbans:
            message = await channel.send(embed=InfractionAdmin.create_unban_embed(ban))
            if message:
                all_published_unbans.append(
                    ctx.db.published_messages.save(
                        PublishedMessage(ban.id, message.id, PublishType.UNBAN)
                    )
                )
            else:
                all_message_errors.append(ban)

        if all_published_unbans or all_message_errors:
            msg = ""
            if all_message_errors:
                msg += "Error publishing these unbans:"
                for error in all_message_errors:
                    msg += f" {error.id}"
                msg += "\n"
            if all_published_unbans:
                msg += "Successfully published the following unbans:"
                bans = ""
                for ban in all_published_unbans:
                    msg += f" {ban.infraction_id}"
                    bans += f"{ban.infraction_id} "

                await self.bot.post_log(
                    ctx.guild,
                    msg=f"{ctx.author.name}#{ctx.author.discriminator} published ban reason of: {bans}",
                    color=ctx.Color.AUTOMATIC_BLUE,
                )

            await ctx.reply(msg, color=ctx.Color.AUTOMATIC_BLUE)

    @staticmethod
    def create_ban_embed(infraction: Infraction):
        """Creates an embed for bans"""
        return discord.Embed(
            title="Ban",
            description=f"**Date:** {infraction.infraction_on.strftime('%Y-%m-%d')}\n"
            f"**User:** {infraction.user.name} ({infraction.user.id})\n"
            f"**Reason:** {infraction.reason}",
        )

    @staticmethod
    def create_unban_embed(infraction: Infraction):
        """Creates an embed for unbans"""
        return discord.Embed(
            title="Unban",
            description=f"**Date:** {infraction.pardon.pardon_on.strftime('%Y-%m-%d')}\n"
            f"**User:** {infraction.user.name} ({infraction.user.id})\n"
            f"**Reason:** {infraction.pardon.reason}",
        )
