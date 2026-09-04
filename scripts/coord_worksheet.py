#!/usr/bin/env python3
"""
Coordinate worksheet: fill coordinates into the master file, one city at a time.

This is the tooling for Option B from the M0 findings, chosen on 4 September
2026: paste real coordinates into Europe_2026_Master_Trip_File.md rather than
geocode. The M0 audit measured 18.5% coverage overall, concentrated entirely in
Amsterdam, Ghent and Luxembourg City. Every other city, Gdansk included, has
none.

Two steps.

1. Export a worksheet for one city:

       python3 scripts/coord_worksheet.py --city Gdansk --out gdansk.csv

   Open it, and fill the `lat` and `lon` columns. Getting a pair from Google
   Maps: right-click the pin, and the first item in the menu is the
   coordinates; clicking it copies them.

2. Turn the filled worksheet into master-file rows:

       python3 scripts/coord_worksheet.py --city Gdansk --apply gdansk.csv

   This prints the replacement tracker rows. Paste them over the matching rows
   in Part 8 of the master file, then re-run the extractor as normal:

       python3 scripts/extract_trip_data.py \\
           --master /path/to/Europe_2026_Master_Trip_File.md \\
           --out data/trip-data.json

The street address is KEPT. The pair is appended in brackets, so the column
holds both, which is what "address or coordinates" allows for and what makes
the row still readable by a human. The extractor finds the pair anywhere in the
string.

Rows you leave blank are skipped, so the worksheet can be filled a few at a
time without losing work.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from coords import (
    alias_index, coords_from_text, derive_coords, fold, haversine_km,
    in_range, load_city_reference,
)

REPO = Path(__file__).resolve().parent.parent
TRIP_DATA = REPO / "data" / "trip-data.json"

TRACKER_COLUMNS = [
    "city", "neighbourhood", "name", "type", "why it made the list",
    "source and date", "confidence", "address or coordinates", "maps link",
    "opening hours", "approx cost", "priority", "best time", "notes",
]

FIELDS = ["name", "type", "priority", "neighbourhood",
          "current address or coordinates", "maps link", "lat", "lon"]

# Sanity bound when a filled row is checked back against the city centroid.
# Deliberately generous: a day trip out of Amsterdam legitimately reaches 57 km.
SANITY_KM = 200


def resolve(city_arg, reference):
    idx = alias_index(reference)
    key = fold(city_arg).strip().lower()
    if key not in idx:
        print(f"ERROR: unknown city {city_arg!r}.", file=sys.stderr)
        print("  Valid: " + ", ".join(sorted(reference)), file=sys.stderr)
        sys.exit(1)
    return idx[key]


def load_places(city):
    if not TRIP_DATA.exists():
        sys.exit(f"ERROR: {TRIP_DATA} not found")
    data = json.loads(TRIP_DATA.read_text(encoding="utf-8"))
    return [p for p in data["places"] if p.get("city") == city]


def do_export(city, places, out_path, reference):
    centroid = reference[city]
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for p in places:
            lat, lon, source, _ = derive_coords(p, centroid)
            already = source in ("tracker", "mapsLink")
            w.writerow({
                "name": p.get("name", ""),
                "type": p.get("type", ""),
                "priority": p.get("priority", ""),
                "neighbourhood": p.get("neighbourhood", ""),
                "current address or coordinates": p.get("address or coordinates", ""),
                "maps link": p.get("maps link", ""),
                # Pre-filled only where a real coordinate already exists, so a
                # centroid can never be mistaken for a filled-in answer.
                "lat": lat if already else "",
                "lon": lon if already else "",
            })

    have = sum(1 for p in places if derive_coords(p, centroid)[2] in ("tracker", "mapsLink"))
    print(f"Wrote {out_path}")
    print(f"  {len(places)} places in {city}, {have} already have coordinates, "
          f"{len(places) - have} to fill")
    print()
    print("Fill the lat and lon columns, then run:")
    print(f"  python3 scripts/coord_worksheet.py --city {city} --apply {out_path}")


def do_apply(city, places, csv_path, reference):
    by_name = {p.get("name", ""): p for p in places}
    centroid = reference[city]

    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    missing = [c for c in ("name", "lat", "lon") if rows and c not in rows[0]]
    if missing:
        sys.exit(f"ERROR: {csv_path} is missing column(s): {missing}")

    out_rows = []
    errors = []
    skipped = 0

    for r in rows:
        name = (r.get("name") or "").strip()
        lat_s = (r.get("lat") or "").strip()
        lon_s = (r.get("lon") or "").strip()

        if not lat_s and not lon_s:
            skipped += 1
            continue
        if bool(lat_s) != bool(lon_s):
            errors.append(f"{name}: one of lat/lon filled but not the other")
            continue
        if name not in by_name:
            errors.append(f"{name!r} is not a place in {city}")
            continue

        try:
            lat, lon = float(lat_s), float(lon_s)
        except ValueError:
            errors.append(f"{name}: lat/lon are not numbers ({lat_s!r}, {lon_s!r})")
            continue
        if not in_range(lat, lon):
            errors.append(f"{name}: {lat}, {lon} is out of range")
            continue

        km = haversine_km(lat, lon, centroid["lat"], centroid["lon"])
        if km > SANITY_KM:
            errors.append(
                f"{name}: {lat}, {lon} is {km:.0f} km from the {city} centroid. "
                f"Check for swapped lat/lon or a wrong sign."
            )
            continue

        place = by_name[name]
        existing = (place.get("address or coordinates") or "").strip()
        pair = f"{lat}, {lon}"

        # Keep the street address and append the pair, rather than overwriting.
        # The column is "address or coordinates"; holding both loses nothing,
        # stays readable, and the extractor finds the pair anywhere in the text.
        if coords_from_text(existing):
            new_addr = existing  # already has a pair, leave it alone
        elif existing:
            new_addr = f"{existing} ({pair})"
        else:
            new_addr = pair

        cells = []
        for col in TRACKER_COLUMNS:
            v = new_addr if col == "address or coordinates" else place.get(col, "")
            cells.append(str(v or "").replace("|", "/"))
        out_rows.append((name, km, "| " + " | ".join(cells) + " |"))

    if errors:
        print("PROBLEMS, nothing printed for these rows:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        print(file=sys.stderr)

    if not out_rows:
        print("No filled rows to apply.", file=sys.stderr)
        return 1 if errors else 0

    print(f"# {len(out_rows)} replacement tracker rows for {city}.")
    print(f"# Paste each over the row with the same place name in Part 8 of the")
    print(f"# master file, then re-run scripts/extract_trip_data.py.")
    print()
    for _, _, line in out_rows:
        print(line)
    print()
    print(f"# {len(out_rows)} rows updated, {skipped} left blank and skipped, "
          f"{len(errors)} rejected.", file=sys.stderr)
    print("# distance from city centre, as a last sanity check:", file=sys.stderr)
    for name, km, _ in sorted(out_rows, key=lambda x: -x[1]):
        print(f"#   {km:6.1f} km  {name}", file=sys.stderr)
    return 1 if errors else 0


def main():
    ap = argparse.ArgumentParser(
        description="Fill coordinates into the master file, one city at a time.")
    ap.add_argument("--city", required=True)
    ap.add_argument("--out", type=Path, help="Write a worksheet CSV here.")
    ap.add_argument("--apply", type=Path, help="Read a filled worksheet CSV.")
    args = ap.parse_args()

    if bool(args.out) == bool(args.apply):
        ap.error("give exactly one of --out or --apply")

    reference = load_city_reference()
    city = resolve(args.city, reference)
    places = load_places(city)
    if not places:
        sys.exit(f"ERROR: no places found for {city}")

    if args.out:
        do_export(city, places, args.out, reference)
        return 0
    return do_apply(city, places, args.apply, reference)


if __name__ == "__main__":
    sys.exit(main())
