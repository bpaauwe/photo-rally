-- Photo Road Rally schema (SQLite)
-- Re-runnable: `flask --app rally init-db` creates missing tables only.

CREATE TABLE IF NOT EXISTS user (
    id        INTEGER PRIMARY KEY,
    username  TEXT NOT NULL UNIQUE,
    pw_hash   TEXT NOT NULL,
    role      TEXT NOT NULL DEFAULT 'organizer'
);

CREATE TABLE IF NOT EXISTS rally (
    id                 INTEGER PRIMARY KEY,
    name               TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft','published','running','scoring','final')),
    -- scoring rules (all distances in meters)
    cap_m              REAL NOT NULL DEFAULT 200,
    missing_penalty_m  REAL NOT NULL DEFAULT 250,
    round_to_m         REAL NOT NULL DEFAULT 5,
    mark_policy        TEXT NOT NULL DEFAULT 'last'
                       CHECK (mark_policy IN ('first','last','best')),
    rules_json         TEXT NOT NULL DEFAULT '{}',   -- extras: tiebreakers, notes
    subtitle           TEXT NOT NULL DEFAULT '',
    event_date         TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS instruction (
    id        INTEGER PRIMARY KEY,
    rally_id  INTEGER NOT NULL REFERENCES rally(id) ON DELETE CASCADE,
    seq       INTEGER NOT NULL,
    kind      TEXT NOT NULL DEFAULT 'instr' CHECK (kind IN ('instr','note')),
    mileage   REAL,                 -- cumulative odometer miles; NULL while still measuring
    text      TEXT NOT NULL,        -- may contain **markup** and literal backslash-n line breaks
    note      TEXT NOT NULL DEFAULT '',   -- organizer-only
    UNIQUE (rally_id, seq)
);

CREATE TABLE IF NOT EXISTS object (
    id                     INTEGER PRIMARY KEY,
    public_id              TEXT,                 -- random token used in participant URLs (ids follow creation order)
    rally_id               INTEGER NOT NULL REFERENCES rally(id) ON DELETE CASCADE,
    code                   TEXT NOT NULL,        -- e.g. "A", "7"
    name                   TEXT NOT NULL,
    photo_path             TEXT,
    desc                   TEXT,
    where_note             TEXT,                 -- "driver's side at 2nd driveway"
    -- organizer capture (original, never overwritten)
    lat                    REAL,
    lon                    REAL,
    acc_m                  REAL,
    samples                INTEGER,
    spread_m               REAL,                 -- RMS scatter of the sampled fixes
    -- optional correction, used for scoring when present
    adj_lat                REAL,
    adj_lon                REAL,
    after_instruction_seq  INTEGER,
    UNIQUE (rally_id, code)
);

CREATE TABLE IF NOT EXISTS team (
    id         INTEGER PRIMARY KEY,
    rally_id   INTEGER NOT NULL REFERENCES rally(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    join_code  TEXT NOT NULL UNIQUE,
    UNIQUE (rally_id, name)
);

CREATE TABLE IF NOT EXISTS mark (
    id           INTEGER PRIMARY KEY,
    team_id      INTEGER NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    object_id    INTEGER NOT NULL REFERENCES object(id) ON DELETE CASCADE,
    lat          REAL NOT NULL,
    lon          REAL NOT NULL,
    accuracy_m   REAL,
    n_samples    INTEGER,
    odometer     REAL,                           -- informational only
    client_ts    TEXT,
    server_ts    TEXT NOT NULL DEFAULT (datetime('now')),
    client_uuid  TEXT NOT NULL UNIQUE            -- idempotent offline sync
);

CREATE INDEX IF NOT EXISTS idx_mark_team_obj ON mark (team_id, object_id);
CREATE INDEX IF NOT EXISTS idx_object_rally  ON object (rally_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_object_public ON object (public_id);
CREATE INDEX IF NOT EXISTS idx_team_rally    ON team (rally_id);
