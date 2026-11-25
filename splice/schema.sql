CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    plan BLOB NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)
);
CREATE TABLE IF NOT EXISTS traces (
    span_id TEXT NOT NULL REFERENCES spans(span_id),
    trace_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('a', 'b')),
    digest TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (span_id, trace_id),
    UNIQUE (span_id, trace_id, direction)
);
CREATE TABLE IF NOT EXISTS active_traces (
    span_id TEXT NOT NULL REFERENCES spans(span_id),
    direction TEXT NOT NULL CHECK (direction IN ('a', 'b')),
    trace_id TEXT NOT NULL,
    PRIMARY KEY (span_id, direction),
    FOREIGN KEY (span_id, trace_id, direction) REFERENCES traces(span_id, trace_id, direction)
);
CREATE TABLE IF NOT EXISTS releases (
    span_id TEXT NOT NULL REFERENCES spans(span_id),
    revision INTEGER NOT NULL,
    digest TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (span_id, revision)
);
CREATE TABLE IF NOT EXISTS span_registry (
    span_id TEXT PRIMARY KEY REFERENCES spans(span_id),
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    stamp INTEGER NOT NULL DEFAULT 0 CHECK (stamp >= 0)
);
CREATE TABLE IF NOT EXISTS limit_tiers (
    span_id TEXT NOT NULL REFERENCES spans(span_id),
    registry_version INTEGER NOT NULL CHECK (registry_version >= 1),
    digest TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (span_id, registry_version)
);
CREATE TABLE IF NOT EXISTS trace_dates (
    span_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    measured_on TEXT NOT NULL,
    PRIMARY KEY (span_id, trace_id),
    FOREIGN KEY (span_id, trace_id) REFERENCES traces(span_id, trace_id)
);
