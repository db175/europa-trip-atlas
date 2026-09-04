#!/usr/bin/env python3
"""
scripts/add_place.py
CLI tool to easily add a personal place to data/my-places.json.

Usage:
  python3 scripts/add_place.py \
    --city "Gdańsk" \
    --name "Pierogarnia Stary Młyn" \
    --type "Food" \
    --why "Recommended for pierogi" \
    --priority Must \
    --best-time "Lunch" \
    --maps "https://maps.google.com/..."
"""

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

# Coordinate regexes for map links
RE_MAPS_AT = re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)')
RE_MAPS_3D4D = re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)')
RE_MAPS_Q = re.compile(r'[?&](?:q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)')

TRACKER_COLUMNS = [
    "city", "neighbourhood", "name", "type", "why it made the list",
    "source and date", "confidence", "address or coordinates", "maps link",
    "opening hours", "approx cost", "priority", "best time", "notes",
]

def strip_accents(text: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

def slugify(text: str) -> str:
    text = strip_accents(text.lower())
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text or 'item'

def load_cities():
    ref_path = Path(__file__).parent / 'city_reference.json'
    if not ref_path.exists():
        sys.exit(f"FATAL: {ref_path} not found.")
    return json.loads(ref_path.read_text(encoding='utf-8'))

def resolve_city(query: str, cities):
    q_norm = strip_accents(query.strip().lower())
    for c in cities:
        names = [c['name'], c['slug']] + c.get('aliases', [])
        for n in names:
            if strip_accents(n.lower()) == q_norm:
                return c
    return None

def extract_coords_from_link(link: str):
    if not link:
        return None, None
    for reg in (RE_MAPS_AT, RE_MAPS_3D4D, RE_MAPS_Q):
        m = reg.search(link)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None, None

def main():
    parser = argparse.ArgumentParser(description="Add a personal place to data/my-places.json")
    parser.add_argument("--city", required=True, help="City name (e.g. Gdańsk or Gdansk)")
    parser.add_argument("--name", required=True, help="Place name")
    parser.add_argument("--type", default="Sight", help="Type/category (default: Sight)")
    parser.add_argument("--why", default="", help="Why it made the list")
    parser.add_argument("--priority", default="Nice", choices=["Must", "Nice", "If nearby"], help="Priority")
    parser.add_argument("--best-time", default="day", help="Best time (e.g. day, night, Lunch)")
    parser.add_argument("--neighbourhood", default="", help="Neighbourhood")
    parser.add_argument("--address", default="", help="Address or coordinates text")
    parser.add_argument("--maps", default="", help="Maps link")
    parser.add_argument("--hours", default="", help="Opening hours")
    parser.add_argument("--cost", default="", help="Approx cost")
    parser.add_argument("--notes", default="", help="Notes")
    parser.add_argument("--lat", type=float, default=None, help="Latitude override")
    parser.add_argument("--lon", type=float, default=None, help="Longitude override")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without modifying my-places.json")

    args = parser.parse_args()

    cities = load_cities()
    city_row = resolve_city(args.city, cities)
    if not city_row:
        valid_cities = ", ".join(c['name'] for c in cities)
        sys.exit(f"ERROR: City '{args.city}' not recognized. Valid cities are:\n{valid_cities}")

    canonical_city = city_row['name']
    today_str = dt.date.today().isoformat()
    place_id = f"{city_row['slug']}-{slugify(args.name)}-{today_str}"

    # Determine coordinates
    coord_src = "tracker"
    lat, lon = args.lat, args.lon
    if lat is not None and lon is not None:
        coord_src = "tracker"
    else:
        link_lat, link_lon = extract_coords_from_link(args.maps)
        if link_lat is not None and link_lon is not None:
            lat, lon = link_lat, link_lon
            coord_src = "mapsLink"
        else:
            lat, lon = city_row['lat'], city_row['lon']
            coord_src = "cityCentroid"
            print(f"NOTICE: Could not extract coordinates from link. Falling back to {canonical_city} centroid ({lat}, {lon}).", file=sys.stderr)

    address_val = args.address
    if not address_val and lat is not None and lon is not None and coord_src != "cityCentroid":
        address_val = f"{lat:.4f}, {lon:.4f}"

    new_place = {
        "id": place_id,
        "city": canonical_city,
        "neighbourhood": args.neighbourhood,
        "name": args.name,
        "type": args.type,
        "why it made the list": args.why,
        "source and date": f"personally added, {today_str}",
        "confidence": "user",
        "address or coordinates": address_val,
        "maps link": args.maps,
        "opening hours": args.hours,
        "approx cost": args.cost,
        "priority": args.priority,
        "best time": args.best_time,
        "notes": args.notes,

        "origin": "personal",
        "addedOn": today_str,
        "addedVia": "chat",
        "lat": lat,
        "lon": lon,
        "coordSource": coord_src
    }

    my_places_path = Path('data/my-places.json')
    if my_places_path.exists():
        data = json.loads(my_places_path.read_text(encoding='utf-8'))
    else:
        data = {"version": 1, "places": []}

    places = data.setdefault("places", [])

    # Check for duplicate id
    for p in places:
        if p.get("id") == place_id:
            sys.exit(f"ERROR: Place with ID '{place_id}' already exists in data/my-places.json")

    # Check for name + city collisions
    norm_name = strip_accents(args.name.lower())
    for p in places:
        if p.get("city") == canonical_city and strip_accents(p.get("name", "").lower()) == norm_name:
            print(f"WARNING: A personal place named '{args.name}' in '{canonical_city}' already exists.", file=sys.stderr)

    # Check against trip-data.json
    trip_data_path = Path('data/trip-data.json')
    if trip_data_path.exists():
        td = json.loads(trip_data_path.read_text(encoding='utf-8'))
        for p in td.get("places", []):
            if p.get("city") == canonical_city and strip_accents(p.get("name", "").lower()) == norm_name:
                print(f"WARNING: A tracker place named '{args.name}' in '{canonical_city}' already exists in trip-data.json.", file=sys.stderr)

    places.append(new_place)

    if args.dry_run:
        print("DRY RUN: New place object:")
        print(json.dumps(new_place, indent=2, ensure_ascii=False))
        return

    my_places_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding='utf-8')
    print(f"Added '{args.name}' in {canonical_city} to data/my-places.json (ID: {place_id})")

if __name__ == "__main__":
    main()
