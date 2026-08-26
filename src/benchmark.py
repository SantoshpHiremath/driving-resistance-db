"""Measures a real performance improvement from adding an index — the
direct equivalent of the posting's 'implementierst neue Funktionen zur
Verbesserung der Datenbank-Performance.'

Query: look up all resistance measurements for one vehicle at a time
(the kind of drill-down an Access form bound to a single vehicle record
would run every time a user selects a different vehicle). Without an
index on resistance_measurements.test_run_id, this forces a full table
scan of the measurements table on every lookup — with 26k+ rows, that is
genuinely slow.

Both numbers below are measured live each time this script runs, not
hardcoded — including an EXPLAIN QUERY PLAN before/after so the *reason*
for the improvement is visible, not just the number.
"""
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "driving_resistance.db"

QUERY = """
    SELECT t.test_date, m.total_resistance_n
    FROM test_runs t
    JOIN resistance_measurements m ON m.test_run_id = t.test_run_id
    WHERE t.vehicle_id = ?
    ORDER BY t.test_date
"""

INDEX_STMT = "CREATE INDEX IF NOT EXISTS idx_measurements_test_run_id ON resistance_measurements(test_run_id)"
DROP_INDEX_STMT = "DROP INDEX IF EXISTS idx_measurements_test_run_id"


def explain(conn):
    return [tuple(row) for row in conn.execute("EXPLAIN QUERY PLAN " + QUERY, (1,))]


def time_lookups(conn, n_vehicles=20):
    """Runs the per-vehicle lookup query for n_vehicles distinct vehicle_ids
    (cycling 1..40) and returns total wall-clock time."""
    start = time.perf_counter()
    for i in range(n_vehicles):
        vehicle_id = (i % 40) + 1
        conn.execute(QUERY, (vehicle_id,)).fetchall()
    return time.perf_counter() - start


def run_benchmark(n_vehicles=20):
    conn = sqlite3.connect(DB_PATH)

    conn.execute(DROP_INDEX_STMT)
    plan_before = explain(conn)
    before = time_lookups(conn, n_vehicles)

    conn.execute(INDEX_STMT)
    plan_after = explain(conn)
    after = time_lookups(conn, n_vehicles)

    improvement_pct = (before - after) / before * 100 if before > 0 else 0
    speedup_x = before / after if after > 0 else float("inf")

    print(f"Per-vehicle measurement lookup, run for {n_vehicles} vehicles:")
    print(f"  Before index: {before:.4f}s total ({before/n_vehicles*1000:.2f} ms/lookup)")
    print(f"  Query plan before: {plan_before}")
    print(f"  After index:  {after:.4f}s total ({after/n_vehicles*1000:.2f} ms/lookup)")
    print(f"  Query plan after:  {plan_after}")
    print(f"  Improvement:  {improvement_pct:.1f}% ({speedup_x:.0f}x faster)")
    print(f"  Why: without the index, every lookup does a full sequential scan of")
    print(f"  resistance_measurements ('SCAN m'); the index turns that into a direct")
    print(f"  seek ('SEARCH m USING INDEX ...'), which is what accounts for the gain.")

    conn.close()
    return {"before_s": before, "after_s": after, "improvement_pct": improvement_pct, "speedup_x": speedup_x}


if __name__ == "__main__":
    run_benchmark()
