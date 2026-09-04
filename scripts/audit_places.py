#!/usr/bin/env python3
"""
Audit script (Milestone 0)
Reads data/trip-data.json and reports:
1. City list and place counts (confirm Gdańsk presence)
2. Coordinate source breakdown (tracker, mapsLink, shortLink, addressOnly, none)
3. Distinct values of 'type', 'priority', and 'best time'
4. Sample shapes of 'opening hours'
Writes summary CSV to /tmp/places_audit.csv.
"""

import json
import csv
import re
from pathlib import Path
from collections import Counter

# Regexes for coordinate extraction from Google Maps URLs
RE_MAPS_AT = re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)')
RE_MAPS_3D4D = re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)')
RE_MAPS_Q = re.compile(r'[?&](?:q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)')
RE_COORDS_TXT = re.compile(r'^(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)')

def classify_coords(place):
    addr = (place.get('address or coordinates') or '').strip()
    link = (place.get('maps link') or '').strip()

    # Check if direct lat,lon in address column
    if RE_COORDS_TXT.match(addr):
        m = RE_COORDS_TXT.match(addr)
        return 'tracker', float(m.group(1)), float(m.group(2))

    # Check maps link regexes
    for reg in (RE_MAPS_AT, RE_MAPS_3D4D, RE_MAPS_Q):
        m = reg.search(link)
        if m:
            return 'mapsLink', float(m.group(1)), float(m.group(2))

    if 'goo.gl' in link or 'maps.app.goo.gl' in link:
        return 'shortLink', None, None

    if addr:
        return 'addressOnly', None, None

    return 'none', None, None

def main():
    json_path = Path('data/trip-data.json')
    if not json_path.exists():
        print("data/trip-data.json not found")
        return

    data = json.loads(json_path.read_text(encoding='utf-8'))
    places = data.get('places', [])

    print("=== CITIES AND PLACE COUNTS ===")
    city_counts = Counter(p.get('city') for p in places)
    for city, count in sorted(city_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {city}: {count}")

    print(f"\nTotal cities: {len(city_counts)}")

    if 'Gdańsk' in city_counts:
        print("CONFIRMED: Gdańsk is present with", city_counts['Gdańsk'], "places.")
    else:
        print("WARNING: Gdańsk not found in city list!")

    print("\n=== COORDINATE COVERAGE ===")
    source_counts = Counter()
    city_sources = {}
    audit_rows = []

    for p in places:
        c_src, lat, lon = classify_coords(p)
        source_counts[c_src] += 1
        city = p.get('city', 'Unknown')
        if city not in city_sources:
            city_sources[city] = Counter()
        city_sources[city][c_src] += 1

        audit_rows.append({
            'city': city,
            'name': p.get('name'),
            'coord_source': c_src,
            'lat': lat if lat is not None else '',
            'lon': lon if lon is not None else '',
            'address': p.get('address or coordinates'),
            'maps_link': p.get('maps link')
        })

    for src, cnt in source_counts.most_common():
        pct = (cnt / len(places)) * 100
        print(f"  {src}: {cnt} ({pct:.1f}%)")

    cov_count = source_counts['tracker'] + source_counts['mapsLink']
    print(f"Direct/Link Coordinate Coverage: {cov_count}/{len(places)} ({cov_count/len(places)*100:.1f}%)")

    print("\n=== DISTINCT PLACE TYPES ===")
    type_counts = Counter(p.get('type') for p in places)
    for t, cnt in type_counts.most_common():
        print(f"  {t!r}: {cnt}")

    print("\n=== DISTINCT PRIORITIES ===")
    prio_counts = Counter(p.get('priority') for p in places)
    for pr, cnt in prio_counts.most_common():
        print(f"  {pr!r}: {cnt}")

    print("\n=== BEST TIME VALUES ===")
    bt_counts = Counter(p.get('best time') for p in places)
    for bt, cnt in bt_counts.most_common():
        print(f"  {bt!r}: {cnt}")

    print("\n=== OPENING HOURS SAMPLE PATTERNS ===")
    hours_list = [p.get('opening hours', '').strip() for p in places if p.get('opening hours')]
    print(f"Total places with opening hours: {len(hours_list)} / {len(places)}")

    # Deduplicate pattern shapes
    pattern_counter = Counter()
    for h in hours_list:
        # replace numbers with 'N' to see abstract patterns
        pat = re.sub(r'\d+', 'N', h)
        pattern_counter[pat] += 1

    print("Top 15 opening hours patterns:")
    for pat, cnt in pattern_counter.most_common(15):
        print(f"  [{cnt}x] {pat!r}")

    # Write CSV to /tmp
    csv_path = Path('/tmp/places_audit.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['city', 'name', 'coord_source', 'lat', 'lon', 'address', 'maps_link'])
        writer.writeheader()
        writer.writerows(audit_rows)

    print(f"\nAudit details written to {csv_path}")

if __name__ == '__main__':
    main()
