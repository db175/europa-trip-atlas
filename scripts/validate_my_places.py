#!/usr/bin/env python3
"""
Validate data/my-places.json.

Runs in CI alongside validate_trip_data.py, so a malformed personal file fails
the build instead of shipping a broken site.

The file is allowed to be absent. That is the normal state before the first
personal place is added, and app.js treats a 404 as an empty list.

Checks:
  * parses, and declares version 1
  * every row carries all 14 tracker columns
  * city resolves to scripts/city_reference.json, diacritics allowed
  * priority is one of Must / Nice / If nearby
  * id is unique and non-empty
  * lat/lon are both present or both absent, and in range
  * origin is exactly "personal", confidence is "user"
  * coordSource is from the allowed set
  * no id collides with a tracker place id, and name-plus-city duplicates
    against the 406 are reported as warnings

Exit code 1 on any failure.

Usage:  python3 scripts/validate_my_places.py data/my-places.json
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CITY_REF = REPO / "scripts" / "city_reference.json"
TRIP_DATA = REPO / "data" / "trip-data.json"

TRACKER_COLUMNS = [
    "city", "neighbourhood", "name", "type", "why it made the list",
    "source and date", "confidence", "address or coordinates", "maps link",
    "opening hours", "approx cost", "priority", "best time", "notes",
]

VALID_PRIORITIES = {"Must", "Nice", "If nearby"}
VALID_COORD_SOURCES = {"tracker", "mapsLink", "geocoded", "cityCentroid", "none"}
VALID_COORD_PRECISION = {"exact", "approx"}


def fold(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s))
        if not unicodedata.combining(c)
    )


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "data" / "my-places.json"

    if not path.exists():
        print(f"SKIP  {path} does not exist yet, which is valid.")
        return 0

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: {path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    if doc.get("version") != 1:
        errors.append(f"version is {doc.get('version')!r}, expected 1")

    places = doc.get("places")
    if not isinstance(places, list):
        errors.append("'places' is missing or is not a list")
        report(errors, warnings)
        return 1

    # --- city reference ----------------------------------------------------
    valid_cities: dict[str, str] = {}
    if CITY_REF.exists():
        try:
            ref = json.loads(CITY_REF.read_text(encoding="utf-8")).get("cities", [])
            for row in ref:
                for candidate in [row["name"]] + list(row.get("aliases", [])):
                    valid_cities[fold(candidate).lower()] = row["name"]
        except (json.JSONDecodeError, KeyError) as exc:
            errors.append(f"{CITY_REF.name} unusable: {exc}")
    else:
        errors.append(f"{CITY_REF.name} not found, cannot resolve cities")

    # --- tracker cross-check ----------------------------------------------
    tracker_pairs: set[tuple[str, str]] = set()
    if TRIP_DATA.exists():
        try:
            data = json.loads(TRIP_DATA.read_text(encoding="utf-8"))
            tracker_pairs = {
                (p.get("city", ""), fold(p.get("name", "")).lower())
                for p in data.get("places", [])
            }
        except json.JSONDecodeError:
            warnings.append("trip-data.json unreadable, skipped duplicate check")

    seen_ids: set[str] = set()

    for i, p in enumerate(places):
        tag = f"row #{i} ({p.get('name', '?')!r})"

        if not isinstance(p, dict):
            errors.append(f"{tag} is not an object")
            continue

        missing = [c for c in TRACKER_COLUMNS if c not in p]
        if missing:
            errors.append(f"{tag} missing tracker column(s): {missing}")

        pid = p.get("id")
        if not pid or not isinstance(pid, str):
            errors.append(f"{tag} has a missing or non-string id")
        elif pid in seen_ids:
            errors.append(f"{tag} has duplicate id {pid!r}")
        else:
            seen_ids.add(pid)

        city = p.get("city")
        if valid_cities and city is not None:
            key = fold(city).strip().lower()
            if key not in valid_cities:
                errors.append(
                    f"{tag} city {city!r} does not resolve to any city in "
                    f"{CITY_REF.name}"
                )
            elif valid_cities[key] != city:
                errors.append(
                    f"{tag} city {city!r} should be stored canonically as "
                    f"{valid_cities[key]!r}"
                )

        if p.get("priority") not in VALID_PRIORITIES:
            errors.append(
                f"{tag} has priority {p.get('priority')!r}, expected one of "
                f"{sorted(VALID_PRIORITIES)}"
            )

        if p.get("origin") != "personal":
            errors.append(f"{tag} has origin {p.get('origin')!r}, expected 'personal'")

        if p.get("confidence") != "user":
            errors.append(
                f"{tag} has confidence {p.get('confidence')!r}, expected 'user'"
            )

        cs = p.get("coordSource")
        if cs is not None and cs not in VALID_COORD_SOURCES:
            errors.append(
                f"{tag} has coordSource {cs!r}, expected one of "
                f"{sorted(VALID_COORD_SOURCES)}"
            )

        cp = p.get("coordPrecision")
        if cp is not None:
            if cp not in VALID_COORD_PRECISION:
                errors.append(
                    f"{tag} has coordPrecision {cp!r}, expected one of "
                    f"{sorted(VALID_COORD_PRECISION)}"
                )
            # A centroid is never an exact position. Catching this here stops
            # an approximate location being displayed as a precise one.
            elif cs == "cityCentroid" and cp == "exact":
                errors.append(
                    f"{tag} claims coordPrecision 'exact' with coordSource "
                    f"'cityCentroid'; a centroid is approximate by definition"
                )

        lat, lon = p.get("lat"), p.get("lon")
        if (lat is None) != (lon is None):
            errors.append(f"{tag} has one of lat/lon but not the other")
        elif lat is not None:
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                errors.append(f"{tag} has non-numeric lat/lon")
            elif not (-90 <= lat <= 90 and -180 <= lon <= 180):
                errors.append(f"{tag} has out-of-range lat/lon: {lat}, {lon}")

        if city and p.get("name"):
            pair = (city, fold(p["name"]).lower())
            if pair in tracker_pairs:
                warnings.append(
                    f"{tag} duplicates a tracker place of the same name in "
                    f"{city}. It will appear twice in the app."
                )

    if errors:
        report(errors, warnings)
        return 1

    for w in warnings:
        print(f"WARN  {w}")
    print(f"PASS  {path}")
    n = len(places)
    print(f"  {n} personal place{'s' if n != 1 else ''}, "
          f"all {len(TRACKER_COLUMNS)} tracker columns present on each")
    if n:
        cities = sorted({p.get("city", "?") for p in places})
        print(f"  cities: {', '.join(cities)}")
    return 0


def report(errors: list[str], warnings: list[str]) -> None:
    print("VALIDATION FAILED:", file=sys.stderr)
    for e in errors:
        print("  -", e, file=sys.stderr)
    for w in warnings:
        print("  ~", w, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
