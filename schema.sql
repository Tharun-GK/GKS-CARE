BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    age INTEGER NOT NULL CHECK (age > 0),
    gender TEXT NOT NULL,
    data_source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patient_history (
    id INTEGER PRIMARY KEY,
    patient_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (patient_id, record_type),
    FOREIGN KEY (patient_id) REFERENCES patients (patient_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    patient_id TEXT NOT NULL,
    measured_at TEXT NOT NULL,
    heart_rate_bpm REAL NOT NULL CHECK (heart_rate_bpm > 0),
    spo2_percent REAL NOT NULL CHECK (spo2_percent >= 0 AND spo2_percent <= 100),
    temperature_value REAL NOT NULL,
    temperature_unit TEXT NOT NULL CHECK (temperature_unit IN ('F', 'C')),
    source TEXT NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patients (patient_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY,
    patient_id TEXT,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patients (patient_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS observations_patient_measured_at
    ON observations (patient_id, measured_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS audit_events_patient_occurred_at
    ON audit_events (patient_id, occurred_at DESC, id DESC);

INSERT OR IGNORE INTO schema_migrations (version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;
