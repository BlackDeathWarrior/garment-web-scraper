#!/usr/bin/env python3
"""Local HTTP worker for instant scraper runs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit
import time

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional runtime fallback
    load_dotenv = None


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.support import freshness, incidents, tokens  # noqa: E402
from scraper.support import routes as support_routes  # noqa: E402

OUTPUTS_DIR = ROOT / "outputs"
LOGS_DIR = OUTPUTS_DIR / "logs"
PUBLIC_LOG_FILE = ROOT / "frontend" / "public" / "scraper.log"
DEFAULT_SOURCES = "amazon,myntra,flipkart"


def _load_runtime_env() -> None:
    """Load runtime env config from common local env files."""
    if load_dotenv is None:
        return
    for env_file in (ROOT / ".env", ROOT / "frontend" / ".env"):
        if env_file.is_file():
            load_dotenv(env_file, override=False)


def _sanitize_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in {"'", '"'}:
        return trimmed[1:-1]
    return trimmed


def _resolve_admin_credentials() -> tuple[str, str | None]:
    admin_user = (
        os.environ.get("ADMIN_USERNAME")
        or os.environ.get("VITE_ADMIN_USERNAME")
        or "scraper_admin"
    )
    admin_pass = (
        os.environ.get("ADMIN_PASSWORD")
        or os.environ.get("VITE_ADMIN_PASSWORD")
    )
    return _sanitize_env_value(admin_user) or "scraper_admin", _sanitize_env_value(admin_pass)


_load_runtime_env()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _in_background(target, *args, **kwargs) -> None:
    """Runs a call to the support desk off the caller's thread: it must never hold up a scrape."""
    threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True).start()


def _tail(path: Path | None, lines: int) -> list[str]:
    if path is None or not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return [line.rstrip() for line in handle.readlines()[-lines:]]
    except OSError:
        return []


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line.rstrip() + "\n")


def _reset_log(path: Path, reason: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"[{datetime.now().strftime('%H:%M:%S')}] [worker    ] INFO "
        f"Instant scrape requested ({reason})"
    )
    path.write_text(header + "\n", encoding="utf-8")


def _discover_python_executable() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return str(candidate)
    return sys.executable


@dataclass
class WorkerStatus:
    running: bool = False
    pid: int | None = None
    last_started_at: str | None = None
    last_ended_at: str | None = None
    last_exit_code: int | None = None
    last_error: str | None = None
    last_log_file: str | None = None
    sources: str = DEFAULT_SOURCES
    max_products: int = 0
    queued: bool = False
    last_reason: str | None = None
    last_stopped_by_user: bool = False


class ScrapeWorker:
    def __init__(self, sources: str, max_products: int):
        self._sources = sources
        self._max_products = max_products
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._archive_handle = None
        self._stopped: subprocess.Popen[str] | None = None
        self._status = WorkerStatus(sources=sources, max_products=max_products)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_payload_unlocked()

    def log_tail(self, lines: int = 30) -> list[str]:
        """The last lines of the log the storefront's admin terminal shows."""
        return _tail(PUBLIC_LOG_FILE, lines)

    def trigger(
        self,
        reason: str = "manual",
        gender_flag: str = "",
        watch: bool = False,
        sources: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Starts a scrape. `sources` narrows this one run; the default is the worker's own list."""
        run_sources = sources or self._sources
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                payload = self._status_payload_unlocked()
                payload["ok"] = False
                payload["reason"] = "already-running"
                return HTTPStatus.CONFLICT, payload

            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            _reset_log(PUBLIC_LOG_FILE, reason)

            archive_path = LOGS_DIR / f"manual-scrape-{_stamp()}.log"
            archive_handle = open(archive_path, "w", encoding="utf-8")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUNBUFFERED"] = "1"
            env["SCRAPER_LOG_FILE"] = str(PUBLIC_LOG_FILE)
            env["SCRAPER_LOG_APPEND"] = "1"
            # Fix: Add ROOT to PYTHONPATH so scraper modules can be found
            env["PYTHONPATH"] = str(ROOT)

            command = [
                _discover_python_executable(),
                "-m",
                "scraper.collect",
                "--max-products",
                str(self._max_products),
                "--sources",
                run_sources,
                "--append-existing",
                "--stream-checkpoints",
            ]
            
            if watch:
                command.extend(["--watch", "--interval-minutes", "5"])
            
            if gender_flag:
                # Splitting " --gender Men" into ["--gender", "Men"]
                command.extend(gender_flag.strip().split())

            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(ROOT),
                    env=env,
                    stdout=archive_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creationflags,
                )
            except Exception as exc:
                archive_handle.close()
                self._status.running = False
                self._status.pid = None
                self._status.last_exit_code = 1
                self._status.last_error = str(exc)
                _append_line(
                    PUBLIC_LOG_FILE,
                    f"[{datetime.now().strftime('%H:%M:%S')}] [worker    ] ERR  {exc}",
                )
                payload = asdict(self._status)
                payload["ok"] = False
                payload["reason"] = "spawn-failed"
                _in_background(
                    incidents.report,
                    "scraper.spawn_failed",
                    "Scraper could not be started",
                    severity="critical",
                    source="worker",
                    message=str(exc),
                    details={"reason": reason, "sources": run_sources},
                    min_interval=0,
                )
                return HTTPStatus.INTERNAL_SERVER_ERROR, payload

            self._process = process
            self._archive_handle = archive_handle
            self._status.running = True
            self._status.pid = process.pid
            self._status.last_started_at = _now_iso()
            self._status.last_ended_at = None
            self._status.last_exit_code = None
            self._status.last_error = None
            self._status.last_log_file = str(archive_path)
            self._status.last_reason = reason
            self._status.last_stopped_by_user = False

            _append_line(
                PUBLIC_LOG_FILE,
                (
                    f"[{datetime.now().strftime('%H:%M:%S')}] [worker    ] INFO "
                    f"Started scraper process pid={process.pid}"
                ),
            )

            watcher = threading.Thread(target=self._watch_process, args=(process,), daemon=True)
            watcher.start()

            payload = self._status_payload_unlocked()
            payload["ok"] = True
            return HTTPStatus.ACCEPTED, payload

    def stop(self) -> tuple[int, dict[str, Any]]:
        """Terminates the current scraper process."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                # A run the admin stopped has not failed: the watcher must not report it.
                self._stopped = self._process
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                
                _append_line(
                    PUBLIC_LOG_FILE,
                    f"[{datetime.now().strftime('%H:%M:%S')}] [worker    ] WARN Scraper stopped manually by user",
                )
                payload = self._status_payload_unlocked()
                payload["ok"] = True
                return HTTPStatus.OK, payload
            
            return HTTPStatus.BAD_REQUEST, {"ok": False, "reason": "not-running"}

    def _watch_process(self, process: subprocess.Popen[str]) -> None:
        exit_code = process.wait()

        with self._lock:
            if self._process is not process:
                return

            if self._archive_handle is not None:
                try:
                    self._archive_handle.close()
                except Exception:
                    pass
                self._archive_handle = None

            stopped_by_user = self._stopped is process
            self._stopped = None
            self._status.running = False
            self._status.pid = None
            self._status.last_ended_at = _now_iso()
            self._status.last_exit_code = exit_code
            self._status.last_error = None if exit_code == 0 else f"Scraper exited with code {exit_code}"
            self._status.last_stopped_by_user = stopped_by_user
            self._process = None
            reason = self._status.last_reason
            log_file = Path(self._status.last_log_file) if self._status.last_log_file else None

        outcome = "OK" if exit_code == 0 else "ERR "
        message = (
            "Scraper cycle finished successfully"
            if exit_code == 0
            else f"Scraper cycle failed with exit code {exit_code}"
        )
        _append_line(
            PUBLIC_LOG_FILE,
            f"[{datetime.now().strftime('%H:%M:%S')}] [worker    ] {outcome} {message}",
        )

        if stopped_by_user:
            return
        if exit_code == 0:
            incidents.recovered("scraper.run_failed", "A scrape finished successfully.")
            incidents.recovered("scraper.spawn_failed")
        else:
            incidents.report(
                "scraper.run_failed",
                f"Scraper run failed (exit code {exit_code})",
                severity="error",
                source="worker",
                message="\n".join(_tail(log_file, 15)) or None,
                details={
                    "exit_code": exit_code,
                    "reason": reason,
                    "log_file": log_file.name if log_file else None,
                },
                # Each run that ends is one failure worth counting.
                min_interval=0,
            )

    def _status_payload_unlocked(self) -> dict[str, Any]:
        running = self._process is not None and self._process.poll() is None
        self._status.running = running
        self._status.pid = self._process.pid if running else None
        return asdict(self._status)


class WorkerRequestHandler(BaseHTTPRequestHandler):
    worker: ScrapeWorker

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_empty(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:  # noqa: N802
        if self._support("GET"):
            return

        if self.path.startswith("/api/scrape-status"):
            self._send_json(HTTPStatus.OK, self.worker.status())
            return

        if self.path.startswith("/api/health"):
            self._send_json(HTTPStatus.OK, {"ok": True, "status": self.worker.status()})
            return

        if self.path.startswith("/scraper.log"):
            if not PUBLIC_LOG_FILE.is_file():
                self._send_text(HTTPStatus.NOT_FOUND, "scraper log not found\n")
                return
            body = PUBLIC_LOG_FILE.read_text(encoding="utf-8")
            self._send_text(HTTPStatus.OK, body)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not-found"})

    def do_POST(self) -> None:  # noqa: N802
        if self._support("POST"):
            return

        if self.path.startswith("/api/auth/login"):
            payload = self._read_json_body()
            user = payload.get("username")
            pw = payload.get("password")

            admin_user, admin_pass = _resolve_admin_credentials()
            print(
                f"DEBUG: Login attempt for user '{user}'. Admin user configured: {bool(admin_user)}",
                flush=True,
            )

            if not admin_pass:
                print("DEBUG: Login blocked: admin password is not configured", flush=True)
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"ok": False, "reason": "admin-auth-not-configured"},
                )
                return

            if user == admin_user and pw == admin_pass:
                print(f"DEBUG: Login success for '{user}'", flush=True)
                # Signed and short-lived: the support endpoints for the admin check it.
                self._send_json(HTTPStatus.OK, {"ok": True, "token": tokens.sign_session(admin_pass)})
                return

            print(f"DEBUG: Login failed for '{user}'", flush=True)
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "reason": "invalid-credentials"})
            return

        if self.path.startswith("/api/scrape-cycle"):
            payload = self._read_json_body()
            reason = str(payload.get("reason") or "manual")
            priority = str(payload.get("priority") or "both")
            
            gender_flag = ""
            if priority == 'men':
                gender_flag = " --gender Men"
            elif priority == 'women':
                gender_flag = " --gender Women"

            code, response = self.worker.trigger(reason=reason, gender_flag=gender_flag)
            self._send_json(code, response)
            return

        if self.path.startswith("/api/stop-scrape"):
            code, response = self.worker.stop()
            self._send_json(code, response)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not-found"})

    def _support(self, method: str) -> bool:
        """Answers /api/support/* requests. False when the path is not one of them."""
        parts = urlsplit(self.path)
        if not parts.path.startswith(support_routes.PREFIX):
            return False
        length = int(self.headers.get("Content-Length") or 0)
        if length > support_routes.MAX_BODY_BYTES:
            # Take what is being sent (within reason) and drop it: a caller that is
            # cut off mid-upload never gets to read why it was refused.
            remaining = min(length, 8 * 1024 * 1024)
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            self.close_connection = True
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "reason": "too-large"})
            return True
        request = support_routes.Request(
            method=method,
            path=unquote(parts.path),
            query=dict(parse_qsl(parts.query)),
            headers={key.lower(): value for key, value in self.headers.items()},
            raw_body=self.rfile.read(length) if length > 0 else b"",
            client=self._client_address(),
            admin=self._admin(),
        )
        try:
            answer = support_routes.handle(request, self.worker)
        except Exception as exc:  # A bug here must not take the worker's other routes down.
            print(f"[support] {method} {parts.path} failed: {exc}", flush=True)
            answer = (HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "reason": "error"})
        if answer is None:
            return False
        self._send_json(answer[0], answer[1])
        return True

    def _admin(self) -> str | None:
        """The admin's username when the request carries the session token from login."""
        header = self.headers.get("Authorization") or ""
        if not header.lower().startswith("bearer "):
            return None
        admin_user, admin_pass = _resolve_admin_credentials()
        return admin_user if tokens.verify_session(admin_pass, header[7:].strip()) else None

    def _client_address(self) -> str:
        """The caller's address. The storefront's dev proxy runs on this machine and says who it speaks for."""
        peer = self.client_address[0]
        forwarded = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if forwarded and peer in ("127.0.0.1", "::1"):
            return forwarded
        return peer

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            raw = self.rfile.read(length).decode("utf-8")
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _send_empty(self, code: int) -> None:
        self.send_response(code)
        self._send_cors_headers()
        self.end_headers()

    def _send_text(self, code: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(code)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-Token")
        self.send_header("Cache-Control", "no-store")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local scraper worker")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--sources", default=DEFAULT_SOURCES)
    parser.add_argument("--max-products", type=int, default=0)
    parser.add_argument(
        "--no-autostart",
        action="store_true",
        help="Do not start the continuous scrape on boot; scrape only when asked to.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    worker = ScrapeWorker(sources=args.sources, max_products=args.max_products)
    WorkerRequestHandler.worker = worker

    # ON BY DEFAULT: Auto-start with a delay in a separate thread so we don't block the server
    def _delayed_trigger():
        time.sleep(10)
        print("Auto-triggering initial scraper cycle (system-boot)...", flush=True)
        worker.trigger(reason="system-boot", watch=True)
    
    if not args.no_autostart:
        threading.Thread(target=_delayed_trigger, daemon=True).start()

    # Tells the support desk when the catalogue goes stale (a no-op when it is not configured).
    freshness.start()

    server = ThreadingHTTPServer((args.host, args.port), WorkerRequestHandler)
    print(
        f"Scraper worker listening on http://{args.host}:{args.port} "
        f"(sources={args.sources}, max_products={args.max_products})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
