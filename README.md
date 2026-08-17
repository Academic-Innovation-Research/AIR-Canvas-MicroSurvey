# AIR Canvas MicroSurvey

An institutional analytics toolset for Canvas LMS. It delivers in-course survey prompts via a JavaScript popup, then pipelines the resulting Qualtrics data—along with Canvas enrollment rosters—into a MySQL database connected to Metabase for reporting.

Built for ERAU Worldwide. Operates across 1–30 courses per survey run.

---

## Quick Start

Three prerequisites, then everything else is automated:

1. **Docker installed** — `start.py` will launch Docker Desktop itself if it isn't running.
2. **`Metabase/.env` present** — gitignored, so it is never in a fresh clone. Copy it from a machine that has it, or `cd Metabase && cp env.sample .env` and set the credentials. `start.py` checks for it first and stops with instructions if it is missing.
3. **Database loaded from a production extract** — the repository contains **no `CREATE TABLE` statements**. A fresh clone against a fresh Docker volume gives you an empty database, and the import tools will fail on the first `INSERT`. See [Production Data and Backups](#production-data-and-backups). This is a one-time step per machine.

Dashboards are a separate step again: they live in Metabase's own application database, so a new machine shows the Metabase setup wizard until you copy that across too. See [Replicating Production Metabase](#replicating-production-metabase).

```bash
cd data-handling-scripts
python3 start.py
```

On the very first run this pulls three Docker images (MySQL, phpMyAdmin, Metabase) and can take several minutes; pull progress prints as it goes. Subsequent runs start in seconds.

`start.py` checks Docker, brings up the full stack (`docker compose up -d`), waits for MySQL to be ready, then opens the Dashboard in your browser automatically. No `pip install` required.

**That command is the only one you need to remember.** Everything after it happens in the browser, from the Dashboard.

| Tool | URL | Purpose |
|---|---|---|
| **Dashboard** | http://localhost:5010 | Landing page — links to all tools with live status |
| Canvas Enrollment Import | http://localhost:5001 | Drag-and-drop roster CSVs → MySQL |
| Qualtrics Survey Import | http://localhost:5002 | Drag-and-drop Qualtrics exports → MySQL |
| SQL Export | http://localhost:5003 | Select terms → download SQL delta for another system |
| phpMyAdmin | http://localhost:8081 | Browse and query the database directly |
| Metabase | http://localhost:3000 | Dashboards and analytics |

---

## Running a New Micro-Survey

The full per-term procedure. Steps 3–6 are browser-only; **step 1 is the single manual file edit in the whole process**, and it is the step most likely to be forgotten between terms.

### 1. Update `Notes.md` — the only non-browser step

`data-handling-scripts/Notes.md` maps each Canvas course ID to its SIS ID and term code. It is gitignored, so it does **not** exist in a fresh clone, and it still contains the *previous* term's courses if you last used it a term ago. Edit it before anything else. Format is in [Notes.md Format](#notesmd-format).

> **⚠ The stale-fallback trap.** If `Notes.md` is missing, the tools silently fall back to the committed `Notes-src.md` (see `pipeline.py:27` `find_notes`). The Enrollment Import page will still show a green status line reading *"Notes.md found — 14 course(s) indexed"* — but those are the **example courses from term 2943**, not yours. A green indicator is not confirmation that your courses are loaded. Always check that the course names on the file badges are the ones you expect.

### 2. Deploy or confirm the Canvas popup

`microsurvey.js` is pasted into **Canvas Admin → Themes → JavaScript**. Confirm `surveyURL` points at the new Qualtrics survey and `popCrs = 1` so the Canvas ID rides along in the response. See [Canvas Popup Configuration](#canvas-popup-configuration).

### 3. Start the stack

```bash
cd data-handling-scripts && python3 start.py
```

The Dashboard opens by itself at localhost:5010. Every remaining step is a link from that page.

### 4. Export the rosters from Canvas

Per course: **People** tab → let the roster finish loading → click the **Canvas Roster Export** bookmarklet. Saves as `<CanvasID>.csv`. Do not rename — the filename is how the importer identifies the course.

### 5. Import enrollment → **Enrollment Import** (localhost:5001)

Drop all roster CSVs at once, enter the Term label, review the badges, click **Import to MySQL**. Populates Terms → Courses → People → Enrollment. Details and badge meanings: [Canvas Enrollment Import](#canvas-enrollment-import--localhost5001).

### 6. Import responses → **Survey Import** (localhost:5002)

Once Qualtrics has responses, export the CSV (either format) and drop it in. Populates Survey_Responses → Survey_Answers.

Steps 5 and 6 are independent and both re-runnable — you can import enrollment early and pull survey responses repeatedly as they accumulate.

### 7. (Optional) Push to another database → **SQL Export** (localhost:5003)

Check the terms, download the SQL delta, import it into the production instance.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Canvas LMS (ERAU Worldwide)                                        │
│                                                                     │
│  microsurvey.js injected via Canvas Theme JS                        │
│  → shows popup/button on course pages                               │
│  → links to Qualtrics survey                                        │
│  → appends ?Course=/courses/<CanvasID> to the URL                  │
│                                                                     │
│  Canvas People page + bookmarklet                                   │
│  → exports roster as <CanvasID>.csv                                 │
└──────────────────┬─────────────────────────┬───────────────────────┘
                   │                         │
          Qualtrics export              Canvas roster CSVs
          (CSV, any format)             (one per course)
                   │                         │
                   ▼                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Local Machine — Data Pipeline                                      │
│                                                                     │
│  python3 start.py                                                   │
│  ├── :5010  dashboard.py         (Dashboard)                        │
│  ├── :5001  upload_app.py        (Enrollment Import)                │
│  ├── :5002  survey_upload_app.py (Survey Import)                    │
│  └── :5003  export_app.py        (SQL Export)                       │
│                                                                     │
│  Both communicate with MySQL via: docker exec mysql-container mysql │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Docker Stack (Metabase/)                                           │
│  ├── mysql-container    :3306  MySQL 8.1                            │
│  ├── phpmyadmin-container :8081  phpMyAdmin 5.2                     │
│  └── metabase-container :3000  Metabase v0.52                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Survey response:
  Student opens Canvas course
    → microsurvey.js fires after popDelay ms
    → popup appears with Qualtrics link
    → URL includes ?Course=/courses/201288
    → student submits Qualtrics form
    → Qualtrics records Response_ID + Course path

Instructor exports Qualtrics CSV (either format)
  → drops onto Survey Import (localhost:5002)
  → tool detects format, strips 3-row Qualtrics header
  → queries DB for existing Response_IDs (no duplicates)
  → inserts new Survey_Responses + Survey_Answers rows

Admin exports Canvas People page per course
  → runs Canvas Roster Export bookmarklet
  → file saves as <CanvasID>.csv automatically
  → drops onto Enrollment Import (localhost:5001)
  → tool reads Notes.md for SIS IDs and term codes
  → inserts Terms → Courses → People → Enrollment rows

Metabase connects to MySQL
  → dashboards show satisfaction scores, enrollment, completion
```

---

## Components

| Component | File(s) | Purpose |
|---|---|---|
| Canvas popup | `microsurvey.js` + `microsurvey.css` | Injects survey prompt into Canvas courses |
| Faculty variant | `microsurvey-RCTLE.js` | Popup variant: mailto link, 4-minute delay |
| WW theme | `canvas-ww/canvas-ww.js` + `.css` | Canvas Worldwide theme: library, bookstore, advisor links |
| Roster bookmarklet | `bookmarklet/canvas-roster.js` | Exports Canvas People page as a named CSV |
| Enrollment import | `data-handling-scripts/upload_app.py` | Drag-and-drop web app, port 5001 |
| Survey import | `data-handling-scripts/survey_upload_app.py` | Drag-and-drop web app, port 5002 |
| SQL export | `data-handling-scripts/export_app.py` | Term-scoped SQL delta export, port 5003 |
| Dashboard | `data-handling-scripts/dashboard.py` | Landing page with live status indicators, port 5010 |
| Launcher | `data-handling-scripts/start.py` | Starts Docker stack + all four tools; opens dashboard |
| Course metadata | `data-handling-scripts/Notes.md` | Hand-maintained per term — maps Canvas IDs to SIS IDs and term codes |
| Shared parsing | `data-handling-scripts/pipeline.py` | `find_notes()` / `parse_notes_md()`, used by the import tools |
| Docker stack | `Metabase/docker-compose.yml` | MySQL 8 + phpMyAdmin + Metabase |

---

## Database Schema

The `Micro-Surveys` database has two logical groups of tables. All tables use `utf8mb4` with InnoDB.

### Enrollment Group

```
Terms ──< Courses ──< Enrollment >── People
```

#### Terms
Populated from the SIS ID prefix during enrollment import.

| Column | Type | Notes |
|---|---|---|
| `TermCode` | `varchar(20)` | PK. Numeric prefix of the SIS ID, e.g. `2963` |
| `Term` | `varchar(20)` | Human label entered at import time, e.g. `Spring 2026` |
| `StartDate` | `date` | Optional |
| `EndDate` | `date` | Optional |

#### Courses
One row per Canvas course. Created from `Notes.md` metadata.

| Column | Type | Notes |
|---|---|---|
| `CanvasID` | `int` | PK. Numeric segment of the course URL |
| `CourseName` | `varchar(50)` | e.g. `ECON 211` |
| `Instructor` | `varchar(100)` | First teacher found in roster |
| `URL` | `varchar(255)` | Full Canvas course URL |
| `Course` | `varchar(255)` | Canvas path appended to survey URLs |
| `TermCode` | `varchar(20)` | FK → Terms |
| `CourseSISID` | `varchar(100)` | Full SIS ID, e.g. `2963_S3_ECON_211_2382668A_W411` |
| `CntStudents` | `int` | Student count from roster |

#### People
One row per person across all courses. PK is the employee ID.

| Column | Type | Notes |
|---|---|---|
| `EMPL_ID` | `varchar(50)` | PK + UNIQUE. Canvas SIS/employee ID |
| `Name` | `varchar(100)` | Full name |
| `Login_ID` | `varchar(50)` | UNIQUE. Campus login |
| `Role` | `varchar(50)` | **Two spellings exist in the data** — see [Role values](#role-values-two-spellings). Canvas emits either `Student`/`Teacher` or `StudentEnrollment`/`TeacherEnrollment` depending on the roster export |

#### Enrollment
Junction table linking people to courses. Rebuilt per-course on each import.

| Column | Type | Notes |
|---|---|---|
| `ID` | `int` | PK, auto-increment |
| `CanvasID` | `int` | FK → Courses |
| `Empl_ID` | `varchar(50)` | FK → People |
| `Role` | `varchar(255)` | Role in this specific course. **Two spellings exist** — never filter with `= 'Student'` alone, see [Role values](#role-values-two-spellings) |

### Survey Group

```
Question_Types ──< Survey_Questions >── Surveys
                         │
                    Survey_Answers >── Survey_Responses
```

#### Surveys
One row per survey campaign. A single Qualtrics survey can span many courses and many terms.

| Column | Type | Notes |
|---|---|---|
| `Survey_ID` | `varchar(50)` | PK. Short human key, e.g. `ERAU_ASIA` |
| `Title` | `varchar(255)` | Display name |
| `Description` | `text` | Optional |
| `Created_At` | `datetime` | Auto-set on insert |
| `Status` | `varchar(20)` | e.g. `Active` |
| `CanvasID` | `int` | Optional link to a specific course |

#### Question_Types
Reference table for question formats.

| Column | Type | Notes |
|---|---|---|
| `Type_ID` | `varchar(50)` | PK. e.g. `satisfaction_scale` |
| `Type_Name` | `varchar(50)` | Display name |
| `Description` | `text` | Optional |

Current types: `satisfaction_scale`, `satisfaction_scale_with_comment`.

#### Survey_Questions
Questions belonging to a survey. Auto-populated when creating a new survey in the import tool.

| Column | Type | Notes |
|---|---|---|
| `Question_ID` | `int` | PK, auto-increment |
| `Survey_ID` | `varchar(50)` | FK → Surveys |
| `Question_Number` | `varchar(10)` | Matches the CSV column name suffix, e.g. `1` for `Q1` |
| `Question_Text` | `text` | Full question text from Qualtrics label row |
| `Question_Type` | `varchar(50)` | FK → Question_Types (nullable) |
| `Question_Order` | `int` | Display order |
| `Created_At` | `datetime` | Auto-set |
| `Updated_At` | `datetime` | Auto-updated |

#### Survey_Responses
One row per Qualtrics response. `Response_ID` is the Qualtrics-assigned identifier and the deduplication key.

| Column | Type | Notes |
|---|---|---|
| `Response_ID` | `varchar(50)` | PK. Qualtrics `ResponseId`, e.g. `R_4aD760otgX6Jp4t` |
| `Survey_ID` | `varchar(50)` | FK → Surveys |
| `StartDate` | `datetime` | When the respondent opened the survey |
| `EndDate` | `datetime` | When they submitted |
| `Status` | `varchar(50)` | Qualtrics status code or label |
| `IPAddress` | `varchar(50)` | Anonymized as `*******` in exports |
| `Progress` | `int` | 0–100 |
| `Duration` | `int` | Seconds |
| `Finished` | `tinyint(1)` | 1 = completed |
| `RecordedDate` | `datetime` | Server-recorded submission time |
| `LocationLatitude` | `decimal(10,7)` | Often NULL (anonymized) |
| `LocationLongitude` | `decimal(10,7)` | Often NULL (anonymized) |
| `DistributionChannel` | `varchar(50)` | e.g. `anonymous` |
| `UserLanguage` | `varchar(10)` | e.g. `EN` |
| `CanvasID` | `int NOT NULL` | Extracted from the `Course` column URL path |
| `Created_At` | `datetime` | Import timestamp |

#### Survey_Answers
One row per question per response. FK to both `Survey_Responses` and `Survey_Questions`.

| Column | Type | Notes |
|---|---|---|
| `Answer_ID` | `int` | PK, auto-increment |
| `Response_ID` | `varchar(50)` | FK → Survey_Responses |
| `Question_ID` | `int` | FK → Survey_Questions |
| `Selected_Option` | `varchar(255)` | Scale answer: numeric code (`1`) or label (`Extremely satisfied`) |
| `Answer_Text` | `text` | Free-text answer (used for comment/open-ended questions) |

Scale questions populate `Selected_Option`; free-text questions populate `Answer_Text`. The format (numeric vs. label) is preserved as-is from the export — both are stored without normalization.

### Entity-Relationship Summary

```
Terms (1) ──────────────── (N) Courses (1) ──── (N) Enrollment (N) ──── (1) People
                                                                               │
                                                                      EMPL_ID (unique)

Surveys (1) ──────────────────── (N) Survey_Questions (N) ──── (1) Question_Types
   │
   └── (1) ──────────────────── (N) Survey_Responses (1) ──── (N) Survey_Answers
                                          │                              │
                                     Response_ID (PK)           FK → Survey_Questions
```

### Stored Procedures (legacy — do not call)

Production carries two stored procedures, restored along with the schema:

| Procedure | Body |
|---|---|
| `SwapCoursesTables` | `RENAME TABLE Courses ↔ Courses_Bak` (via `Courses_Temp`) |
| `SwapPeopleTables` | `RENAME TABLE People ↔ People_Bak` (via `People_Temp`) |

They implement an atomic blue/green table swap — **but `Courses_Bak` and `People_Bak` do not exist**, in production or anywhere else. Calling either procedure fails with `Table 'Micro-Surveys.Courses_Bak' doesn't exist`.

They are leftovers from a superseded import strategy. Nothing in the current toolchain calls them; idempotency now comes from `ON DUPLICATE KEY UPDATE` against the unique index on `People(EMPL_ID)`. Left in place because they are inert, but do not build on them.

### Index note

`People` carries four separate indexes on `EMPL_ID` — `PRIMARY`, `EMPL_ID`, `uniq_people_empl_id`, and `Index_1`. Three are redundant. Harmless at current scale (a few hundred rows), worth collapsing to one whenever the schema is next rebuilt.

---

## Import Tools

### Dashboard — localhost:5010

The Dashboard is the single entry point opened automatically by `start.py`. It shows live status indicators for all tools and the database connection, and provides direct links to each tool. You do not need to remember any other URLs.

---

### Canvas Enrollment Import — localhost:5001

Handles: **Terms → Courses → People → Enrollment**

**Requirements before using:**
- `Notes.md` in `data-handling-scripts/` or `data-handling-scripts/Enrollment/` (see format below), **updated for the current term**
- Canvas roster CSVs exported via the bookmarklet, named `<CanvasID>.csv`

The page shows a `Notes.md` status line on load, served by the `/notes-status` route (`upload_app.py:540`). Read it as *"some notes file was found and N courses were indexed"* — it does not distinguish your `Notes.md` from the `Notes-src.md` fallback, so it can report a confident green count for last term's courses. The per-file badges in step 2 are the real check.

**Workflow:**
1. Drop one or more roster CSVs onto the drop zone (multiple files at once is fine)
2. Each file gets a badge showing its match status:
   - **Green ✔** — Canvas ID found in Notes.md; all 4 tables will be populated
   - **Yellow ⚠** — Canvas ID not in Notes.md; People inserted only, Enrollment skipped
   - **Red ✖** — No Canvas ID parseable from filename; file is skipped
   - **Orange ↺** — Course already has enrollment rows; they will be replaced
3. Enter a **Term label** (e.g. `Spring 2026` or `2026-01`)
4. Review the preview table, then click **Import to MySQL**

**Idempotency:** Enrollment rows for each course are `DELETE`d and re-inserted on every import. Re-importing the same files is safe and produces no duplicates. People and Courses use `ON DUPLICATE KEY UPDATE`.

---

### Qualtrics Survey Import — localhost:5002

Handles: **Survey_Responses → Survey_Answers**

**Qualtrics export format:** Both formats are auto-detected from the first data row — no need to remember which one was used.

| Format | Q1 example | Finished example |
|---|---|---|
| Use Values / IDs | `1` | `1` |
| Use Labels | `Extremely satisfied` | `True` |

The three-row Qualtrics header (machine names → human labels → JSON ImportId metadata) is stripped automatically regardless of format.

**Workflow:**
1. Select an existing survey from the dropdown, or choose **➕ Create new survey…**
2. Drop the Qualtrics CSV onto the drop zone
3. The preview shows:
   - Detected format badge (Numeric Values / With Labels)
   - **✚ N new** responses that will be inserted
   - **⟳ M already imported** responses that will be skipped
   - A sample table of the first rows
4. Click **Import to MySQL**

**Creating a new survey:** Selecting "Create new survey…" reveals a form. After dropping a CSV, question text is pre-populated from the Qualtrics label row. Questions Q1–Q3 default to `satisfaction_scale`; Q4 and beyond default to free-text (NULL type). You can edit before saving. Once created, the survey appears in the dropdown and import proceeds normally.

**Idempotency:** `Response_ID` (the Qualtrics-assigned identifier) is the primary key of `Survey_Responses`. Before importing, the tool queries all existing `Response_ID`s for the selected survey and skips any that are already present. Recurring surveys can be exported and re-imported each term without manual filtering.

**Answer mapping:** Only questions with a row in `Survey_Questions` for the selected survey get answers inserted. Questions in the CSV that have no DB entry are silently skipped. This means you can add questions to an existing survey later without breaking past imports.

---

### SQL Export — localhost:5003

Generates a self-contained SQL file you can import into any other MySQL instance (e.g. a production database) to bring it up to date for the selected terms.

**Workflow:**
1. Check the terms you want to export (the page shows course/enrollment/response counts per term)
2. Click **Download SQL**
3. Import the downloaded `.sql` file into the target database via phpMyAdmin or the `mysql` CLI

**What the SQL includes:**
- `INSERT … ON DUPLICATE KEY UPDATE` for Terms, Courses, People, and Enrollment
- `INSERT IGNORE` for Survey_Responses
- Idempotent Survey_Answers inserts that skip any `Response_ID` already present on the target
- Schema guards at the top — if the target database is missing columns added after its initial setup, they are added automatically before any data is inserted

The output is safe to import multiple times. Re-importing the same export produces no duplicates.

---

## Canvas Popup Configuration

`microsurvey.js` is deployed via **Canvas Admin → Themes → JavaScript**. Configure the variables at the top of the file:

```js
var displayType     = 0;        // 0 = modal popup, 1 = sidebar button
var surveyURL       = "https://...qualtrics.com/jfe/form/...";
var popMsg          = "Share Your Thoughts";
var popBtnTxt       = "Yes";
var popDelay        = 1000;     // ms before popup appears (1000 = 1 second)
var popWhere        = 0;        // 0 = course pages, 1 = home page only
var popCrs          = 1;        // 1 = append ?Course=... to survey URL
var btnBgColor      = "#993333";
var sidebarBtnText  = "Share Your Thoughts";
```

When `popCrs = 1`, the popup appends `?Course=/courses/201288` to the survey URL before opening. Qualtrics captures this in the `Course` column. The survey import tool parses this field to extract the `CanvasID` for each response, linking survey data to the correct course in the database.

---

## Canvas Roster Bookmarklet

This bookmarklet exports a Canvas People page to a CSV file automatically named `<CanvasID>.csv`. Drop that file directly onto the Enrollment Import tool.

> **Source vs. paste:** `bookmarklet/canvas-roster.js` is the readable source. Do not paste it into a browser — paste only the minified one-liner below.

### One-time setup

Copy this entire line (it must be a single unbroken line starting with `javascript:`):

```
javascript:(async()=>{const S=ms=>new Promise(r=>setTimeout(r,ms));try{const T=()=>document.querySelector("table.roster")||document.querySelector("table.ic-Table");let last=0,same=0,scroller=document.scrollingElement||document.documentElement;for(let i=0;i<20&&same<3;i++){scroller.scrollTop=scroller.scrollHeight;await S(500);const n=document.querySelectorAll("table.roster tbody tr, table.ic-Table tbody tr").length;if(n===last)same++;else{same=0;last=n}}const table=T();if(!table){alert("Roster table not found. Navigate to the course People page and try again.");return}const rows=[];let headers=[...table.querySelectorAll("thead th, thead td")].map(c=>c.textContent.trim());if(!headers.length){const fr=table.querySelector("tbody tr");if(fr)headers=[...fr.children].map(c=>c.textContent.trim())}if(headers.length)rows.push(headers);[...table.querySelectorAll("tbody tr")].forEach(tr=>{rows.push([...tr.children].map(td=>td.innerText.trim()))});const esc=v=>{v=(v??"").replace(/ /g," ").replace(/\s+/g," ").trim().replace(/"/g,'""');return`"${v}"`};const csv=rows.map(r=>r.map(esc).join(",")).join("\n");const cid=(location.pathname.match(/\/courses\/(\d+)/)||[])[1];const fn=cid?`${cid}.csv`:`canvas-roster-${new Date().toISOString().slice(0,10)}.csv`;const blob=new Blob([csv],{type:"text/csv;charset=utf-8;"}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=fn;document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(url);a.remove()},1500)}catch(e){console.error(e);alert("Error exporting roster. See console for details.")}})();
```

**Chrome / Edge:** Right-click bookmarks bar → Add page → paste into the URL field.
**Safari:** Add any bookmark → Edit Bookmarks → double-click its URL column → paste.
**Firefox:** Bookmarks → Manage Bookmarks → New Bookmark → paste into Location.

### Usage

1. Open a Canvas course → **People** in the sidebar.
2. Wait for the roster to finish loading.
3. Click **Canvas Roster Export** in your bookmarks bar.
4. The file saves as `201288.csv` (or whatever the Canvas course ID is).

| Symptom | Fix |
|---|---|
| "Roster table not found" | Must be on the People tab, not another course page |
| Date-named file instead of course ID | URL didn't contain `/courses/<id>/` |
| Fewer rows than expected | Wait for full page load and click again |

---

## Notes.md Format

`Notes.md` tells the enrollment import tool how to fill the `Courses` and `Terms` tables. The file is gitignored — copy `Notes-src.md` as a starting point.

This is the one file you maintain by hand each term. There is no editor for it in the Dashboard or the Enrollment Import page; both only read it.

**Where to save it** (checked in this order — `find_notes` in `pipeline.py:27`):
1. `data-handling-scripts/Notes.md`
2. `data-handling-scripts/Enrollment/Notes.md`
3. `data-handling-scripts/Notes-src.md` (committed fallback — **contains stale example data from term 2943**)

Because of entry 3, a missing `Notes.md` never produces an error. It produces a successful-looking import of the wrong courses. Create `Notes.md` explicitly rather than relying on the fallback.

**Format** — separate entries with a blank line; URL and SIS ID can appear in either order; a human-readable description line is ignored:

```
https://erau.instructure.com/courses/201288/
2963_S3_ECON_211_2382668A_W411

2963_S3_RSCH_202_2382668A_W411
https://erau.instructure.com/courses/201520/

1) ECON 211 - Jack Patel
https://erau.instructure.com/courses/201288/
2963_S3_ECON_211_2382668A_W411
```

**SIS ID anatomy:** `2963_S3_ECON_211_2382668A_W411`
- `2963` → TermCode (written to the Terms table)
- `S3` → session
- `ECON_211` → course name
- `2382668A_W411` → section identifiers

---

## Docker Stack

The stack lives in `Metabase/`. Configuration is read from `Metabase/.env`.

```bash
cd Metabase
cp env.sample .env   # edit credentials once
docker compose up -d
```

### Environment variables (`Metabase/.env`)

Full list is in `env.sample`. The ones that matter:

| Variable | `env.sample` default | Purpose |
|---|---|---|
| `DB_NAME` | `Micro-Surveys` | Database name |
| `DB_USER` | `metabase` | Non-root user (Metabase read access) |
| `DB_USER_PASSWORD` | `metabase` | Password for `DB_USER` |
| `DB_PASSWORD` | `password` | MySQL **root** password — used by the import tools for writes and by the MySQL healthcheck |
| `MB_JAVA_TIMEZONE` | `America/New_York` | Metabase JVM timezone |
| `MB_PORT` / `DB_PORT` | `3000` / `3306` | Host ports for Metabase and MySQL |
| `MB_APP_DB_NAME` | `metabase_app` | Metabase **application** database (PostgreSQL) |
| `MB_APP_DB_USER` | `metabase` | Owner of the application database |
| `MB_APP_DB_PASSWORD` | `metabase` | Password for that account |

The import tools read `.env` automatically from `../Metabase/.env` relative to the scripts directory. No environment setup is needed beyond creating the file.

> **The file is required, not optional.** `docker-compose.yml` substitutes these variables directly. Without `.env`, Compose fills every one with an empty string, MySQL refuses to initialise on a blank root password, and the container ends up unhealthy — a failure that surfaces well after the step that caused it. `start.py` now checks for the file before touching Docker.
>
> Change `DB_PASSWORD` after `db-data` already exists and MySQL will reject the new password: the root credential lives in the volume, set at first initialisation. `MYSQL_ROOT_PASSWORD` is read *only* when the data directory is empty. You do not need to destroy the volume to fix this — `ALTER USER` resets the stored credential in place, per account and per source host (see [MySQL accounts are per source host](#mysql-accounts-are-per-source-host)). `docker compose down -v` (**destroys all data**) is a last resort, not the remedy.

### Services

| Container | Port | Image | Holds |
|---|---|---|---|
| `mysql-container` | 3306 | `mysql:8.1` (arm64) | Analytics data — `Micro-Surveys`, `SPOTS` |
| `phpmyadmin-container` | 8081 | `phpmyadmin:5.2.1` | — |
| `metabase-container` | 3000 | `metabase/metabase:v0.55.12` | — |
| `metabase-postgres` | — | `postgres:16` | Metabase **application** DB — dashboards, users |

The two databases are easy to confuse and are completely separate. `mysql-container` holds the data Metabase *queries*. `metabase-postgres` holds Metabase itself — dashboards, questions, collections, users, permissions. Losing the first costs you a re-import; losing the second costs you every dashboard ever built.

`metabase-postgres` publishes no host port. Metabase reaches it over the Compose network, and nothing else needs it.

### Production differs from this compose file

The production server (`dbdkr.erau.edu`, reachable on VPN) diverges from `docker-compose.yml` in three ways, none of which the compose file reflects:

| Container | Port | Image | Difference |
|---|---|---|---|
| `adminer-container` | 8080 | `adminer:4.8.1` | Replaced phpMyAdmin in production — phpMyAdmin was leaking memory. Local dev still gets phpMyAdmin on 8081. |
| `metabase-container` | 3000 | `metabase/metabase:latest` | Unpinned upstream, so a restart can change Metabase versions. The repo pins `v0.55.12`. |
| *(none)* | — | — | Production's Metabase application DB is still the **H2 file**; this repo runs it on the `metabase-postgres` service. See [Replicating Production Metabase](#replicating-production-metabase). |

Deploying straight from this repo therefore gives you phpMyAdmin on **8081**, not Adminer on **8080**. Anywhere this README says phpMyAdmin/8081, read Adminer/8080 if you are on the production box. The database URLs and credentials are identical either way — only the browser client differs.

### MySQL accounts are per source host

`root@'%'`, `root@'localhost'`, and `root@'<literal-ip>'` are **separate accounts with separate passwords**, and MySQL authenticates against the most specific host match. Two consequences worth internalising before debugging any login failure:

- **A healthy container proves nothing about network logins.** The healthcheck (`mysqladmin ping -h localhost`) and `docker exec … mysql -uroot` both go over the local socket and match `root@'localhost'`. Adminer, Metabase, and the import tools connect over TCP from another container and match `root@'%'`. The first pair can succeed while every one of the second fails.
- **Never grant to a literal container IP.** Docker assigns bridge subnets when it creates the network, so `docker compose down && up` can move every container to a new subnet and silently invalidate an IP-pinned grant.

To test the credential that Adminer and the import tools actually use, force a TCP connection so it matches `root@'%'`:

```bash
P=$(docker exec mysql-container printenv MYSQL_ROOT_PASSWORD)
docker exec mysql-container mysql -h mysql-container -uroot -p"$P" -e "select current_user()"
docker exec mysql-container mysql -uroot -p"$P" -e "select user,host,plugin from mysql.user"
```

#### Incident: Adminer "Access denied" after a restart (2026-08-17)

Adminer rejected the root login with `Access denied for user 'root'@'192.168.224.3' (using password: YES)` while `docker ps` reported `mysql-container` healthy and Metabase kept serving.

**Cause.** An earlier fix had granted root from Adminer's container IP at the time, creating a `root@'192.168.32.3'` account. The restart recreated the bridge network on `192.168.224.0/20`, so that grant no longer matched, and logins fell through to `root@'%'` — an account created by hand whose password was never the `DB_PASSWORD` in `.env`. The healthcheck kept passing throughout because it authenticates as `root@'localhost'`, a third account, still on the image's original `caching_sha2_password`.

**Fix applied.** Realigned `root@'%'` with `.env` and removed the IP-pinned account so a future subnet change cannot reintroduce this:

```bash
P=$(docker exec mysql-container printenv MYSQL_ROOT_PASSWORD)
docker exec mysql-container mysql -uroot -p"$P" -e \
  "ALTER USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY '$P'; \
   DROP USER 'root'@'192.168.32.3'; FLUSH PRIVILEGES;"
```

`root@'%'` now matches any source IP and is the single source of truth, synchronised with `Metabase/.env`. If anything on the box still authenticates as root over TCP with a hardcoded password rather than reading `.env`, it needs updating to the `.env` value — the dropped account's password is gone.

**Follow-on: Metabase kept the old password.** Metabase stores the MySQL credential in its own application database, not in `.env`, so it went on presenting the stale password after the `ALTER USER` and its cards began failing with *"There was a problem displaying this chart."* Fixed by re-entering the connection under **Admin settings → Databases → Micro-Surveys** and saving.

The failure was misleading in two ways worth remembering. It looked like an import problem because it surfaced right after a term import, and it looked *partial* — a few cards still rendered — because those were serving cached results rather than hitting MySQL. **Any time root's password changes, re-save the Metabase connection**, and read a half-broken dashboard as a credentials symptom rather than a data one.

> **Known exposure, not yet addressed.** Production publishes MySQL as `0.0.0.0:3306->3306`, and `root@'%'` accepts from any source. Only the host firewall keeps 3306 closed off-box (8080, 3000, and 22 answer over VPN; 3306 does not). Binding `127.0.0.1:3306:3306` would close it properly — nothing outside the Docker network needs 3306.

### Recovering from a hard reboot

If the system is force-restarted while containers are running, MySQL may be left in a state where Docker reports the container as unhealthy. The fix is to stop and remove all containers cleanly, then restart:

```bash
cd Metabase
docker compose down
docker compose up -d
```

---

## Superseded: the numbered CLI scripts

The numbered scripts (`1-build_courses_csv.py` … `5-build_enrollment_inserts.py`, `run_all_course_scripts.py`) and the two `build_survey_*_inserts.py` scripts predate the browser tools. They generated `.sql` files you then imported by hand through phpMyAdmin.

**They are no longer part of the process and their instructions have been removed from this README.** The Enrollment Import and Survey Import tools do the same work, write directly to MySQL, and show a preview first. The scripts are still in the repository because `pipeline.py` — which the web tools *do* use — shares parsing helpers with them.

Do not follow older instructions that tell you to create an `Enrollment/` directory, run the numbered scripts in sequence, or import files from `sql/`. Neither directory exists in a fresh clone, both are gitignored, and nothing in the current process creates or reads them.

---

## Programming Style and Philosophy

### No external dependencies

Every Python script runs on the standard library only. No `pip install`, no virtual environments, no version conflicts. The tools run wherever Python 3.10+ and Docker are present. `requirements.txt` exists but documents this explicitly — it lists no packages.

### Nothing is written without a preview

Both import tools parse the dropped files, show what they found, and wait. The Enrollment Import shows a per-file badge and a preview table; the Survey Import shows the detected format and counts of new vs. already-imported responses. Nothing reaches MySQL until you click Import.

This replaces the older design, where the numbered scripts wrote `.sql` files for you to read before executing them by hand. The preview is faster and harder to skip.

### Writes go through `docker exec`

Neither web app connects to MySQL over TCP or uses a database driver. SQL is piped into MySQL via:

```python
subprocess.run(["docker", "exec", "-i", "mysql-container",
                "mysql", "-uroot", f"-p{password}", db_name], input=sql)
```

This avoids shipping any MySQL client library and means the tools work as long as Docker is running and the container name matches the `.env` file — no host/port/DSN configuration needed.

### Idempotency everywhere

Every import is designed to be safe to run more than once:

- **Terms, Courses, People:** `ON DUPLICATE KEY UPDATE` — re-importing updates existing rows rather than failing or duplicating.
- **Enrollment:** `DELETE FROM ... WHERE CanvasID = ?` followed by a fresh `INSERT` — the row count is always exactly what the roster says.
- **Survey_Responses:** `Response_ID` is the primary key; `ON DUPLICATE KEY UPDATE Response_ID = Response_ID` is a deliberate no-op that lets MySQL silently skip already-imported responses.
- **Survey_Answers:** Only inserted for `Response_ID`s that were newly inserted in the same import run.

The practical effect: you can re-run any import without checking whether it has been run before.

### Format detection, not format selection

The survey import tool does not ask which Qualtrics export format was used. It detects the format from the data itself: if the first response's Q1 value is a pure integer it is numeric/values format; if it is text it is the labels format. Users should not have to track which export option they chose.

Similarly, the enrollment import tool does not require roster files to be named in a particular way — it scans each filename with a regex for any 4-or-more-digit sequence and treats that as the Canvas ID.

### Filenames carry the data

The Canvas roster bookmarklet names the export file `<CanvasID>.csv`. The enrollment import reads the Canvas ID from the filename. This design means there is never a manual "what course does this file belong to?" mapping step. The file name is the primary key.

### One tool per concern

Each web app owns one stage of the pipeline and one port: enrollment (5001), survey responses (5002), export (5003). A failure is isolated to one tool, and `start.py` can restart everything without any of them needing to know about the others.

### Comments are for surprises

Code comments in this project explain constraints or workarounds that would not be obvious to someone reading the code fresh — a Qualtrics CSV quirk, a MySQL NULL handling edge case, a Docker exec pattern. They do not narrate what the code visibly does.

---

## Repository Structure

```
AIR-Canvas-MicroSurvey/
│
├── README.md                            ← you are here
│
├── microsurvey.js                       Canvas popup script (main, active deployment)
├── microsurvey.css                      Popup styles
├── microsurvey-RCTLE.js                 Popup variant: faculty assistance, mailto, 4 min delay
│
├── canvas-ww/
│   ├── canvas-ww.js                     Canvas Worldwide theme JS customizations
│   └── canvas-ww.css                    Canvas WW theme CSS + CIDI Design Tools integration
│
├── bookmarklet/
│   └── canvas-roster.js                 Roster export bookmarklet — readable source (do not paste directly)
│
├── data-handling-scripts/
│   │
│   ├── start.py                         ★ Run this first — Docker + MySQL + all four tools + opens dashboard
│   ├── dashboard.py                     Landing page with live status indicators (port 5010)
│   ├── upload_app.py                    Canvas Enrollment Import web app (port 5001)
│   ├── survey_upload_app.py             Qualtrics Survey Import web app (port 5002)
│   ├── export_app.py                    Term-scoped SQL delta export (port 5003)
│   ├── pipeline.py                      Shared parsing logic — find_notes(), parse_notes_md()
│   │
│   ├── Notes.md                         ★ (gitignored) YOU MAINTAIN THIS — course metadata for the current term
│   ├── Notes-src.md                     Committed example, term 2943 — a template, not current data
│   │
│   ├── schema-setup.sql                 One-time DB setup (unique index on People.EMPL_ID)
│   ├── requirements.txt                 No packages listed — stdlib only
│   │
│   └── (superseded — see "Superseded: the numbered CLI scripts")
│       1-build_courses_csv.py, 2-enrich_courses_csv.py,
│       3-build_courses_inserts.py, 4-build_people_inserts_positional.py,
│       5-build_enrollment_inserts.py, run_all_course_scripts.py,
│       build_survey_responses_inserts.py, build_survey_answers_inserts.py
│
├── Metabase/
│   ├── docker-compose.yml               MySQL 8 + phpMyAdmin + Metabase
│   ├── .env                             ★ (gitignored) credentials — required; stack will not start without it
│   ├── env.sample                       Template for .env
│   └── README.md                        Docker-specific documentation
│
├── ops/                                 Database operations — see "Production Data and Backups"
│   ├── dump-prod-mysql.sh               Pull a dump from production over SSH (read-only on prod)
│   ├── extract-database.sh              Pull ONE database out of a multi-database dump
│   ├── restore-local-mysql.sh           Load a dump into the local container
│   ├── import-metabase-h2.sh            Load a production H2 app DB (see caveat — local now runs Postgres)
│   └── backup-metabase-appdb.sh         pg_dump every dashboard, question, and user — no downtime
│
└── backups/                             ★ (gitignored) dumps land here — real student data, never commit
```

**Not in a fresh clone.** `Metabase/.env`, `data-handling-scripts/Notes.md`, `backups/`, `Enrollment/`, and `sql/` are all gitignored. The first two you must supply, and `backups/` you populate from production. The last two belong to the superseded pipeline and nothing in the current process creates or reads them.

---

## Production Data and Backups

**The repository contains no table definitions.** There is no `CREATE TABLE` anywhere in the tree, and `schema-setup.sql` only adds an index to a `People` table it assumes already exists. A fresh clone against a fresh Docker volume therefore starts with an *empty* database — the stack comes up perfectly and the first import fails with `Table 'Micro-Surveys.Terms' doesn't exist`.

**Production is the schema's source of truth.** Setting up a machine means restoring a production extract, not building a schema by hand. Three steps, scripts in `ops/`.

### 1. Dump production

```bash
PROD_SSH=user@host ./ops/dump-prod-mysql.sh
```

Read-only against production: it runs `mysqldump` *inside* the prod container and streams the gzipped result back over SSH. Nothing is written to the production filesystem and no schema, data, or configuration is modified.

Two details worth knowing:

- **The password never leaves the container.** The script reads `MYSQL_ROOT_PASSWORD` from the container's own environment, so no credential appears in your shell history, in the SSH command, or in either host's process list.
- **`--single-transaction`** takes a consistent InnoDB snapshot without locking production tables, so the dump does not block live traffic.

Override `PROD_CONTAINER` (default `mysql-container`) or `PROD_DB` (default `Micro-Surveys`) if production differs.

The output is verified before it is accepted: gzip integrity plus the presence of the trailing `Dump completed` marker, which proves the dump ran to completion rather than being cut short by a dropped connection. A failed dump deletes its own partial file.

If you obtain a dump another way — Adminer, phpMyAdmin, a colleague — drop it in `backups/` and continue at step 2.

### 2. Extract the single database you need

> **⚠ Full-server dumps contain MySQL's internal `mysql` schema.** That schema holds the account table, including password hashes. Restoring it overwrites your local server's users, grants, and root password — which can lock you out of your own container. Such a dump also carries sibling projects (`SPOTS`) you almost certainly do not want locally.
>
> **Never restore a multi-database dump directly.** Extract first.

```bash
./ops/extract-database.sh backups/db.sql.gz Micro-Surveys
```

This writes `backups/Micro-Surveys-only-<timestamp>.sql.gz` containing that database plus the dump's header preamble, and prints exactly which databases it excluded. Run it with a name that isn't present and it lists what the dump actually holds.

A recent full-server dump looked like this — only the first 0.9% of it was wanted:

```
Micro-Surveys   lines     10–2757     ← keep
SPOTS           lines   2758–176953   ← different project
mysql           lines 176954–316881   ← accounts and password hashes
sys             lines 316882–320739   ← MySQL internals
```

### 3. Restore locally

```bash
./ops/restore-local-mysql.sh backups/Micro-Surveys-only-<timestamp>.sql.gz
```

Destructive locally, never remotely — production is not contacted. It reports how many tables will be replaced and prompts before proceeding (`-y` skips the prompt). It refuses to run on a dump missing its completeness marker, because `mysqldump` emits `DROP TABLE` before each `CREATE`: a truncated file would drop your tables and then fail partway through reloading. Use `-f` to override when you have verified a file yourself.

Bare `CREATE DATABASE` statements are rewritten to `IF NOT EXISTS`, since Compose pre-creates the database via `MYSQL_DATABASE` and the bare form otherwise fails with `ERROR 1007`.

### Verify

```bash
docker exec mysql-container sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot --table "Micro-Surveys" -e "
  SELECT \"Courses\" t, COUNT(*) n FROM Courses
  UNION ALL SELECT \"People\", COUNT(*) FROM People
  UNION ALL SELECT \"Enrollment\", COUNT(*) FROM Enrollment
  UNION ALL SELECT \"Survey_Responses\", COUNT(*) FROM Survey_Responses;"'
```

`SHOW TABLE STATUS` and the `information_schema.tables.table_rows` column report InnoDB *estimates* that can be badly wrong on small tables — a table of 89 rows may report 8. Always `COUNT(*)` when the number matters.

### About `schema-setup.sql`

Production already carries the `uniq_people_empl_id` index, so a restored database needs nothing further. The script remains for the case where you are working against a database that lacks it. It is safe to re-run — it uses `CREATE UNIQUE INDEX IF NOT EXISTS`.

### Restoring additional databases (SPOTS)

The production server hosts more than `Micro-Surveys`. A full-server dump already contains them, so no second pull is needed — extract and restore each one:

```bash
./ops/extract-database.sh backups/db.sql.gz SPOTS
./ops/restore-local-mysql.sh backups/SPOTS-only-<timestamp>.sql.gz
```

Two things bite on databases that contain **views**, and both are handled or documented rather than mysterious:

**Adminer emits an invalid stub for views it cannot introspect.** It dumps each view twice — first a `CREATE TABLE` placeholder so dependants resolve, then a `DROP TABLE` plus the real `CREATE VIEW`. When column introspection fails it writes `CREATE TABLE \`x\` ();`, an empty column list that is not valid SQL and aborts the restore. `restore-local-mysql.sh` rewrites these stubs with one throwaway column; the real definition replaces them moments later.

**Views carry production's `DEFINER`.** SPOTS' views are defined `DEFINER=\`admin\`@\`%\` SQL SECURITY DEFINER`, meaning they execute with that account's privileges. If the account does not exist locally, every read fails:

```
ERROR 1449 (HY000): The user specified as a definer ('admin'@'%') does not exist
```

Create it locally and grant the new database to Metabase, which the container init only granted `Micro-Surveys`:

```bash
docker exec mysql-container sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "
  CREATE USER IF NOT EXISTS \"admin\"@\"%\" IDENTIFIED BY \"admin\";
  GRANT SELECT ON \`SPOTS\`.* TO \"admin\"@\"%\";
  GRANT SELECT ON \`SPOTS\`.* TO \"metabase\"@\"%\";
  FLUSH PRIVILEGES;"'
```

The local `admin` password is arbitrary — nothing authenticates as it. The account only needs to *exist*, with rights on the underlying tables, for `SQL SECURITY DEFINER` views to resolve.

> **If a restore fails partway, drop the database before retrying.** A half-applied dump leaves view stubs as real tables, and the retry then fails with `ERROR 1347: 'x' is not VIEW`. `DROP DATABASE \`SPOTS\`` and restore again from clean.

### Handling dump files

`backups/` is gitignored. Treat its contents as sensitive:

- Extracts of `Micro-Surveys` hold **real student enrollment and survey data**
- Full-server dumps additionally hold **production database credentials** (`mysql.user.authentication_string`)

Keep the extract, delete the full-server dump once you have it, and never commit or forward either.

---

## Replicating Production Metabase

Restoring MySQL gives Metabase something to **query**. It gives it nothing to **display** — a fresh instance shows the setup wizard even with a full database behind it.

Dashboards, questions, collections, users, permissions, and data-source connections all live in Metabase's **application database**, which is entirely separate from `Micro-Surveys`. Replicating production means copying that application database across. There is no partial version: dashboards and users come as one unit.

> Metabase's **serialization** feature (exporting dashboards to YAML) is **Pro/Enterprise only**, and Metabase explicitly states it is *not* a backup mechanism. On open source, copying the application database is the supported path.

### Version must match first

The application database migrates **forward only**. An app DB from a newer Metabase will not boot on an older build; an older one is silently upgraded in place with no way back.

Check production's real version — the image tag may be `latest`, which tells you nothing:

```bash
docker logs metabase-container 2>&1 | grep -iE "Metabase v[0-9]" | head -3
```

Then pin `Metabase/docker-compose.yml` to that exact version before importing anything.

> **⚠ Production runs `metabase/metabase:latest`.** Any `docker compose pull` followed by a restart upgrades Metabase and migrates the H2 application database forward, irreversibly. Pin production to an explicit version.

### Copy the application database

Production stores it as H2 at `/home/saumr/docker-compose/metabase-data/metabase.db/metabase.db.mv.db` — note it sits one directory deeper than `MB_DB_FILE` implies.

**Metabase must be stopped.** H2 holds file locks, and a copy taken while it is running can be internally inconsistent.

```bash
# ON PRODUCTION — downtime is ~10–30 seconds
docker stop metabase-container
cd /home/saumr/docker-compose/metabase-data/metabase.db/
gzip -c metabase.db.mv.db > /tmp/metabase-backup.mv.db.gz

stat -c %s metabase.db.mv.db      # record: size
sha256sum metabase.db.mv.db       # record: checksum

docker start metabase-container
```

Compressing first roughly halves the transfer and makes truncation detectable — gzip carries its own integrity check, whereas a partial H2 file keeps a valid `H:2,` header and looks fine.

Transfer `/tmp/metabase-backup.mv.db.gz` to `backups/`, then:

```bash
gzip -t backups/metabase-backup.mv.db.gz          # transfer is whole
gzip -d backups/metabase-backup.mv.db.gz

EXPECT_SIZE=<size> EXPECT_SHA256=<checksum> \
  ./ops/import-metabase-h2.sh backups/metabase-backup.mv.db
```

The script stops Metabase, preserves the current app DB as `metabase.db.mv.db.pre-import-<timestamp>`, installs the new one, restarts, and polls health for three minutes — **rolling back automatically if it fails to boot**. Passing `EXPECT_SIZE`/`EXPECT_SHA256` is strongly recommended; without them, truncation cannot be detected from the file's contents.

> **File size is not a reliable comparison.** H2 compacts its MVStore on clean shutdown. The same database can read 60 MB while running and 12 MB after `docker stop`. Compare **checksums**, taken in the same state.

### Reconnect the data source

The imported app DB carries **production's** connection settings, including production's credentials. Every report will fail until you re-point it:

```
(conn=NNNN) Access denied for user 'root'@'172.19.0.x' (using password: YES)
```

Log in at http://localhost:3000 with your **production Metabase credentials** — local accounts were replaced by production's user table — then go to **Admin → Databases → (your database) → Edit connection** and set:

| Field | Value | Source |
|---|---|---|
| Host | `db` | Compose service name; resolves on `app-network` |
| Port | `3306` | `DB_PORT` |
| Database name | `Micro-Surveys` | `DB_NAME` |
| Username | `metabase` | `DB_USER` |
| Password | `metabase` | `DB_USER_PASSWORD` |

Use `metabase`, not `root`. The `metabase` account holds `ALL PRIVILEGES ON \`Micro-Surveys\`.*` — everything Metabase needs — while leaving the rest of the server alone. Root stays reserved for the import tools.

Use **`db`**, not `localhost` or `127.0.0.1`: Metabase connects from inside its own container, where `localhost` is the Metabase container itself. `db` is the MySQL service on the shared Compose network.

Verify the credentials independently of Metabase at any time:

```bash
docker exec mysql-container mysql -h db -u metabase -pmetabase "Micro-Surveys" \
  -e "SELECT COUNT(*) FROM Courses;"
```

### This local instance runs PostgreSQL, not H2

Production still uses H2. **This machine no longer does** — the application database was migrated to the `metabase-postgres` service, so backups are an ordinary `pg_dump` instead of a stop-the-service file copy.

That changes how a *future* production import works. `ops/import-metabase-h2.sh` swaps an H2 file into place, which this instance no longer reads — `MB_DB_TYPE=postgres` wins, and the swap would silently do nothing. The script is kept for restoring a pre-migration snapshot or seeding a fresh H2-based instance. To bring a newer production copy in, load it into Postgres instead:

```bash
# 1. Pull prod's H2 file (stop Metabase on prod first — see above), then:
cd Metabase
docker stop metabase-container

# 2. load-from-h2 requires an EMPTY target. Recreate the application database.
docker exec metabase-postgres psql -U metabase -d postgres \
  -c 'DROP DATABASE IF EXISTS metabase_app;' -c 'CREATE DATABASE metabase_app;'

# 3. Copy the H2 file to Metabase/metabase.db.mv.db, then migrate it in.
#    Note the truncated path: metabase.db, NOT metabase.db.mv.db.
docker run --rm --platform linux/amd64 \
  --network metabase_app-network \
  -v "$PWD":/metabase.db \
  -e MB_DB_TYPE=postgres \
  -e MB_DB_CONNECTION_URI="jdbc:postgresql://metabase-app-db:5432/metabase_app?user=metabase&password=metabase" \
  --entrypoint java \
  metabase/metabase:v0.55.12 \
  --add-opens java.base/java.nio=ALL-UNNAMED \
  -jar /app/metabase.jar load-from-h2 /metabase.db/metabase.db

docker compose up -d metabase
```

The Metabase version in that command must match both the H2 file's origin and the running instance. `--entrypoint java` is required — the image's default entrypoint is `run_metabase.sh`, which ignores the arguments.

### Backing up Metabase

```bash
./ops/backup-metabase-appdb.sh
```

Runs against a live instance — **no downtime**. PostgreSQL gives a consistent snapshot without blocking readers or writers. The script verifies gzip integrity and PostgreSQL's own completion marker, then reports what it captured so an empty-but-valid dump is obvious rather than reassuring:

```
✔  Backup verified.
   file       : backups/metabase-appdb-<timestamp>.sql.gz (284K)
   dashboards : 3
   questions  : 73
   users      : 10
```

Restore:

```bash
gzip -dc <file> | docker exec -i metabase-postgres psql -U metabase -d metabase_app
```

For contrast, the H2 procedure this replaced: stop Metabase, copy a 12 MB opaque blob, hope it was consistent, and accept that it can only be restored wholesale into an identical Metabase version. The dump above is 284 KB of readable SQL, taken without interrupting anyone.

> **`backups/` is gitignored and syncs nowhere.** Copy dumps somewhere durable — these files contain user accounts and password hashes as well as dashboard definitions.

---

## Metabase Reporting

### Role values: two spellings

`Enrollment.Role` and `People.Role` are copied verbatim from the Canvas roster CSV. Canvas exports the role as either `Student`/`Teacher` or `StudentEnrollment`/`TeacherEnrollment` depending on which export you take, and `pipeline.py` stores whichever arrived — it only ever substring-matches (`"teacher" in role.lower()`), so both pass through without complaint. Term 2983 loaded the short form; earlier terms loaded the long form.

**Decision: accept both spellings at query time rather than rewriting stored data.** Historic rows keep whatever Canvas sent, which keeps imports faithful to their source. Every report that filters on role must therefore match both:

```sql
WHERE Role IN ('Student', 'StudentEnrollment')
```

Prefer that over `LIKE '%Student%'`, which also matches Canvas's `StudentViewEnrollment` test-student rows and would inflate any student count. A filter written as `Role = 'Student'` silently drops every earlier term — it returns a plausible-looking number rather than an error, which is what makes it dangerous.

### Response rate is per enrollment, not per person

A student enrolled in three courses gets three chances to respond, so the denominator is **enrollments, not people**. In term 2983 that distinction is a factor of ~2.7: 151 student enrollments across only 55 distinct people.

Counting `COUNT(DISTINCT Empl_ID)` against `COUNT(DISTINCT Response_ID)` in a single joined query produces rates above 100%. The denominator collapses each person to one row across every course and term, while the numerator keeps counting that person's course-level responses separately — so as terms accumulate the denominator saturates and the numerator does not. This produced a 150% response rate on the Overview dashboard.

**Aggregate each side per course in its own subquery, then divide the sums.** Neither side can fan out through the join:

```sql
SELECT
  ROUND(SUM(COALESCE(r.responses, 0)) / NULLIF(SUM(COALESCE(s.students, 0)), 0), 4) AS ResponseRate
FROM Courses c
JOIN Terms t ON c.TermCode = t.TermCode
LEFT JOIN (
  SELECT CanvasID, COUNT(DISTINCT Empl_ID) AS students
  FROM Enrollment
  WHERE Role IN ('Student', 'StudentEnrollment')
  GROUP BY CanvasID
) s ON s.CanvasID = c.CanvasID
LEFT JOIN (
  SELECT CanvasID, COUNT(DISTINCT Response_ID) AS responses
  FROM Survey_Responses
  WHERE Survey_ID = 'ERAU_ASIA'
  GROUP BY CanvasID
) r ON r.CanvasID = c.CanvasID
WHERE 1 = 1
  [[AND t.Term = {{term}}]]
  [[AND c.Instructor = {{instructor}}]]
  [[AND c.CourseName = {{course}}]]
```

Three conventions this encodes, all of which caused real wrong answers:

- **Filter the right-hand table inside its subquery or `ON` clause, never in `WHERE`.** `WHERE sr.Survey_ID = 'ERAU_ASIA'` on a `LEFT JOIN` turns it back into an inner join — NULL never equals the literal — dropping every zero-response course, which is precisely the set that would lower the average.
- **Return the fraction, not the percentage.** Cards are formatted as Percent in Metabase's column settings, so `0.32` displays as 32%. Multiplying by 100 as well yields 3200%. Round to 4 places, not 2 — at 2 places a percentage can only land on whole numbers.
- **A single course can still legitimately exceed 100%.** Responses are anonymous and nothing deduplicates at the person level, so one student submitting twice inflates that course. That is a data-quality signal worth surfacing, not something to cap in SQL.

---

## Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `✖ Metabase/.env not found` at startup | Gitignored file absent — normal on a new machine or fresh clone | Copy `.env` from the machine that has it, or `cd Metabase && cp env.sample .env` and set credentials |
| `variable is not set. Defaulting to a blank string` warnings from Compose | Same cause — `.env` missing or in the wrong directory | It must be `Metabase/.env`, beside `docker-compose.yml` |
| `TimeoutExpired: 'docker compose up -d' timed out` | First run pulling three images against too short a timeout | Fixed in `start.py` — the compose step now allows 15 min (`COMPOSE_TIMEOUT`). To pull manually first: `cd Metabase && docker compose pull` |
| Stack starts but `mysql-container` is unhealthy on a **first** run | Blank `MYSQL_ROOT_PASSWORD` from a missing `.env` at initialisation — the empty credential is baked into the volume | `docker compose down -v` (destroys the empty DB), fix `.env`, `docker compose up -d` |
| Dashboard (`localhost:5010`) not loading | Servers not started | Run `python3 start.py` from `data-handling-scripts/` |
| `localhost:5001`, `:5002`, or `:5003` not responding | One tool crashed after start | Restart `python3 start.py`; check terminal output for the failing script |
| `mysql-container is unhealthy` on `docker compose up` | Stale health status after force reboot | `docker compose down && docker compose up -d` |
| `Access denied for user 'root'@'<ip>' (using password: YES)` in Adminer/phpMyAdmin, while the container reports **healthy** | The healthcheck authenticates as `root@'localhost'` over the socket; the browser client arrives over TCP and matches a different account — usually `root@'%'`, whose password drifted from `.env`, or a stale grant pinned to an old container IP | `ALTER USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY '<DB_PASSWORD>'` — see [MySQL accounts are per source host](#mysql-accounts-are-per-source-host). Do **not** grant to the new literal IP; it breaks again on the next restart |
| Root login worked yesterday, fails after `docker compose down && up` | Docker recreated the bridge network on a new subnet, so any grant pinned to a literal container IP stopped matching | Same fix — move the grant to `root@'%'` and drop the IP-pinned account |
| `Table 'Micro-Surveys.<name>' doesn't exist` on import | Empty database — the repo has no `CREATE TABLE` statements, so a fresh clone has no schema | Restore a production extract: [Production Data and Backups](#production-data-and-backups) |
| `ops/dump-prod-mysql.sh` fails with **exit 255** | 255 is SSH's own error code — the connection or authentication failed and `mysqldump` never ran | Test the hop alone: `ssh -v user@host 'docker ps'`. Check key installation, host key acceptance, VPN, or jump host |
| `ERROR 1007 … database exists` when restoring by hand | Dump has a bare `CREATE DATABASE`; Compose already created it via `MYSQL_DATABASE` | Use `ops/restore-local-mysql.sh`, which rewrites it to `IF NOT EXISTS` |
| Restore refuses: `No completeness marker found` | Dump is truncated, or came from a tool whose sign-off isn't recognized | Re-pull the dump. If you have verified the file yourself, re-run with `-f` |
| Locked out of local MySQL after a restore | A full-server dump was restored, overwriting `mysql.user` with production accounts | `cd Metabase && docker compose down -v` (destroys local data), restart, then restore an **extract** — never a full-server dump |
| Row counts look wrong (e.g. 89 rows reported as 8) | `information_schema.tables.table_rows` is an InnoDB estimate | Use `COUNT(*)` whenever the number matters |
| Metabase shows the **setup wizard** despite a loaded database | Dashboards and users live in Metabase's application database, not in `Micro-Surveys` | [Replicating Production Metabase](#replicating-production-metabase) |
| Every report fails: `Access denied for user 'root'@'172.19.0.x'` | Imported app DB carries production's credentials | Re-point the connection to `db` / `3306` / `Micro-Surveys` / `metabase` / `metabase` — see [Reconnect the data source](#reconnect-the-data-source) |
| Metabase can't reach MySQL on `localhost` | Metabase connects from inside its own container, where `localhost` is Metabase itself | Use host `db`, the Compose service name on `app-network` |
| Imported app DB won't boot | Source came from a newer Metabase than this instance; migration is forward-only | Pin `Metabase/docker-compose.yml` to production's version. `import-metabase-h2.sh` rolls back automatically |
| H2 file size differs wildly between machines | H2 compacts its MVStore on clean shutdown — 60 MB running vs 12 MB stopped is the *same* database | Compare `sha256sum`, taken in the same state; never compare sizes across running/stopped |
| Restore aborts: `ERROR 1064 … near ')'` | Adminer wrote an empty view stub, `CREATE TABLE \`x\` ();` | Handled by `restore-local-mysql.sh`. Restoring by hand? Give the stub a throwaway column |
| Restore aborts: `ERROR 1347: 'x' is not VIEW` | An earlier failed restore left a view stub as a real table | `DROP DATABASE` and restore again from clean |
| Reading a view fails: `definer ('admin'@'%') does not exist` | Views carry production's `DEFINER` and run with its privileges | Create the account locally — see [Restoring additional databases](#restoring-additional-databases-spots) |
| Metabase sees `Micro-Surveys` but not `SPOTS` | Container init granted the `metabase` user only `MYSQL_DATABASE` | `GRANT SELECT ON \`SPOTS\`.* TO "metabase"@"%"` |
| Import completes but count is 0 | All Response_IDs already in DB | Normal for re-imports. New data will show non-zero. |
| Yellow ⚠ badge on roster file | Canvas ID not found in Notes.md | Add the course URL + SIS ID to Notes.md |
| Status reads "Notes.md found — 14 course(s) indexed" but badges show unfamiliar course names | No `Notes.md`; the tools fell back to the committed `Notes-src.md` from term 2943 | Create `data-handling-scripts/Notes.md` with the current term's courses |
| Import succeeds but Metabase shows last term's courses | Same stale-fallback cause as above | As above, then re-import — Courses use `ON DUPLICATE KEY UPDATE`, so corrected rows overwrite |
| Red ✖ badge on roster file | No 4+ digit number in filename | Rename file to `<CanvasID>.csv` |
| "No data rows found" in survey import | Wrong file format or not a Qualtrics export | Check that the file is a Qualtrics CSV export, not a manual spreadsheet |
| Metabase shows no data after import | Metabase cache | Browse to the question/dashboard and click the refresh icon |
| Response rate above 100% | Denominator deduplicates people (`COUNT(DISTINCT Empl_ID)`) while the numerator counts each person's per-course responses | Aggregate per course in subqueries, then divide the sums — see [Response rate is per enrollment](#response-rate-is-per-enrollment-not-per-person) |
| A term's counts read as 0, or a term is missing from a report entirely | A role filter written `= 'Student'` excludes terms stored as `StudentEnrollment` (or vice versa) | `WHERE Role IN ('Student', 'StudentEnrollment')` — see [Role values](#role-values-two-spellings) |
| Courses with zero responses missing from a report | A `LEFT JOIN`ed table filtered in `WHERE` instead of `ON`, which makes the join inner | Move the predicate into the `ON` clause or the subquery |
| Dashboard cards show "There was a problem displaying this chart" — **some** cards still render | Metabase's stored DB password no longer matches MySQL (typically after a root password change). The cards that still work are serving cached results, which disguises this as a data or import problem | Re-enter the connection in **Admin settings → Databases → Micro-Surveys** and save. Metabase keeps this credential in its own app DB — editing `Metabase/.env` does not update it |

---

## License

MIT
