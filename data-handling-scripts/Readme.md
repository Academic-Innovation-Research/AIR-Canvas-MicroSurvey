# Data Pipeline — Canvas Enrollment + Survey Data → MySQL

This repository contains Python scripts that transform Canvas and Qualtrics exports into clean, deterministic SQL `INSERT` statements for loading survey data into a MySQL database. That database is connected to Metabase for BI visualization and analysis.

The design goal is boring reliability: explicit inputs, repeatable steps, no hidden state, and SQL you can inspect before importing.

---

## What This Pipeline Does

At a high level:

1. Extract **course, instructor, and enrollment metadata** from Canvas.
2. Normalize and enrich that data into structured CSVs.
3. Generate **SQL insert statements** for:
   - Courses
   - People (students + instructors)
   - Enrollments
   - Survey responses
   - Survey answers
4. Load the SQL into MySQL.
5. Analyze everything in Metabase.

**Shortcut:** Run `python3 start.py` to launch all tools at once. The Dashboard (`http://localhost:5010`) links to the drag-and-drop enrollment import, survey import, and SQL export — no command-line steps needed for routine imports.

No direct database writes occur in the numbered scripts. Python only produces SQL.

---

## Prerequisites

- Python 3.10+ (no exotic dependencies)
- Canvas access with permission to:
  - View course settings
  - Download gradebook rosters
- Qualtrics access to export survey responses
- MySQL database already provisioned
- Metabase connected to that MySQL instance

---

## Directory Assumptions

- `Enrollment/` contains Canvas roster CSVs (one per course)
- Survey exports live alongside the scripts (or paths passed explicitly)
- Output SQL files are generated locally and manually imported into MySQL

---

## Step-by-Step Workflow

Follow these steps **in order**. Each script assumes the previous step completed successfully.

### 1. Capture Course Metadata (Manual)

Create a file called `Notes.md` with one entry per course. All three formats are accepted — mix and match as needed:

```
# Minimal — URL first (or SIS first, either order works):
https://erau.instructure.com/courses/201288/
2963_S3_ECON_211_2382668A_W411

# Human-readable — description line is ignored, URL and SIS are extracted:
1) ECON 211 - Jack Patel
https://erau.instructure.com/courses/201288/
2963_S3_ECON_211_2382668A_W411
```

Separate each course with a blank line.

- **SIS ID** — from Canvas → Course Settings → SIS ID field
- **Canvas ID** — the numeric segment at the end of the course URL (`/courses/201288/`)

**Where to save the file** (checked in this order):

1. `data-handling-scripts/Notes.md` — top-level, gitignored
2. `data-handling-scripts/Enrollment/Notes.md` — alongside roster CSVs, also gitignored
3. `data-handling-scripts/Notes-src.md` — committed fallback/template (used automatically if neither above exists)

`Notes-src.md` in this directory is a committed example you can copy and edit.

---

### 2. Export Canvas Enrollment Rosters

For each course:

1. Open the course in Canvas and click **People** in the left sidebar.
2. Click the **Canvas Roster Export** bookmarklet. The file downloads automatically as `<courseId>.csv` (e.g. `196025.csv`) — no renaming needed.
3. Place the file in the `Enrollment/` directory.

See [README.md — Canvas Roster Bookmarklet](../README.md#canvas-roster-bookmarklet) for one-time bookmarklet setup instructions.

---

### 3. Build Initial Courses CSV

```bash
python3 1-build_courses_csv.py
```

- Reads from `Notes.md`
- Produces `courses.csv`
- Establishes the base course list

---

### 4. Enrich Courses with Instructor & Enrollment Data

```bash
python3 2-enrich_courses_csv.py \
  --infile courses.csv \
  --enroll-dir Enrollment \
  --outfile courses_enriched.csv
```

Adds:

- Instructor name
- Instructor ID
- Student count

This step resolves all foreign-key dependencies needed later.

---

### 5. Generate Course SQL Inserts

```bash
python3 3-build_courses_inserts.py \
  --csv courses_enriched.csv \
  --outfile courses_inserts.sql
```

You will be prompted for the **term**.

Example:

```
2026-01
```

Output: `courses_inserts.sql`

---

### 6. Generate Enrollment SQL Inserts

```bash
python3 5-build_enrollment_inserts.py \
  --root . \
  --outfile enrollment_inserts.sql
```

This script scans the enrollment CSVs and generates per-student enrollment rows.

Output: `enrollment_inserts.sql`

---

### 7. Export Qualtrics Survey Data

From Qualtrics:

- Export **survey responses with labels** (CSV)
- Open the CSV and **remove past survey responses**
  - Only the current survey run should remain

Save the cleaned file as:

```
survey.csv
```

---

### 8. Generate Survey Response Inserts

```bash
python3 build_survey_responses_inserts.py \
  --csv survey.csv \
  --outfile survey_responses_inserts.sql \
  --survey-id ERAU_ASIA
```

This creates one row per respondent per survey.

**`--survey-id`** is a program-level identifier written into every `Survey_Responses` row. It lets the database hold data from multiple active survey campaigns without mixing them up. The default is `ERAU_ASIA`. Change it to a new identifier (e.g. `ERAU_WW`) whenever you are importing responses for a different survey campaign. Pick a value that is unique per campaign and consistent across all imports for that campaign.

---

### 9. Generate Survey Answer Inserts

```bash
python3 build_survey_answers_inserts.py \
  --csv survey.csv \
  --outfile survey_answers_inserts.sql
```

This explodes each response into normalized question/answer rows.

---

## Loading Data into MySQL

### First-time database setup

Before importing any data into a fresh database, run `schema-setup.sql` once:

```bash
# Via mysql CLI inside Docker:
docker exec -i metabase-mysql-1 mysql -u root -p"$MYSQL_ROOT_PASSWORD" Micro-Surveys < schema-setup.sql
```

Or import it via phpMyAdmin. This creates the `UNIQUE INDEX` on `People(EMPL_ID)` that makes re-imports idempotent. It is safe to re-run — it uses `IF NOT EXISTS`.

### Routine imports

Import the SQL files **in dependency order**:

1. `sql/courses_inserts.sql`
2. `sql/people_inserts.sql`
3. `sql/enrollment_inserts.sql`
4. `sql/survey_responses_inserts.sql`
5. `sql/survey_answers_inserts.sql`

You can use phpMyAdmin, the `mysql` CLI, or any SQL client. Review SQL before executing.

---

## Drag-and-Drop Enrollment Import (Recommended Shortcut)

`upload_app.py` replaces scripts 1–5 with a browser UI. It populates all four tables in one step:

**Terms → Courses → People → Enrollment**

### Prerequisites

- Docker stack running (`cd Metabase && docker-compose up -d`)
- `Notes.md` in place (see Step 1 above)
- Roster CSVs exported from Canvas and named with the Canvas course ID (e.g. `201288.csv`)

### Launch

```bash
cd data-handling-scripts
python3 start.py
```

`start.py` starts the full Docker stack, waits for MySQL, then opens the Dashboard at `http://localhost:5010` automatically. From there, click **Enrollment Import** to reach the upload tool. No `pip install` required — all tools use Python 3.10+ stdlib only and write to MySQL via `docker exec`.

To run the enrollment tool on its own without the full stack:

```bash
python3 upload_app.py
# open http://localhost:5001
```

### Workflow

1. The status bar at the top confirms MySQL is reachable and shows how many courses were indexed from `Notes.md`.
2. Drag all roster CSVs onto the drop zone (drop multiple files at once).
3. Each file gets a color-coded badge:
   - **Green ✔** — Canvas ID matched in Notes.md; all 4 tables will be populated.
   - **Yellow ⚠** — Not in Notes.md; only People will be inserted, Enrollment skipped.
   - **Red ✖** — No Canvas ID found in filename; file will be skipped entirely.
4. Enter a **Term label** in the text field (e.g. `Spring 2026` or `2026-01`). This is written to the Terms table alongside the term code from the SIS ID.
5. Review the preview table, then click **Import to MySQL**.

On success, the result panel shows row counts for all four tables. **Re-importing is safe** — enrollment rows for each course are deleted and re-inserted, so running the same files twice produces no duplicates.

### Credentials

The app reads `DB_PASSWORD` and `DB_NAME` from `../Metabase/.env`. The root MySQL user is used for writes (the `metabase` user is read-only).

### What this does NOT handle

- Survey response data (use `build_survey_responses_inserts.py` and `build_survey_answers_inserts.py`)
- The `Course` column in the Courses table (this is a Canvas page path captured at survey time via the Qualtrics popup; it cannot be derived from a roster)

---

## Metabase

Once loaded:

- Metabase automatically detects new rows
- Dashboards and models should refresh without schema changes
- All joins are stable because IDs are deterministic

---

## Design Philosophy

- Python prepares data; SQL writes data
- No silent transformations
- Every step is inspectable
- If something looks wrong, stop and fix upstream

This pipeline favors traceability over speed.

---

## Common Failure Modes

- Wrong Canvas course ID in roster filename
- Old Qualtrics responses not removed
- Term value inconsistent across runs
- Enrollment CSV missing or mismatched

When in doubt: regenerate from the last clean CSV.

---

## License / Usage

Internal tooling. No guarantees. No magic.

