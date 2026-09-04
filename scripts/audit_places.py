#!/usr/bin/env python3
"""
Milestone 0 audit, per handoff v2 section 13.3.

Read-only reconnaissance over data/trip-data.json. Answers the two open
factual questions in section 12 and prints the reference values the
feature design depends on.

This script NEVER writes to data/. It prints to stdout and writes one CSV
to an --out path (default /tmp/audit_places.csv).

Usage:
    python3 scripts/audit_places.py [--data data/trip-data.json]
                                    [--out /tmp/audit_places.csv]
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict

from coords import (
    COORD_PAIR, LINK_PATTERNS, SHORT_LINK_HOSTS, R_KM, coords_from_link,
    coords_from_text, fold as strip_diacritics, haversine_km,
    in_range as plausible,
)

TRACKER_COLUMNS = [
    "city", "neighbourhood", "name", "type", "why it made the list",
    "source and date", "confidence", "address or coordinates", "maps link",
    "opening hours", "approx cost", "priority", "best time", "notes",
]

COORD_SOURCES = ["tracker", "mapsLink", "shortLink", "addressOnly", "none"]


def classify(place):
    """Return (coordSource, lat, lon, detail)."""
    addr = (place.get("address or coordinates") or "").strip()
    link = (place.get("maps link") or "").strip()

    hit = coords_from_text(addr)
    if hit:
        return "tracker", hit[0], hit[1], "bare pair in address column"

    hit = coords_from_link(link)
    if hit:
        return "mapsLink", hit[0], hit[1], hit[2]

    if link and any(h in link for h in SHORT_LINK_HOSTS):
        return "shortLink", None, None, "redirect resolution required"

    if addr:
        return "addressOnly", None, None, "free text address, no coordinates"

    return "none", None, None, "no address and no usable link"


# ------------------------------------------------------- hours patterning

def hours_shape(s):
    """Collapse an opening-hours string to a coarse shape signature."""
    if s is None or not s.strip():
        return "<blank>"
    t = s.strip()
    t = re.sub(r"\d{1,2}[:.]\d{2}", "HH:MM", t)
    t = re.sub(r"(?<![\w:])\d{1,2}(?=\s*(?:am|pm|AM|PM))", "H", t)
    t = re.sub(r"(?<![\w:])\d{1,2}(?![\w:])", "N", t)
    t = re.sub(r"\s+", " ", t)
    return t


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/trip-data.json")
    ap.add_argument("--out", default="/tmp/audit_places.csv")
    ap.add_argument("--top-distance", type=int, default=20)
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as fh:
        data = json.load(fh)

    meta = data.get("meta", {})
    places = data.get("places", [])
    cities_field = data.get("cities")
    route = data.get("route", [])
    itinerary = data.get("itinerary", [])

    out = []
    P = out.append

    P("=" * 78)
    P("M0 AUDIT, europa-trip-atlas")
    P("=" * 78)
    P(f"data file      : {args.data}")
    P(f"generatedAt    : {meta.get('generatedAt')}")
    P(f"top-level keys : {', '.join(data.keys())}")
    P(f"meta.places    : {meta.get('places')}   actual len(places): {len(places)}")
    P(f"meta.cities    : {meta.get('cities')}   len(cities field): "
      f"{len(cities_field) if cities_field is not None else 'ABSENT'}")
    P(f"route legs     : {len(route)}   itinerary rows: {len(itinerary)}")
    P("")

    # --- 1. schema check -------------------------------------------------
    P("-" * 78)
    P("1. SCHEMA")
    P("-" * 78)
    keys = list(places[0].keys()) if places else []
    P(f"place keys ({len(keys)}): {', '.join(keys)}")
    missing_cols = defaultdict(int)
    for p in places:
        for c in TRACKER_COLUMNS:
            if c not in p:
                missing_cols[c] += 1
    if missing_cols:
        P("MISSING tracker columns: " + json.dumps(missing_cols))
    else:
        P("All 14 tracker columns present on all 406 rows: OK")
    for f in ("lat", "lon", "coordSource", "coordPrecision", "hoursParsed"):
        P(f"  field '{f}' present on any place: {any(f in p for p in places)}")
    P("")

    # --- 2. the city question -------------------------------------------
    P("-" * 78)
    P("2. CITIES (section 12, open question 1)")
    P("-" * 78)

    place_city_counts = Counter((p.get("city") or "").strip() for p in places)
    route_cities = []
    for leg in route:
        c = leg.get("city")
        if c and c not in route_cities:
            route_cities.append(c)
    base_cities = sorted({(r.get("baseCity") or r.get("base") or "").strip()
                          for r in itinerary} - {""})

    if isinstance(cities_field, dict):
        ref_names = sorted(cities_field.keys())
        P(f"data['cities'] is a DICT of {len(ref_names)} entries "
          f"(name -> country/lat/lon), not the array section 13.4 proposes.")
    elif isinstance(cities_field, list):
        ref_names = sorted(c.get("name", "") for c in cities_field)
        P(f"data['cities'] is a LIST of {len(ref_names)} entries.")
    else:
        ref_names = []
        P("data['cities'] absent.")

    P("")
    P(f"{'city':<22}{'places':>7}  {'in route':>9}  {'is a base':>10}  {'centroid':>9}")
    for name in ref_names:
        n = place_city_counts.get(name, 0)
        entry = cities_field[name] if isinstance(cities_field, dict) else {}
        has_centroid = plausible(entry.get("lat"), entry.get("lon"))
        P(f"{name:<22}{n:>7}  {'yes' if name in route_cities else 'no':>9}  "
          f"{'yes' if name in base_cities else 'no':>10}  "
          f"{'yes' if has_centroid else 'NO':>9}")
    P("")
    P(f"distinct cities in places[].city : {len(place_city_counts)}")
    P(f"distinct cities in route[]       : {len(route_cities)}")
    P(f"distinct base cities in itinerary: {len(base_cities)}")

    unresolved = [c for c in place_city_counts if c not in ref_names]
    P(f"places[].city values with no entry in cities: "
      f"{unresolved if unresolved else 'none'}")
    zero_place = [c for c in ref_names if place_city_counts.get(c, 0) == 0]
    P(f"cities with zero places: {zero_place if zero_place else 'none'}")

    gd = [c for c in place_city_counts
          if strip_diacritics(c).lower() == "gdansk"]
    P("")
    P(f"GDANSK CHECK: {'FOUND as ' + repr(gd[0]) if gd else 'NOT FOUND'}"
      + (f", {place_city_counts[gd[0]]} places" if gd else ""))
    P("")

    # --- 3. coordinate coverage -----------------------------------------
    P("-" * 78)
    P("3. COORDINATE COVERAGE (section 12, open question 2; decision gate 13.3)")
    P("-" * 78)

    rows = []
    src_counts = Counter()
    pattern_counts = Counter()
    per_city = defaultdict(Counter)

    for i, p in enumerate(places):
        src, lat, lon, detail = classify(p)
        src_counts[src] += 1
        if src == "mapsLink":
            pattern_counts[detail] += 1
        city = (p.get("city") or "").strip()
        per_city[city][src] += 1

        cent = cities_field.get(city) if isinstance(cities_field, dict) else None
        dist = None
        if lat is not None and cent and plausible(cent.get("lat"), cent.get("lon")):
            dist = haversine_km(lat, lon, cent["lat"], cent["lon"])

        rows.append({
            "idx": i,
            "city": city,
            "name": p.get("name", ""),
            "type": p.get("type", ""),
            "priority": p.get("priority", ""),
            "best time": p.get("best time", ""),
            "coordSource": src,
            "detail": detail,
            "lat": lat,
            "lon": lon,
            "km_from_centroid": round(dist, 3) if dist is not None else "",
            "address or coordinates": p.get("address or coordinates", ""),
            "maps link": p.get("maps link", ""),
            "opening hours": p.get("opening hours", ""),
            "hours_shape": hours_shape(p.get("opening hours")),
        })

    total = len(places)
    P(f"{'source':<14}{'count':>7}{'pct':>9}")
    for s in COORD_SOURCES:
        n = src_counts.get(s, 0)
        P(f"{s:<14}{n:>7}{100.0 * n / total:>8.1f}%")
    usable = src_counts.get("tracker", 0) + src_counts.get("mapsLink", 0)
    P("")
    P(f"OFFLINE-USABLE (tracker + mapsLink): {usable} / {total} "
      f"= {100.0 * usable / total:.1f}%")
    P(f"DECISION GATE (13.3, threshold ~90%): "
      f"{'PASS, links-only path is viable' if usable >= 0.90 * total else 'FAIL, bring numbers to user before choosing a geocoding path'}")
    if pattern_counts:
        P("")
        P("maps-link patterns that matched:")
        for k, v in pattern_counts.most_common():
            P(f"  {k:<12}{v:>5}")
    P("")
    P("per-city coverage (tracker + mapsLink):")
    P(f"{'city':<22}{'n':>5}{'usable':>8}{'pct':>8}   {'short':>6}{'addrOnly':>9}{'none':>6}")
    for city in sorted(per_city, key=lambda c: -sum(per_city[c].values())):
        c = per_city[city]
        n = sum(c.values())
        u = c.get("tracker", 0) + c.get("mapsLink", 0)
        P(f"{city:<22}{n:>5}{u:>8}{100.0 * u / n:>7.0f}%   "
          f"{c.get('shortLink', 0):>6}{c.get('addressOnly', 0):>9}{c.get('none', 0):>6}")
    P("")

    # --- 4. centroid distance outliers ----------------------------------
    P("-" * 78)
    P(f"4. TOP {args.top_distance} PLACE-TO-CENTROID DISTANCES (sets the 13.5 threshold)")
    P("-" * 78)
    far = sorted(
        (r for r in rows if r["km_from_centroid"] != ""),
        key=lambda r: -r["km_from_centroid"],
    )[:args.top_distance]
    P(f"{'km':>8}  {'city':<16}{'name':<44}{'source'}")
    for r in far:
        P(f"{r['km_from_centroid']:>8.1f}  {r['city']:<16}{r['name'][:42]:<44}{r['coordSource']}")
    P("")
    P("Every one of these is either a legitimate day trip or a parse error.")
    P("The user confirms which, and those ids go in the commented allowlist.")
    P("")

    # --- 5. taxonomies ---------------------------------------------------
    def dump(title, field, note=""):
        P("-" * 78)
        P(title)
        if note:
            P(note)
        P("-" * 78)
        c = Counter((p.get(field) if p.get(field) not in (None, "") else "<blank>")
                    for p in places)
        P(f"{len(c)} distinct values")
        for k, v in c.most_common():
            P(f"  {v:>5}  {k!r}")
        P("")

    dump("5. TYPE VALUES (reuse these for the nearby type facet, 13.8)", "type")
    dump("6. PRIORITY VALUES (13.6: unknown is a value, not a gap)", "priority")
    dump("7. BEST TIME VALUES", "best time")
    dump("8. CONFIDENCE VALUES", "confidence")
    dump("9. TIMEBUCKET (derived)", "timeBucket")

    # --- 10. hours shapes ------------------------------------------------
    P("-" * 78)
    P("10. OPENING HOURS SHAPES (fixture set for scripts/parse_hours.py, 13.7)")
    P("-" * 78)
    shapes = Counter(hours_shape(p.get("opening hours")) for p in places)
    P(f"{len(shapes)} distinct shapes across {total} places")
    P("")
    examples = {}
    for p in places:
        s = hours_shape(p.get("opening hours"))
        examples.setdefault(s, (p.get("opening hours") or "").strip())
    for k, v in shapes.most_common():
        P(f"  {v:>4}  {k!r}")
        if k != "<blank>" and examples[k] != k:
            P(f"        e.g. {examples[k]!r}")
    P("")

    # --- write CSV -------------------------------------------------------
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    P(f"per-place CSV written to {args.out}  ({len(rows)} rows)")
    P("")
    P("This script wrote nothing to data/. Nothing in the repo was modified.")

    text = "\n".join(out)
    print(text)
    return text


if __name__ == "__main__":
    main()
