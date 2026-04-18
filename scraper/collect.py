#!/usr/bin/env python3
"""Main scraping orchestrator.

Usage:
    python -m scraper.collect
    python -m scraper.collect --max-products 300 --sources flipkart,myntra,amazon --append-existing
    python -m scraper.collect --watch --interval-minutes 10 --append-existing
"""

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
    
    # Track raw products from each source in a thread-safe-ish way for callbacks
    source_results = {p.__class__.__name__.replace("Parser", ""): [] for p in parsers}
    
    async def scrape_source(parser):
        name = parser.__class__.__name__.replace("Parser", "")
        max_label = "unlimited" if max_products <= 0 else str(max_products)
        log.info(name, f"Starting parallel scrape - max {max_label}")

        def _progress(parser_products):
            if not on_partial:
                return
            try:
                # Update our local tracker for this source
                source_results[name] = parser_products
                
                # Merge current source's latest with all other sources' known totals
                current_all_raw = []
                for s_list in source_results.values():
                    current_all_raw.extend(s_list)
                
                on_partial(normalize(current_all_raw), name)
            except Exception as cb_exc:
                log.warn("collect", f"Progress callback failed in {name}: {cb_exc}")

        try:
            raw = await parser.scrape(max_products=max_products, on_progress=_progress)
            if raw:
                log.success(name, f"Finished! Total raw: {len(raw)}")
                source_results[name] = raw
            else:
                log.warn(name, "No products returned")
            
            # Final checkpoint for this specific source finishing
            if on_partial:
                all_raw = [item for sublist in source_results.values() for item in sublist]
                on_partial(normalize(all_raw), name)
        except Exception as exc:
            log.error(name, f"Fatal error: {exc}")

    # RUN ALL SOURCES IN PARALLEL
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
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            clean_path,
            "",
            "",
        )
    )



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
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
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
    except (TypeError, ValueError):
        return None
    return num if num > 0 else None


def _compute_discount_percent(cur: float | None, orig: float | None) -> int | None:
    if cur is None or orig is None or orig <= cur:
        return None
    pct = round((1 - cur / orig) * 100)
    if pct < 1 or pct > 95:
        return None
    return int(pct)


def _recalc_discounts(products: list[dict]) -> list[dict]:
    """Recalculate discount_percent from actual prices and suppress impossible values."""
    for p in products:
        cur = _to_positive_float(p.get("price_current"))
        orig = _to_positive_float(p.get("price_original"))
        pct = _compute_discount_percent(cur, orig)
        if pct is None:
            p["price_original"] = None
            p["discount_percent"] = None
            continue
        p["price_current"] = cur
        p["price_original"] = orig
        p["discount_percent"] = pct
    return products


def _enforce_scope(products: list[dict]) -> list[dict]:
    """Keep only Men/Women products when merging with historical snapshots."""
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

    if dropped:
        log.warn("collect", f"Scope filter dropped {dropped} rows outside Men/Women")
    return scoped


def merge_with_existing(products: list[dict]) -> list[dict]:
    existing = _load_existing_output()
    merged_map: dict[str, dict] = {}
    order: list[str] = []

    for item in products + existing:
        if not isinstance(item, dict):
            continue
        key = _dedup_key(item) or str(item.get("id") or "")
        if not key:
            continue
        if key not in merged_map:
            merged_map[key] = item
            order.append(key)
            continue
        merged_map[key] = _merge_records(merged_map[key], item)

    merged = [merged_map[k] for k in order]
    log.info(
        "collect",
        f"Merge: {len(existing)} existing + {len(products)} new -> {len(merged)} total",
    )
    return merged


def _balance_gender_sequence(products: list[dict]) -> list[dict]:
    queues = {
        "Men": deque(),
        "Women": deque(),
        "Other": deque(),
    }
    for item in products:
        gender = item.get("target_gender")
        if gender in ("Men", "Women"):
            queues[gender].append(item)
        else:
            queues["Other"].append(item)

    balanced: list[dict] = []
    primary_gender = "Women" if len(queues["Women"]) > len(queues["Men"]) else "Men"
    secondary_gender = "Men" if primary_gender == "Women" else "Women"

    while queues["Men"] or queues["Women"]:
        if queues[primary_gender]:
            balanced.append(queues[primary_gender].popleft())

        if queues[secondary_gender]:
            balanced.append(queues[secondary_gender].popleft())

    return [*balanced, *list(queues["Other"])]


def _to_dynamo_item(item: dict) -> dict:
    """Recursively convert floats to Decimal for DynamoDB."""
    new_item = {}
    for k, v in item.items():
        if isinstance(v, float):
            new_item[k] = Decimal(str(v))
        elif isinstance(v, dict):
            new_item[k] = _to_dynamo_item(v)
        elif isinstance(v, list):
            new_item[k] = [
                _to_dynamo_item(x) if isinstance(x, dict) else (Decimal(str(x)) if isinstance(x, float) else x)
                for x in v
            ]
        elif v is None:
            continue
        else:
            new_item[k] = v
    return new_item


def save_output(products: list[dict]) -> Path:
    products = _balance_gender_sequence(products)
    products = _recalc_discounts(products)
    
    # Save locally as JSON
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    log.success("collect", f"Written -> {OUTPUT_FILE}  ({len(products)} products)")

    if FRONTEND_PUBLIC.is_dir():
        dest = FRONTEND_PUBLIC / "products.json"
        shutil.copy2(OUTPUT_FILE, dest)
        log.success("collect", f"Mirrored -> {dest}")

    # Export to DynamoDB if configured
    table_name = os.environ.get("AWS_DYNAMODB_TABLE")
    if table_name:
        try:
            import boto3
            dynamodb = boto3.resource('dynamodb')
            table = dynamodb.Table(table_name)
            log.info("aws", f"Exporting {len(products)} items to DynamoDB table: {table_name}")
            with table.batch_writer() as batch:
                for product in products:
                    batch.put_item(Item=_to_dynamo_item(product))
            log.success("aws", "DynamoDB export complete")
        except Exception as e:
            log.error("aws", f"Failed to export to DynamoDB: {e}")

    # Export to S3 (Updates the Live Website)
    bucket_name = "ethnic-threads-showcase-ap-south-1"
    try:
        import boto3
        s3 = boto3.client('s3', region_name='ap-south-1')
        log.info("aws", f"Uploading latest data to S3 bucket: {bucket_name}")
        s3.upload_file(
            str(OUTPUT_FILE), 
            bucket_name, 
            "products.json",
            ExtraArgs={'ContentType': 'application/json', 'CacheControl': 'no-cache, no-store, must-revalidate'}
        )
        log.success("aws", "S3 sync complete - Website is now fresh")
    except Exception as e:
        log.error("aws", f"Failed to sync to S3: {e}")

    return OUTPUT_FILE


def run_once(
    max_products: int,
    sources: list[str],
    append_existing: bool,
    stream_checkpoints: bool = False,
) -> int:
    checkpoint = None

    if stream_checkpoints:
        def _checkpoint(partial_products: list[dict], source_name: str):
            checkpoint_output = (
                merge_with_existing(partial_products) if append_existing else partial_products
            )
            checkpoint_output = _enforce_scope(checkpoint_output)
            save_output(checkpoint_output)
            log.info(
                "collect",
                f"Checkpoint after {source_name} -> {len(checkpoint_output)} products",
            )

        checkpoint = _checkpoint

    products = asyncio.run(run(max_products, sources, on_partial=checkpoint))

    if not products:
        log.error("collect", "No products scraped. Check logs above.")
        return 1

    output_products = merge_with_existing(products) if append_existing else products
    output_products = _enforce_scope(output_products)
    save_output(output_products)
    return 0


def run_watch_loop(
    max_products: int,
    sources: list[str],
    append_existing: bool,
    interval_minutes: float,
    max_runs: int,
) -> int:
    run_no = 0
    failure_streak = 0
    base_wait_seconds = max(60, int(interval_minutes * 60))

    log.banner(sources, interval_minutes, max_products, mode="watch")

    while max_runs == 0 or run_no < max_runs:
        run_no += 1
        log.cycle_start(run_no)

        def _checkpoint(partial_products: list[dict], source_name: str):
            checkpoint_output = (
                merge_with_existing(partial_products) if append_existing else partial_products
            )
            checkpoint_output = _enforce_scope(checkpoint_output)
            save_output(checkpoint_output)
            log.info(
                "watch",
                f"Checkpoint after {source_name} -> {len(checkpoint_output)} products",
            )

        try:
            products = asyncio.run(run(max_products, sources, on_partial=_checkpoint))
            if products:
                output_products = merge_with_existing(products) if append_existing else products
                output_products = _enforce_scope(output_products)
                save_output(output_products)
                failure_streak = 0

                wait_seconds = int(base_wait_seconds * random.uniform(0.9, 1.1))
                log.cycle_end(run_no, len(output_products), str(OUTPUT_FILE.name), wait_seconds)
            else:
                failure_streak = min(failure_streak + 1, 4)
                log.warn("watch", f"Cycle #{run_no} scraped 0 products - keeping previous output")
        except KeyboardInterrupt:
            log.info("watch", "Stopped by user (Ctrl+C)")
            return 0
        except Exception as exc:
            failure_streak = min(failure_streak + 1, 4)
            log.error("watch", f"Cycle #{run_no} failed: {exc}")

        if max_runs and run_no >= max_runs:
            break

        manual_request = _consume_manual_trigger_request()
        if manual_request:
            requested_at = manual_request.get("requested_at") or "unknown"
            source = manual_request.get("source") or "unknown"
            log.info(
                "watch",
                f"Manual trigger from {source} queued at {requested_at} - starting next cycle now",
            )
            continue

        backoff_multiplier = 2 ** failure_streak
        jitter = random.uniform(0.9, 1.2)
        wait_seconds = int(base_wait_seconds * backoff_multiplier * jitter)
        log.info(
            "watch",
            f"Sleeping {wait_seconds}s"
            + (f" (backoff x{backoff_multiplier})" if failure_streak else ""),
        )

        remaining = wait_seconds
        while remaining > 0:
            manual_request = _consume_manual_trigger_request()
            if manual_request:
                requested_at = manual_request.get("requested_at") or "unknown"
                source = manual_request.get("source") or "unknown"
                log.info(
                    "watch",
                    f"Manual trigger from {source} queued at {requested_at} - interrupting sleep",
                )
                break
            sleep_chunk = min(5, remaining)
            time.sleep(sleep_chunk)
            remaining -= sleep_chunk

    log.success("watch", "All requested cycles complete.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ethnic clothing scraper")
    parser.add_argument(
        "--max-products",
        type=int,
        default=0,
        help="Max products per source; 0 means unlimited (default: 0)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="flipkart,myntra,amazon",
        help="Comma-separated sources: flipkart,myntra,amazon",
    )
    parser.add_argument(
        "--gender",
        type=str,
        choices=["Men", "Women"],
        help="Prioritize a specific gender during this scrape cycle",
    )
    parser.add_argument(
        "--append-existing",
        action="store_true",
        help="Merge new products with existing outputs/products.json",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuously in the background with interval + backoff",
    )
    parser.add_argument(
        "--interval-minutes",
        type=float,
        default=10.0,
        help="Watch mode polling interval in minutes (default: 10)",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Watch mode cycles to run; 0 = run forever",
    )
    parser.add_argument(
        "--stream-checkpoints",
        action="store_true",
        help="Write partial outputs after each successful batch in once mode",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    sources = [s.strip().lower() for s in args.sources.split(",")]
    valid = {"flipkart", "myntra", "amazon"}
    sources = [s for s in sources if s in valid]
    if not sources:
        log.error("collect", "No valid sources. Use: flipkart, myntra, amazon")
        sys.exit(1)

    # Configure file logging so the frontend terminal can show live output.
    configured_log_file = os.environ.get("SCRAPER_LOG_FILE")
    append_log = os.environ.get("SCRAPER_LOG_APPEND") == "1"
    if configured_log_file:
        log.configure(log_file=configured_log_file, append=append_log)
    elif FRONTEND_PUBLIC.is_dir():
        log.configure(log_file=str(FRONTEND_PUBLIC / "scraper.log"), append=append_log)

    append_existing = args.append_existing or args.watch

    if args.watch:
        code = run_watch_loop(
            max_products=args.max_products,
            sources=sources,
            append_existing=append_existing,
            interval_minutes=args.interval_minutes,
            max_runs=args.max_runs,
        )
        sys.exit(code)

    log.banner(sources, args.interval_minutes, args.max_products, mode="once")
    code = run_once(
        max_products=args.max_products,
        sources=sources,
        append_existing=append_existing,
        stream_checkpoints=args.stream_checkpoints,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()


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
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            clean_path,
            "",
            "",
        )
    )



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
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
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
    except (TypeError, ValueError):
        return None
    return num if num > 0 else None


def _compute_discount_percent(cur: float | None, orig: float | None) -> int | None:
    if cur is None or orig is None or orig <= cur:
        return None
    pct = round((1 - cur / orig) * 100)
    if pct < 1 or pct > 95:
        return None
    return int(pct)


def _recalc_discounts(products: list[dict]) -> list[dict]:
    """Recalculate discount_percent from actual prices and suppress impossible values."""
    for p in products:
        cur = _to_positive_float(p.get("price_current"))
        orig = _to_positive_float(p.get("price_original"))
        pct = _compute_discount_percent(cur, orig)
        if pct is None:
            p["price_original"] = None
            p["discount_percent"] = None
            continue
        p["price_current"] = cur
        p["price_original"] = orig
        p["discount_percent"] = pct
    return products


def _enforce_scope(products: list[dict]) -> list[dict]:
    """Keep only Men/Women products when merging with historical snapshots."""
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

    if dropped:
        log.warn("collect", f"Scope filter dropped {dropped} rows outside Men/Women")
    return scoped


def merge_with_existing(products: list[dict]) -> list[dict]:
    existing = _load_existing_output()
    merged_map: dict[str, dict] = {}
    order: list[str] = []

    for item in products + existing:
        if not isinstance(item, dict):
            continue
        key = _dedup_key(item) or str(item.get("id") or "")
        if not key:
            continue
        if key not in merged_map:
            merged_map[key] = item
            order.append(key)
            continue
        merged_map[key] = _merge_records(merged_map[key], item)

    merged = [merged_map[k] for k in order]
    log.info(
        "collect",
        f"Merge: {len(existing)} existing + {len(products)} new -> {len(merged)} total",
    )
    return merged


def _balance_gender_sequence(products: list[dict]) -> list[dict]:
    queues = {
        "Men": deque(),
        "Women": deque(),
        "Other": deque(),
    }
    for item in products:
        gender = item.get("target_gender")
        if gender in ("Men", "Women"):
            queues[gender].append(item)
        else:
            queues["Other"].append(item)

    balanced: list[dict] = []
    primary_gender = "Women" if len(queues["Women"]) > len(queues["Men"]) else "Men"
    secondary_gender = "Men" if primary_gender == "Women" else "Women"

    while queues["Men"] or queues["Women"]:
        if queues[primary_gender]:
            balanced.append(queues[primary_gender].popleft())

        if queues[secondary_gender]:
            balanced.append(queues[secondary_gender].popleft())

    return [*balanced, *list(queues["Other"])]


def _to_dynamo_item(item: dict) -> dict:
    """Recursively convert floats to Decimal for DynamoDB."""
    new_item = {}
    for k, v in item.items():
        if isinstance(v, float):
            new_item[k] = Decimal(str(v))
        elif isinstance(v, dict):
            new_item[k] = _to_dynamo_item(v)
        elif isinstance(v, list):
            new_item[k] = [
                _to_dynamo_item(x) if isinstance(x, dict) else (Decimal(str(x)) if isinstance(x, float) else x)
                for x in v
            ]
        elif v is None:
            continue
        else:
            new_item[k] = v
    return new_item


def save_output(products: list[dict]) -> Path:
    products = _balance_gender_sequence(products)
    products = _recalc_discounts(products)
    
    # Save locally as JSON
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    log.success("collect", f"Written -> {OUTPUT_FILE}  ({len(products)} products)")

    if FRONTEND_PUBLIC.is_dir():
        dest = FRONTEND_PUBLIC / "products.json"
        shutil.copy2(OUTPUT_FILE, dest)
        log.success("collect", f"Mirrored -> {dest}")

    # Export to DynamoDB if configured
    table_name = os.environ.get("AWS_DYNAMODB_TABLE")
    if table_name:
        try:
            import boto3
            dynamodb = boto3.resource('dynamodb')
            table = dynamodb.Table(table_name)
            log.info("aws", f"Exporting {len(products)} items to DynamoDB table: {table_name}")
            with table.batch_writer() as batch:
                for product in products:
                    batch.put_item(Item=_to_dynamo_item(product))
            log.success("aws", "DynamoDB export complete")
        except Exception as e:
            log.error("aws", f"Failed to export to DynamoDB: {e}")

    #!/usr/bin/env python3
    """Main scraping orchestrator.

    Usage:
        python -m scraper.collect
        python -m scraper.collect --max-products 300 --sources flipkart,myntra,amazon --append-existing
        python -m scraper.collect --watch --interval-minutes 10 --append-existing
    """

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
        raw_all = []

        for parser in parsers:
            name = parser.__class__.__name__.replace("Parser", "")
            max_label = "unlimited" if max_products <= 0 else str(max_products)
            log.info(name, f"Starting - max {max_label} products")

            def _progress(parser_products):
                if not on_partial:
                    return
                try:
                    combined = [*raw_all, *parser_products]
                    on_partial(normalize(combined), name)
                except Exception as cb_exc:
                    log.warn("collect", f"Progress callback failed in {name}: {cb_exc}")

            try:
                raw = await parser.scrape(max_products=max_products, on_progress=_progress)
                if raw:
                    log.success(name, f"Scraped {len(raw)} raw products")
                else:
                    log.warn(name, "No products returned")
                raw_all.extend(raw)
                if on_partial:
                    try:
                        on_partial(normalize(raw_all), name)
                    except Exception as cb_exc:
                        log.warn("collect", f"Checkpoint callback failed after {name}: {cb_exc}")
            except Exception as exc:
                log.error(name, f"Fatal: {exc}")

        normalized = normalize(raw_all)
        log.info("collect", f"{len(raw_all)} raw -> {len(normalized)} after normalize/dedup/filter")
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
        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                clean_path,
                "",
                "",
            )
        )



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
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
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
        except (TypeError, ValueError):
            return None
        return num if num > 0 else None


    def _compute_discount_percent(cur: float | None, orig: float | None) -> int | None:
        if cur is None or orig is None or orig <= cur:
            return None
        pct = round((1 - cur / orig) * 100)
        if pct < 1 or pct > 95:
            return None
        return int(pct)


    def _recalc_discounts(products: list[dict]) -> list[dict]:
        """Recalculate discount_percent from actual prices and suppress impossible values."""
        for p in products:
            cur = _to_positive_float(p.get("price_current"))
            orig = _to_positive_float(p.get("price_original"))
            pct = _compute_discount_percent(cur, orig)
            if pct is None:
                p["price_original"] = None
                p["discount_percent"] = None
                continue
            p["price_current"] = cur
            p["price_original"] = orig
            p["discount_percent"] = pct
        return products


    def _enforce_scope(products: list[dict]) -> list[dict]:
        """Keep only Men/Women products when merging with historical snapshots."""
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

        if dropped:
            log.warn("collect", f"Scope filter dropped {dropped} rows outside Men/Women")
        return scoped


    def merge_with_existing(products: list[dict]) -> list[dict]:
        existing = _load_existing_output()
        merged_map: dict[str, dict] = {}
        order: list[str] = []

        for item in products + existing:
            if not isinstance(item, dict):
                continue
            key = _dedup_key(item) or str(item.get("id") or "")
            if not key:
                continue
            if key not in merged_map:
                merged_map[key] = item
                order.append(key)
                continue
            merged_map[key] = _merge_records(merged_map[key], item)

        merged = [merged_map[k] for k in order]
        log.info(
            "collect",
            f"Merge: {len(existing)} existing + {len(products)} new -> {len(merged)} total",
        )
        return merged


    def _balance_gender_sequence(products: list[dict]) -> list[dict]:
        queues = {
            "Men": deque(),
            "Women": deque(),
            "Other": deque(),
        }
        for item in products:
            gender = item.get("target_gender")
            if gender in ("Men", "Women"):
                queues[gender].append(item)
            else:
                queues["Other"].append(item)

        balanced: list[dict] = []
        primary_gender = "Women" if len(queues["Women"]) > len(queues["Men"]) else "Men"
        secondary_gender = "Men" if primary_gender == "Women" else "Women"

        while queues["Men"] or queues["Women"]:
            if queues[primary_gender]:
                balanced.append(queues[primary_gender].popleft())

            if queues[secondary_gender]:
                balanced.append(queues[secondary_gender].popleft())

        return [*balanced, *list(queues["Other"])]


    def _to_dynamo_item(item: dict) -> dict:
        """Recursively convert floats to Decimal for DynamoDB."""
        new_item = {}
        for k, v in item.items():
            if isinstance(v, float):
                new_item[k] = Decimal(str(v))
            elif isinstance(v, dict):
                new_item[k] = _to_dynamo_item(v)
            elif isinstance(v, list):
                new_item[k] = [
                    _to_dynamo_item(x) if isinstance(x, dict) else (Decimal(str(x)) if isinstance(x, float) else x)
                    for x in v
                ]
            elif v is None:
                continue
            else:
                new_item[k] = v
        return new_item


    def save_output(products: list[dict]) -> Path:
        products = _balance_gender_sequence(products)
        products = _recalc_discounts(products)

        # Save locally as JSON
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        log.success("collect", f"Written -> {OUTPUT_FILE}  ({len(products)} products)")

        if FRONTEND_PUBLIC.is_dir():
            dest = FRONTEND_PUBLIC / "products.json"
            shutil.copy2(OUTPUT_FILE, dest)
            log.success("collect", f"Mirrored -> {dest}")

        # Export to DynamoDB if configured
        table_name = os.environ.get("AWS_DYNAMODB_TABLE")
        if table_name:
            try:
                import boto3
                dynamodb = boto3.resource('dynamodb')
                table = dynamodb.Table(table_name)
                log.info("aws", f"Exporting {len(products)} items to DynamoDB table: {table_name}")
                with table.batch_writer() as batch:
                    for product in products:
                        batch.put_item(Item=_to_dynamo_item(product))
                log.success("aws", "DynamoDB export complete")
            except Exception as e:
                log.error("aws", f"Failed to export to DynamoDB: {e}")

        # Export to S3 (Updates the Live Website)
        bucket_name = "ethnic-threads-showcase-ap-south-1"
        try:
            import boto3
            s3 = boto3.client('s3', region_name='ap-south-1')
            log.info("aws", f"Uploading latest data to S3 bucket: {bucket_name}")
            s3.upload_file(
                str(OUTPUT_FILE), 
                bucket_name, 
                "products.json",
                ExtraArgs={'ContentType': 'application/json', 'CacheControl': 'no-cache, no-store, must-revalidate'}
            )
            log.success("aws", "S3 sync complete - Website is now fresh")
        except Exception as e:
            log.error("aws", f"Failed to sync to S3: {e}")

        return OUTPUT_FILE


    def run_once(
        max_products: int,
        sources: list[str],
        append_existing: bool,
        stream_checkpoints: bool = False,
    ) -> int:
        checkpoint = None

        if stream_checkpoints:
            def _checkpoint(partial_products: list[dict], source_name: str):
                checkpoint_output = (
                    merge_with_existing(partial_products) if append_existing else partial_products
                )
                checkpoint_output = _enforce_scope(checkpoint_output)
                save_output(checkpoint_output)
                log.info(
                    "collect",
                    f"Checkpoint after {source_name} -> {len(checkpoint_output)} products",
                )

            checkpoint = _checkpoint

        products = asyncio.run(run(max_products, sources, on_partial=checkpoint))

        if not products:
            log.error("collect", "No products scraped. Check logs above.")
            return 1

        output_products = merge_with_existing(products) if append_existing else products
        output_products = _enforce_scope(output_products)
        save_output(output_products)
        return 0


    def run_watch_loop(
        max_products: int,
        sources: list[str],
        append_existing: bool,
        interval_minutes: float,
        max_runs: int,
    ) -> int:
        run_no = 0
        failure_streak = 0
        base_wait_seconds = max(60, int(interval_minutes * 60))

        log.banner(sources, interval_minutes, max_products, mode="watch")

        while max_runs == 0 or run_no < max_runs:
            run_no += 1
            log.cycle_start(run_no)

            def _checkpoint(partial_products: list[dict], source_name: str):
                checkpoint_output = (
                    merge_with_existing(partial_products) if append_existing else partial_products
                )
                checkpoint_output = _enforce_scope(checkpoint_output)
                save_output(checkpoint_output)
                log.info(
                    "watch",
                    f"Checkpoint after {source_name} -> {len(checkpoint_output)} products",
                )

            try:
                products = asyncio.run(run(max_products, sources, on_partial=_checkpoint))
                if products:
                    output_products = merge_with_existing(products) if append_existing else products
                    output_products = _enforce_scope(output_products)
                    save_output(output_products)
                    failure_streak = 0

                    wait_seconds = int(base_wait_seconds * random.uniform(0.9, 1.1))
                    log.cycle_end(run_no, len(output_products), str(OUTPUT_FILE.name), wait_seconds)
                else:
                    failure_streak = min(failure_streak + 1, 4)
                    log.warn("watch", f"Cycle #{run_no} scraped 0 products - keeping previous output")
            except KeyboardInterrupt:
                log.info("watch", "Stopped by user (Ctrl+C)")
                return 0
            except Exception as exc:
                failure_streak = min(failure_streak + 1, 4)
                log.error("watch", f"Cycle #{run_no} failed: {exc}")

            if max_runs and run_no >= max_runs:
                break

            manual_request = _consume_manual_trigger_request()
            if manual_request:
                requested_at = manual_request.get("requested_at") or "unknown"
                source = manual_request.get("source") or "unknown"
                log.info(
                    "watch",
                    f"Manual trigger from {source} queued at {requested_at} - starting next cycle now",
                )
                continue

            backoff_multiplier = 2 ** failure_streak
            jitter = random.uniform(0.9, 1.2)
            wait_seconds = int(base_wait_seconds * backoff_multiplier * jitter)
            log.info(
                "watch",
                f"Sleeping {wait_seconds}s"
                + (f" (backoff x{backoff_multiplier})" if failure_streak else ""),
            )

            remaining = wait_seconds
            while remaining > 0:
                manual_request = _consume_manual_trigger_request()
                if manual_request:
                    requested_at = manual_request.get("requested_at") or "unknown"
                    source = manual_request.get("source") or "unknown"
                    log.info(
                        "watch",
                        f"Manual trigger from {source} queued at {requested_at} - interrupting sleep",
                    )
                    break
                sleep_chunk = min(5, remaining)
                time.sleep(sleep_chunk)
                remaining -= sleep_chunk

        log.success("watch", "All requested cycles complete.")
        return 0


    def parse_args() -> argparse.Namespace:
        parser = argparse.ArgumentParser(description="Ethnic clothing scraper")
        parser.add_argument(
            "--max-products",
            type=int,
            default=0,
            help="Max products per source; 0 means unlimited (default: 0)",
        )
        parser.add_argument(
            "--sources",
            type=str,
            default="flipkart,myntra,amazon",
            help="Comma-separated sources: flipkart,myntra,amazon",
        )
        parser.add_argument(
            "--gender",
            type=str,
            choices=["Men", "Women"],
            help="Prioritize a specific gender during this scrape cycle",
        )
        parser.add_argument(
            "--append-existing",
            action="store_true",
            help="Merge new products with existing outputs/products.json",
        )
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Run continuously in the background with interval + backoff",
        )
        parser.add_argument(
            "--interval-minutes",
            type=float,
            default=10.0,
            help="Watch mode polling interval in minutes (default: 10)",
        )
        parser.add_argument(
            "--max-runs",
            type=int,
            default=0,
            help="Watch mode cycles to run; 0 = run forever",
        )
        parser.add_argument(
            "--stream-checkpoints",
            action="store_true",
            help="Write partial outputs after each successful batch in once mode",
        )
        return parser.parse_args()


    def main():
        args = parse_args()

        sources = [s.strip().lower() for s in args.sources.split(",")]
        valid = {"flipkart", "myntra", "amazon"}
        sources = [s for s in sources if s in valid]
        if not sources:
            log.error("collect", "No valid sources. Use: flipkart, myntra, amazon")
            sys.exit(1)

        # Configure file logging so the frontend terminal can show live output.
        configured_log_file = os.environ.get("SCRAPER_LOG_FILE")
        append_log = os.environ.get("SCRAPER_LOG_APPEND") == "1"
        if configured_log_file:
            log.configure(log_file=configured_log_file, append=append_log)
        elif FRONTEND_PUBLIC.is_dir():
            log.configure(log_file=str(FRONTEND_PUBLIC / "scraper.log"), append=append_log)

        append_existing = args.append_existing or args.watch

        if args.watch:
            code = run_watch_loop(
                max_products=args.max_products,
                sources=sources,
                append_existing=append_existing,
                interval_minutes=args.interval_minutes,
                max_runs=args.max_runs,
            )
            sys.exit(code)

        log.banner(sources, args.interval_minutes, args.max_products, mode="once")
        code = run_once(
            max_products=args.max_products,
            sources=sources,
            append_existing=append_existing,
            stream_checkpoints=args.stream_checkpoints,
        )
        sys.exit(code)


    if __name__ == "__main__":
        main()


    return OUTPUT_FILE


def run_once(
    max_products: int,
    sources: list[str],
    append_existing: bool,
    stream_checkpoints: bool = False,
) -> int:
    checkpoint = None

    if stream_checkpoints:
        def _checkpoint(partial_products: list[dict], source_name: str):
            checkpoint_output = (
                merge_with_existing(partial_products) if append_existing else partial_products
            )
            checkpoint_output = _enforce_scope(checkpoint_output)
            save_output(checkpoint_output)
            log.info(
                "collect",
                f"Checkpoint after {source_name} -> {len(checkpoint_output)} products",
            )

        checkpoint = _checkpoint

    products = asyncio.run(run(max_products, sources, on_partial=checkpoint))

    if not products:
        log.error("collect", "No products scraped. Check logs above.")
        return 1

    output_products = merge_with_existing(products) if append_existing else products
    output_products = _enforce_scope(output_products)
    save_output(output_products)
    return 0


def run_watch_loop(
    max_products: int,
    sources: list[str],
    append_existing: bool,
    interval_minutes: float,
    max_runs: int,
) -> int:
    run_no = 0
    failure_streak = 0
    base_wait_seconds = max(60, int(interval_minutes * 60))

    log.banner(sources, interval_minutes, max_products, mode="watch")

    while max_runs == 0 or run_no < max_runs:
        run_no += 1
        log.cycle_start(run_no)

        def _checkpoint(partial_products: list[dict], source_name: str):
            checkpoint_output = (
                merge_with_existing(partial_products) if append_existing else partial_products
            )
            checkpoint_output = _enforce_scope(checkpoint_output)
            save_output(checkpoint_output)
            log.info(
                "watch",
                f"Checkpoint after {source_name} -> {len(checkpoint_output)} products",
            )

        try:
            products = asyncio.run(run(max_products, sources, on_partial=_checkpoint))
            if products:
                output_products = merge_with_existing(products) if append_existing else products
                output_products = _enforce_scope(output_products)
                save_output(output_products)
                failure_streak = 0

                wait_seconds = int(base_wait_seconds * random.uniform(0.9, 1.1))
                log.cycle_end(run_no, len(output_products), str(OUTPUT_FILE.name), wait_seconds)
            else:
                failure_streak = min(failure_streak + 1, 4)
                log.warn("watch", f"Cycle #{run_no} scraped 0 products - keeping previous output")
        except KeyboardInterrupt:
            log.info("watch", "Stopped by user (Ctrl+C)")
            return 0
        except Exception as exc:
            failure_streak = min(failure_streak + 1, 4)
            log.error("watch", f"Cycle #{run_no} failed: {exc}")

        if max_runs and run_no >= max_runs:
            break

        manual_request = _consume_manual_trigger_request()
        if manual_request:
            requested_at = manual_request.get("requested_at") or "unknown"
            source = manual_request.get("source") or "unknown"
            log.info(
                "watch",
                f"Manual trigger from {source} queued at {requested_at} - starting next cycle now",
            )
            continue

        backoff_multiplier = 2 ** failure_streak
        jitter = random.uniform(0.9, 1.2)
        wait_seconds = int(base_wait_seconds * backoff_multiplier * jitter)
        log.info(
            "watch",
            f"Sleeping {wait_seconds}s"
            + (f" (backoff x{backoff_multiplier})" if failure_streak else ""),
        )

        remaining = wait_seconds
        while remaining > 0:
            manual_request = _consume_manual_trigger_request()
            if manual_request:
                requested_at = manual_request.get("requested_at") or "unknown"
                source = manual_request.get("source") or "unknown"
                log.info(
                    "watch",
                    f"Manual trigger from {source} queued at {requested_at} - interrupting sleep",
                )
                break
            sleep_chunk = min(5, remaining)
            time.sleep(sleep_chunk)
            remaining -= sleep_chunk

    log.success("watch", "All requested cycles complete.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ethnic clothing scraper")
    parser.add_argument(
        "--max-products",
        type=int,
        default=0,
        help="Max products per source; 0 means unlimited (default: 0)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="flipkart,myntra,amazon",
        help="Comma-separated sources: flipkart,myntra,amazon",
    )
    parser.add_argument(
        "--gender",
        type=str,
        choices=["Men", "Women"],
        help="Prioritize a specific gender during this scrape cycle",
    )
    parser.add_argument(
        "--append-existing",
        action="store_true",
        help="Merge new products with existing outputs/products.json",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuously in the background with interval + backoff",
    )
    parser.add_argument(
        "--interval-minutes",
        type=float,
        default=10.0,
        help="Watch mode polling interval in minutes (default: 10)",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Watch mode cycles to run; 0 = run forever",
    )
    parser.add_argument(
        "--stream-checkpoints",
        action="store_true",
        help="Write partial outputs after each successful batch in once mode",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    sources = [s.strip().lower() for s in args.sources.split(",")]
    valid = {"flipkart", "myntra", "amazon"}
    sources = [s for s in sources if s in valid]
    if not sources:
        log.error("collect", "No valid sources. Use: flipkart, myntra, amazon")
        sys.exit(1)

    # Configure file logging so the frontend terminal can show live output.
    configured_log_file = os.environ.get("SCRAPER_LOG_FILE")
    append_log = os.environ.get("SCRAPER_LOG_APPEND") == "1"
    if configured_log_file:
        log.configure(log_file=configured_log_file, append=append_log)
    elif FRONTEND_PUBLIC.is_dir():
        log.configure(log_file=str(FRONTEND_PUBLIC / "scraper.log"), append=append_log)

    append_existing = args.append_existing or args.watch

    if args.watch:
        code = run_watch_loop(
            max_products=args.max_products,
            sources=sources,
            append_existing=append_existing,
            interval_minutes=args.interval_minutes,
            max_runs=args.max_runs,
        )
        sys.exit(code)

    log.banner(sources, args.interval_minutes, args.max_products, mode="once")
    code = run_once(
        max_products=args.max_products,
        sources=sources,
        append_existing=append_existing,
        stream_checkpoints=args.stream_checkpoints,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
