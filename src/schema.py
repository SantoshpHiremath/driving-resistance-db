"""Schema definition for the driving-resistance database.

A database tracking driving-resistance ("Fahrwiderstand") measurements per
vehicle variant/market, plus a weekly approval workflow. Built in SQLite
(rather than MS Access) — see README.
"""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    model_code      TEXT NOT NULL,
    market          TEXT NOT NULL,
    powertrain      TEXT NOT NULL CHECK (powertrain IN ('ICE', 'PHEV', 'BEV')),
    model_year      INTEGER NOT NULL CHECK (model_year BETWEEN 2018 AND 2027)
);

CREATE TABLE IF NOT EXISTS test_runs (
    test_run_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id      INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
    test_date       TEXT NOT NULL,
    test_type       TEXT NOT NULL CHECK (test_type IN ('Prüfstand', 'Straße')),
    track_or_rig    TEXT NOT NULL,
    UNIQUE (vehicle_id, test_date, track_or_rig)
);

CREATE TABLE IF NOT EXISTS resistance_measurements (
    measurement_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    test_run_id         INTEGER NOT NULL REFERENCES test_runs(test_run_id),
    rolling_resistance_n REAL NOT NULL CHECK (rolling_resistance_n >= 0),
    aero_drag_coefficient REAL NOT NULL CHECK (aero_drag_coefficient >= 0 AND aero_drag_coefficient < 1),
    total_resistance_n   REAL NOT NULL CHECK (total_resistance_n >= 0)
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    test_run_id     INTEGER NOT NULL REFERENCES test_runs(test_run_id),
    status          TEXT NOT NULL CHECK (status IN ('Pending', 'Approved', 'Rejected', 'Needs Rework')),
    reviewer        TEXT,
    review_date     TEXT,
    notes           TEXT
);
"""
