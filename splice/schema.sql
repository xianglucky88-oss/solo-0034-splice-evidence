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

CREATE TABLE IF NOT EXISTS plan_versions (
    span_id TEXT NOT NULL REFERENCES spans(span_id),
    plan_version INTEGER NOT NULL CHECK (plan_version >= 2),
    parent_version INTEGER NOT NULL,
    basis TEXT NOT NULL,
    plan BLOB NOT NULL,
    PRIMARY KEY (span_id, plan_version)
);
CREATE TABLE IF NOT EXISTS plan_relations (
    span_id TEXT NOT NULL,
    parent_version INTEGER NOT NULL,
    plan_version INTEGER NOT NULL,
    relation TEXT NOT NULL CHECK (relation IN ('split', 'merge', 'continue', 'added', 'retired')),
    from_site TEXT,
    to_site TEXT,
    PRIMARY KEY (span_id, plan_version, relation, from_site, to_site),
    FOREIGN KEY (span_id, plan_version) REFERENCES plan_versions(span_id, plan_version)
);
CREATE TABLE IF NOT EXISTS version_traces (
    span_id TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    trace_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('a', 'b')),
    digest TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (span_id, plan_version, trace_id),
    UNIQUE (span_id, plan_version, trace_id, direction),
    FOREIGN KEY (span_id, plan_version) REFERENCES plan_versions(span_id, plan_version)
);
CREATE TABLE IF NOT EXISTS version_active (
    span_id TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('a', 'b')),
    trace_id TEXT NOT NULL,
    PRIMARY KEY (span_id, plan_version, direction),
    FOREIGN KEY (span_id, plan_version, trace_id, direction)
        REFERENCES version_traces(span_id, plan_version, trace_id, direction)
);
CREATE TABLE IF NOT EXISTS version_releases (
    span_id TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    digest TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (span_id, plan_version, revision),
    FOREIGN KEY (span_id, plan_version) REFERENCES plan_versions(span_id, plan_version)
);
