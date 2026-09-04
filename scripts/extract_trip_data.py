#!/usr/bin/env python3
"""
Rebuild data/trip-data.json from Europe_2026_Master_Trip_File.md.

This replaces the script the old README pointed at (`../scripts/extract_trip_data.py`),
which was never committed and which produced the data errors this repo used to ship:
45 of 406 places, 23 of 76 days, 9 of 14 fields, and 58 field-level contradictions
against the master tracker.

Design rules:
  1. The master markdown is the ONLY source of truth. Nothing is paraphrased,
     re-derived, or invented. Tracker values are copied verbatim.
  2. Every one of the 14 Section 16 columns survives into the JSON.
  3. Derived helper fields (timeBucket, costTier, lat, lon, coordSource, coordPrecision, hoursParsed)
     are ADDED alongside the raw value, never instead of it.
  4. The script asserts its own output. If the master file changes shape, this
     fails loudly rather than silently emitting a smaller file.

Usage:
    python3 scripts/extract_trip_data.py \
        --master path/to/Europe_2026_Master_Trip_File.md \
        --out data/trip-data.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

# Import opening hours parser
try:
    from scripts.parse_hours import parse_hours_str
except ImportError:
    from parse_hours import parse_hours_str

# ---------------------------------------------------------------------------
# Reference data. Loaded from scripts/city_reference.json.
# ---------------------------------------------------------------------------

def load_city_reference() -> dict[str, dict]:
    ref_file = Path(__file__).parent / "city_reference.json"
    if not ref_file.exists():
        sys.exit(f"FATAL: {ref_file} not found.")
    data = json.loads(ref_file.read_text(encoding="utf-8"))
    return {c["name"]: c for c in data}

CITIES_REF = load_city_reference()

# Fallback CITIES map for backwards compatibility
CITIES = {
    name: {"country": c["country"], "lat": c["lat"], "lon": c["lon"]}
    for name, c in CITIES_REF.items()
}

# Day stops: places passed through without sleeping there. Taken from the
# master's own day text ("Drive to Córdoba... then on to Sevilla").
DAY_STOPS = {
    "2026-10-22": ["Palma"],
    "2026-10-25": ["Córdoba"],
    "2026-10-29": ["Setenil"],
    "2026-11-01": ["Peñíscola"],
    "2026-11-10": ["Bratislava"],
}

MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}

TRIP_START = dt.date(2026, 9, 26)
TRIP_END = dt.date(2026, 12, 10)

EXPECTED_PLACES = 406
EXPECTED_DAYS = 76
EXPECTED_MUSTS = 149

TRACKER_COLUMNS = [
    "city", "neighbourhood", "name", "type", "why it made the list",
    "source and date", "confidence", "address or coordinates", "maps link",
    "opening hours", "approx cost", "priority", "best time", "notes",
]

# Coordinate regexes
RE_MAPS_AT = re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)')
RE_MAPS_3D4D = re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)')
RE_MAPS_Q = re.compile(r'[?&](?:q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)')
RE_COORDS_TXT = re.compile(r'^(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)')

# ---------------------------------------------------------------------------
# Derived-field helpers. These ADD to the raw value; they never replace it.
# ---------------------------------------------------------------------------

def extract_place_coords(address: str, maps_link: str, city_name: str):
    addr = (address or "").strip()
    link = (maps_link or "").strip()

    # 1. Direct coordinates in address field
    m = RE_COORDS_TXT.match(addr)
    if m:
        return float(m.group(1)), float(m.group(2)), "tracker", "exact"

    # 2. Extract from Google Maps URL
    for reg in (RE_MAPS_AT, RE_MAPS_3D4D, RE_MAPS_Q):
        m = reg.search(link)
        if m:
            return float(m.group(1)), float(m.group(2)), "mapsLink", "exact"

    # 3. Fallback to city centroid
    city_info = CITIES_REF.get(city_name)
    if city_info:
        return city_info["lat"], city_info["lon"], "cityCentroid", "approx"

    return None, None, "none", "approx"


def time_bucket(raw: str) -> str:
    """Collapse the tracker's 40 distinct `best time` strings into filterable
    buckets, without discarding the original."""
    v = (raw or "").strip().lower()
    if not v or v == "-":
        return "any"
    if v in ("day", "night", "weekday", "weekend"):
        return v
    if v == "day/night":
        return "day or night"
    if re.search(r"\b(sep|oct|nov|dec|mon|tue|wed|thu|fri|sat|sun|specific)\b", v):
        return "specific date"
    return "any"


def cost_tier(raw: str) -> str:
    """Bucket the tracker's 196 distinct cost strings."""
    v = (raw or "").strip().lower()
    if not v:
        return "unknown"
    if re.search(r"\b(free|eurail[- ]covered|eurail free|no charge)\b", v) or v == "0":
        return "free"
    if v == "€€€" or "€€€" in v:
        return "high"
    if v == "€€" or "€€" in v:
        return "moderate"
    if re.search(r"\b(cheap|small fee|low)\b", v) or v == "€":
        return "low"
    if re.search(r"\b(varies|vary|market prices|ticketed|ticket needed|depends)\b", v):
        return "varies"
    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", v)]
    if nums:
        lo = min(nums)
        if "huf" in v:
            lo /= 400.0
        elif "czk" in v:
            lo /= 25.0
        elif "pln" in v:
            lo /= 4.3
        elif "dkk" in v:
            lo /= 7.45
        if lo == 0:
            return "free"
        if lo < 12:
            return "low"
        if lo < 35:
            return "moderate"
        return "high"
    return "unknown"


def clean(cell: str) -> str:
    c = (cell or "").strip()
    return "" if c in ("-", "—", "–") else c


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def read_markdown_table(lines, header_predicate):
    """Return the list of data rows (as cell lists) for the first table whose
    header line satisfies `header_predicate`."""
    for i, line in enumerate(lines):
        if line.startswith("|") and header_predicate(line):
            if i + 1 >= len(lines) or not re.match(r"^\|[\s:\-|]+\|$", lines[i + 1]):
                continue
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].startswith("|"):
                rows.append([c.strip() for c in lines[j].strip("|").split("|")])
                j += 1
            return rows
    raise SystemExit("FATAL: could not locate the expected table in the master file.")


def parse_places(lines):
    rows = read_markdown_table(
        lines,
        lambda l: l.startswith("| city | neighbourhood | name | type |"),
    )
    places = []
    for cells in rows:
        if len(cells) != len(TRACKER_COLUMNS):
            raise SystemExit(
                f"FATAL: tracker row has {len(cells)} columns, expected "
                f"{len(TRACKER_COLUMNS)}: {cells[:3]}"
            )
        rec = {col: clean(val) for col, val in zip(TRACKER_COLUMNS, cells)}
        if rec["city"] == "city":
            continue

        rec["timeBucket"] = time_bucket(rec["best time"])
        rec["costTier"] = cost_tier(rec["approx cost"])

        lat, lon, src, prec = extract_place_coords(
            rec["address or coordinates"], rec["maps link"], rec["city"]
        )
        rec["lat"] = lat
        rec["lon"] = lon
        rec["coordSource"] = src
        rec["coordPrecision"] = prec
        rec["hoursParsed"] = parse_hours_str(rec["opening hours"])

        places.append(rec)
    return places


def parse_itinerary(lines):
    rows = read_markdown_table(
        lines,
        lambda l: l.startswith("| Date | Day | Base for the night |"),
    )
    itinerary = []
    for cells in rows:
        if len(cells) < 4:
            break
        date_txt, dow, base_txt, day_txt = cells[0], cells[1], cells[2], cells[3]
        m = re.match(r"(\d+)\s+(\w+)", date_txt)
        if not m:
            break
        date = dt.date(2026, MONTHS[m.group(2)], int(m.group(1)))

        heavy = "**[H]**" in day_txt
        notes = day_txt.replace("**[H]**", "").strip()

        row = {
            "date": date.isoformat(),
            "dow": dow,
            "base": base_txt,
            "baseCity": None,
            "country": None,
            "kind": "city",
            "heavy": heavy,
            "notes": notes,
            "stops": [],
            "branches": [],
        }

        if base_txt in CITIES_REF:
            row["baseCity"] = base_txt
            row["country"] = CITIES_REF[base_txt]["country"]
        elif "branch" in base_txt.lower():
            row["kind"] = "branch"
            row["branches"] = split_branches(base_txt, notes)
            row["baseCity"] = "Frankfurt"
            row["country"] = "Germany"
        elif "night train" in base_txt.lower():
            row["kind"] = "transit"
        else:
            row["kind"] = "depart"

        for stop in DAY_STOPS.get(row["date"], []):
            stop_ref = CITIES_REF.get(stop, {})
            row["stops"].append({
                "name": stop,
                "country": stop_ref.get("country", ""),
                "lat": stop_ref.get("lat"),
                "lon": stop_ref.get("lon"),
            })

        itinerary.append(row)
    return itinerary


def split_branches(base_txt, notes):
    branches = []
    for tag, city in (("A", "Dortmund"), ("B", "Frankfurt")):
        m = re.search(rf"BRANCH {tag}:\s*(.+?)(?=\s*BRANCH [AB]:|$)", notes, re.S)
        city_ref = CITIES_REF.get(city, {})
        branches.append({
            "id": tag,
            "city": city,
            "country": city_ref.get("country", ""),
            "lat": city_ref.get("lat"),
            "lon": city_ref.get("lon"),
            "notes": m.group(1).strip().rstrip(".") if m else "",
        })
    return branches


def build_route(itinerary):
    route = []
    for row in itinerary:
        city = row["baseCity"]
        if not city:
            continue
        city_ref = CITIES_REF.get(city, {})
        if route and route[-1]["city"] == city:
            route[-1]["until"] = row["date"]
            route[-1]["nights"] += 1
            continue
        route.append({
            "city": city,
            "country": city_ref.get("country", ""),
            "lat": city_ref.get("lat"),
            "lon": city_ref.get("lon"),
            "from": row["date"],
            "until": row["date"],
            "nights": 1,
        })
    return route


# ---------------------------------------------------------------------------
# Validation.
# ---------------------------------------------------------------------------

def validate(places, itinerary, route):
    errors = []

    if len(places) != EXPECTED_PLACES:
        errors.append(f"expected {EXPECTED_PLACES} places, got {len(places)}")

    musts = sum(1 for p in places if p["priority"] == "Must")
    if musts != EXPECTED_MUSTS:
        errors.append(f"expected {EXPECTED_MUSTS} Must places, got {musts}")

    if len(itinerary) != EXPECTED_DAYS:
        errors.append(f"expected {EXPECTED_DAYS} days, got {len(itinerary)}")

    seen = [dt.date.fromisoformat(r["date"]) for r in itinerary]
    if len(set(seen)) != len(seen):
        errors.append("duplicate dates in itinerary")
    cursor = TRIP_START
    while cursor <= TRIP_END:
        if cursor not in set(seen):
            errors.append(f"missing itinerary day {cursor}")
        cursor += dt.timedelta(days=1)

    for city in sorted({p["city"] for p in places}):
        if city not in CITIES_REF:
            errors.append(f"place city '{city}' has no entry in CITIES_REF")

    for p in places:
        for col in TRACKER_COLUMNS:
            if col not in p:
                errors.append(f"place '{p.get('name')}' is missing column '{col}'")
                break

    branch_days = [r for r in itinerary if r["kind"] == "branch"]
    if not branch_days:
        errors.append("no branch day found; the Dortmund/Frankfurt split was lost")
    for r in branch_days:
        if len(r["branches"]) != 2 or any(not b["notes"] for b in r["branches"]):
            errors.append(f"branch day {r['date']} did not parse both branches")

    if not route:
        errors.append("route is empty")

    return errors


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    lines = args.master.read_text(encoding="utf-8").splitlines()

    places = parse_places(lines)
    itinerary = parse_itinerary(lines)
    route = build_route(itinerary)

    errors = validate(places, itinerary, route)
    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        sys.exit(1)

    cities_used = sorted({p["city"] for p in places})
    slept_in = sorted({r["country"] for r in itinerary if r["country"]})
    visited = sorted({CITIES_REF[c]["country"] for c in cities_used} | set(slept_in))

    city_dict = {}
    for c in sorted(set(cities_used) | {r["baseCity"] for r in itinerary if r["baseCity"]} | {"Dortmund"}):
        ref = CITIES_REF[c]
        p_count = sum(1 for p in places if p["city"] == c)
        city_dict[c] = {
            "name": ref["name"],
            "slug": ref.get("slug", c.lower()),
            "country": ref["country"],
            "lat": ref["lat"],
            "lon": ref["lon"],
            "tz": ref.get("tz", "UTC"),
            "placeCount": p_count
        }

    payload = {
        "meta": {
            "generatedAt": dt.datetime.now(dt.timezone.utc)
                             .replace(microsecond=0).isoformat(),
            "source": args.master.name,
            "tripStart": TRIP_START.isoformat(),
            "tripEnd": TRIP_END.isoformat(),
            "days": len(itinerary),
            "nights": (TRIP_END - TRIP_START).days,
            "places": len(places),
            "musts": sum(1 for p in places if p["priority"] == "Must"),
            "cities": len(cities_used),
            "countriesVisited": len(visited),
            "countriesSleptIn": len(slept_in),
            "heavyDays": sum(1 for r in itinerary if r["heavy"]),
        },
        "cities": city_dict,
        "route": route,
        "places": places,
        "itinerary": itinerary,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    m = payload["meta"]
    print(f"Wrote {args.out}")
    print(f"  places   {m['places']} ({m['musts']} Must) across {m['cities']} cities")
    print(f"  days     {m['days']} ({m['heavyDays']} heavy), {m['nights']} nights")
    print(f"  route    {len(route)} legs")
    print(f"  countries {m['countriesVisited']} visited, {m['countriesSleptIn']} slept in")


if __name__ == "__main__":
    main()
