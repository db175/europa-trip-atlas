#!/usr/bin/env python3
"""
scripts/validate_my_places.py
Validator for data/my-places.json.

Usage:
  python3 scripts/validate_my_places.py data/my-places.json
"""

import json
import sys
from pathlib import Path

TRACKER_COLUMNS = [
    "city", "neighbourhood", "name", "type", "why it made the list",
    "source and date", "confidence", "address or coordinates", "maps link",
    "opening hours", "approx cost", "priority", "best time", "notes",
]

VALID_PRIORITIES = {"Must", "Nice", "If nearby"}

def load_city_names():
    ref_path = Path(__file__).parent / 'city_reference.json'
    if not ref_path.exists():
        sys.exit(f"FAIL: {ref_path} not found.")
    ref_data = json.loads(ref_path.read_text(encoding='utf-8'))
    return {c['name'] for c in ref_data}

def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('data/my-places.json')
    if not path.exists():
        print(f"FAIL: {path} does not exist", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: {path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    errors = []

    if data.get("version") != 1:
        errors.append(f"version must be 1, got {data.get('version')}")

    places = data.get("places")
    if not isinstance(places, list):
        errors.append("'places' key must be a list")
        places = []

    valid_cities = load_city_names()
    seen_ids = set()

    for i, p in enumerate(places):
        place_name = p.get("name", f"index {i}")

        # Check ID
        pid = p.get("id")
        if not pid:
            errors.append(f"place '{place_name}' missing 'id'")
        elif pid in seen_ids:
            errors.append(f"duplicate id '{pid}' in my-places.json")
        else:
            seen_ids.add(pid)

        # Check tracker columns
        missing_cols = [c for c in TRACKER_COLUMNS if c not in p]
        if missing_cols:
            errors.append(f"place '{place_name}' missing column(s): {missing_cols}")

        # Check city
        city = p.get("city")
        if city not in valid_cities:
            errors.append(f"place '{place_name}' city '{city}' not in city_reference.json")

        # Check priority
        prio = p.get("priority")
        if prio not in VALID_PRIORITIES:
            errors.append(f"place '{place_name}' priority '{prio}' invalid")

        # Check origin
        origin = p.get("origin")
        if origin != "personal":
            errors.append(f"place '{place_name}' origin must be 'personal', got '{origin}'")

        # Check coordinates if present
        lat, lon = p.get("lat"), p.get("lon")
        if lat is not None or lon is not None:
            if not isinstance(lat, (int, float)) or not (-90 <= lat <= 90):
                errors.append(f"place '{place_name}' has invalid latitude: {lat}")
            if not isinstance(lon, (int, float)) or not (-180 <= lon <= 180):
                errors.append(f"place '{place_name}' has invalid longitude: {lon}")

    if errors:
        print("VALIDATION FAILED for my-places.json:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 1

    print(f"PASS  {path}")
    print(f"  {len(places)} personal place(s) validated successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
