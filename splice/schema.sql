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
CREATE TABLE IF NOT EXISTS review_rosters (
    span_id TEXT NOT NULL REFERENCES spans(span_id),
    direction TEXT NOT NULL CHECK (direction IN ('a', 'b')),
    trace_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    tolerance_mdb INTEGER NOT NULL CHECK (tolerance_mdb >= 0),
    PRIMARY KEY (span_id, direction, trace_id),
    UNIQUE (span_id, direction, position),
    FOREIGN KEY (span_id, trace_id, direction) REFERENCES traces(span_id, trace_id, direction)
);
CREATE TABLE IF NOT EXISTS releases (
    span_id TEXT NOT NULL REFERENCES spans(span_id),
    revision INTEGER NOT NULL,
    digest TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (span_id, revision)
);
