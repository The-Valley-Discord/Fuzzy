import logging
import sqlite3
from pathlib import Path

from fuzzy.interfaces import *
from fuzzy.models import *


class Database:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("fuzzy")
        self.log.setLevel(logging.INFO)

        self.conn = sqlite3.connect(
            config["database"]["path"],
            isolation_level=None,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        self.conn.row_factory = sqlite3.Row
        last_migration_number = 0
        try:
            last_migration_number = self.conn.execute(
                "SELECT * FROM applied_migrations ORDER BY number DESC LIMIT 1;"
            ).fetchone()[0]
        except sqlite3.DatabaseError:
            pass

        for path in sorted(Path(config["database"]["migrations"]).glob("*.sql")):
            number = int(path.stem)
            if number > last_migration_number:
                self.conn.executescript(
                    f"""
                    BEGIN TRANSACTION;
                    {path.read_text()}
                    INSERT INTO applied_migrations VALUES({number});
                    COMMIT;
                    """
                )
                self.log.info(f"Applied migration {number}")

        self.infractions = Infractions(self.conn, self)
        self.pardons = Pardons(self.conn)
        self.mutes = Mutes(self.conn, self)
        self.guilds = Guilds(self.conn)
        self.locks = Locks(self.conn, self)
        self.published_messages = PublishedMessages(self.conn)
        self.thread_locks = ThreadLocks(self.conn, self)


class Infractions(IInfractions):
    def __init__(self, conn: sqlite3.Connection, db: Database):
        self.conn = conn
        self.db = db

    def find_by_id(self, infraction_id: int, guild_id: int) -> Infraction:
        infraction = None
        try:
            infraction = self.conn.execute(
                "SELECT * FROM infractions WHERE oid=:id AND guild_id=:guild_id",
                {"id": infraction_id, "guild_id": guild_id},
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        finally:
            return (
                Infraction(
                    infraction["oid"],
                    DBUser(infraction["user_id"], infraction["user_name"]),
                    DBUser(infraction["moderator_id"], infraction["moderator_name"]),
                    self.db.guilds.find_by_id(guild_id),
                    infraction["reason"],
                    infraction["infraction_on"],
                    InfractionType(infraction["infraction_type"]),
                    self.db.pardons.find_by_id(infraction_id),
                    self.db.published_messages.find_by_id_and_type(
                        infraction_id, PublishType.BAN
                    ),
                    self.db.published_messages.find_by_id_and_type(
                        infraction_id, PublishType.UNBAN
                    ),
                )
                if infraction
                else None
            )

    def find_by_id_only(self, infraction_id: int):
        infraction = None
        try:
            infraction = self.conn.execute(
                "SELECT * FROM infractions WHERE oid=:id",
                {"id": infraction_id},
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        finally:
            return (
                Infraction(
                    infraction["oid"],
                    DBUser(infraction["user_id"], infraction["user_name"]),
                    DBUser(infraction["moderator_id"], infraction["moderator_name"]),
                    self.db.guilds.find_by_id(infraction["guild_id"]),
                    infraction["reason"],
                    infraction["infraction_on"],
                    InfractionType(infraction["infraction_type"]),
                    self.db.pardons.find_by_id(infraction_id),
                    self.db.published_messages.find_by_id_and_type(
                        infraction_id, PublishType.BAN
                    ),
                    self.db.published_messages.find_by_id_and_type(
                        infraction_id, PublishType.UNBAN
                    ),
                )
                if infraction
                else None
            )

    def save(self, infraction: Infraction) -> Infraction:
        if infraction.id:
            self.conn.execute(
                "UPDATE infractions SET reason=:reason, "
                "moderator_id=:moderator_id, "
                "moderator_name=:moderator_name WHERE oid=:id",
                {
                    "reason": infraction.reason,
                    "moderator_id": infraction.moderator.id,
                    "moderator_name": infraction.moderator.name,
                    "id": infraction.id,
                },
            )
            self.conn.commit()
        else:
            values = (
                infraction.user.id,
                infraction.user.name,
                infraction.moderator.id,
                infraction.moderator.name,
                infraction.guild.id,
                infraction.reason,
                infraction.infraction_on,
                infraction.infraction_type.value,
            )
            sql = """INSERT INTO infractions (user_id, user_name, moderator_id, moderator_name, guild_id, reason, 
            infraction_on, infraction_type) VALUES(?,?,?,?,?,?,?,?)"""
            try:
                infraction.id = self.conn.execute(sql, values).lastrowid
                self.conn.commit()
            except sqlite3.DatabaseError:
                pass
        return self.find_by_id(infraction.id, infraction.guild.id)

    def delete(self, infraction_id: int) -> None:
        self.db.pardons.delete(infraction_id)
        self.db.published_messages.delete_all_with_id(infraction_id)
        self.conn.execute(
            "DELETE FROM infractions WHERE oid=:id", {"id": infraction_id}
        )
        self.conn.commit()

    def find_recent_ban_by_id(self, user_id, guild_id) -> Infraction:
        infraction = None
        try:
            infraction = self.conn.execute(
                "SELECT * FROM infractions WHERE user_id=:user_id "
                "AND guild_id=:guild_id ORDER BY DATETIME(infraction_on) DESC Limit 1",
                {"user_id": user_id, "guild_id": guild_id},
            ).fetchone()
        except sqlite3.DatabaseError:
            pass

        return (
            Infraction(
                infraction["oid"],
                DBUser(infraction["user_id"], infraction["user_name"]),
                DBUser(infraction["moderator_id"], infraction["moderator_name"]),
                self.db.guilds.find_by_id(guild_id),
                infraction["reason"],
                infraction["infraction_on"],
                InfractionType(infraction["infraction_type"]),
                self.db.pardons.find_by_id(infraction["oid"]),
                self.db.published_messages.find_by_id_and_type(
                    infraction["oid"], PublishType.BAN
                ),
                self.db.published_messages.find_by_id_and_type(
                    infraction["oid"], PublishType.UNBAN
                ),
            )
            if infraction
            else None
        )

    def find_recent_ban_by_id_time_limited(self, user_id, guild_id) -> Infraction:
        infraction = None
        infraction_on = datetime.now(timezone.utc) - timedelta(minutes=1)
        try:
            infraction = self.conn.execute(
                "SELECT * FROM infractions WHERE user_id=:user_id "
                "AND guild_id=:guild_id AND DATETIME(infraction_on) > :infraction_on",
                {
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "infraction_on": infraction_on,
                },
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        return (
            Infraction(
                infraction["oid"],
                DBUser(infraction["user_id"], infraction["user_name"]),
                DBUser(infraction["moderator_id"], infraction["moderator_name"]),
                self.db.guilds.find_by_id(guild_id),
                infraction["reason"],
                infraction["infraction_on"].replace(tzinfo=timezone.utc),
                InfractionType(infraction["infraction_type"]),
                self.db.pardons.find_by_id(infraction["oid"]),
                self.db.published_messages.find_by_id_and_type(
                    infraction["oid"], PublishType.BAN
                ),
                self.db.published_messages.find_by_id_and_type(
                    infraction["oid"], PublishType.UNBAN
                ),
            )
            if infraction
            else None
        )

    def find_all_for_user(self, user_id: int, guild_id: int) -> List[Infraction]:
        expired_time = self.db.guilds.find_by_id(guild_id).infraction_expired_time()

        infractions = []
        try:
            infractions = self.conn.execute(
                "SELECT * FROM infractions "
                "WHERE user_id=:user_id AND guild_id=:guild_id "
                "AND DATETIME(infraction_on) > :expired_time "
                "ORDER BY datetime(infraction_on) ASC",
                {
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "expired_time": expired_time,
                },
            ).fetchall()
        except sqlite3.DatabaseError:
            pass
        objectified_infractions = []
        for infraction in infractions:
            objectified_infractions.append(
                Infraction(
                    infraction["oid"],
                    DBUser(infraction["user_id"], infraction["user_name"]),
                    DBUser(infraction["moderator_id"], infraction["moderator_name"]),
                    self.db.guilds.find_by_id(guild_id),
                    infraction["reason"],
                    infraction["infraction_on"].replace(tzinfo=timezone.utc),
                    InfractionType(infraction["infraction_type"]),
                    self.db.pardons.find_by_id(infraction["oid"]),
                    self.db.published_messages.find_by_id_and_type(
                        infraction["oid"], PublishType.BAN
                    ),
                    self.db.published_messages.find_by_id_and_type(
                        infraction["oid"], PublishType.UNBAN
                    ),
                )
            )
        return objectified_infractions

    def find_warns_for_user(self, user_id: int, guild_id: int) -> List[Infraction]:
        expired_time = self.db.guilds.find_by_id(guild_id).infraction_expired_time()

        infractions = []
        try:
            infractions = self.conn.execute(
                "SELECT * FROM infractions "
                "WHERE user_id=:user_id AND guild_id=:guild_id "
                "AND DATETIME(infraction_on) > :expired_time "
                "AND infraction_type=:infraction_type "
                "ORDER BY DATETIME(infraction_on) ASC",
                {
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "expired_time": expired_time,
                    "infraction_type": InfractionType.WARN.value,
                },
            ).fetchall()
        except sqlite3.DatabaseError:
            pass
        objectified_infractions = []
        for infraction in infractions:
            objectified_infractions.append(
                Infraction(
                    infraction["oid"],
                    DBUser(infraction["user_id"], infraction["user_name"]),
                    DBUser(infraction["moderator_id"], infraction["moderator_name"]),
                    self.db.guilds.find_by_id(guild_id),
                    infraction["reason"],
                    infraction["infraction_on"].replace(tzinfo=timezone.utc),
                    InfractionType(infraction["infraction_type"]),
                    self.db.pardons.find_by_id(infraction["oid"]),
                    self.db.published_messages.find_by_id_and_type(
                        infraction["oid"], PublishType.BAN
                    ),
                    self.db.published_messages.find_by_id_and_type(
                        infraction["oid"], PublishType.UNBAN
                    ),
                )
            )
        return objectified_infractions

    def find_mutes_for_user(self, user_id: int, guild_id: int) -> List[Infraction]:
        expired_time = self.db.guilds.find_by_id(guild_id).infraction_expired_time()

        infractions = []
        try:
            infractions = self.conn.execute(
                "SELECT * FROM infractions "
                "WHERE user_id=:user_id AND guild_id=:guild_id "
                "AND DATETIME(infraction_on) > :expired_time "
                "AND infraction_type=:infraction_type "
                "ORDER BY DATETIME(infraction_on) ASC",
                {
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "expired_time": expired_time,
                    "infraction_type": InfractionType.MUTE.value,
                },
            ).fetchall()
        except sqlite3.DatabaseError:
            pass
        objectified_infractions = []
        for infraction in infractions:
            objectified_infractions.append(
                Infraction(
                    infraction["oid"],
                    DBUser(infraction["user_id"], infraction["user_name"]),
                    DBUser(infraction["moderator_id"], infraction["moderator_name"]),
                    self.db.guilds.find_by_id(guild_id),
                    infraction["reason"],
                    infraction["infraction_on"].replace(tzinfo=timezone.utc),
                    InfractionType(infraction["infraction_type"]),
                    self.db.pardons.find_by_id(infraction["oid"]),
                    self.db.published_messages.find_by_id_and_type(
                        infraction["oid"], PublishType.BAN
                    ),
                    self.db.published_messages.find_by_id_and_type(
                        infraction["oid"], PublishType.UNBAN
                    ),
                )
            )
        return objectified_infractions

    def find_bans_for_user(self, user_id: int, guild_id: int) -> List[Infraction]:
        expired_time = self.db.guilds.find_by_id(guild_id).infraction_expired_time()

        infractions = []
        try:
            infractions = self.conn.execute(
                "SELECT * FROM infractions "
                "WHERE user_id=:user_id AND guild_id=:guild_id "
                "AND DATETIME(infraction_on) > :expired_time "
                "AND infraction_type=:infraction_type "
                "ORDER BY DATETIME(infraction_on) ASC",
                {
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "expired_time": expired_time,
                    "infraction_type": InfractionType.BAN.value,
                },
            ).fetchall()
        except sqlite3.DatabaseError:
            pass
        objectified_infractions = []
        for infraction in infractions:
            objectified_infractions.append(
                Infraction(
                    infraction["oid"],
                    DBUser(infraction["user_id"], infraction["user_name"]),
                    DBUser(infraction["moderator_id"], infraction["moderator_name"]),
                    self.db.guilds.find_by_id(guild_id),
                    infraction["reason"],
                    infraction["infraction_on"].replace(tzinfo=timezone.utc),
                    InfractionType(infraction["infraction_type"]),
                    self.db.pardons.find_by_id(infraction["oid"]),
                    self.db.published_messages.find_by_id_and_type(
                        infraction["oid"], PublishType.BAN
                    ),
                    self.db.published_messages.find_by_id_and_type(
                        infraction["oid"], PublishType.UNBAN
                    ),
                )
            )
        return objectified_infractions

    def find_mod_actions(self, moderator_id, guild_id) -> Dict:
        warns = []
        mutes = []
        bans = []
        try:
            warns = self.conn.execute(
                "SELECT * FROM infractions "
                "WHERE moderator_id=:moderator_id AND guild_id=:guild_id "
                "AND infraction_type=:infraction_type",
                {
                    "moderator_id": moderator_id,
                    "guild_id": guild_id,
                    "infraction_type": InfractionType.WARN.value,
                },
            ).fetchall()
            mutes = self.conn.execute(
                "SELECT * FROM infractions "
                "WHERE moderator_id=:moderator_id AND guild_id=:guild_id "
                "AND infraction_type=:infraction_type",
                {
                    "moderator_id": moderator_id,
                    "guild_id": guild_id,
                    "infraction_type": InfractionType.MUTE.value,
                },
            ).fetchall()
            bans = self.conn.execute(
                "SELECT * FROM infractions "
                "WHERE moderator_id=:moderator_id AND guild_id=:guild_id "
                "AND infraction_type=:infraction_type",
                {
                    "moderator_id": moderator_id,
                    "guild_id": guild_id,
                    "infraction_type": InfractionType.BAN.value,
                },
            ).fetchall()
        except sqlite3.DatabaseError:
            pass
        return {"warns": len(warns), "mutes": len(mutes), "bans": len(bans)}


class Pardons(IPardons):
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def find_by_id(self, infraction_id: int) -> Pardon:
        pardon = None
        try:
            pardon = self.conn.execute(
                "SELECT * FROM pardons WHERE infraction_id=:infraction_id",
                {"infraction_id": infraction_id},
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        finally:
            return (
                Pardon(
                    pardon["infraction_id"],
                    DBUser(pardon["moderator_id"], pardon["moderator_name"]),
                    pardon["pardon_on"].replace(tzinfo=timezone.utc),
                    pardon["reason"],
                )
                if pardon
                else None
            )

    def save(self, pardon: Pardon) -> Pardon:
        retrieved_pardon = None
        try:
            retrieved_pardon = self.conn.execute(
                "SELECT * FROM pardons WHERE infraction_id=:infraction_id",
                {"infraction_id": pardon.infraction_id},
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        if retrieved_pardon:
            self.conn.execute(
                "UPDATE pardons SET reason=:reason WHERE infraction_id=:infraction_id",
                {"reason": pardon.reason, "infraction_id": pardon.infraction_id},
            )
            self.conn.commit()
        else:
            values = (
                pardon.infraction_id,
                pardon.moderator.id,
                pardon.moderator.name,
                pardon.pardon_on,
                pardon.reason,
            )
            sql = """INSERT INTO pardons (infraction_id, moderator_id, moderator_name, pardon_on, reason)
            Values(?,?,?,?,?)"""
            self.conn.execute(sql, values)
            self.conn.commit()

        return self.find_by_id(pardon.infraction_id)

    def delete(self, infraction_id: int) -> None:
        self.conn.execute(
            "DELETE FROM pardons WHERE infraction_id=:id", {"id": infraction_id}
        )
        self.conn.commit()


class Mutes(IMutes):
    def __init__(self, conn: sqlite3.Connection, db: Database):
        self.conn = conn
        self.db = db

    def find_by_id(self, infraction_id: int) -> Mute:
        mute = None
        try:
            mute = self.conn.execute(
                "SELECT * FROM mutes WHERE infraction_id=:infraction_id",
                {"infraction_id": infraction_id},
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        finally:
            return (
                Mute(
                    self.db.infractions.find_by_id_only(mute["infraction_id"]),
                    mute["end_time"].replace(tzinfo=timezone.utc),
                    DBUser(mute["user_id"], mute["user_name"]),
                )
                if mute
                else None
            )

    def find_expired_mutes(self) -> List[Mute]:
        mutes = []
        try:
            mutes = self.conn.execute(
                "SELECT * FROM mutes WHERE DATETIME(end_time) < :time",
                {"time": datetime.now(timezone.utc)},
            ).fetchall()
        except sqlite3.DatabaseError:
            pass
        finally:
            objectified_mutes = []
            for mute in mutes:
                objectified_mutes.append(
                    Mute(
                        self.db.infractions.find_by_id_only(mute["infraction_id"]),
                        mute["end_time"].replace(tzinfo=timezone.utc),
                        DBUser(mute["user_id"], mute["user_name"]),
                    )
                )
            return objectified_mutes

    def save(self, mute: Mute) -> Mute:
        values = (mute.infraction.id, mute.end_time, mute.user.id, mute.user.name)
        sql = """INSERT INTO mutes (infraction_id, end_time, user_id, user_name) VALUES(?,?,?,?)"""
        try:
            self.conn.execute(sql, values)
            self.conn.commit()
        except sqlite3.DatabaseError:
            pass
        finally:
            return self.find_by_id(mute.infraction.id)

    def delete(self, infraction_id: int) -> None:
        self.conn.execute(
            "DELETE FROM mutes WHERE infraction_id=:id", {"id": infraction_id}
        )
        self.conn.commit()

    def find_active_mute(self, user_id, guild_id) -> Mute:
        mute = None
        try:
            mute = self.conn.execute(
                "SELECT * FROM mutes WHERE DATETIME(end_time) > :time AND user_id=:user_id",
                {"time": datetime.now(timezone.utc), "user_id": user_id},
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        finally:
            return (
                Mute(
                    self.db.infractions.find_by_id_only(mute["infraction_id"]),
                    mute["end_time"].replace(tzinfo=timezone.utc),
                    DBUser(mute["user_id"], mute["user_name"]),
                )
                if mute
                else None
            )


class Guilds(IGuilds):
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def find_by_id(self, guild_id: int) -> GuildSettings:
        guild = None
        try:
            guild = self.conn.execute(
                "SELECT * FROM guilds WHERE id=:id", {"id": guild_id}
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        finally:
            return (
                GuildSettings(
                    guild["id"],
                    guild["mod_log"],
                    guild["public_log"],
                    DurationType(guild["duration_type"])
                    if guild["duration_type"]
                    else None,
                    guild["duration"],
                    guild["mute_role"],
                )
                if guild
                else None
            )

    def save(self, guild: GuildSettings) -> GuildSettings:
        retrieved_guild = self.find_by_id(guild.id)
        if retrieved_guild:
            try:
                self.conn.execute(
                    "UPDATE guilds "
                    "SET mod_log=:mod_log,"
                    "public_log=:public_log,"
                    "duration_type=:duration_type,"
                    "duration=:duration,"
                    "mute_role=:mute_role "
                    "WHERE id=:id",
                    {
                        "mod_log": guild.mod_log,
                        "public_log": guild.public_log,
                        "duration_type": guild.duration_type.value,
                        "duration": guild.duration,
                        "mute_role": guild.mute_role,
                        "id": guild.id,
                    },
                )
                self.conn.commit()
            except sqlite3.DatabaseError:
                pass
        else:
            try:
                values = (
                    guild.id,
                    guild.mod_log,
                    guild.public_log,
                    guild.duration_type.value,
                    guild.duration,
                    guild.mute_role,
                )
                sql = (
                    "INSERT INTO guilds (id, mod_log, public_log, duration_type, duration, mute_role) "
                    "VALUES(?,?,?,?,?,?)"
                )
                self.conn.execute(sql, values)
                self.conn.commit()
            except sqlite3.DatabaseError:
                pass
        return self.find_by_id(guild.id)

    def delete(self, guild_id: int) -> None:
        self.conn.execute("DELETE FROM guilds WHERE id=:id", {"id": guild_id})
        self.conn.commit()


class Locks(ILocks):
    def __init__(self, conn: sqlite3.Connection, db: Database):
        self.conn = conn
        self.db = db

    def find_by_id(self, channel_id: int) -> Lock:
        lock = None
        try:
            lock = self.conn.execute(
                "SELECT * FROM locks WHERE channel_id=:id", {"id": channel_id}
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        finally:
            return (
                Lock(
                    lock["channel_id"],
                    bool(lock["previous_value"])
                    if lock["previous_value"] is not None
                    else None,
                    DBUser(lock["moderator_id"], lock["moderator_name"]),
                    self.db.guilds.find_by_id(lock["guild_id"]),
                    lock["reason"],
                    lock["end_time"].replace(tzinfo=timezone.utc),
                )
                if lock
                else None
            )

    def find_expired_locks(self) -> List[Lock]:
        locks = []
        try:
            locks = self.conn.execute(
                "SELECT * FROM locks WHERE DATETIME(end_time) < :time",
                {"time": datetime.now(timezone.utc)},
            ).fetchall()
        except sqlite3.DatabaseError:
            pass
        finally:
            objectified_locks = []
            for lock in locks:
                objectified_locks.append(
                    Lock(
                        lock["channel_id"],
                        bool(lock["previous_value"])
                        if lock["previous_value"] is not None
                        else None,
                        DBUser(lock["moderator_id"], lock["moderator_name"]),
                        self.db.guilds.find_by_id(lock["guild_id"]),
                        lock["reason"],
                        lock["end_time"].replace(tzinfo=timezone.utc),
                    )
                )
            return objectified_locks

    def save(self, lock: Lock) -> Lock:
        retrieved_lock = self.find_by_id(lock.channel_id)
        if retrieved_lock:
            try:
                self.conn.execute(
                    "UPDATE locks SET "
                    "moderator_id=:moderator_id,"
                    "moderator_name=:moderator_name,"
                    "reason=:reason,"
                    "end_time=:end_time "
                    "WHERE channel_id=channel_id",
                    {
                        "moderator_id": lock.moderator.id,
                        "moderator_name": lock.moderator.name,
                        "reason": lock.reason,
                        "end_time": lock.end_time,
                        "channel_id": lock.channel_id,
                    },
                )
                self.conn.commit()
            except sqlite3.DatabaseError:
                pass
        else:
            try:
                values = (
                    lock.channel_id,
                    lock.previous_value,
                    lock.moderator.id,
                    lock.moderator.name,
                    lock.guild.id,
                    lock.reason,
                    lock.end_time,
                )
                sql = (
                    "INSERT INTO locks (channel_id, previous_value, moderator_id, moderator_name, "
                    "guild_id, reason, end_time) "
                    "VALUES(?,?,?,?,?,?,?)"
                )
                self.conn.execute(sql, values)
                self.conn.commit()
            except sqlite3.DatabaseError:
                pass
        return self.find_by_id(lock.channel_id)

    def delete(self, channel_id: int) -> None:
        self.conn.execute("DELETE FROM locks WHERE channel_id=:id", {"id": channel_id})
        self.conn.commit()

class ThreadLocks(IThreadLocks):
    def __init__(self, conn: sqlite3.Connection, db: Database):
        self.conn = conn
        self.db = db

    def find_by_id(self, channel_id: int) -> Lock:
        lock = None
        try:
            lock = self.conn.execute(
                "SELECT * FROM thread_locks WHERE channel_id=:id", {"id": channel_id}
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        finally:
            return (
                ThreadLock(
                    lock["channel_id"],
                    DBUser(lock["moderator_id"], lock["moderator_name"]),
                    self.db.guilds.find_by_id(lock["guild_id"]),
                    lock["reason"],
                    lock["end_time"].replace(tzinfo=timezone.utc),
                )
                if lock
                else None
            )

    def find_expired_locks(self) -> List[ThreadLock]:
        locks = []
        try:
            locks = self.conn.execute(
                "SELECT * FROM thread_locks WHERE DATETIME(end_time) < :time",
                {"time": datetime.now(timezone.utc)},
            ).fetchall()
        except sqlite3.DatabaseError:
            pass
        finally:
            objectified_locks = []
            for lock in locks:
                objectified_locks.append(
                    ThreadLock(
                        lock["channel_id"],
                        DBUser(lock["moderator_id"], lock["moderator_name"]),
                        self.db.guilds.find_by_id(lock["guild_id"]),
                        lock["reason"],
                        lock["end_time"].replace(tzinfo=timezone.utc),
                    )
                )
            return objectified_locks

    def save(self, lock: ThreadLock) -> ThreadLock:
        retrieved_lock = self.find_by_id(lock.channel_id)
        if retrieved_lock:
            try:
                self.conn.execute(
                    "UPDATE thread_locks SET "
                    "moderator_id=:moderator_id,"
                    "moderator_name=:moderator_name,"
                    "reason=:reason,"
                    "end_time=:end_time "
                    "WHERE channel_id=channel_id",
                    {
                        "moderator_id": lock.moderator.id,
                        "moderator_name": lock.moderator.name,
                        "reason": lock.reason,
                        "end_time": lock.end_time,
                        "channel_id": lock.channel_id,
                    },
                )
                self.conn.commit()
            except sqlite3.DatabaseError:
                pass
        else:
            try:
                values = (
                    lock.channel_id,
                    lock.moderator.id,
                    lock.moderator.name,
                    lock.guild.id,
                    lock.reason,
                    lock.end_time,
                )
                sql = (
                    "INSERT INTO thread_locks (channel_id, moderator_id, moderator_name, "
                    "guild_id, reason, end_time) "
                    "VALUES(?,?,?,?,?,?)"
                )
                self.conn.execute(sql, values)
                self.conn.commit()
            except sqlite3.DatabaseError:
                pass
        return self.find_by_id(lock.channel_id)

    def delete(self, channel_id: int) -> None:
        self.conn.execute("DELETE FROM thread_locks WHERE channel_id=:id", {"id": channel_id})
        self.conn.commit()


class PublishedMessages(IPublishedMessages):
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def find_by_id_and_type(
        self, infraction_id: int, publish_type: PublishType
    ) -> PublishedMessage:
        publish = None
        try:
            publish = self.conn.execute(
                "SELECT * FROM published_messages WHERE infraction_id=:infraction_id "
                "AND publish_type=:publish_type",
                {"infraction_id": infraction_id, "publish_type": publish_type.value},
            ).fetchone()
        except sqlite3.DatabaseError:
            pass
        return (
            PublishedMessage(
                publish["infraction_id"],
                publish["message_id"],
                PublishType(publish["publish_type"]),
            )
            if publish
            else None
        )

    def save(self, published_ban: PublishedMessage) -> PublishedMessage:
        self.delete_with_type(published_ban.infraction_id, published_ban.publish_type)
        try:
            values = (
                published_ban.infraction_id,
                published_ban.message_id,
                published_ban.publish_type.value,
            )
            sql = (
                "INSERT INTO published_messages (infraction_id, message_id, publish_type) "
                "VALUES(?,?,?)"
            )
            self.conn.execute(sql, values)
            self.conn.commit()
        except sqlite3.DatabaseError:
            pass
        return self.find_by_id_and_type(
            published_ban.infraction_id, published_ban.publish_type
        )

    def delete_with_type(self, infraction_id: int, publish_type: PublishType) -> None:
        self.conn.execute(
            "DELETE FROM published_messages WHERE infraction_id=:infraction_id AND publish_type=:publish_type",
            {"infraction_id": infraction_id, "publish_type": publish_type.value},
        )
        self.conn.commit()

    def delete_all_with_id(self, infraction_id: int) -> None:
        self.conn.execute(
            "DELETE FROM published_messages WHERE infraction_id=:infraction_id",
            {"infraction_id": infraction_id},
        )
        self.conn.commit()
