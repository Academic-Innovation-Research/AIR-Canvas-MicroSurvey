# AIR Canvas MicroSurvey

An institutional analytics toolset for Canvas LMS. It delivers in-course survey prompts via a JavaScript popup, then pipelines the resulting Qualtrics data—along with Canvas enrollment rosters—into a MySQL database connected to Metabase for reporting.

Built for ERAU Worldwide. Operates across 1–30 courses per survey run.

---

## Quick Start

Two prerequisites, then everything else is automated:

1. **Docker installed** — `start.py` will launch Docker Desktop itself if it isn't running.
2. **`Metabase/.env` present** — gitignored, so it is never in a fresh clone. Copy it from a machine that has it, or `cd Metabase && cp env.sample .env` and set the credentials. `start.py` checks for it first and stops with instructions if it is missing.

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
| `Role` | `varchar(50)` | `StudentEnrollment`, `TeacherEnrollment`, etc. |

#### Enrollment
Junction table linking people to courses. Rebuilt per-course on each import.

| Column | Type | Notes |
|---|---|---|
| `ID` | `int` | PK, auto-increment |
| `CanvasID` | `int` | FK → Courses |
| `Empl_ID` | `varchar(50)` | FK → People |
| `Role` | `varchar(255)` | Role in this specific course |

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

The import tools read `.env` automatically from `../Metabase/.env` relative to the scripts directory. No environment setup is needed beyond creating the file.

> **The file is required, not optional.** `docker-compose.yml` substitutes these variables directly. Without `.env`, Compose fills every one with an empty string, MySQL refuses to initialise on a blank root password, and the container ends up unhealthy — a failure that surfaces well after the step that caused it. `start.py` now checks for the file before touching Docker.
>
> Change `DB_PASSWORD` after `db-data` already exists and MySQL will reject the new password: the root credential lives in the volume, set at first initialisation. To genuinely reset it, `docker compose down -v` (**destroys all data**) and re-import.

### Services

| Container | Port | Image |
|---|---|---|
| `mysql-container` | 3306 | `mysql:8.1` (arm64) |
| `phpmyadmin-container` | 8081 | `phpmyadmin:5.2.1` |
| `metabase-container` | 3000 | `metabase/metabase:v0.52.3` |

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
└── Metabase/
    ├── docker-compose.yml               MySQL 8 + phpMyAdmin + Metabase
    ├── .env                             ★ (gitignored) credentials — required; stack will not start without it
    ├── env.sample                       Template for .env
    └── README.md                        Docker-specific documentation
```

**Not in a fresh clone.** `Metabase/.env`, `data-handling-scripts/Notes.md`, `Enrollment/`, and `sql/` are all gitignored. The first two you must supply. The last two belong to the superseded pipeline and nothing in the current process creates or reads them.

---

## First-time Database Setup

After the Docker stack is running for the first time, apply the schema setup script once:

```bash
docker exec -i mysql-container mysql -uroot -p"$(grep DB_PASSWORD Metabase/.env | cut -d= -f2)" Micro-Surveys < data-handling-scripts/schema-setup.sql
```

This creates the unique index on `People(EMPL_ID)` that makes re-imports idempotent. It is safe to re-run — it uses `CREATE UNIQUE INDEX IF NOT EXISTS`.

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
| Import completes but count is 0 | All Response_IDs already in DB | Normal for re-imports. New data will show non-zero. |
| Yellow ⚠ badge on roster file | Canvas ID not found in Notes.md | Add the course URL + SIS ID to Notes.md |
| Status reads "Notes.md found — 14 course(s) indexed" but badges show unfamiliar course names | No `Notes.md`; the tools fell back to the committed `Notes-src.md` from term 2943 | Create `data-handling-scripts/Notes.md` with the current term's courses |
| Import succeeds but Metabase shows last term's courses | Same stale-fallback cause as above | As above, then re-import — Courses use `ON DUPLICATE KEY UPDATE`, so corrected rows overwrite |
| Red ✖ badge on roster file | No 4+ digit number in filename | Rename file to `<CanvasID>.csv` |
| "No data rows found" in survey import | Wrong file format or not a Qualtrics export | Check that the file is a Qualtrics CSV export, not a manual spreadsheet |
| Metabase shows no data after import | Metabase cache | Browse to the question/dashboard and click the refresh icon |

---

## License

MIT
