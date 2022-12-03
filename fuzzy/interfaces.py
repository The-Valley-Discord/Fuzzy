from abc import ABC, abstractmethod
from typing import Dict, List

from fuzzy.models import *


class IInfractions(ABC):
    """Manages the infraction section of the database."""

    @abstractmethod
    def find_by_id(self, infraction_id: int, guild_id: int) -> Infraction:
        """Finds an infraction when given an infraction_id and guild_id"""
        pass

    @abstractmethod
    def save(self, infraction: Infraction) -> Infraction:
        """Saves an infraction into the database. If infraction already exists then updates the saved instance."""
        pass

    @abstractmethod
    def delete(self, infraction_id: int) -> None:
        """Deletes an infraction from the database."""
        pass

    @abstractmethod
    def find_recent_ban_by_id(self, user_id, guild_id) -> Infraction:
        pass

    @abstractmethod
    def find_all_for_user(self, user_id: int, guild_id: int) -> List[Infraction]:
        pass

    @abstractmethod
    def find_warns_for_user(self, user_id: int, guild_id: int) -> List[Infraction]:
        pass

    @abstractmethod
    def find_mutes_for_user(self, user_id: int, guild_id: int) -> List[Infraction]:
        pass

    @abstractmethod
    def find_bans_for_user(self, user_id: int, guild_id: int) -> List[Infraction]:
        pass

    @abstractmethod
    def find_mod_actions(self, moderator_id, guild_id) -> Dict:
        pass


class IPardons(ABC):
    @abstractmethod
    def find_by_id(self, infraction_id: int) -> Pardon:
        pass

    @abstractmethod
    def save(self, pardon: Pardon) -> Pardon:
        pass

    @abstractmethod
    def delete(self, infraction_id: int) -> None:
        pass


class IMutes(ABC):
    @abstractmethod
    def find_by_id(self, infraction_id: int) -> Mute:
        pass

    @abstractmethod
    def find_expired_mutes(self) -> List[Mute]:
        pass

    @abstractmethod
    def save(self, mute: Mute) -> Mute:
        pass

    @abstractmethod
    def delete(self, infraction_id: int) -> None:
        pass

    @abstractmethod
    def find_active_mute(self, user_id, guild_id) -> Mute:
        pass


class IGuilds(ABC):
    @abstractmethod
    def find_by_id(self, guild_id: int) -> GuildSettings:
        pass

    @abstractmethod
    def save(self, guild: GuildSettings) -> GuildSettings:
        pass

    @abstractmethod
    def delete(self, guild_id: int) -> None:
        pass


class ILocks(ABC):
    @abstractmethod
    def find_by_id(self, channel_id: int) -> Lock:
        pass

    @abstractmethod
    def find_expired_locks(self) -> List[Lock]:
        pass

    @abstractmethod
    def save(self, lock: Lock) -> Lock:
        pass

    @abstractmethod
    def delete(self, channel_id: int) -> None:
        pass


class IThreadLocks(ABC):
    @abstractmethod
    def find_by_id(self, channel_id: int) -> Lock:
        pass

    @abstractmethod
    def find_expired_locks(self) -> List[Lock]:
        pass

    @abstractmethod
    def save(self, lock: Lock) -> Lock:
        pass

    @abstractmethod
    def delete(self, channel_id: int) -> None:
        pass


class IPublishedMessages(ABC):
    @abstractmethod
    def find_by_id_and_type(
        self, infraction_id: int, publish_type: PublishType
    ) -> PublishedMessage:
        pass

    @abstractmethod
    def save(self, published_ban: PublishedMessage) -> PublishedMessage:
        pass

    @abstractmethod
    def delete_with_type(self, infraction_id: int, infraction_type) -> None:
        pass

    @abstractmethod
    def delete_all_with_id(self, infraction_id: int):
        pass
