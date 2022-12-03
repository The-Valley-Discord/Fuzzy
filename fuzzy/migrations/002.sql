-- Locked Channels
CREATE TABLE IF NOT EXISTS thread_locks (
    channel_id      INTEGER     PRIMARY KEY,
    moderator_id    INTEGER     NOT NULL,
    moderator_name  TEXT        NOT NULL,
    guild_id        INTEGER     NOT NULL,
    reason          TEXT,
    end_time        timestamp   NOT NULL,

    FOREIGN KEY(guild_id) REFERENCES guilds(id)
);