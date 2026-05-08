#!/usr/bin/env python3
"""
AIR Canvas MicroSurvey — Start Script

Usage:
    python3 start.py           # from data-handling-scripts/
    python3 data-handling-scripts/start.py   # from repo root

What it does:
  1. Checks that Docker is running (prompts you to start it if not)
  2. Starts the Metabase Docker stack (MySQL + phpMyAdmin + Metabase)
  3. Waits for MySQL to accept connections
  4. Opens the dashboard in your browser:
       http://localhost:5010  — Dashboard (links to all tools)
  5. Runs all four servers (Ctrl+C to stop)
"""

import os
import platform
import subprocess
import sys
import time
import threading
import webbrowser
from pathlib import Path

HERE         = Path(__file__).parent
METABASE_DIR = HERE.parent / "Metabase"
PORT_DASH    = int(os.environ.get("DASHBOARD_PORT",     5010))
PORT_ENROLL  = int(os.environ.get("UPLOAD_PORT",        5001))
PORT_SURVEY  = int(os.environ.get("SURVEY_UPLOAD_PORT", 5002))
PORT_EXPORT  = int(os.environ.get("EXPORT_PORT",        5003))
URL_DASH     = f"http://localhost:{PORT_DASH}"
URL_ENROLL   = f"http://localhost:{PORT_ENROLL}"
URL_SURVEY   = f"http://localhost:{PORT_SURVEY}"
URL_EXPORT   = f"http://localhost:{PORT_EXPORT}"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_dotenv() -> dict:
    env: dict = {}
    env_path = METABASE_DIR / ".env"
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def _run(*args, cwd=None, capture=True):
    return subprocess.run(
        list(args), capture_output=capture,
        cwd=str(cwd) if cwd else None, timeout=30,
    )


def _docker_running() -> bool:
    try:
        return _run("docker", "info").returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _start_docker_desktop() -> bool:
    system = platform.system()
    if system == "Darwin":
        print("  Starting Docker Desktop…")
        subprocess.Popen(["open", "-a", "Docker"])
    elif system == "Windows":
        candidates = [
            r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
            r"C:\Program Files (x86)\Docker\Docker\Docker Desktop.exe",
        ]
        for path in candidates:
            if Path(path).exists():
                print("  Starting Docker Desktop…")
                subprocess.Popen([path])
                break
        else:
            return False
    else:
        print("  Cannot auto-start Docker on Linux — please start it manually.")
        return False

    print("  Waiting for Docker to be ready", end="", flush=True)
    for _ in range(30):
        time.sleep(2)
        print(".", end="", flush=True)
        if _docker_running():
            print(" ready.")
            return True
    print(" timed out.")
    return False


def _mysql_ready(container: str, password: str) -> bool:
    try:
        r = _run(
            "docker", "exec", container,
            "mysql", "-uroot", f"-p{password}", "-e", "SELECT 1",
        )
        return r.returncode == 0
    except Exception:
        return False


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    dotenv    = _load_dotenv()
    container = os.environ.get("MYSQL_CONTAINER") or dotenv.get("MYSQL_CONTAINER") or "mysql-container"
    password  = os.environ.get("DB_PASSWORD")     or dotenv.get("DB_PASSWORD")     or "password"

    print(f"\nAIR Canvas MicroSurvey")
    print("=" * 48)
    print(f"  Dashboard         : {URL_DASH}  ← open this")
    print(f"  Enrollment Import : {URL_ENROLL}")
    print(f"  Survey Import     : {URL_SURVEY}")
    print(f"  SQL Export        : {URL_EXPORT}")
    print(f"  phpMyAdmin        : http://localhost:8081")
    print(f"  Metabase          : http://localhost:3000")

    # 1. Docker
    print("\n[1/4] Docker")
    if not _docker_running():
        print("  Docker is not running.")
        if not _start_docker_desktop():
            print("\n✖  Please start Docker Desktop manually, then re-run this script.")
            sys.exit(1)
    else:
        print("  Docker is running. ✔")

    # 2. Docker stack
    print("\n[2/4] Starting Docker stack (MySQL + phpMyAdmin + Metabase)…")
    for compose_cmd in (["docker", "compose"], ["docker-compose"]):
        r = _run(*compose_cmd, "up", "-d", cwd=METABASE_DIR)
        if r.returncode == 0:
            break
    else:
        print(f"\n✖  docker compose failed:\n{r.stderr.decode()}")
        sys.exit(1)
    print("  Stack is up. ✔")

    # 3. Wait for MySQL
    print(f"\n[3/4] Waiting for MySQL ({container})…", end="", flush=True)
    for attempt in range(20):
        if _mysql_ready(container, password):
            print(" ready. ✔")
            break
        print(".", end="", flush=True)
        time.sleep(3)
    else:
        print("\n⚠  MySQL did not become ready in 60 s — proceeding anyway.")

    # 4. Start all servers + open dashboard
    print(f"\n[4/4] Starting tools…")

    procs = [
        subprocess.Popen([sys.executable, str(HERE / "dashboard.py")],        cwd=str(HERE)),
        subprocess.Popen([sys.executable, str(HERE / "upload_app.py")],        cwd=str(HERE)),
        subprocess.Popen([sys.executable, str(HERE / "survey_upload_app.py")], cwd=str(HERE)),
        subprocess.Popen([sys.executable, str(HERE / "export_app.py")],        cwd=str(HERE)),
    ]

    def _open_browsers():
        time.sleep(1.5)
        webbrowser.open(URL_DASH)

    threading.Thread(target=_open_browsers, daemon=True).start()

    print(f"\n✔  All tools running. Press Ctrl+C to stop.\n")
    print(f"  Dashboard → {URL_DASH}\n")

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()
        print("\n\nStopped.")


if __name__ == "__main__":
    main()
