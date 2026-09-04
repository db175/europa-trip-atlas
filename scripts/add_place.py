#!/usr/bin/env python3
"""
Add a personal place to data/my-places.json.

This is the whole of "add it very easily": one command, validated, no manual
JSON editing, and no extractor run, because data/trip-data.json is not touched.

    python3 scripts/add_place.py \
        --city "Gdansk" \
        --name "Example Place" \
        --type food \
        --why "Recommended by a friend who lived there" \
        --priority Must

Then:

    git add data/my-places.json
    git commit -m "Add place: Example Place, Gdansk"
    git push

Notes on the deliberate limits here:

  * The city must already be one of the cities in scripts/city_reference.json.
    An unknown city is a hard error listing the valid names, rather than a
    silent new city that would then fail the trip-data validator's
    "every place city has a cities entry" check.
  * Coordinates are never invented. They come from --lat/--lon, or from a
    coordinate pair inside --maps, or they fall back to the city centroid,
    and the fallback is announced on stdout.
  * The 14 tracker columns are always all present, in tracker order, so a row
    can be pasted into the master file later with no translation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from coords import (
    COORD_PAIR, coords_from_text, coords_from_link, fold, in_range, slugify,
)

REPO = Path(__file__).resolve().parent.parent
CITY_REF = REPO / "scripts" / "city_reference.json"
MY_PLACES = REPO / "data" / "my-places.json"
TRIP_DATA = REPO / "data" / "trip-data.json"

# Tracker order, from Section 16 of the master file. Order is preserved on
# write so a row reads the same as a master-file row.
TRACKER_COLUMNS = [
    "city", "neighbourhood", "name", "type", "why it made the list",
    "source and date", "confidence", "address or coordinates", "maps link",
    "opening hours", "approx cost", "priority", "best time", "notes",
]

VALID_PRIORITIES = ["Must", "Nice", "If nearby"]

def die(msg: str) -> "NoReturn":  # noqa: F821
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_city_reference() -> list[dict]:
    if not CITY_REF.exists():
        die(f"{CITY_REF} not found")
    try:
        doc = json.loads(CITY_REF.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"{CITY_REF} is not valid JSON: {exc}")
    return doc.get("cities", [])


def resolve_city(raw: str, ref: list[dict]) -> dict:
    """Diacritic-insensitive lookup across canonical names and aliases."""
    target = fold(raw).strip().lower()
    for row in ref:
        candidates = [row["name"]] + list(row.get("aliases", []))
        if any(fold(c).strip().lower() == target for c in candidates):
            return row
    names = ", ".join(r["name"] for r in ref)
    die(f"unknown city {raw!r}.\n  Valid cities: {names}")


def load_my_places() -> dict:
    if not MY_PLACES.exists():
        return {"version": 1, "places": []}
    try:
        doc = json.loads(MY_PLACES.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"{MY_PLACES} is not valid JSON, fix it before adding: {exc}")
    if doc.get("version") != 1:
        die(f"{MY_PLACES} has version {doc.get('version')!r}, expected 1")
    doc.setdefault("places", [])
    return doc


def tracker_names() -> set[tuple[str, str]]:
    """(city, folded name) for every tracker place, for the collision warning."""
    if not TRIP_DATA.exists():
        return set()
    try:
        data = json.loads(TRIP_DATA.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return {
        (p.get("city", ""), fold(p.get("name", "")).lower())
        for p in data.get("places", [])
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Add a personal place to data/my-places.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--city", required=True,
                   help="One of the cities in scripts/city_reference.json. "
                        "Accents optional: 'Gdansk' resolves to 'Gdansk'.")
    p.add_argument("--name", required=True, help="Place name.")
    p.add_argument("--type", default="sight",
                   help="Tracker type value, e.g. sight, food, bar, market, "
                        "viewpoint, street, club, day trip, event, shop, hike.")
    p.add_argument("--why", default="", dest="why",
                   help="Why it made the list. Shown on the card.")
    p.add_argument("--priority", default="Nice", choices=VALID_PRIORITIES)
    p.add_argument("--neighbourhood", default="")
    p.add_argument("--best-time", default="", dest="best_time")
    p.add_argument("--maps", default="", help="Maps URL. Coordinates are read "
                                              "from it if it carries any.")
    p.add_argument("--address", default="", help="Street address, or a "
                                                 "'lat, lon' pair.")
    p.add_argument("--hours", default="")
    p.add_argument("--cost", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--lat", type=float, default=None)
    p.add_argument("--lon", type=float, default=None)
    p.add_argument("--added-on", default=None, dest="added_on",
                   help="ISO date. Defaults to today.")
    p.add_argument("--added-via", default="chat", dest="added_via",
                   choices=["chat", "cli"])
    p.add_argument("--dry-run", action="store_true",
                   help="Print the object and write nothing.")
    p.add_argument("--force", action="store_true",
                   help="Proceed despite a name collision warning.")
    return p


def main() -> int:
    args = build_parser().parse_args()

    ref = load_city_reference()
    city = resolve_city(args.city, ref)
    if city["name"] != args.city:
        print(f"City resolved: {args.city!r} -> {city['name']!r}")

    doc = load_my_places()
    added_on = args.added_on or dt.date.today().isoformat()
    try:
        dt.date.fromisoformat(added_on)
    except ValueError:
        die(f"--added-on {added_on!r} is not an ISO date")

    # --- coordinates, in descending order of trustworthiness ---------------
    if (args.lat is None) != (args.lon is None):
        die("give both --lat and --lon, or neither")

    if args.lat is not None:
        if not in_range(args.lat, args.lon):
            die(f"--lat/--lon out of range: {args.lat}, {args.lon}")
        lat, lon, coord_source = args.lat, args.lon, "tracker"
        print(f"Coordinates: from --lat/--lon ({lat}, {lon}).")
    elif (hit := coords_from_text(args.address)) is not None:
        lat, lon, coord_source = hit[0], hit[1], "tracker"
        print(f"Coordinates: parsed from --address ({lat}, {lon}).")
    elif (hit := coords_from_link(args.maps)) is not None:
        lat, lon, coord_source = hit[0], hit[1], "mapsLink"
        print(f"Coordinates: parsed from --maps ({lat}, {lon}), pattern {hit[2]}.")
    else:
        lat, lon, coord_source = city["lat"], city["lon"], "cityCentroid"
        print(
            f"Coordinates: NONE given, falling back to the {city['name']} "
            f"centroid ({lat}, {lon}). This is an approximate location. "
            f"Re-run with --lat/--lon, or edit the entry later, to make it exact."
        )

    coord_precision = "exact" if coord_source in ("tracker", "mapsLink") else "approx"

    # The tracker column records what is actually KNOWN about the location.
    # A city centroid is not, so it is never written here: it would read as a
    # recorded coordinate to anyone later pasting this row into the master
    # file, and would present an inferred position as an exact one. The
    # centroid still populates lat/lon, flagged approx by coordSource.
    if args.address:
        address_col = args.address
    elif coord_precision == "exact":
        address_col = f"{lat}, {lon}"
    else:
        address_col = ""

    place_id = f"{city['slug']}-{slugify(args.name)}-{added_on}"

    existing_ids = {p.get("id") for p in doc["places"]}
    if place_id in existing_ids:
        die(
            f"id {place_id!r} already exists in {MY_PLACES.name}. "
            f"Change --name, or pass --added-on with a different date."
        )

    # Warn, do not fail: a name that already exists in the tracker usually
    # means the place is one of the 406 already.
    collision = (city["name"], fold(args.name).lower())
    if collision in tracker_names():
        msg = (
            f"WARNING: {args.name!r} in {city['name']} already exists as a "
            f"tracker place among the 406. Adding it here creates a duplicate."
        )
        if args.force:
            print(msg + " Continuing because --force was given.")
        else:
            print(msg)
            print("Pass --force to add it anyway, or pick a different name.")
            return 1

    entry = {
        "id": place_id,
        # The 14 tracker columns, in tracker order.
        "city": city["name"],
        "neighbourhood": args.neighbourhood,
        "name": args.name,
        "type": args.type,
        "why it made the list": args.why,
        "source and date": f"personally added, {added_on}",
        "confidence": "user",
        "address or coordinates": address_col,
        "maps link": args.maps,
        "opening hours": args.hours,
        "approx cost": args.cost,
        "priority": args.priority,
        "best time": args.best_time,
        "notes": args.notes,
        # Provenance and derived helpers. Additions, never replacements.
        "origin": "personal",
        "addedOn": added_on,
        "addedVia": args.added_via,
        "lat": lat,
        "lon": lon,
        "coordSource": coord_source,
        "coordPrecision": coord_precision,
    }

    missing = [c for c in TRACKER_COLUMNS if c not in entry]
    if missing:
        die(f"internal error, entry is missing columns: {missing}")

    print()
    print("--- entry to be added " + "-" * 54)
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    print("-" * 76)

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    doc["places"].append(entry)
    MY_PLACES.parent.mkdir(parents=True, exist_ok=True)
    MY_PLACES.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {MY_PLACES.relative_to(REPO)} ({len(doc['places'])} personal "
          f"place{'s' if len(doc['places']) != 1 else ''} total).")

    # Validate immediately, so a bad write is caught here and not in CI.
    validator = REPO / "scripts" / "validate_my_places.py"
    if validator.exists():
        import subprocess
        print()
        result = subprocess.run(
            [sys.executable, str(validator), str(MY_PLACES)], check=False
        )
        if result.returncode != 0:
            print("\nThe file failed validation. Fix it before committing.",
                  file=sys.stderr)
            return 1
    else:
        print(f"NOTE: {validator.name} not found, skipped validation.")

    print()
    print("Next:")
    print("  git add data/my-places.json")
    print(f'  git commit -m "Add place: {args.name}, {city["name"]}"')
    print("  git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
