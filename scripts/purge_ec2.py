import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))

from scraper.parsers.base import RawProduct
from scraper.normalize import normalize

def main():
    path = ROOT / "outputs" / "products.json"
    if not path.exists():
        print(f"File not found: {path}")
        return

    print(f"Loading {path}...")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Normalizing {len(data)} items using current Nuclear Filters...")
    
    raw_objs = []
    for d in data:
        # Strip calculated fields so normalize can re-calc or discard them
        cleaned_dict = {k: v for k, v in d.items() if k not in ["trust_score", "other_sources"]}
        try:
            p = RawProduct(**cleaned_dict)
            raw_objs.append(p)
        except Exception:
            continue

    cleaned = normalize(raw_objs)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2)

    print(f"SUCCESS: Purged database on EC2. Count: {len(data)} -> {len(cleaned)}")

if __name__ == "__main__":
    main()
