"""Data-cleaning pass over the driving-resistance database.

Supports the management and optimization of the driving-resistance
database: finds and fixes real data-quality problems in an existing
database rather than just building on a clean one.

Run standalone: python3 clean.py
Also importable: clean.find_orphaned_measurements(conn), etc. — used by
the test suite to verify each check independently.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "driving_resistance.db"


def find_orphaned_measurements(conn):
    """Measurements referencing a test_run_id that no longer exists."""
    return conn.execute("""
        SELECT m.measurement_id, m.test_run_id
        FROM resistance_measurements m
        LEFT JOIN test_runs t ON m.test_run_id = t.test_run_id
        WHERE t.test_run_id IS NULL
    """).fetchall()


def quarantine_orphaned_measurements(conn):
    """Moves orphaned rows to a quarantine table instead of silently
    deleting them — preserves the data for review rather than destroying
    it, which is the safer real-world choice."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quarantine_orphaned_measurements AS
        SELECT m.* FROM resistance_measurements m
        LEFT JOIN test_runs t ON m.test_run_id = t.test_run_id
        WHERE t.test_run_id IS NULL AND 0
    """)  # ensure table exists with right shape even if empty
    orphans = find_orphaned_measurements(conn)
    ids = [o[0] for o in orphans]
    if ids:
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"""
            INSERT INTO quarantine_orphaned_measurements
            SELECT * FROM resistance_measurements WHERE measurement_id IN ({placeholders})
        """, ids)
        conn.execute(f"DELETE FROM resistance_measurements WHERE measurement_id IN ({placeholders})", ids)
    return len(ids)


def find_suspect_rows(conn):
    """Rows in the unconstrained staging table with physically implausible
    values (negative rolling resistance) — simulates legacy bad data."""
    return conn.execute("""
        SELECT * FROM staging_suspect_measurements WHERE rolling_resistance_n < 0
    """).fetchall()


def quarantine_suspect_rows(conn):
    suspects = find_suspect_rows(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quarantine_suspect_measurements AS
        SELECT * FROM staging_suspect_measurements WHERE 0
    """)
    if suspects:
        conn.executemany(
            "INSERT INTO quarantine_suspect_measurements VALUES (?, ?, ?, ?)",
            suspects,
        )
        conn.execute("DELETE FROM staging_suspect_measurements WHERE rolling_resistance_n < 0")
    return len(suspects)


def find_duplicate_test_runs(conn):
    """Test runs that are logically duplicates (same vehicle+date+track)
    but weren't caught by the UNIQUE constraint because it was added after
    some rows already existed — the constraint itself prevents *new*
    duplicates going forward, but this check audits for any that slipped
    in before it existed."""
    return conn.execute("""
        SELECT vehicle_id, test_date, track_or_rig, COUNT(*) as cnt
        FROM test_runs
        GROUP BY vehicle_id, test_date, track_or_rig
        HAVING cnt > 1
    """).fetchall()


def run_cleaning_pass():
    conn = sqlite3.connect(DB_PATH)
    orphan_count = quarantine_orphaned_measurements(conn)
    suspect_count = quarantine_suspect_rows(conn)
    dupes = find_duplicate_test_runs(conn)
    conn.commit()

    print(f"Orphaned measurements quarantined: {orphan_count}")
    print(f"Suspect (negative-resistance) rows quarantined: {suspect_count}")
    print(f"Duplicate test-run groups found (post-UNIQUE-constraint, should be 0): {len(dupes)}")

    conn.close()
    return {"orphans": orphan_count, "suspects": suspect_count, "duplicates": len(dupes)}


if __name__ == "__main__":
    run_cleaning_pass()
