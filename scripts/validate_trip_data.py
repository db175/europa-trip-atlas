#!/usr/bin/env python3
"""
Validate data/trip-data.json without needing the master markdown.

Checks invariants:
  * every calendar day of the trip is present exactly once
  * the headline counts in `meta` agree with the arrays they describe
  * every Section 16 column is present on every place
  * every referenced city has coordinates
  * coordinates are in valid range and within distance threshold from centroid
  * the 9 December branch still carries both options
  * the route keeps consecutive-run collapsing, so revisits survive

Exit code 1 on any failure, so a bad data commit cannot reach Pages.

Usage:  python3 scripts/validate_trip_data.py data/trip-data.json
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

TRACKER_COLUMNS = [
    "city", "neighbourhood", "name", "type", "why it made the list",
    "source and date", "confidence", "address or coordinates", "maps link",
    "opening hours", "approx cost", "priority", "best time", "notes",
]

VALID_PRIORITIES = {"Must", "Nice", "If nearby"}
VALID_COORD_SOURCES = {"tracker", "mapsLink", "geocoded", "cityCentroid", "none"}
VALID_COORD_PRECISION = {"exact", "approx"}
MAX_CENTROID_DIST_KM = 120.0  # Allow day trips up to 120km from base city

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/trip-data.json")
    if not path.exists():
        print(f"FAIL: {path} does not exist", file=sys.stderr)
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: {path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    for key in ("meta", "cities", "route", "places", "itinerary"):
        if key not in data:
            errors.append(f"top-level key '{key}' is missing")
    if errors:
        report(errors)
        return 1

    meta = data["meta"]
    cities = data["cities"]
    places = data["places"]
    itinerary = data["itinerary"]
    route = data["route"]

    # --- counts must match the arrays they claim to describe ---------------
    if meta.get("places") != len(places):
        errors.append(f"meta.places={meta.get('places')} but places array has {len(places)}")
    if meta.get("days") != len(itinerary):
        errors.append(f"meta.days={meta.get('days')} but itinerary has {len(itinerary)}")

    musts = sum(1 for p in places if p.get("priority") == "Must")
    if meta.get("musts") != musts:
        errors.append(f"meta.musts={meta.get('musts')} but {musts} places are Must")

    distinct_cities = {p.get("city") for p in places}
    if meta.get("cities") != len(distinct_cities):
        errors.append(
            f"meta.cities={meta.get('cities')} but places span {len(distinct_cities)}"
        )

    heavy = sum(1 for r in itinerary if r.get("heavy"))
    if meta.get("heavyDays") != heavy:
        errors.append(f"meta.heavyDays={meta.get('heavyDays')} but {heavy} days are heavy")

    # --- calendar coverage ------------------------------------------------
    try:
        start = dt.date.fromisoformat(meta["tripStart"])
        end = dt.date.fromisoformat(meta["tripEnd"])
    except (KeyError, ValueError) as exc:
        errors.append(f"meta.tripStart / meta.tripEnd unusable: {exc}")
        start = end = None

    if start and end:
        dates = []
        for r in itinerary:
            try:
                dates.append(dt.date.fromisoformat(r["date"]))
            except (KeyError, ValueError):
                errors.append(f"itinerary row has an unparseable date: {r.get('date')!r}")
        seen = set(dates)
        if len(seen) != len(dates):
            errors.append("itinerary contains duplicate dates")
        missing = []
        cursor = start
        while cursor <= end:
            if cursor not in seen:
                missing.append(cursor.isoformat())
            cursor += dt.timedelta(days=1)
        if missing:
            errors.append(
                f"{len(missing)} calendar day(s) missing from the itinerary, "
                f"first few: {', '.join(missing[:5])}"
            )
        stray = sorted(d for d in seen if not (start <= d <= end))
        if stray:
            errors.append(f"itinerary has dates outside the trip: {stray[:5]}")

    # --- every place keeps all 14 columns & new coordinate fields ---------
    for i, p in enumerate(places):
        pname = p.get("name", f"index {i}")
        missing_cols = [c for c in TRACKER_COLUMNS if c not in p]
        if missing_cols:
            errors.append(f"place '{pname}' missing column(s): {missing_cols}")
            break
        if p.get("priority") not in VALID_PRIORITIES:
            errors.append(f"place '{pname}' has invalid priority {p.get('priority')!r}")
            break

        c_src = p.get("coordSource")
        if c_src and c_src not in VALID_COORD_SOURCES:
            errors.append(f"place '{pname}' has invalid coordSource '{c_src}'")

        c_prec = p.get("coordPrecision")
        if c_prec and c_prec not in VALID_COORD_PRECISION:
            errors.append(f"place '{pname}' has invalid coordPrecision '{c_prec}'")

        lat, lon = p.get("lat"), p.get("lon")
        if lat is not None or lon is not None:
            if not isinstance(lat, (int, float)) or not (-90 <= lat <= 90):
                errors.append(f"place '{pname}' has invalid lat {lat}")
            if not isinstance(lon, (int, float)) or not (-180 <= lon <= 180):
                errors.append(f"place '{pname}' has invalid lon {lon}")

            # Check distance threshold if precision is exact and city exists
            if c_prec == "exact" and p.get("city") in cities:
                c_info = cities[p["city"]]
                if isinstance(c_info.get("lat"), (int, float)) and isinstance(c_info.get("lon"), (int, float)):
                    dist = haversine_km(lat, lon, c_info["lat"], c_info["lon"])
                    if dist > MAX_CENTROID_DIST_KM:
                        errors.append(
                            f"place '{pname}' is {dist:.1f} km from city '{p['city']}' centroid, "
                            f"exceeds threshold of {MAX_CENTROID_DIST_KM} km"
                        )

    # --- everything mappable ----------------------------------------------
    for city in sorted(distinct_cities):
        if city not in cities:
            errors.append(f"place city '{city}' has no entry in cities")
    for r in itinerary:
        base = r.get("baseCity")
        if base and base not in cities:
            errors.append(f"itinerary baseCity '{base}' has no entry in cities")

    if isinstance(cities, dict):
        for name, c in cities.items():
            if not isinstance(c.get("lat"), (int, float)) or not isinstance(c.get("lon"), (int, float)):
                errors.append(f"city '{name}' has non-numeric coordinates")

    # --- branch validation ------------------------------------------------
    branch_rows = [r for r in itinerary if r.get("kind") == "branch"]
    if not branch_rows:
        errors.append("no branch day present; the Dortmund/Frankfurt split was lost")
    for r in branch_rows:
        ids = sorted(b.get("id") for b in r.get("branches", []))
        if ids != ["A", "B"]:
            errors.append(f"branch day {r.get('date')} has branches {ids}, expected ['A', 'B']")
        for b in r.get("branches", []):
            if not b.get("notes"):
                errors.append(f"branch {b.get('id')} on {r.get('date')} has empty notes")

    # --- route validation -------------------------------------------------
    if not route:
        errors.append("route is empty")
    for a, b in zip(route, route[1:]):
        if a.get("city") == b.get("city"):
            errors.append(f"route has adjacent duplicate legs for {a.get('city')}")

    if errors:
        report(errors)
        return 1

    print(f"PASS  {path}")
    print(f"  {meta['places']} places ({meta['musts']} Must) across {meta['cities']} cities")
    print(f"  {meta['days']} days ({meta['heavyDays']} heavy), {len(route)} route legs")
    print(f"  all tracker columns & coordinate invariants verified.")
    return 0


def report(errors: list[str]) -> None:
    print("VALIDATION FAILED:", file=sys.stderr)
    for e in errors:
        print("  -", e, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
