#!/usr/bin/env python3
"""Main scraping orchestrator."""

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import sys
import time
from collections import deque
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from decimal import Decimal

from scraper import log

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"
FRONTEND_PUBLIC = ROOT / "frontend" / "public"
OUTPUT_FILE = OUTPUTS_DIR / 'products.json'
MANUAL_TRIGGER_FILE = OUTPUTS_DIR / 'scrape-request.json'


def _build_parsers(sources: list[str]):
    parsers = []
    parser_factories = {
        "flipkart": lambda: __import__("scraper.parsers.flipkart", fromlist=["FlipkartParser"]).FlipkartParser(),
        "myntra": lambda: __import__("scraper.parsers.myntra", fromlist=["MyntraParser"]).MyntraParser(),
        "amazon": lambda: __import__("scraper.parsers.amazon", fromlist=["AmazonParser"]).AmazonParser(),
    }
    for source in sources:
        factory = parser_factories.get(source)
        if factory:
            parsers.append(factory())
    return parsers


async def run(
    max_products: int,
    sources: list[str],
    on_partial: Callable[[list[dict], str], None] | None = None,
) -> list[dict]:
    from scraper.normalize import normalize

    parsers = _build_parsers(sources)
    source_results = {p.__class__.__name__.replace("Parser", ""): [] for p in parsers}
    
    # CONCURRENCY LIMIT: Max 2 active browsers to protect t3.micro RAM (1GB)
    sem = asyncio.Semaphore(2)
    
    async def scrape_source(parser):
        async with sem:
            name = parser.__class__.__name__.replace("Parser", "")
            max_label = "unlimited" if max_products <= 0 else str(max_products)
            log.info(name, f"Starting parallel scrape - max {max_label}")

            def _progress(parser_products):
                if not on_partial:
                    return
                try:
                    source_results[name] = parser_products
                    current_all_raw = []
                    for s_list in source_results.values():
                        current_all_raw.extend(s_list)
                    on_partial(normalize(current_all_raw), name)
                except Exception as cb_exc:
                    log.warn("collect", f"Progress callback failed in {name}: {cb_exc}")

            try:
                raw = await parser.scrape(max_products=max_products, on_progress=_progress)
                if raw:
                    log.success(name, f"Finished! Yielded {len(raw)} raw products")
                    source_results[name] = raw
                else:
                    log.warn(name, "Finished with 0 products found")
                
                if on_partial:
                    all_raw = [item for sublist in source_results.values() for item in sublist]
                    on_partial(normalize(all_raw), name)
            except Exception as exc:
                log.error(name, f"Fatal error during scrape: {exc}")

    # START ALL SOURCES (Semaphore will queue them safely)
    await asyncio.gather(*(scrape_source(p) for p in parsers))

    all_raw_final = [item for sublist in source_results.values() for item in sublist]
    normalized = normalize(all_raw_final)
    log.info("collect", f"Parallel run complete: {len(all_raw_final)} raw -> {len(normalized)} normalized")
    return normalized


def _dedup_key(item: dict) -> str | None:
    source = str(item.get("source") or "").strip().lower()
    product_url = _normalize_product_url(item.get("product_url"))
    if source and product_url:
        return f"{source}::{product_url}"

    title = re.sub(r"\s+", " ", str(item.get("title") or "").strip().lower())
    if not source or not title:
        return None
    return f"{source}::{title[:120]}"


def _normalize_product_url(url) -> str | None:
    if not url:
        return None
    value = str(url).strip()
    if not value:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return value.rstrip("/").lower()
    if not parts.scheme or not parts.netloc:
        return value.rstrip("/").lower()
    clean_path = re.sub(r"/+", "/", parts.path or "/").rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), clean_path, "", ""))


def _consume_manual_trigger_request() -> dict | None:
    if not MANUAL_TRIGGER_FILE.is_file():
        return None
    try:
        payload = json.loads(MANUAL_TRIGGER_FILE.read_text(encoding="utf-8"))
    except Exception:
        payload = {"requested_at": None, "source": "unknown"}
    try:
        MANUAL_TRIGGER_FILE.unlink(missing_ok=True)
    except Exception as exc:
        log.warn("watch", f"Could not clear manual trigger request: {exc}")
    return payload if isinstance(payload, dict) else {"requested_at": None, "source": "unknown"}

def _load_existing_output() -> list[dict]:
    if not OUTPUT_FILE.is_file():
        return []
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as exc:
        log.error("collect", f"Could not read existing output: {exc}")
        return []


def _has_meaningful_value(value) -> bool:
    if value is None: return False
    if isinstance(value, str): return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)): return bool(value)
    return True


def _merge_records(primary: dict, secondary: dict) -> dict:
    merged = dict(primary)
    for key, value in secondary.items():
        if key not in merged or not _has_meaningful_value(merged.get(key)):
            merged[key] = value
    return merged


def _to_positive_float(value) -> float | None:
    try:
        num = float(value)
        return num if num > 0 else None
    except (TypeError, ValueError):
        return None


def _compute_discount_percent(cur: float | None, orig: float | None) -> int | None:
    if cur is None or orig is None or orig <= cur: return None
    pct = round((1 - cur / orig) * 100)
    return int(pct) if 1 <= pct <= 95 else None


def _recalc_discounts(products: list[dict]) -> list[dict]:
    for p in products:
        cur = _to_positive_float(p.get("price_current"))
        orig = _to_positive_float(p.get("price_original"))
        pct = _compute_discount_percent(cur, orig)
        if pct is None:
            p["price_original"] = None
            p["discount_percent"] = None
        else:
            p["price_current"] = cur
            p["price_original"] = orig
            p["discount_percent"] = pct
    return products


def _enforce_scope(products: list[dict]) -> list[dict]:
    from scraper.normalize import _infer_target_gender, _normalize_gender
    scoped: list[dict] = []
    dropped = 0
    for item in products:
        if not isinstance(item, dict):
            dropped += 1
            continue
        gender = _normalize_gender(item.get("target_gender"))
        if gender not in ("Men", "Women"):
            gender = _infer_target_gender(item.get("title") or "", item.get("category"))
        if gender not in ("Men", "Women"):
            dropped += 1
            continue
        row = dict(item)
        row["target_gender"] = gender
        scoped.append(row)
    if dropped: log.warn("collect", f"Scope filter dropped {dropped} rows outside Men/Women")
    return scoped


def merge_with_existing(products: list[dict]) -> list[dict]:
    existing = _load_existing_output()
    merged_map: dict[str, dict] = {}
    order: list[str] = []
    for item in products + existing:
        if not isinstance(item, dict): continue
        key = _dedup_key(item) or str(item.get("id") or "")
        if not key: continue
        if key not in merged_map:
            merged_map[key] = item
            order.append(key)
        else:
            merged_map[key] = _merge_records(merged_map[key], item)
    merged = [merged_map[k] for k in order]
    log.info("collect", f"Merge: {len(existing)} existing + {len(products)} new -> {len(merged)} total")
    return merged


def _balance_gender_sequence(products: list[dict]) -> list[dict]:
    queues = {"Men": deque(), "Women": deque(), "Other": deque()}
    for item in products:
        gender = item.get("target_gender")
        if gender in ("Men", "Women"): queues[gender].append(item)
        else: queues["Other"].append(item)
    balanced: list[dict] = []
    p_gender = "Women" if len(queues["Women"]) > len(queues["Men"]) else "Men"
    s_gender = "Men" if p_gender == "Women" else "Women"
    while queues["Men"] or queues["Women"]:
        if queues[p_gender]: balanced.append(queues[p_gender].popleft())
        if queues[s_gender]: balanced.append(queues[s_gender].popleft())
    return [*balanced, *list(queues["Other"])]


def _to_dynamo_item(item: dict) -> dict:
    new_item = {}
    for k, v in item.items():
        if isinstance(v, float): new_item[k] = Decimal(str(v))
        elif isinstance(v, dict): new_item[k] = _to_dynamo_item(v)
        elif isinstance(v, list):
            new_item[k] = [_to_dynamo_item(x) if isinstance(x, dict) else (Decimal(str(x)) if isinstance(x, float) else x) for x in v]
        elif v is None: continue
        else: new_item[k] = v
    return new_item


def save_output(products: list[dict]) -> Path:
    products = _balance_gender_sequence(products)
    products = _recalc_discounts(products)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    log.success("collect", f"Written -> {OUTPUT_FILE} ({len(products)} items)")
    if FRONTEND_PUBLIC.is_dir():
        dest = FRONTEND_PUBLIC / "products.json"
        shutil.copy2(OUTPUT_FILE, dest)
        log.success("collect", f"Mirrored -> {dest}")
    bucket_name = "ethnic-threads-showcase-ap-south-1"
    try:
        import boto3
        s3 = boto3.client('s3', region_name='ap-south-1')
        s3.upload_file(str(OUTPUT_FILE), bucket_name, "products.json", ExtraArgs={'ContentType': 'application/json', 'CacheControl': 'no-cache, no-store, must-revalidate'})
        log.success("aws", "S3 sync complete - Live Website updated")
    except Exception as e: log.error("aws", f"S3 sync failed: {e}")
    return OUTPUT_FILE


def run_once(max_products: int, sources: list[str], append_existing: bool, stream_checkpoints: bool = False) -> int:
    def _checkpoint(partial_products: list[dict], source_name: str):
        out = merge_with_existing(partial_products) if append_existing else partial_products
        save_output(_enforce_scope(out))
        log.info("collect", f"Checkpoint ({source_name}) -> {len(out)} products")
    products = asyncio.run(run(max_products, sources, on_partial=(_checkpoint if stream_checkpoints else None)))
    if not products: return 1
    out = merge_with_existing(products) if append_existing else products
    save_output(_enforce_scope(out))
    return 0


def run_watch_loop(max_products: int, sources: list[str], append_existing: bool, interval_minutes: float, max_runs: int) -> int:
    run_no = 0
    failure_streak = 0
    base_wait = max(60, int(interval_minutes * 60))
    log.banner(sources, interval_minutes, max_products, mode="watch")
    while max_runs == 0 or run_no < max_runs:
        total, used, free = shutil.disk_usage(ROOT)
        free_pct = free / total
        if free_pct < 0.05:
            log.error("watch", f"DISK SPACE CRITICAL: {free_pct:.1%} free. Stopping indefinitely.")
            break

        run_no += 1
        log.cycle_start(run_no)
        def _checkpoint(partial_products: list[dict], source_name: str):
            out = merge_with_existing(partial_products) if append_existing else partial_products
            save_output(_enforce_scope(out))
            log.info("watch", f"Checkpoint ({source_name}) -> {len(out)} products")
        try:
            products = asyncio.run(run(max_products, sources, on_partial=_checkpoint))
            if products:
                out = merge_with_existing(products) if append_existing else products
                save_output(_enforce_scope(out))
                failure_streak = 0
                wait = int(base_wait * random.uniform(0.9, 1.1))
                log.cycle_end(run_no, len(out), str(OUTPUT_FILE.name), wait)
            else:
                failure_streak = min(failure_streak + 1, 4)
                log.warn("watch", f"Cycle #{run_no} scraped 0 products")
        except Exception as exc:
            failure_streak = min(failure_streak + 1, 4)
            log.error("watch", f"Cycle #{run_no} failed: {exc}")
        if max_runs and run_no >= max_runs: break
        manual_request = _consume_manual_trigger_request()
        if manual_request: continue
        wait = int(base_wait * (2 ** failure_streak) * random.uniform(0.9, 1.2))
        log.info("watch", f"Sleeping {wait}s")
        remaining = wait
        while remaining > 0:
            if _consume_manual_trigger_request(): break
            time.sleep(min(5, remaining))
            remaining -= 5
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ethnic clothing scraper")
    parser.add_argument("--max-products", type=int, default=0)
    parser.add_argument("--sources", type=str, default="flipkart,myntra,amazon")
    parser.add_argument("--gender", type=str, choices=["Men", "Women"])
    parser.add_argument("--append-existing", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-minutes", type=float, default=10.0)
    parser.add_argument("--max-runs", type=int, default=0)
    parser.add_argument("--stream-checkpoints", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    sources = [s.strip().lower() for s in args.sources.split(",")]
    valid = {"flipkart", "myntra", "amazon"}
    sources = [s for s in sources if s in valid]
    if not sources: sys.exit(1)
    conf_log = os.environ.get("SCRAPER_LOG_FILE")
    append_log = os.environ.get("SCRAPER_LOG_APPEND") == "1"
    if conf_log: log.configure(log_file=conf_log, append=append_log)
    elif FRONTEND_PUBLIC.is_dir(): log.configure(log_file=str(FRONTEND_PUBLIC / "scraper.log"), append=append_log)
    if args.watch:
        sys.exit(run_watch_loop(args.max_products, sources, True, args.interval_minutes, args.max_runs))
    log.banner(sources, args.interval_minutes, args.max_products, mode="once")
    sys.exit(run_once(args.max_products, sources, args.append_existing, args.stream_checkpoints))


if __name__ == "__main__":
    main()
