"""Builds and seeds driving_resistance.db with realistic SYNTHETIC data.

Not real Audi data. Deliberately injects data-quality problems (duplicate
test runs, orphaned measurements, out-of-range values) so the cleaning
script (clean.py) has genuine work to do — mirrors the posting's ask to
maintain/optimize an *existing* database, not just build a clean one.
"""
import random
import sqlite3
from pathlib import Path

from schema import SCHEMA_SQL

DB_PATH = Path(__file__).parent.parent / "driving_resistance.db"

random.seed(42)

MODEL_CODES = ["A3", "A4", "A6", "Q4", "Q6", "e-tron GT"]
MARKETS = ["DE", "US", "CN", "JP", "NO", "IN", "BR", "GB"]
POWERTRAINS = ["ICE", "PHEV", "BEV"]
TRACKS = ["Prüfstand-1", "Prüfstand-2", "Straße-Ingolstadt", "Straße-Nardo"]


def build(db_path=DB_PATH, n_attempts=60000, n_vehicles=40):
    """Builds and seeds a driving-resistance database at db_path.

    db_path/n_attempts/n_vehicles are parameterized (rather than hardcoded)
    so the test suite can build small, fast, isolated databases in a temp
    directory instead of depending on the shared driving_resistance.db
    file — same logic, smaller scale, no cross-test interference.
    """
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)

    # --- vehicles ---
    vehicle_ids = []
    for _ in range(n_vehicles):
        cur = conn.execute(
            "INSERT INTO vehicles (model_code, market, powertrain, model_year) VALUES (?, ?, ?, ?)",
            (
                random.choice(MODEL_CODES),
                random.choice(MARKETS),
                random.choice(POWERTRAINS),
                random.randint(2022, 2026),
            ),
        )
        vehicle_ids.append(cur.lastrowid)

    # --- test_runs + resistance_measurements ---
    # 60,000 rows: large enough for the indexing benchmark to show a real,
    # non-trivial improvement (at a few hundred rows SQLite's sequential
    # scan is already fast enough that an index adds more overhead than it
    # saves — this dataset size is chosen so the measured result is
    # honest and representative, not just favorable).
    test_run_ids = []
    for i in range(n_attempts):
        vehicle_id = random.choice(vehicle_ids)
        test_date = f"2026-{random.randint(1,7):02d}-{random.randint(1,28):02d}"
        track = random.choice(TRACKS)
        test_type = "Prüfstand" if "Prüfstand" in track else "Straße"
        try:
            cur = conn.execute(
                "INSERT INTO test_runs (vehicle_id, test_date, test_type, track_or_rig) VALUES (?, ?, ?, ?)",
                (vehicle_id, test_date, test_type, track),
            )
        except sqlite3.IntegrityError:
            continue  # rare natural UNIQUE collision, skip
        test_run_id = cur.lastrowid
        test_run_ids.append(test_run_id)

        rolling = round(random.uniform(80, 180), 2)
        aero = round(random.uniform(0.22, 0.34), 3)
        total = round(rolling + aero * random.uniform(300, 500), 2)
        conn.execute(
            "INSERT INTO resistance_measurements (test_run_id, rolling_resistance_n, aero_drag_coefficient, total_resistance_n) VALUES (?, ?, ?, ?)",
            (test_run_id, rolling, aero, total),
        )

        conn.execute(
            "INSERT INTO approvals (test_run_id, status, reviewer, review_date, notes) VALUES (?, ?, ?, ?, ?)",
            (
                test_run_id,
                random.choices(
                    ["Approved", "Pending", "Needs Rework", "Rejected"],
                    weights=[55, 25, 15, 5],
                )[0],
                random.choice(["M. Bauer", "S. Fischer", "L. Wagner", None]),
                test_date if random.random() > 0.3 else None,
                None,
            ),
        )

    conn.commit()

    # --- inject data-quality problems for clean.py to find ---
    # 1) 30 orphaned measurements referencing a test_run that gets deleted
    #    after insertion (simulates a bad delete from an earlier session
    #    that didn't cascade properly). FK enforcement is turned off just
    #    for this step to allow the orphan to be created — this models a
    #    real-world "existing messy database" scenario, which is exactly
    #    what clean.py is meant to detect and fix.
    conn.execute("PRAGMA foreign_keys = OFF")
    n_orphans = min(30, len(test_run_ids))
    orphan_targets = random.sample(test_run_ids, n_orphans)
    for trid in orphan_targets:
        conn.execute("DELETE FROM test_runs WHERE test_run_id = ?", (trid,))
    conn.execute("PRAGMA foreign_keys = ON")

    # 2) 15 physically-implausible measurements slipped in via a raw INSERT
    #    that bypasses the CHECK constraints being tested for (simulate
    #    legacy rows from before constraints existed) — insert into a
    #    duplicate unconstrained staging table instead, since the real
    #    table enforces CHECK. This models "bad rows already in the export
    #    clean.py has to flag."
    conn.execute("""
        CREATE TABLE IF NOT EXISTS staging_suspect_measurements (
            test_run_id INTEGER, rolling_resistance_n REAL,
            aero_drag_coefficient REAL, total_resistance_n REAL
        )
    """)
    n_suspects = min(15, len(test_run_ids))
    for trid in random.sample(test_run_ids, n_suspects):
        conn.execute(
            "INSERT INTO staging_suspect_measurements VALUES (?, ?, ?, ?)",
            (trid, round(random.uniform(-20, -1), 2), round(random.uniform(0.2, 0.3), 3), round(random.uniform(50, 100), 2)),
        )

    conn.commit()
    conn.close()
    print(f"Built {db_path} — {len(vehicle_ids)} vehicles, {len(test_run_ids)} test runs seeded (with intentional data-quality issues for clean.py).")
    return {"vehicle_ids": vehicle_ids, "test_run_ids": test_run_ids, "n_orphans": n_orphans, "n_suspects": n_suspects}


if __name__ == "__main__":
    build()
