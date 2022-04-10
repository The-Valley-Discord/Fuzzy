import asyncio
import base64
import logging
import re
import traceback
from configparser import ConfigParser
from importlib import metadata
from string import Template
from typing import Optional, List

import discord
from discord.ext import commands

from fuzzy import cogs
from fuzzy.customizations import Fuzzy
from fuzzy.databases import Database
from fuzzy.errors import AnticipatedError, PleaseRestate, Unauthorized
from fuzzy.models import DurationType, GuildSettings

config = ConfigParser()
config.read("./fuzzy.cfg")

logging.basicConfig(
    format="%(levelname)s %(name)s: %(message)s", level=config["log"]["level"]
)

for source in config["log"]["suppress"].split(","):
    logging.getLogger(source).addFilter(
        lambda row: row.levelno > getattr(logging, config["log"]["level"])
    )

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# noinspection PyTypeChecker
database: Database = Database(config)

bot = Fuzzy(
    config,
    database,
    case_insensitive=True,
    activity=Fuzzy.random_status(),
    help_command=None,
    intents=intents,
)


def process_docstrings(text) -> str:
    """Turn a raw function docstring into a help text for display"""
    return re.sub(
        r"(.+)\n *",
        r"\1 ",
        Template(text).safe_substitute(
            {
                "pfx": bot.config["discord"]["prefix"],
            }
        ),
    )


ONCE_LOCK = False


@bot.event
async def on_ready():
    """Hello world."""
    bot.log.info(f"Logged in as {bot.user}")

    global ONCE_LOCK  # pylint: disable=global-statement
    if not ONCE_LOCK:
        bot.owner_id = (await bot.application_info()).owner.id

        # inserting runtime data into help
        for command in bot.walk_commands():
            command.help = process_docstrings(command.help)

        ONCE_LOCK = True
        for guild in bot.guilds:
            guild_settings = bot.db.guilds.find_by_id(guild.id)
            if not guild_settings:
                # noinspection PyTypeChecker
                bot.db.guilds.save(
                    GuildSettings(
                        guild.id,
                        None,
                        None,
                        DurationType.YEARS,
                        30,
                        None,
                    )
                )


@bot.command()
async def ping(ctx):
    """Pings the bot. Mostly used to check bot status."""
    embed = discord.Embed(
        title="**Ping**", description=f"Pong! {round(bot.latency * 1000)}ms"
    )
    embed.set_author(name=f"{bot.user.name}", icon_url=bot.user.avatar.url)
    await ctx.send(embed=embed)


@bot.event
async def on_guild_join(guild: discord.Guild):
    guild_settings = bot.db.guilds.find_by_id(guild.id)
    if not guild_settings:
        # noinspection PyTypeChecker
        bot.db.guilds.save(
            GuildSettings(
                guild.id,
                None,
                None,
                DurationType.YEARS,
                30,
                None,
            )
        )


@bot.command(name="help")
async def _help(ctx: Fuzzy.Context, *, subject: Optional[str]):
    """Display the usage of commands."""

    # noinspection PyShadowingNames
    def signature(cmd: commands.Command) -> str:
        out = f"`{cmd.qualified_name}"
        if cmd.signature:
            out += " " + cmd.signature
        out += "`"
        return out

    embed = discord.Embed(color=ctx.Color.I_GUESS, title="Fuzzy Manual")

    if not subject:
        embed.description = process_docstrings(
            f"""This is [Fuzzy]({ctx.bot.config['info']['source']}), a general-purpose moderation bot for Discord.


            For detailed help on any command, you can use `{signature(_help)}`. Fuzzy
            is [open-source]({ctx.bot.config['info']['source']}). This instance runs version
            {metadata.version('fuzzy')} and is active on {len(ctx.bot.guilds)} servers with
            {len(ctx.bot.users)} members."""
        )

        invite = ctx.bot.config["info"].get("support_invite")
        if invite:
            embed.description += f"\nYou can join the support server here: {invite}."

        all_commands = ""
        standalone_commands = ""
        group_hierarchy: List[commands.GroupMixin] = []
        for cmd in sorted(ctx.bot.walk_commands(), key=lambda x: x.qualified_name):
            if cmd.__class__ == commands.Command:
                if not cmd.parent:
                    standalone_commands += (
                        f"`{bot.command_prefix}{cmd.qualified_name}` "
                    )
                    if group_hierarchy:
                        group_hierarchy.clear()
                else:
                    if len(group_hierarchy) != len(cmd.parents):
                        all_commands += f"\n**`{bot.command_prefix}{' '.join([cmd.name for cmd in reversed(cmd.parents)])}`** "
                    all_commands += f"`{cmd.name}` "
                group_hierarchy = cmd.parents
        embed.add_field(
            name="All Commands", value=standalone_commands + "\n" + all_commands
        )

    else:
        for command in ctx.bot.walk_commands():
            if subject.casefold() in (
                command.qualified_name.casefold(),
                command.qualified_name.replace(ctx.bot.command_prefix, "").casefold(),
            ):
                embed.title = signature(command)
                embed.description = command.help

                if command.__class__ == commands.Group:
                    embed.description += "\n\n" + "\n\n".join(
                        signature(sub) + "\n" + sub.help.split("\n")[0]
                        for sub in command.commands
                    )

    await ctx.send(embed=embed)


@bot.event
async def on_command(ctx: Fuzzy.Context):
    """Log when we invoke commands"""
    args = [
        arg
        for arg in ctx.args
        if not isinstance(arg, Fuzzy.Cog) and not isinstance(arg, Fuzzy.Context)
    ]
    args.extend(list(ctx.kwargs.values()))
    ctx.log.info(f"{ctx.author} invoked with {args}")


@bot.event
async def on_command_error(ctx: Fuzzy.Context, error):
    """
    Handle errors, delegating all "internal errors" (exceptions foreign to
    discordpy) to stderr and discordpy (i.e. high-level) errors to the user.
    """
    if isinstance(error, commands.CommandInvokeError) and isinstance(
        error.original, AnticipatedError
    ):
        original = error.original
        await ctx.reply(
            str(original),
            title=original.TEXT,
            color=ctx.Color.BAD,
            delete_after=5.0 if isinstance(original, Unauthorized) else None,
        )
        return
    elif isinstance(error, commands.UserInputError):
        await ctx.reply(
            str(error),
            title=PleaseRestate.TEXT,
            color=ctx.Color.BAD,
        )
        return
    elif isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        pass
    else:
        error_int = int(ctx.author.id) + int(ctx.message.id)
        error_bytes = error_int.to_bytes(
            (error_int.bit_length() + 7) // 8, byteorder="little"
        )
        error_id = str(
            base64.urlsafe_b64encode(error_bytes),
            encoding="utf-8",
        ).replace("=", "")

        ctx.log.error(
            f"Encountered exception while executing {ctx.command} [ID {error_id}]",
            exc_info=error,
        )

        try:
            channel_id = ctx.bot.config["log"].get("error_log_id")
            if channel_id:
                channel = ctx.bot.get_channel(int(channel_id))
                tb_lines = traceback.format_tb(error.__cause__.__traceback__)
                tb_lines = "".join(tb_lines)

                await channel.send(
                    f"Encountered exception while executing {ctx.command} [ID `{error_id}`]"
                    f"\n```py\n{error}\n{tb_lines}\n```"
                )

        except discord.HTTPException as ex:
            ctx.log.error(f"Couldn't send error to Discord: {ex}")

        await ctx.reply(
            f"If you report this bug, please give us this log ID: `{error_id}`",
            title="Unable to comply, internal error.",
            color=ctx.Color.BAD,
        )


async def main():  # pylint: disable=missing-function-docstring
    async with bot:
        await bot.start(config["discord"]["token"])


if __name__ == "__main__":
    asyncio.run(main())
