"""Test suite for the driving-resistance database project.

Each test builds its own small, isolated SQLite database in a temp
directory (via build_db.build(db_path=..., n_attempts=..., n_vehicles=...))
rather than depending on the shared driving_resistance.db file — same
schema and logic, smaller scale, no cross-test interference or ordering
dependency.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import build_db
import clean
import reports
import benchmark


@pytest.fixture
def db(tmp_path):
    """A small (but not trivial) seeded database, fresh per test."""
    db_path = tmp_path / "test.db"
    info = build_db.build(db_path=db_path, n_attempts=3000, n_vehicles=10)
    conn = sqlite3.connect(db_path)
    yield conn, info
    conn.close()


@pytest.fixture
def clean_db(tmp_path):
    """A database with NO injected data-quality problems — used to test
    that cleaning functions correctly report zero issues on already-clean
    data, not just that they find problems when problems exist."""
    db_path = tmp_path / "clean_test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(build_db.SCHEMA_SQL)
    cur = conn.execute(
        "INSERT INTO vehicles (model_code, market, powertrain, model_year) VALUES ('A3', 'DE', 'BEV', 2026)"
    )
    vehicle_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO test_runs (vehicle_id, test_date, test_type, track_or_rig) VALUES (?, '2026-01-01', 'Prüfstand', 'Prüfstand-1')",
        (vehicle_id,),
    )
    test_run_id = cur.lastrowid
    conn.execute(
        "INSERT INTO resistance_measurements (test_run_id, rolling_resistance_n, aero_drag_coefficient, total_resistance_n) VALUES (?, 100.0, 0.28, 220.0)",
        (test_run_id,),
    )
    conn.execute(
        "CREATE TABLE staging_suspect_measurements (test_run_id INTEGER, rolling_resistance_n REAL, aero_drag_coefficient REAL, total_resistance_n REAL)"
    )
    conn.commit()
    yield conn
    conn.close()


# --- Schema constraint tests ---------------------------------------------

def test_check_constraint_rejects_negative_rolling_resistance(clean_db):
    with pytest.raises(sqlite3.IntegrityError):
        clean_db.execute(
            "INSERT INTO resistance_measurements (test_run_id, rolling_resistance_n, aero_drag_coefficient, total_resistance_n) VALUES (1, -5.0, 0.28, 220.0)"
        )


def test_check_constraint_rejects_invalid_powertrain(clean_db):
    with pytest.raises(sqlite3.IntegrityError):
        clean_db.execute(
            "INSERT INTO vehicles (model_code, market, powertrain, model_year) VALUES ('A4', 'DE', 'DIESEL', 2026)"
        )


def test_check_constraint_rejects_invalid_test_type(clean_db):
    with pytest.raises(sqlite3.IntegrityError):
        clean_db.execute(
            "INSERT INTO test_runs (vehicle_id, test_date, test_type, track_or_rig) VALUES (1, '2026-01-01', 'Labor', 'Prüfstand-1')"
        )


def test_unique_constraint_rejects_duplicate_test_run(clean_db):
    with pytest.raises(sqlite3.IntegrityError):
        clean_db.execute(
            "INSERT INTO test_runs (vehicle_id, test_date, test_type, track_or_rig) VALUES (1, '2026-01-01', 'Prüfstand', 'Prüfstand-1')"
        )


def test_foreign_key_rejects_measurement_for_nonexistent_test_run(clean_db):
    clean_db.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        clean_db.execute(
            "INSERT INTO resistance_measurements (test_run_id, rolling_resistance_n, aero_drag_coefficient, total_resistance_n) VALUES (9999, 100.0, 0.28, 220.0)"
        )


# --- Cleaning logic tests --------------------------------------------------

def test_finds_expected_number_of_orphaned_measurements(db):
    conn, info = db
    orphans = clean.find_orphaned_measurements(conn)
    assert len(orphans) == info["n_orphans"]


def test_clean_db_has_zero_orphans(clean_db):
    assert clean.find_orphaned_measurements(clean_db) == []


def test_quarantine_orphaned_measurements_removes_them_from_main_table(db):
    conn, info = db
    removed = clean.quarantine_orphaned_measurements(conn)
    assert removed == info["n_orphans"]
    assert clean.find_orphaned_measurements(conn) == []


def test_quarantine_orphaned_measurements_preserves_the_data(db):
    conn, info = db
    before_ids = {row[0] for row in clean.find_orphaned_measurements(conn)}
    clean.quarantine_orphaned_measurements(conn)
    quarantined_ids = {
        row[0] for row in conn.execute("SELECT measurement_id FROM quarantine_orphaned_measurements")
    }
    assert before_ids == quarantined_ids  # nothing lost, nothing invented


def test_finds_expected_number_of_suspect_rows(db):
    conn, info = db
    suspects = clean.find_suspect_rows(conn)
    assert len(suspects) == info["n_suspects"]


def test_clean_db_has_zero_suspect_rows(clean_db):
    assert clean.find_suspect_rows(clean_db) == []


def test_quarantine_suspect_rows_removes_them(db):
    conn, info = db
    removed = clean.quarantine_suspect_rows(conn)
    assert removed == info["n_suspects"]
    assert clean.find_suspect_rows(conn) == []


def test_no_duplicate_test_runs_after_unique_constraint(db):
    conn, info = db
    assert clean.find_duplicate_test_runs(conn) == []


# --- Reports tests ----------------------------------------------------------

def test_approval_queue_summary_total_matches_approvals_table(db):
    conn, info = db
    summary = reports.approval_queue_summary(conn)
    total_from_summary = sum(summary.values())
    total_from_table = conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
    assert total_from_summary == total_from_table


def test_approval_queue_summary_only_has_valid_statuses(db):
    conn, info = db
    summary = reports.approval_queue_summary(conn)
    assert set(summary.keys()) <= {"Approved", "Pending", "Rejected", "Needs Rework"}


def test_pending_approvals_detail_only_returns_pending_or_rework(db):
    conn, info = db
    rows = reports.pending_approvals_detail(conn, limit=1000)
    statuses = {row[5] for row in rows}
    assert statuses <= {"Pending", "Needs Rework"}


def test_pending_approvals_detail_respects_limit(db):
    conn, info = db
    rows = reports.pending_approvals_detail(conn, limit=3)
    assert len(rows) <= 3


def test_market_resistance_averages_match_manual_calculation(db):
    conn, info = db
    results = {market: avg for market, avg, cnt in reports.market_resistance_averages(conn)}
    # Spot-check one market against a manually computed average.
    a_market = next(iter(results))
    manual_avg = conn.execute("""
        SELECT ROUND(AVG(m.total_resistance_n), 2)
        FROM resistance_measurements m
        JOIN test_runs t ON m.test_run_id = t.test_run_id
        JOIN vehicles v ON t.vehicle_id = v.vehicle_id
        WHERE v.market = ?
    """, (a_market,)).fetchone()[0]
    assert results[a_market] == manual_avg


def test_outlier_measurements_detects_a_known_injected_outlier(db):
    conn, info = db
    # Inject one obvious outlier tied to a real test_run so the detector
    # has something guaranteed to be extreme, rather than depending on
    # whatever the random synthetic data happens to produce.
    test_run_id = conn.execute("SELECT test_run_id FROM test_runs LIMIT 1").fetchone()[0]
    conn.execute(
        "INSERT INTO resistance_measurements (test_run_id, rolling_resistance_n, aero_drag_coefficient, total_resistance_n) VALUES (?, 179.0, 0.33, 999999.0)",
        (test_run_id,),
    )
    conn.commit()
    outliers = reports.outlier_measurements(conn)
    outlier_values = {row[2] for row in outliers}
    assert 999999.0 in outlier_values


def test_outlier_measurements_empty_on_uniform_data(clean_db):
    # A single-row (or perfectly uniform) dataset has zero variance, so
    # nothing should be flagged and the function must not divide by zero.
    assert reports.outlier_measurements(clean_db) == []


# --- Benchmark correctness tests --------------------------------------------

def test_benchmark_query_returns_identical_results_with_and_without_index(db):
    """The whole point of an index is that it changes performance, not
    results — this test verifies the index doesn't silently change what
    the query returns."""
    conn, info = db
    conn.execute(benchmark.DROP_INDEX_STMT)
    before_rows = conn.execute(benchmark.QUERY, (info["vehicle_ids"][0],)).fetchall()

    conn.execute(benchmark.INDEX_STMT)
    after_rows = conn.execute(benchmark.QUERY, (info["vehicle_ids"][0],)).fetchall()

    assert before_rows == after_rows


def test_benchmark_index_changes_query_plan_from_scan_to_search(db):
    conn, info = db
    conn.execute(benchmark.DROP_INDEX_STMT)
    plan_before = benchmark.explain(conn)
    assert any("SCAN m" in step[3] for step in plan_before)

    conn.execute(benchmark.INDEX_STMT)
    plan_after = benchmark.explain(conn)
    assert any("SEARCH m USING INDEX idx_measurements_test_run_id" in step[3] for step in plan_after)
