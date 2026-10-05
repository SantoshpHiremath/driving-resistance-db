"""Query/reporting layer — the equivalent of what an Access report or bound
form would surface, built here as plain SQL + Python on SQLite
(see README).
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "driving_resistance.db"


def approval_queue_summary(conn):
    """Supports the weekly driving-resistance approval round
    ('Freigaberunde') — counts of test runs by approval status, the kind of
    summary a moderator would pull up at the start of the weekly meeting."""
    rows = conn.execute("""
        SELECT status, COUNT(*) as cnt
        FROM approvals
        GROUP BY status
        ORDER BY cnt DESC
    """).fetchall()
    return {status: cnt for status, cnt in rows}


def pending_approvals_detail(conn, limit=20):
    """The actual worklist for the meeting: which test runs are still
    Pending or Needs Rework, with vehicle context."""
    return conn.execute("""
        SELECT a.approval_id, v.model_code, v.market, t.test_date, t.track_or_rig, a.status
        FROM approvals a
        JOIN test_runs t ON a.test_run_id = t.test_run_id
        JOIN vehicles v ON t.vehicle_id = v.vehicle_id
        WHERE a.status IN ('Pending', 'Needs Rework')
        ORDER BY t.test_date
        LIMIT ?
    """, (limit,)).fetchall()


def market_resistance_averages(conn):
    """'marktspezifische weltweite Fahrwiderstände' — average total
    resistance per market, the core cross-market comparison the role
    supports."""
    return conn.execute("""
        SELECT v.market, ROUND(AVG(m.total_resistance_n), 2) as avg_total_resistance,
               COUNT(*) as measurement_count
        FROM resistance_measurements m
        JOIN test_runs t ON m.test_run_id = t.test_run_id
        JOIN vehicles v ON t.vehicle_id = v.vehicle_id
        GROUP BY v.market
        ORDER BY avg_total_resistance DESC
    """).fetchall()


def outlier_measurements(conn, z_threshold=2.5):
    """Flags measurements whose total_resistance_n is more than
    z_threshold standard deviations from the mean — the 'Analyse ... zur
    Verbesserung der Datenbank-Performance/-Qualität' angle: surfacing
    rows worth a second look rather than trusting every row blindly."""
    stats = conn.execute("""
        SELECT AVG(total_resistance_n),
               (SELECT AVG((total_resistance_n - sub.avg_val) * (total_resistance_n - sub.avg_val))
                FROM resistance_measurements,
                     (SELECT AVG(total_resistance_n) as avg_val FROM resistance_measurements) sub)
        FROM resistance_measurements
    """).fetchone()
    mean = stats[0]
    variance = stats[1]
    stddev = variance ** 0.5 if variance else 0
    if stddev == 0:
        return []
    rows = conn.execute("""
        SELECT measurement_id, test_run_id, total_resistance_n FROM resistance_measurements
    """).fetchall()
    outliers = [
        r for r in rows
        if abs(r[2] - mean) / stddev > z_threshold
    ]
    return outliers


def print_all_reports():
    conn = sqlite3.connect(DB_PATH)

    print("=== Approval Queue Summary ===")
    for status, cnt in approval_queue_summary(conn).items():
        print(f"  {status}: {cnt}")

    print("\n=== Pending/Needs-Rework Detail (first 10) ===")
    for row in pending_approvals_detail(conn, limit=10):
        print(f"  #{row[0]} | {row[1]} ({row[2]}) | {row[3]} | {row[4]} | {row[5]}")

    print("\n=== Market Resistance Averages ===")
    for market, avg, cnt in market_resistance_averages(conn):
        print(f"  {market}: {avg} N avg (n={cnt})")

    print("\n=== Outlier Measurements (|z| > 2.5) ===")
    outliers = outlier_measurements(conn)
    print(f"  {len(outliers)} flagged")
    for o in outliers[:5]:
        print(f"    measurement_id={o[0]} test_run_id={o[1]} total_resistance_n={o[2]}")

    conn.close()


if __name__ == "__main__":
    print_all_reports()
