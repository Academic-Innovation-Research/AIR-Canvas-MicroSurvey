/**
 * Canvas Roster Exporter — Bookmarklet Source
 *
 * Exports the Canvas People page roster to a CSV file named after the
 * Canvas course ID (e.g. 201288.csv). This filename is required by
 * the upload_app.py enrollment import tool.
 *
 * USAGE
 *   1. Navigate to a Canvas course → People page.
 *   2. Click the bookmarklet.
 *   3. Wait a few seconds while it scrolls to load all rows.
 *   4. The file downloads automatically as <courseId>.csv.
 *
 * TO BUILD THE BOOKMARKLET
 *   Minify this file (remove comments and whitespace) and prepend
 *   "javascript:" — the result is what you paste into the bookmark URL.
 *   The ready-to-use one-liner is in README.md.
 *
 * FILENAME LOGIC
 *   Extracts the Canvas course ID from the page URL:
 *     https://erau.instructure.com/courses/201288/users → 201288.csv
 *   Falls back to canvas-roster-YYYY-MM-DD.csv if no course ID is found.
 */

(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  try {
    // Locate the roster table (Canvas uses different class names across versions)
    const getTable = () =>
      document.querySelector("table.roster") ||
      document.querySelector("table.ic-Table");

    // Scroll incrementally to trigger lazy-loading of all roster rows.
    // Stops early if the row count stabilises (3 consecutive equal counts).
    let lastCount = 0, stableRuns = 0;
    const scroller = document.scrollingElement || document.documentElement;
    for (let i = 0; i < 20 && stableRuns < 3; i++) {
      scroller.scrollTop = scroller.scrollHeight;
      await sleep(500);
      const n = document.querySelectorAll(
        "table.roster tbody tr, table.ic-Table tbody tr"
      ).length;
      if (n === lastCount) stableRuns++;
      else { stableRuns = 0; lastCount = n; }
    }

    const table = getTable();
    if (!table) {
      alert("Roster table not found. Navigate to the course People page and try again.");
      return;
    }

    // Extract header row
    const rows = [];
    let headers = [...table.querySelectorAll("thead th, thead td")]
      .map(c => c.textContent.trim());
    if (!headers.length) {
      // Some Canvas themes put headers in the first tbody row
      const firstRow = table.querySelector("tbody tr");
      if (firstRow) headers = [...firstRow.children].map(c => c.textContent.trim());
    }
    if (headers.length) rows.push(headers);

    // Extract data rows
    [...table.querySelectorAll("tbody tr")].forEach(tr => {
      rows.push([...tr.children].map(td => td.innerText.trim()));
    });

    // CSV-escape a single cell value:
    //   - Normalise non-breaking spaces and collapse whitespace
    //   - Wrap in double quotes, escaping internal quotes as ""
    const escCell = v => {
      v = (v ?? "").replace(/ /g, " ").replace(/\s+/g, " ").trim().replace(/"/g, '""');
      return `"${v}"`;
    };
    const csv = rows.map(r => r.map(escCell).join(",")).join("\n");

    // Derive filename from Canvas course ID in the URL.
    // Works on any Canvas page under /courses/<id>/...
    const courseId = (location.pathname.match(/\/courses\/(\d+)/) || [])[1];
    const filename = courseId
      ? `${courseId}.csv`
      : `canvas-roster-${new Date().toISOString().slice(0, 10)}.csv`;

    // Trigger the download
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1500);

  } catch (e) {
    console.error(e);
    alert("Error exporting roster. See the browser console for details.");
  }
})();
