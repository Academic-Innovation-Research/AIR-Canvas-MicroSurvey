#!/usr/bin/env python3
"""
AIR Canvas MicroSurvey — Dashboard  (port 5010)

Landing page that links to all data management tools with live status
indicators. This is the first page opened by start.py.

Usage:
    python3 dashboard.py
    # open http://localhost:5010
"""

import json
import os
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict

# ── Config ─────────────────────────────────────────────────────────────────────

def _load_dotenv(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

_HERE   = Path(__file__).parent
_dotenv = _load_dotenv(_HERE.parent / "Metabase" / ".env")

def _cfg(key: str, fallback: str) -> str:
    return os.environ.get(key) or _dotenv.get(key) or fallback

MYSQL_CONTAINER  = _cfg("MYSQL_CONTAINER", "mysql-container")
DB_ROOT_PASSWORD = _cfg("DB_PASSWORD",     "password")
DB_NAME          = _cfg("DB_NAME",         "Micro-Surveys")
PORT             = int(os.environ.get("DASHBOARD_PORT", 5010))

# ── Status helpers ─────────────────────────────────────────────────────────────

def _port_open(port: int) -> bool:
    """TCP connect check — fast, no HTTP overhead."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _db_ok() -> bool:
    try:
        r = subprocess.run(
            ["docker", "exec", MYSQL_CONTAINER,
             "mysql", "-uroot", f"-p{DB_ROOT_PASSWORD}", "-e", "SELECT 1"],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _status() -> dict:
    return {
        "db":       _db_ok(),
        "enroll":   _port_open(5001),
        "survey":   _port_open(5002),
        "export":   _port_open(5003),
        "phpmyadmin": _port_open(8081),
        "metabase": _port_open(3000),
    }

# ── HTML ───────────────────────────────────────────────────────────────────────

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AIR Canvas MicroSurvey</title>
<style>
  :root {
    --bg:       #0f1117;
    --surface:  #1a1d27;
    --surface2: #21253a;
    --border:   #2a2d3a;
    --accent:   #4f8ef7;
    --green:    #38c97d;
    --amber:    #f5a623;
    --red:      #e05c5c;
    --text:     #e2e4ec;
    --muted:    #7a7f9a;
    --radius:   12px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    min-height: 100vh;
    padding: 40px 24px 80px;
  }

  /* ── Header ── */
  header {
    max-width: 900px;
    margin: 0 auto 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
  }
  .brand h1 { font-size: 1.4rem; font-weight: 700; letter-spacing: -0.4px; }
  .brand p  { color: var(--muted); font-size: 0.85rem; margin-top: 3px; }

  .db-badge {
    display: flex; align-items: center; gap: 8px;
    padding: 7px 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    font-size: 0.82rem;
    color: var(--muted);
  }
  .db-badge .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--border); flex-shrink: 0; }
  .db-badge.ok   .dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .db-badge.ok        { color: var(--text); }
  .db-badge.err  .dot { background: var(--red); }

  /* ── Section labels ── */
  .section-label {
    max-width: 900px;
    margin: 0 auto 14px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--muted);
  }

  /* ── Card grid ── */
  .grid {
    max-width: 900px;
    margin: 0 auto 36px;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }
  .grid.two { grid-template-columns: repeat(2, 1fr); }

  @media (max-width: 680px) {
    .grid, .grid.two { grid-template-columns: 1fr; }
  }

  /* ── Card ── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px 22px 18px;
    display: flex;
    flex-direction: column;
    gap: 0;
    transition: border-color .15s, box-shadow .15s;
  }
  .card:hover { border-color: #3a3f52; box-shadow: 0 4px 24px rgba(0,0,0,.35); }

  .card-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 14px;
  }
  .card-icon {
    width: 40px; height: 40px;
    background: var(--surface2);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    color: var(--accent);
    flex-shrink: 0;
  }
  .card-icon svg { width: 20px; height: 20px; }

  .status-dot {
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--border);
    margin-top: 4px;
    flex-shrink: 0;
    transition: background .3s, box-shadow .3s;
  }
  .status-dot.up   { background: var(--green); box-shadow: 0 0 7px var(--green); }
  .status-dot.down { background: var(--muted); }

  .card h2 { font-size: 0.97rem; font-weight: 700; margin-bottom: 6px; }
  .card p  { font-size: 0.83rem; color: var(--muted); line-height: 1.5; flex: 1; }

  .card-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
  }
  .port-badge {
    font-size: 0.75rem;
    color: var(--muted);
    font-family: "SF Mono", "Fira Mono", monospace;
  }
  .open-btn {
    display: flex; align-items: center; gap: 6px;
    padding: 7px 14px;
    background: var(--accent);
    color: #fff;
    font-size: 0.82rem; font-weight: 600;
    border: none; border-radius: 7px;
    cursor: pointer; text-decoration: none;
    transition: background .15s, opacity .15s;
  }
  .open-btn:hover { background: #6fa3ff; }
  .open-btn.secondary {
    background: var(--surface2);
    color: var(--text);
    border: 1px solid var(--border);
  }
  .open-btn.secondary:hover { background: #2a2d3f; }

  /* ── Footer ── */
  footer {
    max-width: 900px;
    margin: 48px auto 0;
    text-align: center;
    font-size: 0.78rem;
    color: var(--muted);
  }
  footer kbd {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 6px;
    font-family: "SF Mono", "Fira Mono", monospace;
    font-size: 0.75rem;
  }
</style>
</head>
<body>

<header>
  <div class="brand">
    <h1>AIR Canvas MicroSurvey</h1>
    <p>ERAU Worldwide · Data Management Tools</p>
  </div>
  <div class="db-badge" id="db-badge">
    <div class="dot"></div>
    <span id="db-label">Checking database…</span>
  </div>
</header>

<div class="section-label">Import Tools</div>

<div class="grid" id="primary-grid">

  <div class="card">
    <div class="card-top">
      <div class="card-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
      </div>
      <div class="status-dot" id="dot-enroll"></div>
    </div>
    <h2>Canvas Enrollment Import</h2>
    <p>Drag and drop Canvas roster CSVs to import enrollment data — Terms, Courses, People, and Enrollment rows.</p>
    <div class="card-footer">
      <span class="port-badge">:5001</span>
      <a href="http://localhost:5001" target="_blank" class="open-btn">
        Open
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
      </a>
    </div>
  </div>

  <div class="card">
    <div class="card-top">
      <div class="card-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
      </div>
      <div class="status-dot" id="dot-survey"></div>
    </div>
    <h2>Qualtrics Survey Import</h2>
    <p>Drag and drop Qualtrics exports (either format) to import survey responses. Auto-detects format; skips duplicates.</p>
    <div class="card-footer">
      <span class="port-badge">:5002</span>
      <a href="http://localhost:5002" target="_blank" class="open-btn">
        Open
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
      </a>
    </div>
  </div>

  <div class="card">
    <div class="card-top">
      <div class="card-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3"/>
          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
        </svg>
      </div>
      <div class="status-dot" id="dot-export"></div>
    </div>
    <h2>SQL Export Tool</h2>
    <p>Select one or more terms and download a complete SQL delta — enrollment and survey data — ready to import elsewhere.</p>
    <div class="card-footer">
      <span class="port-badge">:5003</span>
      <a href="http://localhost:5003" target="_blank" class="open-btn">
        Open
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
      </a>
    </div>
  </div>

</div>

<div class="section-label">Administration</div>

<div class="grid two">

  <div class="card">
    <div class="card-top">
      <div class="card-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
          <line x1="8" y1="21" x2="16" y2="21"/>
          <line x1="12" y1="17" x2="12" y2="21"/>
        </svg>
      </div>
      <div class="status-dot" id="dot-phpmyadmin"></div>
    </div>
    <h2>phpMyAdmin</h2>
    <p>Browse tables, run queries, and inspect the Micro-Surveys database directly in the browser.</p>
    <div class="card-footer">
      <span class="port-badge">:8081</span>
      <a href="http://localhost:8081" target="_blank" class="open-btn secondary">
        Open
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
      </a>
    </div>
  </div>

  <div class="card">
    <div class="card-top">
      <div class="card-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="20" x2="18" y2="10"/>
          <line x1="12" y1="20" x2="12" y2="4"/>
          <line x1="6"  y1="20" x2="6"  y2="14"/>
          <line x1="2"  y1="20" x2="22" y2="20"/>
        </svg>
      </div>
      <div class="status-dot" id="dot-metabase"></div>
    </div>
    <h2>Metabase</h2>
    <p>Dashboards, charts, and analytics. Visualize satisfaction scores, enrollment trends, and response rates.</p>
    <div class="card-footer">
      <span class="port-badge">:3000</span>
      <a href="http://localhost:3000" target="_blank" class="open-btn secondary">
        Open
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
          <polyline points="15 3 21 3 21 9"/>
          <line x1="10" y1="14" x2="21" y2="3"/>
        </svg>
      </a>
    </div>
  </div>

</div>

<footer>
  Status refreshes every 15 s &nbsp;·&nbsp; Press <kbd>Ctrl+C</kbd> in the terminal to stop all tools
</footer>

<script>
async function refresh() {
  try {
    const r = await fetch('/status');
    const s = await r.json();

    // DB badge
    const badge = document.getElementById('db-badge');
    const label = document.getElementById('db-label');
    if (s.db) {
      badge.className = 'db-badge ok';
      label.textContent = 'Database connected';
    } else {
      badge.className = 'db-badge err';
      label.textContent = 'Database offline';
    }

    // Tool dots
    const map = {
      'dot-enroll':     s.enroll,
      'dot-survey':     s.survey,
      'dot-export':     s.export,
      'dot-phpmyadmin': s.phpmyadmin,
      'dot-metabase':   s.metabase,
    };
    for (const [id, up] of Object.entries(map)) {
      const el = document.getElementById(id);
      if (el) el.className = 'status-dot ' + (up ? 'up' : 'down');
    }
  } catch (e) {
    // dashboard itself is fine, network error is transient
  }
}

refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>
"""

# ── HTTP handler ───────────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def _send_html(self, html: str) -> None:
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/":
            self._send_html(_HTML)
        elif path == "/status":
            self._send_json(_status())
        else:
            self.send_response(404)
            self.end_headers()


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    server = HTTPServer(("", PORT), DashboardHandler)
    print(f"\n  Dashboard running at http://localhost:{PORT}")
    print(f"  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
