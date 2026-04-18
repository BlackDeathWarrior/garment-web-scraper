"""
Lightweight terminal logger for the scraper.

Outputs timestamped, color-coded lines to stdout/stderr.
Also optionally writes plain-text lines to a log file (for the frontend terminal).
All strings are pure ASCII to avoid cp1252 encode errors on Windows.
"""

import os
import sys
import threading
from datetime import datetime

# ANSI escape codes
_C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "dim":    "\033[2m",
    "green":  "\033[92m",
    "red":    "\033[91m",
    "yellow": "\033[93m",
    "cyan":   "\033[96m",
    "blue":   "\033[94m",
    "gray":   "\033[90m",
    "white":  "\033[97m",
}

_USE_COLOR = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False

# File logging state
_log_file_path: str | None = None
_log_lock = threading.Lock()
_MAX_LOG_LINES = 500
_line_counter = 0


def configure(log_file: str | None = None, append: bool = False) -> None:
    """Set the plain-text log file path. Call once at startup."""
    global _log_file_path
    _log_file_path = log_file
    if not log_file:
        return
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        mode = "a" if append else "w"
        with open(log_file, mode, encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] [system    ] INFO Scraper session started\n")
    except Exception:
        pass


def _write_file(plain: str) -> None:
    global _line_counter
    if not _log_file_path:
        return
    with _log_lock:
        try:
            with open(_log_file_path, "a", encoding="utf-8") as f:
                f.write(plain + "\n")
            _line_counter += 1
            # Trim file every 100 lines to stay under _MAX_LOG_LINES
            if _line_counter % 100 == 0:
                with open(_log_file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                if len(lines) > _MAX_LOG_LINES:
                    with open(_log_file_path, "w", encoding="utf-8") as f:
                        f.writelines(lines[-_MAX_LOG_LINES:])
        except Exception:
            pass


def _c(color: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"{_C.get(color, '')}{text}{_C['reset']}"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _tag(source: str) -> str:
    return _c("cyan", f"[{_ts()}]") + " " + _c("blue", f"[{source:<10}]")


def _plain_tag(source: str) -> str:
    return f"[{_ts()}] [{source:<10}]"


# ---- Public API -----------------------------------------------------------


def info(source: str, msg: str) -> None:
    print(f"{_tag(source)} {msg}", flush=True)
    _write_file(f"{_plain_tag(source)} INFO {msg}")


def success(source: str, msg: str) -> None:
    print(f"{_tag(source)} {_c('green', 'OK  ')} {msg}", flush=True)
    _write_file(f"{_plain_tag(source)} OK   {msg}")


def warn(source: str, msg: str) -> None:
    print(f"{_tag(source)} {_c('yellow', 'WARN')} {msg}", flush=True)
    _write_file(f"{_plain_tag(source)} WARN {msg}")


def error(source: str, msg: str) -> None:
    print(f"{_tag(source)} {_c('red', 'ERR ')} {msg}", file=sys.stderr, flush=True)
    _write_file(f"{_plain_tag(source)} ERR  {msg}")


def scrape_batch(source: str, query: str, page: int, count: int, total: int) -> None:
    q_display = _c("white", f"'{query}'")
    if count == 0:
        warn(source, f"'{query}' p{page} - no products found")
        return
    print(
        f"{_tag(source)} {_c('green', 'OK  ')} {q_display} p{page}"
        f" -> {_c('green', f'+{count}')} products"
        f"  {_c('dim', f'(total: {total})')}",
        flush=True,
    )
    _write_file(
        f"{_plain_tag(source)} OK   '{query}' p{page} -> +{count} products (total: {total})"
    )


def rule(width: int = 60, double: bool = False) -> None:
    char = "=" if double else "-"
    line = char * width
    print(_c("gray", line), flush=True)
    _write_file(line)


def banner(sources: list[str], interval_m: float, max_products: int, mode: str = "watch") -> None:
    rule(double=True)
    hdr = "  Ethnic Threads -- Scraper"
    print(_c("bold", hdr), flush=True)
    _write_file(hdr)
    src_str = "  ".join(s.title() for s in sources)
    src_line = f"  Sources  : {src_str}"
    print(_c("dim", src_line), flush=True)
    _write_file(src_line)
    max_label = "Unlimited" if max_products <= 0 else str(max_products)
    if mode == "watch":
        int_line = f"  Interval : {interval_m} min   Max/source : {max_label}"
        print(_c("dim", int_line), flush=True)
        _write_file(int_line)
        stop_line = "  Press Ctrl+C to stop"
        print(_c("dim", stop_line), flush=True)
        _write_file(stop_line)
    else:
        mp_line = f"  Max/source : {max_label}"
        print(_c("dim", mp_line), flush=True)
        _write_file(mp_line)
    rule(double=True)


def cycle_start(run_no: int) -> None:
    rule()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"  Cycle #{run_no}  {ts}"
    print(_c("bold", f"  Cycle #{run_no}") + "  " + _c("dim", ts), flush=True)
    _write_file(line)
    rule()


def cycle_end(run_no: int, count: int, path: str, next_in_s: int) -> None:
    rule()
    success("collect", f"Cycle #{run_no} done - {count} products -> {path}")
    info("watch", f"Next cycle in {next_in_s}s ({next_in_s // 60}m {next_in_s % 60}s)")
    rule()
