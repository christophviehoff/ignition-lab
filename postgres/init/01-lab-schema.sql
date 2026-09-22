-- Runs once, on the first start of an empty postgres-data volume.
-- To re-run it: docker compose down -v, then docker compose up -d
--
-- Ignition creates its own tables for tag history and the store and
-- forward engine. This file only adds a small schema you can query
-- from a Perspective table or a named query, so there is something
-- to look at on day one.

CREATE SCHEMA IF NOT EXISTS lab;

-- A simple state log, the shape a lot of OEE and downtime tables take.
CREATE TABLE IF NOT EXISTS lab.machine_state (
    id           BIGSERIAL    PRIMARY KEY,
    recorded_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    line         TEXT         NOT NULL,
    machine      TEXT         NOT NULL,
    state        TEXT         NOT NULL,
    temp_c       NUMERIC(6,2),
    speed_rpm    NUMERIC(7,1)
);

CREATE INDEX IF NOT EXISTS machine_state_recorded_at_idx
    ON lab.machine_state (recorded_at DESC);

CREATE INDEX IF NOT EXISTS machine_state_line_machine_idx
    ON lab.machine_state (line, machine);

-- A downtime reason lookup, handy for dropdowns in Perspective.
CREATE TABLE IF NOT EXISTS lab.downtime_reason (
    code         TEXT PRIMARY KEY,
    description  TEXT NOT NULL,
    planned      BOOLEAN NOT NULL DEFAULT false
);

INSERT INTO lab.downtime_reason (code, description, planned) VALUES
    ('CHANGEOVER', 'Product changeover',      true),
    ('CLEAN',      'Scheduled cleaning',      true),
    ('JAM',        'Material jam',            false),
    ('STARVED',    'Upstream starved',        false),
    ('BLOCKED',    'Downstream blocked',      false),
    ('FAULT',      'Equipment fault',         false)
ON CONFLICT (code) DO NOTHING;

-- Seed rows so a query returns something before you wire up logging.
INSERT INTO lab.machine_state (recorded_at, line, machine, state, temp_c, speed_rpm) VALUES
    (now() - interval '50 minutes', 'line1', 'mixer',   'RUNNING', 63.40, 120.0),
    (now() - interval '40 minutes', 'line1', 'mixer',   'RUNNING', 65.10, 122.5),
    (now() - interval '30 minutes', 'line1', 'mixer',   'STOPPED', 58.20,   0.0),
    (now() - interval '20 minutes', 'line1', 'mixer',   'RUNNING', 64.80, 119.0),
    (now() - interval '45 minutes', 'line1', 'filler',  'RUNNING', 41.00, 240.0),
    (now() - interval '15 minutes', 'line1', 'filler',  'RUNNING', 42.30, 238.5),
    (now() - interval '35 minutes', 'line1', 'capper',  'RUNNING', 38.90, 300.0),
    (now() - interval '10 minutes', 'line1', 'capper',  'STOPPED', 36.10,   0.0);

-- The compose file connects Ignition as the database owner, so no
-- extra grants are needed. If you add a read only reporting user,
-- this is where you would grant it USAGE on the lab schema.
