#!/usr/bin/env python3
"""Local HTTP worker for instant scraper runs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"
LOGS_DIR = OUTPUTS_DIR / "logs"
PUBLIC_LOG_FILE = ROOT / "frontend" / "public" / "scraper.log"
DEFAULT_SOURCES = "amazon,myntra,flipkart"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


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


class ScrapeWorker:
    def __init__(self, sources: str, max_products: int):
        self._sources = sources
        self._max_products = max_products
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._archive_handle = None
        self._status = WorkerStatus(sources=sources, max_products=max_products)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_payload_unlocked()

    def trigger(self, reason: str = "manual") -> tuple[int, dict[str, Any]]:
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

            command = [
                _discover_python_executable(),
                "-m",
                "scraper.collect",
                "--max-products",
                str(self._max_products),
                "--sources",
                self._sources,
                "--append-existing",
                "--stream-checkpoints",
            ]

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

            self._status.running = False
            self._status.pid = None
            self._status.last_ended_at = _now_iso()
            self._status.last_exit_code = exit_code
            self._status.last_error = None if exit_code == 0 else f"Scraper exited with code {exit_code}"
            self._process = None

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
        if self.path.startswith("/api/scrape-cycle"):
            payload = self._read_json_body()
            reason = str(payload.get("reason") or "manual")
            code, response = self.worker.trigger(reason=reason)
            self._send_json(code, response)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "reason": "not-found"})

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
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local scraper worker")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--sources", default=DEFAULT_SOURCES)
    parser.add_argument("--max-products", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    worker = ScrapeWorker(sources=args.sources, max_products=args.max_products)
    WorkerRequestHandler.worker = worker

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
