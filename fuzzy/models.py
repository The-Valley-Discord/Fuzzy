from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

import discord


class DurationType(Enum):
    DAYS = 1
    MONTHS = 2
    YEARS = 3


class InfractionType(Enum):
    WARN = "Warn"
    MUTE = "Mute"
    BAN = "Ban"


class PublishType(Enum):
    BAN = 1
    UNBAN = 2


@dataclass
class GuildSettings(object):
    id: int
    mod_log: int
    public_log: int
    duration_type: DurationType
    duration: int
    mute_role: int

    def infraction_expired_time(self) -> datetime:
        if self.duration_type.value == DurationType.DAYS.value:
            return datetime.now(timezone.utc) - timedelta(days=self.duration)
        if self.duration_type.value == DurationType.MONTHS.value:
            return datetime.now(timezone.utc) - timedelta(days=(self.duration * 30))
        if self.duration_type.value == DurationType.YEARS.value:
            return datetime.now(timezone.utc) - timedelta(days=(self.duration * 365))


@dataclass()
class DBUser(object):
    id: int
    name: str


@dataclass()
class Pardon(object):
    infraction_id: int
    moderator: DBUser
    pardon_on: datetime
    reason: str


@dataclass()
class PublishedMessage(object):
    infraction_id: int
    message_id: int
    publish_type: PublishType


@dataclass()
class Infraction(object):
    id: int
    user: DBUser
    moderator: DBUser
    guild: GuildSettings
    reason: str
    infraction_on: datetime
    infraction_type: InfractionType
    pardon: Pardon
    published_ban: PublishedMessage
    published_unban: PublishedMessage

    @classmethod
    def create(
        cls,
        ctx,
        who: discord.User,
        reason: str,
        infraction_type: InfractionType,
    ):
        """Creates a new Infraction ready to be stored in DB.
        This will not have id pardon or published_ban attributes. Use normal constructor if those are required"""
        # noinspection PyTypeChecker
        return cls(
            None,
            DBUser(who.id, f"{who.name}#{who.discriminator}"),
            DBUser(ctx.author.id, f"{ctx.author.name}#{ctx.author.discriminator}"),
            ctx.db.guilds.find_by_id(ctx.guild.id),
            reason,
            datetime.now(timezone.utc),
            infraction_type,
            None,
            None,
            None,
        )


@dataclass()
class Mute(object):
    infraction: Infraction
    end_time: datetime
    user: DBUser


@dataclass()
class Lock(object):
    channel_id: int
    previous_value: bool
    moderator: DBUser
    guild: GuildSettings
    reason: str
    end_time: datetime


@dataclass()
class ThreadLock(object):
    channel_id: int
    moderator: DBUser
    guild: GuildSettings
    reason: str
    end_time: datetime
