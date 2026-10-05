# Driving Resistance Database & Reporting Tool

A tested relational database project for maintaining and extending a driving-resistance ("Fahrwiderstand") database: schema design, data-quality cleaning, a reporting layer, and a measured performance optimization, with a small Python application on top.

## What it does

- Defines a relational schema with real constraints for driving-resistance measurements and a weekly approval workflow.
- Seeds a synthetic, deliberately dirty dataset and cleans it with an auditable pass.
- Provides a query/reporting layer (approval queue, per-market averages, statistical outliers).
- Measures the speedup from adding an index, live on each run.

## Technology

- **SQLite** is the file-based relational database engine, with the core database skillset: schema design, primary/foreign keys, indexing, SQL queries, and forms-over-tables style reporting. Microsoft Access (Jet/ACE) is a Windows desktop alternative for the same kind of file-based database.
- **Python** provides the application and query logic (data entry validation, report generation, performance-optimization queries).

## Domain

The schema and data track driving-resistance measurements for vehicle variants across global markets, plus a weekly approval ("Freigabe") workflow. All data is synthetic, generated to be realistic, and the schema is built so real measurement data can replace it.

- `vehicles`: vehicle variant master data (model, market, powertrain).
- `test_runs`: individual driving-resistance test executions (test bench or road, date, conditions).
- `resistance_measurements`: the measured values per test run (rolling resistance, aerodynamic drag, total resistance coefficients).
- `approvals`: the weekly approval-round workflow: status per test run (Pending / Approved / Rejected / Needs Rework), reviewer, notes.

## Results

- **Schema with real constraints**: foreign keys, `CHECK` constraints on physically plausible ranges (e.g. drag coefficient can't be negative), and a `UNIQUE` constraint preventing duplicate test-run entries for the same vehicle/date/track combination.
- **Data-quality cleaning pass** (maintaining and improving an existing database): ~26,700 test runs and their measurements are seeded, with 30 measurements deliberately orphaned (referencing a test run deleted without cascading, a realistic legacy-database problem) and 15 out-of-range rows slipped into a staging table (negative resistance values, physically impossible). A `UNIQUE` constraint on (vehicle, date, track) prevents new duplicate test-run rows going forward; `clean.py` audits for any that predate the constraint (finds zero, confirming the constraint is doing its job) and finds, then quarantines (not silently deletes) the orphaned and suspect rows.
- **Query/reporting layer** (`src/reports.py`): functions that mirror what an Access report or form would surface: an approval-queue summary (for the weekly "Fahrwiderstands-Freigaberunde"), per-market resistance averages, and a statistical (z-score) outlier report.
- **A measured performance optimization**: `src/benchmark.py` times a per-vehicle measurement lookup (the kind of drill-down a form does every time a user selects a different vehicle) before and after adding an index, and prints the `EXPLAIN QUERY PLAN` for both so the reason for the change is visible, not just the number. On this dataset it measures a ~1,070x speedup (a full table scan becomes an index seek), measured live on each run rather than hardcoded.

## Tests

22 automated tests (`tests/test_db.py`) covering schema constraints (CHECK/UNIQUE/FOREIGN KEY all verified to reject bad data), the cleaning logic (against both dirty and already-clean databases), every report function (including a manually recomputed spot check and a deliberately injected outlier to confirm the detector detects it), and the benchmark (verifying the index changes the query plan and speed without changing the query's results).

## Project structure

```
src/
  schema.py     -- table definitions and constraints
  build_db.py   -- builds and seeds driving_resistance.db (synthetic, deliberately dirty data)
  clean.py      -- data-quality audit and quarantine pass
  reports.py    -- approval queue, market averages, outlier report
  benchmark.py  -- index performance measurement
tests/
  test_db.py    -- 22 tests
driving_resistance.db
```

## Running it

```bash
python3 src/build_db.py       # creates driving_resistance.db, seeds ~26,700 synthetic + dirty rows
python3 src/clean.py          # runs the cleaning pass, prints before/after counts
python3 src/reports.py        # prints the approval-queue, market-average, and outlier reports
python3 src/benchmark.py      # measures and prints the indexing performance improvement
python3 -m pytest tests/ -v   # runs all 22 tests (against small, isolated temp databases)
```

## Possible extensions

- Add a simple front end (forms over the tables) for data entry and approvals.
- Add a scheduled export of the weekly approval summary.
- Load real measurement exports in place of the synthetic seed data.
