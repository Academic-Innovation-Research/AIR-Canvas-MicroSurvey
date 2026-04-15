# Survey Data → MySQL → Metabase Pipeline

This repository contains Python scripts that transform Canvas and Qualtrics exports into clean, deterministic SQL `INSERT` statements for loading survey data into a MySQL database. That database is connected to Metabase for BI visualization and analysis.

The design goal is boring reliability: explicit inputs, repeatable steps, no hidden state, and SQL you can inspect before importing.

---

## What This Pipeline Does

At a high level:

1. Extract **course, instructor, and enrollment metadata** from Canvas.
2. Normalize and enrich that data into structured CSVs.
3. Generate **SQL insert statements** for:
   - Courses
   - Enrollments
   - Survey responses
   - Survey answers
4. Load the SQL into MySQL.
5. Analyze everything in Metabase.

No direct database writes occur in Python. Python only produces SQL.

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

Create a file called `Notes.md` with the following information for each course:

- **SIS ID** (from Canvas → Course Settings)
  - Example: `2943_S3_MMIS_320_1798701A_W411`
- **Course URL**
  - Example: `https://erau.instructure.com/courses/196025`

This file is the authoritative input for course identity.

---

### 2. Export Canvas Enrollment Rosters

For each course:

1. Open the course in Canvas
2. Select **People** from the course menu
3. Use the **Download Gradebook** bookmarklet to export the roster
4. Rename the file using the **Canvas course ID** (last numeric segment of the URL)
   - Example: `196025.csv`
5. Place the file in the `Enrollment/` directory

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
  --outfile survey_responses_inserts.sql
```

This creates one row per respondent per survey.

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

Import the SQL files **in dependency order**:

1. `courses_inserts.sql`
2. `enrollment_inserts.sql`
3. `survey_responses_inserts.sql`
4. `survey_answers_inserts.sql`

You can use `mysql`, a GUI client, or a migration tool. Review SQL before execution.

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

