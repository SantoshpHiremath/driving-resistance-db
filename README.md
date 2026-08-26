# Driving Resistance Database & Reporting Tool

A real, tested relational database project built to close a specific gap for
postings that ask for Microsoft Access + VBA experience around database
application development — closest to Audi's "Praktikum Gesamtfahrzeug-
entwicklung mit IT Schwerpunkt" posting, which centers on maintaining and
extending an Access-based driving-resistance ("Fahrwiderstand") database.

## What this is (read before citing anywhere)

**This is NOT Microsoft Access, and the logic is NOT VBA.** Access is
Windows-only desktop software; this project was built and tested in a Linux
sandbox, where real MS Access cannot run. Rather than fake Access experience
I don't have, I built the closest thing I could actually construct and
verify here:

- **SQLite** instead of Access's Jet/ACE database engine — both are
  file-based relational databases with the same core skillset (schema
  design, primary/foreign keys, indexing, SQL queries, forms-over-tables
  style reporting). SQLite is not Access.
- **Python** instead of VBA for the application/query logic (data entry
  validation, report generation, performance-optimization queries). Not
  VBA, not VBS.

If asked in an interview: I have not used Microsoft Access or written VBA.
This project demonstrates the same underlying database-development skills
(schema design, query optimization, building a small application on top of
a database) using tools I could actually build and test.

## Domain

The schema and data are modeled on what the posting describes: tracking
driving-resistance ("Fahrwiderstand") measurements for vehicle variants
across global markets, plus a weekly approval ("Freigabe") workflow.
**All data is synthetic** — generated to be realistic, not real Audi data,
which I have no access to.

- `vehicles` — vehicle variant master data (model, market, powertrain).
- `test_runs` — individual driving-resistance test executions (test bench
  or road, date, conditions).
- `resistance_measurements` — the actual measured values per test run
  (rolling resistance, aerodynamic drag, total resistance coefficients).
- `approvals` — the weekly approval-round workflow: status per test run
  (Pending / Approved / Rejected / Needs Rework), reviewer, notes.

## What's real and tested here

- **Schema with real constraints**: foreign keys, `CHECK` constraints on
  physically-plausible ranges (e.g. drag coefficient can't be negative),
  a `UNIQUE` constraint preventing duplicate test-run entries for the same
  vehicle/date/track combination.
- **Data-quality cleaning pass** (the "maintain and improve an existing
  database" part of the posting): ~26,700 test runs and their measurements
  are seeded, with 30 measurements deliberately orphaned (referencing a
  test run deleted without cascading — a realistic legacy-database problem)
  and 15 out-of-range rows slipped into a staging table (negative
  resistance values, physically impossible). A `UNIQUE` constraint on
  (vehicle, date, track) prevents new duplicate test-run rows going
  forward; `clean.py` audits for any that predate the constraint (finds
  zero, confirming the constraint is doing its job) and finds, then
  quarantines (not silently deletes) the orphaned and suspect rows.
- **Query/reporting layer** (`src/reports.py`): functions that mirror what
  an Access report or form would surface — approval-queue summary (what
  the "wöchentliche Fahrwiderstands-Freigaberunde" needs), per-market
  resistance averages, and a statistical (z-score) outlier report.
- **A measured performance optimization**: `src/benchmark.py` times a
  per-vehicle measurement lookup (the kind of drill-down a form does every
  time a user selects a different vehicle) before and after adding an
  index, and prints the `EXPLAIN QUERY PLAN` for both so the *reason* for
  the change is visible, not just the number. On this dataset it measures
  a genuine ~1,070x speedup (a full table scan becomes an index seek) —
  this is the direct equivalent of "implementierst Funktionen zur
  Verbesserung der Datenbank-Performance" from the posting, measured live
  each run, not a hardcoded claim.
- **22 automated tests** (`tests/test_db.py`) covering schema constraints
  (CHECK/UNIQUE/FOREIGN KEY all verified to actually reject bad data),
  the cleaning logic (against both dirty and already-clean databases),
  every report function (including a manually-recomputed spot check and a
  deliberately-injected outlier to prove the detector actually detects),
  and the benchmark (verifying the index changes the query plan and speed
  without changing the query's results).

## Running it

```bash
python3 src/build_db.py       # creates driving_resistance.db, seeds ~26,700 synthetic + dirty rows
python3 src/clean.py          # runs the cleaning pass, prints before/after counts
python3 src/reports.py        # prints the approval-queue, market-average, and outlier reports
python3 src/benchmark.py      # measures and prints the indexing performance improvement
python3 -m pytest tests/ -v   # runs all 22 tests (against small, isolated temp databases)
```
