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
  3. Derived helper fields (timeBucket, costTier) are ADDED alongside the raw
     value, never instead of it.
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

from coords import derive_coords, load_city_reference

# ---------------------------------------------------------------------------
# Reference data. Not present in the master file, so it lives here.
# Coordinates spot-checked against public gazetteer values.
# ---------------------------------------------------------------------------

# CITIES was a hardcoded table here. It is now read from
# scripts/city_reference.json, which is also what add_place.py resolves user
# input against. Two hand-maintained copies of the same 28 centroids drift
# apart the moment one is edited; this makes the JSON file the only copy.
# The values are unchanged: the reference file was seeded from this table.
CITY_REFERENCE = load_city_reference()
CITIES = {
    name: {"country": row["country"], "lat": row["lat"], "lon": row["lon"]}
    for name, row in CITY_REFERENCE.items()
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


# ---------------------------------------------------------------------------
# Derived-field helpers. These ADD to the raw value; they never replace it.
# ---------------------------------------------------------------------------

def time_bucket(raw: str) -> str:
    """Collapse the tracker's 40 distinct `best time` strings into filterable
    buckets, without discarding the original. Date-specific values become
    'specific date' so the constraint stays visible in the UI."""
    v = (raw or "").strip().lower()
    if not v or v == "-":
        return "any"
    if v in ("day", "night", "weekday", "weekend"):
        return v
    if v == "day/night":
        return "day or night"
    # Anything mentioning a month, a weekday name or the word "specific"
    # is a hard date constraint.
    if re.search(r"\b(sep|oct|nov|dec|mon|tue|wed|thu|fri|sat|sun|specific)\b", v):
        return "specific date"
    return "any"


def cost_tier(raw: str) -> str:
    """Bucket the tracker's 196 distinct cost strings. Raw string is preserved
    separately as `approx cost`."""
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
    # Try to read an actual number and bucket it in rough EUR terms.
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
            # next line must be the separator
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
        # Derived, additive, never replacing a tracker column. Coordinates are
        # read only from text the master file already holds: an explicit pair
        # in the address column, or a maps link that carries one. Nothing is
        # geocoded or guessed; a place with neither falls back to its city
        # centroid and is flagged approx so the app can say so.
        lat, lon, source, precision = derive_coords(rec, CITIES.get(rec["city"]))
        rec["lat"] = lat
        rec["lon"] = lon
        rec["coordSource"] = source
        rec["coordPrecision"] = precision
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

        if base_txt in CITIES:
            row["baseCity"] = base_txt
            row["country"] = CITIES[base_txt]["country"]
        elif "branch" in base_txt.lower():
            row["kind"] = "branch"
            row["branches"] = split_branches(base_txt, notes)
            # Branch B (Frankfurt) is the fallback that always works, so the
            # route line follows it. Branch A is drawn as a spur.
            row["baseCity"] = "Frankfurt"
            row["country"] = "Germany"
        elif "night train" in base_txt.lower():
            row["kind"] = "transit"
        else:
            row["kind"] = "depart"

        for stop in DAY_STOPS.get(row["date"], []):
            row["stops"].append({
                "name": stop,
                "country": CITIES[stop]["country"],
                "lat": CITIES[stop]["lat"],
                "lon": CITIES[stop]["lon"],
            })

        itinerary.append(row)
    return itinerary


def split_branches(base_txt, notes):
    """Pull the two 9 December branches apart so neither is silently dropped.
    The old data file kept only branch B and lost the Champions League match
    the master file calls its single most important unknown."""
    branches = []
    for tag, city in (("A", "Dortmund"), ("B", "Frankfurt")):
        m = re.search(rf"BRANCH {tag}:\s*(.+?)(?=\s*BRANCH [AB]:|$)", notes, re.S)
        branches.append({
            "id": tag,
            "city": city,
            "country": CITIES[city]["country"],
            "lat": CITIES[city]["lat"],
            "lon": CITIES[city]["lon"],
            "notes": m.group(1).strip().rstrip(".") if m else "",
        })
    return branches


def build_route(itinerary):
    """Ordered legs, collapsing only CONSECUTIVE repeats. This is what makes
    the two separate Cologne blocks both appear on the map; the old code used
    a global unique() and drew Cologne once."""
    route = []
    for row in itinerary:
        city = row["baseCity"]
        if not city:
            continue
        if route and route[-1]["city"] == city:
            route[-1]["until"] = row["date"]
            route[-1]["nights"] += 1
            continue
        route.append({
            "city": city,
            "country": CITIES[city]["country"],
            "lat": CITIES[city]["lat"],
            "lon": CITIES[city]["lon"],
            "from": row["date"],
            "until": row["date"],
            "nights": 1,
        })
    return route


# ---------------------------------------------------------------------------
# Validation. The whole point of this file.
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

    # Every calendar day between start and end must be present exactly once.
    seen = [dt.date.fromisoformat(r["date"]) for r in itinerary]
    if len(set(seen)) != len(seen):
        errors.append("duplicate dates in itinerary")
    cursor = TRIP_START
    while cursor <= TRIP_END:
        if cursor not in set(seen):
            errors.append(f"missing itinerary day {cursor}")
        cursor += dt.timedelta(days=1)

    # Every place city must be mappable.
    for city in sorted({p["city"] for p in places}):
        if city not in CITIES:
            errors.append(f"place city '{city}' has no coordinates in CITIES")

    # Every field must survive.
    for p in places:
        for col in TRACKER_COLUMNS:
            if col not in p:
                errors.append(f"place '{p.get('name')}' is missing column '{col}'")
                break

    # The 9 December branch must carry both options.
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
    visited = sorted({CITIES[c]["country"] for c in cities_used} | set(slept_in))

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
        # Kept as an object keyed by canonical name, not converted to an
        # array: nothing reads it positionally, and a name-keyed lookup is what
        # both the app and the validator want. slug and tz are new. tz matters
        # because the trip crosses 15 countries and runs through the end of EU
        # summer time on 25 October 2026, so a single UTC offset would be wrong
        # for the back half of it. placeCount counts TRACKER places only;
        # personal places are counted separately and never touch this file.
        "cities": {
            c: {
                "country": CITIES[c]["country"],
                "lat": CITIES[c]["lat"],
                "lon": CITIES[c]["lon"],
                "slug": CITY_REFERENCE[c]["slug"],
                "tz": CITY_REFERENCE[c]["tz"],
                "placeCount": sum(1 for p in places if p["city"] == c),
            }
            for c in sorted(set(cities_used) | {r["baseCity"] for r in itinerary if r["baseCity"]}
                            | {"Dortmund"})
        },
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

    exact = sum(1 for p in places if p["coordPrecision"] == "exact")
    by_source = {}
    for p in places:
        by_source[p["coordSource"]] = by_source.get(p["coordSource"], 0) + 1
    pct = 100.0 * exact / len(places) if places else 0.0
    print(f"  coords   {exact}/{len(places)} exact ({pct:.1f}%), "
          + ", ".join(f"{k} {v}" for k, v in sorted(by_source.items())))
    if pct < 100.0:
        print(f"           the remaining {len(places) - exact} fall back to a city "
              f"centroid and are shown as approximate")


if __name__ == "__main__":
    main()
